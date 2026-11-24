#!/usr/bin/env python3
"""配置：路径、端口、同步节奏。"""
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
DB = os.path.join(DATA, "xyz.db")
RUN = os.path.join(DATA, "run.json")
TOKEN = os.environ.get("XYZ_TOKEN", os.path.expanduser("~/.dsh/xiaoyuzhou/token.json"))

HOST = os.environ.get("XYZ_HOST", "100.87.197.52")
PORT = int(os.environ.get("XYZ_PORT", "8101"))

SYNC_INTERVAL = 24 * 3600  # 每天同步一次
HISTORY_LIMIT = 20         # 每页条数
MAX_PAGES = 400            # 历史最多翻多少页（防跑飞）
GAP = 1.2                  # 请求间隔
