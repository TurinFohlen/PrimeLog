"""
bridge.py — PrimeLog × Postmare 桥接层

职责：
  primelog.export() 完成后，调用 deliver() 将导出文件
  打包成 .tar.gz 并投递到指定 mailbag 目录。

用法（在业务代码里）：
    import primelog
    from primelog.postoffice.bridge import Bridge

    bridge = Bridge(mailbag_dir='./postoffice/Project1/mailbag')
    primelog.export()                    # 正常导出
    bridge.deliver(project='my-project') # 打包 → mailbag

或者一行完成：
    bridge.export_and_deliver(project='my-project')
"""

import gzip
import hashlib
import json
import logging
import os
import shutil
import tarfile
import tempfile
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger('postmare.bridge')


class Bridge:
    """
    参数：
        mailbag_dir   Postmare 的 mailbag 目录
        log_base      primelog 的日志根目录（默认 './logs'）
        keep_original 投递后是否保留原始导出文件（默认 True）
    """

    def __init__(self,
                 mailbag_dir:    str,
                 log_base:       str = './logs',
                 keep_original:  bool = True):
        self.mailbag_dir   = Path(mailbag_dir).resolve()
        self.log_base      = Path(log_base).resolve()
        self.keep_original = keep_original
        self.mailbag_dir.mkdir(parents=True, exist_ok=True)

    # ── 主接口 ────────────────────────────────────────────────

    def deliver(self, project: str,
                export_dir: Optional[str] = None) -> Optional[Path]:
        """
        扫描 project 的导出目录，将最新一批导出文件
        打包为 .tar.gz，投递到 mailbag。

        返回投递后的 tar 包路径；无文件可投递时返回 None。
        """
        scan_dir = Path(export_dir) if export_dir else (self.log_base / project)

        if not scan_dir.exists():
            logger.warning(f"导出目录不存在: {scan_dir}")
            return None

        # 找到上次投递之后新增的导出文件
        marker = self._marker_path(project)
        last_ts = self._read_marker(marker)
        new_files = self._collect_new_files(scan_dir, last_ts)

        if not new_files:
            logger.debug(f"[{project}] 无新导出文件")
            return None

        logger.info(f"[{project}] 发现 {len(new_files)} 个新文件，准备打包")
        tar_path = self._pack(project, new_files)
        self._write_marker(marker)

        if not self.keep_original:
            for f in new_files:
                try:
                    f.unlink()
                except Exception as e:
                    logger.warning(f"删除原文件失败 {f}: {e}")

        logger.info(f"[{project}] 已投递 → {tar_path.name}")
        return tar_path

    def export_and_deliver(self, project: str) -> Optional[Path]:
        """
        一步完成：primelog.export() + deliver()。
        需要 primelog 已经 init(project)。
        """
        try:
            import primelog
            primelog.export(project=project)
        except Exception as e:
            logger.error(f"primelog.export 失败: {e}")
            return None
        return self.deliver(project)

    # ── 内部工具 ──────────────────────────────────────────────

    def _collect_new_files(self, scan_dir: Path, since_ts: float) -> list:
        """收集 scan_dir 里 mtime > since_ts 的导出文件。"""
        exts = {'.json', '.wl', '.gz', '.csv', '.jsonl'}
        files = []
        for f in scan_dir.iterdir():
            if not f.is_file():
                continue
            if f.suffix not in exts:
                continue
            if f.stat().st_mtime > since_ts:
                files.append(f)
        return sorted(files, key=lambda f: f.stat().st_mtime)

    def _pack(self, project: str, files: list) -> Path:
        """将 files 打包为 .tar.gz，存入 mailbag，返回路径。"""
        ts       = time.strftime('%Y%m%d_%H%M%S')
        tar_name = f"{project}_{ts}.tar.gz"
        tar_path = self.mailbag_dir / tar_name

        with tarfile.open(tar_path, 'w:gz') as tar:
            # 写一个 manifest（元数据）
            manifest = {
                'project':   project,
                'timestamp': ts,
                'files':     [f.name for f in files],
                'node_id':   self._node_id(),
            }
            manifest_bytes = json.dumps(manifest, indent=2).encode()
            with tempfile.NamedTemporaryFile(delete=False, suffix='.json') as tmp:
                tmp.write(manifest_bytes)
                tmp_path = tmp.name
            tar.add(tmp_path, arcname='manifest.json')
            os.unlink(tmp_path)

            # 打包所有导出文件
            for f in files:
                tar.add(str(f), arcname=f.name)

        # 验证
        size = tar_path.stat().st_size
        fid  = self._file_id(tar_path)
        logger.info(f"打包完成  {tar_name}  {size//1024} KB  sha256={fid[:12]}…")
        return tar_path

    def _node_id(self) -> str:
        """读取本节点指纹（从 senders.json），找不到就返回主机名。"""
        try:
            sender_path = self.mailbag_dir.parent / 'missionlist' / 'senders.json'
            if sender_path.exists():
                with open(sender_path) as f:
                    data = json.load(f)
                fp = data.get('fingerprint', '')
                if fp:
                    return fp
        except Exception:
            pass
        import socket
        return socket.gethostname()

    @staticmethod
    def _file_id(path: Path) -> str:
        h = hashlib.sha256()
        with open(path, 'rb') as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest()

    def _marker_path(self, project: str) -> Path:
        """记录上次投递时间的标记文件。"""
        return self.mailbag_dir / f".bridge_marker_{project}"

    def _read_marker(self, marker: Path) -> float:
        try:
            return float(marker.read_text().strip())
        except Exception:
            return 0.0

    def _write_marker(self, marker: Path):
        marker.write_text(str(time.time()))
