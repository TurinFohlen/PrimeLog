#!/usr/bin/env python3
"""
test_full_chain.py — 完整链路测试
覆盖：Node / Mailbag / Bridge / 文件接收回调 / 中间节点中继
"""

import sys, os, time, json, tarfile, tempfile, shutil
sys.path.insert(0, os.path.dirname(__file__))

from node    import PostmareNode
from mailbag import PostmareMailbag
from bridge  import Bridge
from pathlib import Path

PASS, FAIL = [], []

def check(name, cond, detail=''):
    (PASS if cond else FAIL).append(name)
    print(f"  {'✅' if cond else '❌'} {name}" + (f"  [{detail}]" if not cond else ''))


# ══════════════════════════════════════════════════════
# 1. Bridge：导出文件打包投递
# ══════════════════════════════════════════════════════
print('\n─── Bridge：打包投递 ───')

with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)

    # 模拟 primelog 导出目录
    log_dir = tmp / 'logs' / 'my-project'
    log_dir.mkdir(parents=True)
    (log_dir / 'error_events_20260223_100000.json').write_text('{"metadata":{"format_version":"3.0"}}')
    (log_dir / 'adjacency_matrix_20260223_100000.wl').write_text('nodes = {};')
    (log_dir / 'error_events_compact_20260223_100000.wl').write_text('events = {};')

    mailbag_dir = tmp / 'mailbag'
    mailbag_dir.mkdir()

    bridge = Bridge(
        mailbag_dir  = mailbag_dir,
        log_base     = tmp / 'logs',
        keep_original = True,
    )

    result = bridge.deliver(project='my-project')
    check('deliver 返回 Path', result is not None and isinstance(result, Path))
    check('tar.gz 在 mailbag', result is not None and result.parent == mailbag_dir)
    check('tar.gz 可解压', result is not None and tarfile.is_tarfile(result))

    # 验证 manifest
    if result:
        with tarfile.open(result, 'r:gz') as tar:
            with tar.extractfile('manifest.json') as mf:
                manifest = json.load(mf)
        check('manifest.project 正确', manifest['project'] == 'my-project')
        check('manifest.files 包含3个', len(manifest['files']) == 3)

    # 第二次 deliver：无新文件，应返回 None
    result2 = bridge.deliver(project='my-project')
    check('无新文件返回 None', result2 is None)

    # 新增一个文件后再 deliver
    time.sleep(0.01)
    (log_dir / 'error_events_20260223_110000.json').write_text('{"metadata":{"format_version":"3.0"}}')
    result3 = bridge.deliver(project='my-project')
    check('新文件后 deliver 成功', result3 is not None)
    if result3:
        with tarfile.open(result3, 'r:gz') as tar:
            names = tar.getnames()
        check('只打包新文件', 'error_events_20260223_110000.json' in names
              and 'error_events_20260223_100000.json' not in names)


# ══════════════════════════════════════════════════════
# 2. 主机端文件接收 + 解压
# ══════════════════════════════════════════════════════
print('\n─── 主机：文件接收与解压 ───')

with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)

    # 制作一个 tar.gz
    log_dir = tmp / 'logs' / 'proj-a'
    log_dir.mkdir(parents=True)
    (log_dir / 'error_events_test.json').write_bytes(b'{"test":1}')

    mailbag = tmp / 'mailbag'
    mailbag.mkdir()
    bridge  = Bridge(mailbag_dir=mailbag, log_base=tmp/'logs')
    pkg     = bridge.deliver(project='proj-a')
    check('测试包创建', pkg is not None)

    # 模拟主机的 _on_file_received
    incoming = tmp / 'incoming'
    incoming.mkdir()
    received = []

    def host_receive(path: Path):
        received.append(path)
        # 解压（简化版，不用完整 Postmare）
        import tarfile as tf
        with tf.open(path, 'r:gz') as tar:
            with tar.extractfile('manifest.json') as mf:
                manifest = json.load(mf)
        project = manifest['project']
        dest = incoming / project
        dest.mkdir(exist_ok=True)
        with tf.open(path, 'r:gz') as tar:
            tar.extractall(str(dest))

    if pkg:
        host_receive(pkg)
        check('回调被触发', len(received) == 1)
        check('解压目录存在', (incoming / 'proj-a').exists())
        check('文件已解压', (incoming / 'proj-a' / 'error_events_test.json').exists())


# ══════════════════════════════════════════════════════
# 3. 中间节点中继：收到文件后搬进自己的 mailbag
# ══════════════════════════════════════════════════════
print('\n─── 中间节点中继 ───')

with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)

    # 模拟上游节点 A 产生的日志包
    log_dir = tmp / 'logs' / 'proj-x'
    log_dir.mkdir(parents=True)
    (log_dir / 'error_events.json').write_bytes(b'{"data":"test"}')

    # A 的 mailbag
    a_mailbag = tmp / 'a_mailbag'
    a_mailbag.mkdir()
    bridge_a = Bridge(mailbag_dir=a_mailbag, log_base=tmp/'logs')
    pkg_a    = bridge_a.deliver(project='proj-x')
    check('A 打包成功', pkg_a is not None)

    # B 是中间节点，B 的 mailbag
    b_mailbag = tmp / 'b_mailbag'
    b_mailbag.mkdir()

    # 模拟 Transport 把文件从 A 传到 B 的 /tmp/incoming，然后 B 搬进自己 mailbag
    b_incoming_tmp = tmp / 'b_incoming_tmp'
    b_incoming_tmp.mkdir()

    if pkg_a:
        # 模拟 SFTP 传输（直接复制模拟）
        received_at_b = b_incoming_tmp / pkg_a.name
        shutil.copy(str(pkg_a), str(received_at_b))

        # 中间节点的 relay 逻辑（transport._on_sftp_file_received 的行为）
        relay_dest = b_mailbag / received_at_b.name
        shutil.move(str(received_at_b), str(relay_dest))
        check('B 收到后放入自己 mailbag', relay_dest.exists())

        # B 的 Mailbag 扫描，应该发现这个文件
        sent_by_b = []
        node_b = PostmareNode('b'*64, 'h'*64, lambda v: None)
        node_b.start()
        node_b.update('c'*64, 0.0)  # B 知道 C 是更近的邻居

        mb_b = PostmareMailbag(
            mailbag_dir  = b_mailbag,
            incoming_dir = tmp / 'b_incoming_final',
            get_next_hop = node_b.get_next_hop,
            send_file_fn = lambda fp, local, remote, **kw: sent_by_b.append(fp) or True,
            self_fp      = 'b'*64,
            host_fp      = 'h'*64,
            is_host      = False,
        )
        mb_b._scan_and_send()
        check('B 扫描到转发文件', len(sent_by_b) == 1)
        check('B 转发给 C（下一跳）', sent_by_b[0] == 'c'*64)
        node_b.stop()


# ══════════════════════════════════════════════════════
# 4. Bridge.export_and_deliver（mock primelog）
# ══════════════════════════════════════════════════════
print('\n─── Bridge.export_and_deliver (mock) ───')

with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)
    mailbag = tmp / 'mailbag'
    mailbag.mkdir()
    log_dir = tmp / 'logs' / 'mock-proj'
    log_dir.mkdir(parents=True)

    # 注入 mock primelog
    import types
    mock_pl = types.ModuleType('primelog')
    export_called = []

    def mock_export(project=None, **kw):
        export_called.append(project)
        # 模拟导出：创建一个文件
        (log_dir / f'error_events_{project}.json').write_bytes(b'{}')

    mock_pl.export = mock_export
    sys.modules['primelog'] = mock_pl

    bridge = Bridge(mailbag_dir=mailbag, log_base=tmp/'logs')
    result = bridge.export_and_deliver(project='mock-proj')
    check('export 被调用', len(export_called) == 1)
    check('export_and_deliver 返回包', result is not None)

    del sys.modules['primelog']


# ══════════════════════════════════════════════════════
print(f'\n{"─"*45}')
print(f'通过 {len(PASS)}/{len(PASS)+len(FAIL)}')
if FAIL:
    print(f'失败: {FAIL}')
    sys.exit(1)
else:
    print('全部通过 ✅')
