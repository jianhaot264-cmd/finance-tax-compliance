#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""财税合规问答系统 · 启动引导（SkillHub 打包版）

用法：
    python run.py              # 默认 8777 端口
    python run.py 9000         # 指定端口

首次运行会自动从 kb.json + corpus-articles.json 构建本地 SQLite 索引
（finance-tax-compliance.db），约需 3-5 秒；之后直接复用。
仅依赖 Python 3.9+ 标准库，无需 pip install。
"""
import os
import subprocess
import sys

BIN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bin")
DB = os.path.join(BIN, "finance-tax-compliance.db")
sys.path.insert(0, BIN)


def ensure_db():
    """数据库不存在或为 0 字节时，从 JSON 资产重建。"""
    if os.path.exists(DB) and os.path.getsize(DB) > 1024:
        return
    print("[setup] 首次运行，正在构建本地索引 ...", flush=True)
    r = subprocess.run([sys.executable, os.path.join(BIN, "build_v5.py")],
                       cwd=BIN)
    if r.returncode != 0 or not os.path.exists(DB):
        print("[setup] 索引构建失败。请确认 bin/ 下 kb.json、corpus-articles.json、"
              "golden_extra.json 三个文件存在。", flush=True)
        sys.exit(1)
    print("[setup] 索引构建完成。", flush=True)


def main():
    port = sys.argv[1] if len(sys.argv) > 1 else "8777"
    ensure_db()
    os.chdir(BIN)
    sys.argv = [os.path.join(BIN, "server.py"), port]
    os.execv(sys.executable, [sys.executable, os.path.join(BIN, "server.py"), port])


if __name__ == "__main__":
    main()
