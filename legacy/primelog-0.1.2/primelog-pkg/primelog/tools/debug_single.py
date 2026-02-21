#!/usr/bin/env python3
"""调试脚本：处理单个视频目录"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ''))
from registry import registry
import loader  # 确保组件已加载

def main():
    if len(sys.argv) != 3:
        print("用法: python debug_single.py <UID> <c_folder>")
        sys.exit(1)
    uid = sys.argv[1]
    c_folder = sys.argv[2]

    # 加载所有组件
    loader.load_all_components()

    # 获取所需组件
    scanner = registry.get_service("bili.scanner")
    entry_reader = registry.get_service("bili.entry_reader")
    format_detector = registry.get_service("bili.format_detector")
    extractor_dash = registry.get_service("extractor.dash")
    extractor_blv = registry.get_service("extractor.blv")
    merger = registry.get_service("merger.ffmpeg")
    progress_mgr = registry.get_service("progress.manager")
    video_processor = registry.get_processor("video.processor")

    # 注入依赖（如果组件需要setter）
    rish_exec = registry.get_service("rish.executor")
    file_op = registry.get_service("file.operator")
    file_op.set_rish_executor(rish_exec)
    extractor_dash.set_dependencies(file_op, rish_exec)
    extractor_blv.set_dependencies(file_op, rish_exec)
    # ... 其他依赖注入，参考 main.py 中的 setup_dependencies

    # 加载进度（如果需要）
    progress = progress_mgr.load()

    # 处理单个目录
    print(f"🔍 开始调试: UID={uid}, c_folder={c_folder}")
    success = video_processor.process(uid, c_folder, progress)
    if success:
        print("✅ 处理成功")
    else:
        print("❌ 处理失败")

    # 可选：保存进度
    progress_mgr.save(progress)

if __name__ == "__main__":
    main()