#!/usr/bin/env python3
"""把本地库导出成 JSONL，推到私有数据仓库。"""
import json
import os
import shutil
import sqlite3
import subprocess
import time

import config

DEST = os.environ.get("XYZ_DATA_DIR", os.path.expanduser("~/xiaoyuzhou-data"))
TABLES = ("podcasts", "episodes", "plays", "subscriptions", "profile")


def export():
    os.makedirs(DEST, exist_ok=True)
    con = sqlite3.connect(config.DB)
    counts = {}
    try:
        for t in TABLES:
            cols = [r[1] for r in con.execute(f"PRAGMA table_info({t})")]
            path = os.path.join(DEST, t + ".jsonl")
            n = 0
            with open(path, "w", encoding="utf-8") as f:
                for row in con.execute(f"SELECT * FROM {t}"):
                    f.write(json.dumps(dict(zip(cols, row)), ensure_ascii=False) + "\n")
                    n += 1
            counts[t] = n
    finally:
        con.close()
    with open(os.path.join(DEST, "meta.json"), "w", encoding="utf-8") as f:
        json.dump({"ts": int(time.time()), "date": time.strftime("%F %H:%M"), "rows": counts},
                  f, ensure_ascii=False, indent=2)
    return counts


def _git(*args):
    return subprocess.run(["git", "-C", DEST] + list(args), capture_output=True, text=True)


def push():
    _git("add", "-A")
    if not _git("status", "--porcelain").stdout.strip():
        return "没有变化"
    _git("commit", "-m", "snapshot " + time.strftime("%F %H:%M"))
    r = _git("push", "origin", "main")
    return "pushed" if r.returncode == 0 else "push 失败：" + (r.stderr or r.stdout)[-200:]


def run(commit=True):
    counts = export()
    result = push() if commit else "已导出"
    print(json.dumps({"counts": counts, "git": result}, ensure_ascii=False), flush=True)
    return counts, result


if __name__ == "__main__":
    run()
