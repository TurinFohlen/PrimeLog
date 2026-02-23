#!/usr/bin/env python3
"""
postmare.py — 信息素驱动的分布式日志汇聚守护进程 v2.5

用法：
    python postmare.py --config ./Project1          # 普通节点
    python postmare.py --config ./Project1 --host   # 主机模式
    python postmare.py --config ./Project1 --status # 查看路由状态

目录结构：
    Project1/
    ├── missionlist/
    │   ├── senders.json      本节点配置
    │   └── receivers.json    邻居配置
    ├── mailbag/              待发送文件（PrimeLog 导出包放这里）
    │   └── ssh/
    │       ├── id_ed25519
    │       └── id_ed25519.pub
    └── incoming/             主机：接收并重组完成的文件
"""

import argparse
import hashlib
import json
import logging
import signal
import sys
import time
from pathlib import Path
from typing import Optional

import paramiko

from node      import PostmareNode
from transport import PostmareTransport
from mailbag   import PostmareMailbag
from bridge    import Bridge

logging.basicConfig(
    level   = logging.INFO,
    format  = '%(asctime)s  %(name)-24s  %(levelname)-8s  %(message)s',
    datefmt = '%Y-%m-%d %H:%M:%S',
)
logger = logging.getLogger('postmare')


# ── 配置工具 ──────────────────────────────────────────────────

def load_or_create_key(key_path: Path) -> paramiko.Ed25519Key:
    if key_path.exists():
        return paramiko.Ed25519Key.from_private_key_file(str(key_path))
    key = paramiko.Ed25519Key.generate()
    key_path.parent.mkdir(parents=True, exist_ok=True)
    key.write_private_key_file(str(key_path))
    with open(key_path.with_suffix('.pub'), 'w') as f:
        f.write(f"ssh-ed25519 {key.get_base64()} postmare\n")
    logger.info(f"生成新密钥对: {key_path}")
    return key


def fingerprint(key: paramiko.Ed25519Key) -> str:
    return hashlib.sha256(key.get_base64().encode()).hexdigest()


def load_config(config_dir: Path) -> dict:
    sender_path   = config_dir / 'missionlist' / 'senders.json'
    receiver_path = config_dir / 'missionlist' / 'receivers.json'

    if not sender_path.exists():
        sender_path.parent.mkdir(parents=True, exist_ok=True)
        default = {
            'listen_port':        2222,
            'key_path':           'mailbag/ssh/id_ed25519',
            'host_fingerprint':   '',
            'broadcast_interval': 30,
        }
        with open(sender_path, 'w') as f:
            json.dump(default, f, indent=2)
        logger.warning(f"已生成默认配置 {sender_path}，请填写 host_fingerprint 后重启")

    with open(sender_path) as f:
        sender = json.load(f)

    receivers = {}
    if receiver_path.exists():
        with open(receiver_path) as f:
            try:
                receivers = json.load(f)
            except json.JSONDecodeError:
                logger.warning(f"receivers.json 格式错误，已忽略: {receiver_path}")

    return {'sender': sender, 'receivers': receivers}


# ── Postmare 主类 ─────────────────────────────────────────────

class Postmare:
    def __init__(self, config_dir: str, force_host: bool = False):
        self.config_dir = Path(config_dir).resolve()
        cfg             = load_config(self.config_dir)
        sender          = cfg['sender']
        receivers       = cfg['receivers']

        # 密钥 + 指纹
        key_path     = self.config_dir / sender.get('key_path', 'mailbag/ssh/id_ed25519')
        self._key    = load_or_create_key(key_path)
        self.self_fp = fingerprint(self._key)

        # 写指纹回 senders.json（方便其他节点参考）
        if sender.get('fingerprint') != self.self_fp:
            sender['fingerprint'] = self.self_fp
            with open(self.config_dir / 'missionlist' / 'senders.json', 'w') as f:
                json.dump(sender, f, indent=2)

        # 主机指纹
        host_fp_raw = sender.get('host_fingerprint', '').strip()
        if force_host or not host_fp_raw:
            self.host_fp = self.self_fp
            if force_host and host_fp_raw != self.self_fp:
                sender['host_fingerprint'] = self.self_fp
                with open(self.config_dir / 'missionlist' / 'senders.json', 'w') as f:
                    json.dump(sender, f, indent=2)
        else:
            self.host_fp = host_fp_raw

        self.is_host   = (self.host_fp == self.self_fp)
        listen_port    = sender.get('listen_port', 2222)

        logger.info(f"self_fp  = {self.self_fp[:16]}…")
        logger.info(f"host_fp  = {self.host_fp[:16]}…")
        logger.info(f"is_host  = {self.is_host}")
        logger.info(f"邻居数量 = {len(receivers)}")
        logger.info(f"公钥     = {self._key.get_base64()[:40]}…")

        # 目录
        mailbag_dir   = self.config_dir / 'mailbag'
        incoming_dir  = self.config_dir / 'incoming'
        relay_mailbag = mailbag_dir if not self.is_host else None
        mailbag_dir.mkdir(parents=True, exist_ok=True)
        incoming_dir.mkdir(parents=True, exist_ok=True)

        # ── 层 1：Transport ──
        self._transport = PostmareTransport(
            self_fp          = self.self_fp,
            private_key      = self._key,
            neighbors        = receivers,
            listen_port      = listen_port,
            is_host          = self.is_host,
            relay_mailbag    = relay_mailbag,
            on_file_received = self._on_file_received if self.is_host else None,
        )

        # ── 层 2：Node ──
        def _broadcast_cb(value: float):
            self._transport.broadcast_heartbeat(value, self.host_fp)

        self._node = PostmareNode(
            self_fp            = self.self_fp,
            host_fp            = self.host_fp,
            broadcast_cb       = _broadcast_cb,
            broadcast_interval = sender.get('broadcast_interval', 30),
        )
        self._transport.register_handler(
            'pheromone',
            lambda sender_fp, data: self._node.update(
                sender_fp, data.get('value', float('inf'))
            )
        )

        # ── 层 3：Mailbag ──
        self._mailbag = PostmareMailbag(
            mailbag_dir  = mailbag_dir,
            incoming_dir = incoming_dir,
            get_next_hop = self._node.get_next_hop,
            send_file_fn = self._transport.send_file,
            self_fp      = self.self_fp,
            host_fp      = self.host_fp,
            is_host      = self.is_host,
        )

        # ── Bridge（供外部调用，也可以内部定时触发） ──
        self.bridge = Bridge(
            mailbag_dir   = mailbag_dir,
            keep_original = True,
        )

    # ── 主机文件接收处理 ──────────────────────────────────────

    def _on_file_received(self, path: Path):
        """
        主机收到一个完整文件（tar.gz）后调用。
        解压 manifest，记录日志，文件已在 incoming_dir 里。
        """
        try:
            import tarfile
            with tarfile.open(path, 'r:gz') as tar:
                manifest_member = tar.getmember('manifest.json')
                with tar.extractfile(manifest_member) as mf:
                    manifest = json.load(mf)
            logger.info(
                f"📬 收到日志包  project={manifest.get('project')}  "
                f"node={str(manifest.get('node_id',''))[:12]}…  "
                f"文件数={len(manifest.get('files', []))}"
            )
            # 解压到 incoming/project_name/
            project   = manifest.get('project', 'unknown')
            dest      = path.parent / project
            dest.mkdir(exist_ok=True)
            with tarfile.open(path, 'r:gz') as tar:
                tar.extractall(str(dest))
            logger.info(f"解压完成 → {dest}")
        except Exception as e:
            logger.error(f"解析收到的日志包失败 {path.name}: {e}")

    # ── 生命周期 ──────────────────────────────────────────────

    def start(self):
        self._transport.start()
        self._node.start()
        self._mailbag.start()
        logger.info("✅ Postmare 全部启动")

    def stop(self):
        logger.info("正在停止…")
        self._mailbag.stop()
        self._node.stop()
        self._transport.stop()
        logger.info("Postmare 已停止")

    def status(self):
        val = self._node.get_pheromone_value(self.host_fp)
        hop = self._node.get_next_hop(self.host_fp)
        print(f"\n{'─'*52}")
        print(f"  self     : {self.self_fp[:20]}…")
        print(f"  host     : {self.host_fp[:20]}…")
        print(f"  is_host  : {self.is_host}")
        print(f"  到主机成本: {'∞' if val == float('inf') else int(val)} 跳")
        print(f"  下一跳   : {(hop[:20] + '…') if hop else '无路由（等待心跳）'}")
        print(f"{'─'*52}\n")


# ── CLI ───────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='Postmare v2.5 — 信息素驱动的日志汇聚守护进程'
    )
    parser.add_argument('--config',  default='.', help='项目配置目录')
    parser.add_argument('--host',    action='store_true', help='主机模式（信息素=0）')
    parser.add_argument('--status',  action='store_true', help='打印路由状态后退出')
    parser.add_argument('--deliver', metavar='PROJECT', help='立即投递指定项目的导出文件')
    parser.add_argument('--verbose', action='store_true', help='DEBUG 日志')
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    pm = Postmare(config_dir=args.config, force_host=args.host)
    pm.start()

    if args.deliver:
        result = pm.bridge.deliver(project=args.deliver)
        if result:
            print(f"✅ 已投递: {result.name}")
        else:
            print("⚠️  无新文件可投递")
        pm.stop()
        return

    if args.status:
        time.sleep(0.5)
        pm.status()
        pm.stop()
        return

    def _sig(sig, frame):
        pm.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT,  _sig)
    signal.signal(signal.SIGTERM, _sig)

    logger.info("运行中… Ctrl-C 退出")
    while True:
        time.sleep(60)
        pm.status()


if __name__ == '__main__':
    main()
