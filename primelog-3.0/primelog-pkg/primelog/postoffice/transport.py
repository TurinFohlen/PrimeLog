"""
transport.py — PostmareTransport
所有网络通信：SSH 连接、心跳收发、文件直传。
向上层暴露：
    send_heartbeat(neighbor_fp, value)
    send_file(neighbor_fp, local_path, remote_path, via=None)
    register_handler(msg_type, callback)
    start() / stop()
"""

import json
import socket
import base64
import hashlib
import shutil
import threading
import logging
import time
from pathlib import Path
from typing import Dict, Callable, Optional

import paramiko

logger = logging.getLogger('postmare.transport')

# 每个邻居的 SSH 连接复用缓存
_CONN_TTL = 120  # 空闲超过此时间关闭连接（秒）


class _CachedConn:
    """带空闲超时的 SSH 连接包装。"""
    def __init__(self, client: paramiko.SSHClient):
        self.client    = client
        self.last_used = time.time()

    def touch(self):
        self.last_used = time.time()

    @property
    def idle(self) -> float:
        return time.time() - self.last_used


class _PostmareServerInterface(paramiko.ServerInterface):
    """
    paramiko 服务端接口：只允许持有已知公钥的客户端连接。
    known_keys: {fingerprint: Ed25519Key}
    """
    def __init__(self, known_keys: Dict[str, paramiko.Ed25519Key]):
        self._known  = known_keys
        self.peer_fp = None          # 认证成功后记录对方指纹

    def check_channel_request(self, kind, chanid):
        if kind == 'session':
            return paramiko.OPEN_SUCCEEDED
        return paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED

    def check_auth_publickey(self, username, key):
        pub_b64 = key.get_base64().encode()
        fp      = hashlib.sha256(pub_b64).hexdigest()
        if fp in self._known:
            self.peer_fp = fp
            logger.debug(f"公钥认证通过  fp={fp[:8]}…")
            return paramiko.AUTH_SUCCESSFUL
        logger.warning(f"拒绝未知公钥  fp={fp[:8]}…")
        return paramiko.AUTH_FAILED

    def get_allowed_auths(self, username):
        return 'publickey'


class PostmareTransport:
    """
    参数：
        self_fp      本节点指纹
        private_key  本节点 Ed25519 私钥（paramiko.Ed25519Key）
        neighbors    {fp: {'host':str,'port':int,'user':str,'pubkey':str,'via':str|None}}
        listen_port  本节点监听端口
    """

    def __init__(self,
                 self_fp:          str,
                 private_key:      paramiko.Ed25519Key,
                 neighbors:        Dict[str, dict],
                 listen_port:      int = 2222,
                 on_file_received: Optional[Callable] = None,
                 is_host:          bool = False,
                 relay_mailbag:    Optional[Path] = None):
        self.self_fp          = self_fp
        self._key             = private_key
        self._neighbors       = neighbors
        self._listen_port     = listen_port
        self._on_file_received = on_file_received  # callable(path: Path) or None
        self._is_host          = is_host
        self._relay_mailbag    = relay_mailbag      # 中间节点：收到文件后放入此目录

        # 解析邻居公钥
        self._known_keys: Dict[str, paramiko.Ed25519Key] = {}
        for fp, info in neighbors.items():
            try:
                raw = base64.b64decode(info['pubkey'])
                self._known_keys[fp] = paramiko.Ed25519Key(data=raw)
            except Exception as e:
                logger.warning(f"无法解析邻居公钥 {fp[:8]}…: {e}")

        # 连接缓存
        self._conn_cache: Dict[str, _CachedConn] = {}
        self._cache_lock = threading.Lock()

        # 消息处理器：msg_type → callback(sender_fp, data)
        self._handlers: Dict[str, Callable] = {}

        self._running = False

    # ── 处理器注册 ────────────────────────────────────────────

    def register_handler(self, msg_type: str, callback: Callable):
        """注册消息处理回调：callback(sender_fp: str, payload: dict)"""
        self._handlers[msg_type] = callback

    # ── 心跳发送（小包，JSON over SSH exec） ─────────────────

    def send_heartbeat(self, neighbor_fp: str, pheromone_value: float,
                       host_fp: str) -> bool:
        """向单个邻居发送信息素心跳包。"""
        msg = {
            'type':      'pheromone',
            'sender':    self.self_fp,
            'target':    host_fp,
            'value':     pheromone_value,
            'timestamp': time.time(),
        }
        signed = self._wrap_signed(msg)
        return self._send_json(neighbor_fp, signed)

    def broadcast_heartbeat(self, pheromone_value: float, host_fp: str):
        """向所有邻居广播心跳。供 PostmareNode 的 broadcast_cb 调用。"""
        for fp in list(self._neighbors.keys()):
            self.send_heartbeat(fp, pheromone_value, host_fp)

    # ── 文件直传（SFTP，支持 ProxyJump） ─────────────────────

    def send_file(self,
                  neighbor_fp:  str,
                  local_path:   Path,
                  remote_path:  str,
                  progress_cb:  Optional[Callable] = None) -> bool:
        """
        通过 SFTP 将文件发给邻居（支持 via 跳板）。
        progress_cb(sent_bytes, total_bytes) 可选。
        """
        client = self._get_conn(neighbor_fp)
        if not client:
            return False
        try:
            sftp = client.open_sftp()
            total = local_path.stat().st_size

            def _cb(sent, total_=total):
                if progress_cb:
                    progress_cb(sent, total_)

            sftp.put(str(local_path), remote_path, callback=_cb)
            sftp.close()
            logger.info(
                f"文件发送完成 → {neighbor_fp[:8]}…  "
                f"{local_path.name}  ({total//1024} KB)"
            )
            return True
        except Exception as e:
            logger.error(f"文件发送失败 → {neighbor_fp[:8]}…: {e}")
            self._drop_conn(neighbor_fp)
            return False

    # ── 服务端监听 ────────────────────────────────────────────

    def _server_loop(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(('0.0.0.0', self._listen_port))
        sock.listen(64)
        sock.settimeout(2.0)
        logger.info(f"Transport 监听 :{self._listen_port}")
        while self._running:
            try:
                conn, addr = sock.accept()
            except socket.timeout:
                continue
            except Exception as e:
                if self._running:
                    logger.warning(f"accept 异常: {e}")
                break
            threading.Thread(
                target=self._handle_conn,
                args=(conn, addr),
                daemon=True
            ).start()
        sock.close()

    def _handle_conn(self, conn, addr):
        """处理单个入站 SSH 连接，接收 JSON 心跳或文件。"""
        iface = _PostmareServerInterface(self._known_keys)
        try:
            transport = paramiko.Transport(conn)
            transport.add_server_key(self._key)
            transport.start_server(server=iface)
            chan = transport.accept(timeout=10)
            if chan is None:
                return
            if iface.peer_fp is None:
                chan.close()
                return

            # 读取完整消息（循环直到对端关闭）
            buf = b''
            while True:
                chunk = chan.recv(65536)
                if not chunk:
                    break
                buf += chunk

            chan.close()
            transport.close()
        except Exception as e:
            logger.debug(f"连接处理异常 {addr}: {e}")
            return

        if not buf:
            return

        try:
            packet = json.loads(buf.decode())
        except Exception:
            logger.warning(f"无法解析 JSON from {addr}")
            return

        if not self._verify_signed(packet, iface.peer_fp):
            logger.warning(f"签名验证失败 from {iface.peer_fp[:8]}…")
            return

        msg_type = packet.get('data', {}).get('type')
        handler  = self._handlers.get(msg_type)
        if handler:
            try:
                handler(iface.peer_fp, packet['data'])
            except Exception as e:
                logger.error(f"处理器异常 type={msg_type}: {e}")
        else:
            logger.debug(f"无处理器 type={msg_type}")

    def _on_sftp_file_received(self, path: Path):
        """
        SFTP 落盘后调用（由 _SFTPServerHandle 触发）。
        - 主机：调用 on_file_received 回调（让 Mailbag 重组/处理）
        - 中间节点：把文件移入 relay_mailbag，Postmare 自动继续转发
        """
        if self._is_host:
            if self._on_file_received:
                try:
                    self._on_file_received(path)
                except Exception as e:
                    logger.error(f"on_file_received 回调异常: {e}")
            else:
                logger.info(f"主机收到文件: {path}")
        else:
            # 中间节点：搬进自己的 mailbag 继续转发
            if self._relay_mailbag:
                dest = self._relay_mailbag / path.name
                try:
                    shutil.move(str(path), str(dest))
                    logger.info(f"中继：文件已移入 mailbag → {dest.name}")
                except Exception as e:
                    logger.error(f"中继移文件失败: {e}")
            else:
                logger.warning(f"中间节点未配置 relay_mailbag，文件滞留: {path}")

    # ── 连接缓存 ──────────────────────────────────────────────

    def _get_conn(self, neighbor_fp: str) -> Optional[paramiko.SSHClient]:
        with self._cache_lock:
            cached = self._conn_cache.get(neighbor_fp)
            if cached and cached.client.get_transport() and \
               cached.client.get_transport().is_active():
                cached.touch()
                return cached.client
            # 旧连接失效，重建
            if cached:
                try:
                    cached.client.close()
                except Exception:
                    pass
                del self._conn_cache[neighbor_fp]

        info = self._neighbors.get(neighbor_fp)
        if not info:
            logger.error(f"邻居信息不存在: {neighbor_fp[:8]}…")
            return None

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.RejectPolicy())

        # 加载邻居的已知主机密钥
        known_key = self._known_keys.get(neighbor_fp)
        if known_key:
            client.get_host_keys().add(
                info['host'], 'ssh-ed25519', known_key)

        # 可选 ProxyJump（via 字段）
        sock = None
        via_fp = info.get('via')
        if via_fp:
            sock = self._make_proxy_sock(via_fp, info['host'], info.get('port', 2222))
            if sock is None:
                return None

        try:
            client.connect(
                hostname = info['host'],
                port     = info.get('port', 2222),
                username = info.get('user', 'postmare'),
                pkey     = self._key,
                sock     = sock,
                timeout  = 10,
                banner_timeout = 10,
            )
        except Exception as e:
            logger.error(f"SSH 连接失败 → {info['host']}: {e}")
            return None

        with self._cache_lock:
            self._conn_cache[neighbor_fp] = _CachedConn(client)
        logger.debug(f"SSH 连接建立 → {neighbor_fp[:8]}…")
        return client

    def _make_proxy_sock(self, via_fp: str, dest_host: str, dest_port: int):
        """通过跳板机建立 TCP 隧道，返回 socket-like 对象。"""
        jump_client = self._get_conn(via_fp)
        if not jump_client:
            logger.error(f"跳板连接失败: {via_fp[:8]}…")
            return None
        try:
            jump_transport = jump_client.get_transport()
            sock = jump_transport.open_channel(
                'direct-tcpip',
                (dest_host, dest_port),
                ('127.0.0.1', 0)
            )
            return sock
        except Exception as e:
            logger.error(f"ProxyJump 隧道失败: {e}")
            return None

    def _drop_conn(self, neighbor_fp: str):
        with self._cache_lock:
            cached = self._conn_cache.pop(neighbor_fp, None)
        if cached:
            try:
                cached.client.close()
            except Exception:
                pass

    def _conn_reaper(self):
        """定期清理空闲连接。"""
        while self._running:
            time.sleep(30)
            with self._cache_lock:
                stale = [fp for fp, c in self._conn_cache.items()
                         if c.idle > _CONN_TTL]
                for fp in stale:
                    try:
                        self._conn_cache[fp].client.close()
                    except Exception:
                        pass
                    del self._conn_cache[fp]
                    logger.debug(f"关闭空闲连接 {fp[:8]}…")

    # ── 签名工具 ──────────────────────────────────────────────

    def _wrap_signed(self, data: dict) -> dict:
        """对 data dict 签名，返回 {data, signature}。"""
        payload = json.dumps(data, sort_keys=True).encode()
        msg     = self._key.sign_ssh_data(payload)
        sig     = msg.asbytes() if hasattr(msg, 'asbytes') else bytes(msg)
        return {
            'data':      data,
            'signature': sig.hex(),
        }

    def _verify_signed(self, packet: dict, sender_fp: str) -> bool:
        known_key = self._known_keys.get(sender_fp)
        if not known_key:
            return False
        try:
            payload = json.dumps(packet['data'], sort_keys=True).encode()
            sig     = bytes.fromhex(packet['signature'])
            msg     = paramiko.Message(sig)
            known_key.verify_ssh_sig(payload, msg)
            return True
        except Exception:
            return False

    def _send_json(self, neighbor_fp: str, packet: dict) -> bool:
        """建立 SSH 连接，开一个 session channel，发送 JSON，关闭。"""
        client = self._get_conn(neighbor_fp)
        if not client:
            return False
        try:
            transport = client.get_transport()
            chan = transport.open_session()
            chan.invoke_shell()                   # 开 PTY-free shell
            data = json.dumps(packet).encode()
            chan.sendall(data)
            chan.shutdown_write()
            chan.close()
            return True
        except Exception as e:
            logger.error(f"发送 JSON 失败 → {neighbor_fp[:8]}…: {e}")
            self._drop_conn(neighbor_fp)
            return False

    # ── 生命周期 ──────────────────────────────────────────────

    def start(self):
        self._running = True
        threading.Thread(target=self._server_loop, daemon=True, name='transport-srv').start()
        threading.Thread(target=self._conn_reaper, daemon=True, name='transport-reap').start()
        logger.info("PostmareTransport 启动")

    def stop(self):
        self._running = False
        with self._cache_lock:
            for c in self._conn_cache.values():
                try:
                    c.client.close()
                except Exception:
                    pass
            self._conn_cache.clear()
