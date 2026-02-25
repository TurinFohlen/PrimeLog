"""
mailbag.py — PostmareMailbag
文件扫描、分片、断点续传、本地状态管理。
"""

import json
import time
import hashlib
import threading
import logging
from pathlib import Path
from typing import Optional, Callable, Dict, List

logger = logging.getLogger('postmare.mailbag')

CHUNK_SIZE    = 2 * 1024 * 1024   # 2 MB / 片
SCAN_INTERVAL = 30                 # 扫描目录间隔（秒）
RETRY_DELAY   = 60                 # 发送失败后重试间隔（秒）
MAX_RETRIES   = 5                  # 每个文件最大重试次数


class FragmentState:
    """单个文件的发送状态（持久化到 .state.json）。"""

    def __init__(self, file_path: Path, file_id: str, total: int):
        self.file_path  = file_path
        self.file_id    = file_id
        self.total      = total
        self.sent       = set()     # 已成功发送的分片索引
        self.retries    = 0
        self.last_try   = 0.0

    @property
    def done(self) -> bool:
        return len(self.sent) == self.total

    @property
    def pending_indices(self) -> List[int]:
        return [i for i in range(self.total) if i not in self.sent]

    def to_dict(self) -> dict:
        return {
            'file_id':  self.file_id,
            'total':    self.total,
            'sent':     sorted(self.sent),
            'retries':  self.retries,
            'last_try': self.last_try,
        }

    @classmethod
    def from_dict(cls, file_path: Path, d: dict) -> 'FragmentState':
        fs = cls(file_path, d['file_id'], d['total'])
        fs.sent     = set(d.get('sent', []))
        fs.retries  = d.get('retries', 0)
        fs.last_try = d.get('last_try', 0.0)
        return fs


class PostmareMailbag:
    """
    参数：
        mailbag_dir   本地 mailbag 目录（扫描待发文件）
        incoming_dir  主机模式：接收文件的存放目录
        get_next_hop  callable(target_fp) → Optional[str]，由 Node 提供
        send_file_fn  callable(neighbor_fp, local, remote) → bool，由 Transport 提供
        self_fp       本节点指纹
        host_fp       主机指纹
        is_host       是否是主机节点
    """

    def __init__(self,
                 mailbag_dir:  Path,
                 incoming_dir: Path,
                 get_next_hop: Callable,
                 send_file_fn: Callable,
                 self_fp:      str,
                 host_fp:      str,
                 is_host:      bool = False):
        self.mailbag_dir  = mailbag_dir
        self.incoming_dir = incoming_dir
        self._get_next_hop = get_next_hop
        self._send_file    = send_file_fn
        self.self_fp       = self_fp
        self.host_fp       = host_fp
        self.is_host       = is_host

        self._state_dir = mailbag_dir / '.state'
        self._state_dir.mkdir(parents=True, exist_ok=True)
        incoming_dir.mkdir(parents=True, exist_ok=True)

        # file_id → FragmentState
        self._states: Dict[str, FragmentState] = {}
        self._lock    = threading.Lock()
        self._running = False

        self._load_states()

    # ── 状态持久化 ────────────────────────────────────────────

    def _state_path(self, file_id: str) -> Path:
        return self._state_dir / f"{file_id}.json"

    def _save_state(self, fs: FragmentState):
        try:
            with open(self._state_path(fs.file_id), 'w') as f:
                json.dump(fs.to_dict(), f)
        except Exception as e:
            logger.warning(f"保存状态失败 {fs.file_id[:8]}…: {e}")

    def _load_states(self):
        """启动时恢复未完成的发送任务。"""
        for sp in self._state_dir.glob('*.json'):
            try:
                with open(sp) as f:
                    d = json.load(f)
                file_id   = d['file_id']
                file_path = self.mailbag_dir / sp.stem  # 同名文件
                # 找实际文件（可能有不同扩展名）
                candidates = list(self.mailbag_dir.glob(f"*{file_id[:8]}*"))
                if not candidates:
                    sp.unlink()   # 原文件已消失，清除状态
                    continue
                fs = FragmentState.from_dict(candidates[0], d)
                self._states[file_id] = fs
                logger.info(f"恢复发送任务 {file_id[:8]}… "
                            f"({len(fs.sent)}/{fs.total} 片已完成)")
            except Exception as e:
                logger.warning(f"加载状态失败 {sp}: {e}")

    # ── 文件 ID 计算 ──────────────────────────────────────────

    @staticmethod
    def _file_id(path: Path) -> str:
        """SHA256 of file content，用作唯一 ID。"""
        h = hashlib.sha256()
        with open(path, 'rb') as f:
            while chunk := f.read(8192):
                h.update(chunk)
        return h.hexdigest()

    # ── 分片迭代器 ────────────────────────────────────────────

    @staticmethod
    def _iter_chunks(path: Path, start: int = 0):
        """从 start 片开始，逐片 yield (index, bytes)。"""
        with open(path, 'rb') as f:
            f.seek(start * CHUNK_SIZE)
            idx = start
            while True:
                data = f.read(CHUNK_SIZE)
                if not data:
                    break
                yield idx, data
                idx += 1

    @staticmethod
    def _total_chunks(path: Path) -> int:
        size = path.stat().st_size
        return max(1, (size + CHUNK_SIZE - 1) // CHUNK_SIZE)

    # ── 主扫描循环 ────────────────────────────────────────────

    def _scan_loop(self):
        while self._running:
            self._scan_and_send()
            time.sleep(SCAN_INTERVAL)

    def _scan_and_send(self):
        """扫描 mailbag_dir，将新文件加入任务，推进所有未完成任务。"""
        if self.is_host:
            return   # 主机不发送

        # 发现新文件（非隐藏、非状态文件）
        for fp in self.mailbag_dir.iterdir():
            if fp.name.startswith('.') or not fp.is_file():
                continue
            try:
                fid = self._file_id(fp)
            except Exception:
                continue

            with self._lock:
                if fid not in self._states:
                    total = self._total_chunks(fp)
                    fs    = FragmentState(fp, fid, total)
                    self._states[fid] = fs
                    self._save_state(fs)
                    logger.info(f"新文件入队 {fp.name}  {total} 片")

        # 推进所有未完成任务
        with self._lock:
            tasks = list(self._states.values())

        for fs in tasks:
            if fs.done:
                self._finish(fs)
                continue
            if fs.retries >= MAX_RETRIES:
                logger.error(f"放弃发送 {fs.file_id[:8]}…（超过最大重试次数）")
                continue
            if time.time() - fs.last_try < RETRY_DELAY and fs.retries > 0:
                continue
            self._send_task(fs)

    def _send_task(self, fs: FragmentState):
        """尝试发送一个文件的所有未完成分片。"""
        next_hop = self._get_next_hop(self.host_fp)
        if not next_hop:
            logger.debug(f"无路由，跳过 {fs.file_id[:8]}…")
            return

        fs.last_try = time.time()

        # 如果文件只有 1 片，直接整体发（最常见情况）
        if fs.total == 1 and 0 not in fs.sent:
            remote = f"/tmp/postmare_incoming/{fs.file_id}.frag.0"
            ok = self._send_file(next_hop, fs.file_path, remote)
            if ok:
                fs.sent.add(0)
                self._save_state(fs)
            else:
                fs.retries += 1
                self._save_state(fs)
            return

        # 多分片：逐片发送
        for idx in list(fs.pending_indices):
            frag_path = self._state_dir / f"{fs.file_id}.{idx}.tmp"
            try:
                # 写临时分片文件
                _, data = next(
                    (i, d) for i, d in self._iter_chunks(fs.file_path, idx)
                    if i == idx
                )
                with open(frag_path, 'wb') as f:
                    f.write(data)

                remote = f"/tmp/postmare_incoming/{fs.file_id}.frag.{idx}"
                ok = self._send_file(next_hop, frag_path, remote)
                frag_path.unlink(missing_ok=True)

                if ok:
                    fs.sent.add(idx)
                    self._save_state(fs)
                else:
                    fs.retries += 1
                    self._save_state(fs)
                    break   # 本轮放弃，下轮重试
            except Exception as e:
                logger.error(f"分片发送异常 {fs.file_id[:8]}…[{idx}]: {e}")
                if frag_path.exists():
                    frag_path.unlink(missing_ok=True)
                fs.retries += 1
                break

    def _finish(self, fs: FragmentState):
        """发送完成，清理状态文件和本地文件。"""
        try:
            self._state_path(fs.file_id).unlink(missing_ok=True)
        except Exception:
            pass
        with self._lock:
            self._states.pop(fs.file_id, None)
        logger.info(f"✅ 发送完成，已清理本地文件 {fs.file_path.name}")
        # 可选：删除或归档本地日志包
        # fs.file_path.unlink(missing_ok=True)

    # ── 主机端：接收分片并重组 ────────────────────────────────

    def receive_fragment(self, file_id: str, frag_idx: int,
                         frag_total: int, frag_path: Path):
        """
        主机调用：收到一个分片文件，尝试重组。
        frag_path 是已落盘的临时文件路径。
        """
        key = file_id
        with self._lock:
            if key not in self._states:
                self._states[key] = FragmentState(frag_path, file_id, frag_total)
            fs = self._states[key]
            fs.sent.add(frag_idx)

        if fs.done:
            self._assemble(fs)

    def _assemble(self, fs: FragmentState):
        """将所有分片重组为完整文件。"""
        out_path = self.incoming_dir / f"{fs.file_id[:16]}.log.gz"
        try:
            with open(out_path, 'wb') as out:
                for idx in range(fs.total):
                    frag = self.incoming_dir / f"{fs.file_id}.frag.{idx}"
                    if not frag.exists():
                        # 回退：在 /tmp 找
                        frag = Path(f"/tmp/postmare_incoming/{fs.file_id}.frag.{idx}")
                    with open(frag, 'rb') as f:
                        out.write(f.read())
                    frag.unlink(missing_ok=True)
            logger.info(f"📦 文件重组完成 → {out_path}")
        except Exception as e:
            logger.error(f"文件重组失败 {fs.file_id[:8]}…: {e}")
            return

        with self._lock:
            self._states.pop(fs.file_id, None)

    # ── 生命周期 ──────────────────────────────────────────────

    def start(self):
        self._running = True
        threading.Thread(target=self._scan_loop, daemon=True,
                         name='mailbag-scan').start()
        logger.info(f"PostmareMailbag 启动  dir={self.mailbag_dir}")

    def stop(self):
        self._running = False
