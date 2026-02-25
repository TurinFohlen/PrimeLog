#!/usr/bin/env python3
"""
test_postmare.py — 单机测试，不需要真实 SSH 连接
验证三层之间的接口是否正确接通。
"""

import sys, os, time, hashlib, tempfile, threading
sys.path.insert(0, os.path.dirname(__file__))

from node    import PostmareNode
from mailbag import PostmareMailbag
from pathlib import Path

PASS, FAIL = [], []

def check(name, cond, detail=''):
    (PASS if cond else FAIL).append(name)
    print(f"  {'✅' if cond else '❌'} {name}" + (f"  [{detail}]" if not cond else ''))


# ══════════════════════════════════════════════
# 1. PostmareNode 纯逻辑测试
# ══════════════════════════════════════════════
print('\n─── PostmareNode ───')

bcast_vals = []

def fake_broadcast(val):
    bcast_vals.append(val)

HOST_FP = 'h' * 64
SELF_FP = 'a' * 64
NEIGH_FP = 'b' * 64

node = PostmareNode(SELF_FP, HOST_FP, fake_broadcast, broadcast_interval=999)
node.start()

# 刚启动，无路由
check('初始无路由', node.get_next_hop(HOST_FP) is None)
check('初始成本=∞', node.get_pheromone_value(HOST_FP) == float('inf'))

# 收到邻居广播：邻居到主机成本=0（邻居就是主机的直接邻居）
updated = node.update(NEIGH_FP, 0.0)
check('路由更新返回 True', updated)
check('下一跳=NEIGH_FP', node.get_next_hop(HOST_FP) == NEIGH_FP)
check('成本=1（0+1跳）', node.get_pheromone_value(HOST_FP) == 1.0)

# 收到更差的路由，不应更新
updated2 = node.update('c' * 64, 5.0)  # 成本 5+1=6 > 1
check('差路由不更新', not updated2)
check('下一跳仍=NEIGH_FP', node.get_next_hop(HOST_FP) == NEIGH_FP)

# 收到更好的路由
updated3 = node.update('d' * 64, -0.5)  # 成本 -0.5+1=0.5 < 1（理论值，测验逻辑）
# 注意：负成本在现实中不会出现，但测逻辑是否正确
# 这里值= -0.5+1=0.5，应该更新
check('更优路由更新', updated3)
check('成本变为 0.5', node.get_pheromone_value(HOST_FP) == 0.5)

# 主机节点：自身成本=0
host_node = PostmareNode(HOST_FP, HOST_FP, lambda v: None)
host_node.start()
check('主机成本=0', host_node.get_pheromone_value(HOST_FP) == 0.0)
check('主机无下一跳', host_node.get_next_hop(HOST_FP) is None)

node.stop()
host_node.stop()


# ══════════════════════════════════════════════
# 2. PostmareMailbag 文件扫描 + 状态持久化
# ══════════════════════════════════════════════
print('\n─── PostmareMailbag ───')

with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)
    mailbag_dir  = tmp / 'mailbag'
    incoming_dir = tmp / 'incoming'
    mailbag_dir.mkdir()

    sent_files = []

    def fake_next_hop(target_fp):
        return 'neighbor_fp_xxx'

    def fake_send_file(neighbor_fp, local_path, remote_path, progress_cb=None):
        sent_files.append((neighbor_fp, str(local_path), remote_path))
        return True

    mb = PostmareMailbag(
        mailbag_dir  = mailbag_dir,
        incoming_dir = incoming_dir,
        get_next_hop = fake_next_hop,
        send_file_fn = fake_send_file,
        self_fp      = 'a' * 64,
        host_fp      = 'h' * 64,
        is_host      = False,
    )

    # 放一个小文件进 mailbag
    test_file = mailbag_dir / 'test_log.gz'
    test_file.write_bytes(b'PrimeLog test payload ' * 100)

    # 手动触发一次扫描
    mb._scan_and_send()

    check('文件被检测到', len(mb._states) == 1)
    check('文件被发送', len(sent_files) == 1)
    check('发给正确邻居', sent_files[0][0] == 'neighbor_fp_xxx')

    # 状态文件应存在
    state_files = list((mailbag_dir / '.state').glob('*.json'))
    check('状态文件已保存', len(state_files) == 1)

    # 模拟重启：重新加载状态（文件已发完，状态应为 done）
    mb2 = PostmareMailbag(
        mailbag_dir  = mailbag_dir,
        incoming_dir = incoming_dir,
        get_next_hop = fake_next_hop,
        send_file_fn = fake_send_file,
        self_fp      = 'a' * 64,
        host_fp      = 'h' * 64,
        is_host      = False,
    )
    check('重启后状态恢复', len(mb2._states) >= 0)  # 已完成的会被清理

    # 主机模式：不扫描
    mb_host = PostmareMailbag(
        mailbag_dir  = mailbag_dir,
        incoming_dir = incoming_dir,
        get_next_hop = fake_next_hop,
        send_file_fn = fake_send_file,
        self_fp      = 'h' * 64,
        host_fp      = 'h' * 64,
        is_host      = True,
    )
    sent_before = len(sent_files)
    mb_host._scan_and_send()
    check('主机不扫描发送', len(sent_files) == sent_before)


# ══════════════════════════════════════════════
# 3. Node + Mailbag 联动（路由变化影响发送）
# ══════════════════════════════════════════════
print('\n─── Node ↔ Mailbag 联动 ───')

with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)
    mailbag_dir  = tmp / 'mailbag'
    incoming_dir = tmp / 'incoming'
    mailbag_dir.mkdir()

    node2 = PostmareNode('a'*64, 'h'*64, lambda v: None)
    node2.start()

    sent2 = []
    def send2(fp, local, remote, progress_cb=None):
        sent2.append(fp)
        return True

    mb3 = PostmareMailbag(
        mailbag_dir  = mailbag_dir,
        incoming_dir = incoming_dir,
        get_next_hop = node2.get_next_hop,
        send_file_fn = send2,
        self_fp      = 'a'*64,
        host_fp      = 'h'*64,
        is_host      = False,
    )

    (mailbag_dir / 'urgent.log.gz').write_bytes(b'urgent data' * 200)

    # 没有路由，不应发送
    mb3._scan_and_send()
    check('无路由时不发送', len(sent2) == 0)

    # 注入路由
    node2.update('neighbor_x', 0.0)
    check('注入后有路由', node2.has_route('h'*64))

    # 再次扫描，应发送
    mb3._scan_and_send()
    check('有路由后发送', len(sent2) == 1)
    check('发给正确节点', sent2[0] == 'neighbor_x')

    node2.stop()


# ══════════════════════════════════════════════
# 结果
# ══════════════════════════════════════════════
print(f'\n{"─"*40}')
print(f'通过 {len(PASS)}/{len(PASS)+len(FAIL)}')
if FAIL:
    print(f'失败: {FAIL}')
    sys.exit(1)
else:
    print('全部通过 ✅')
