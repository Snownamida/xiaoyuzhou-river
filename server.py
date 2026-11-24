#!/usr/bin/env python3
"""小宇宙收听史页面 + 定时同步。"""
import json
import os
import sqlite3
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, parse_qs

import config
import sync as sync_mod

_lock = threading.Lock()


def db():
    con = sqlite3.connect(config.DB, timeout=20)
    con.row_factory = sqlite3.Row
    return con


def read_run():
    try:
        with open(config.RUN, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def history(limit=300, q=None):
    sql = ["SELECT p.eid, p.pid, p.played_at, p.progress, p.ord,",
           "       e.title, e.duration, e.image AS ep_image, e.pub_date,",
           "       c.title AS podcast, c.author, c.image AS pod_image",
           "FROM plays p LEFT JOIN episodes e ON e.eid = p.eid",
           "LEFT JOIN podcasts c ON c.pid = p.pid",
           "WHERE 1=1"]
    args = []
    if q:
        sql.append("AND (e.title LIKE ? OR c.title LIKE ?)")
        args += [f"%{q}%", f"%{q}%"]
    sql.append("ORDER BY COALESCE(p.played_at, '') DESC, p.ord ASC LIMIT ?")
    args.append(limit)
    con = db()
    try:
        return [dict(r) for r in con.execute(" ".join(sql), args)]
    finally:
        con.close()


def stats():
    con = db()
    try:
        n = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
             for t in ("plays", "episodes", "podcasts", "subscriptions")}
    finally:
        con.close()
    n["run"] = read_run()
    return n


def _start_sync(background=True):
    if _lock.locked():
        return False

    def job():
        with _lock:
            try:
                sync_mod.run()
            except Exception as e:
                print("sync failed:", repr(e), flush=True)

    if background:
        threading.Thread(target=job, daemon=True).start()
    else:
        job()
    return True


def scheduler():
    time.sleep(3)
    while True:
        last = (read_run() or {}).get("ts", 0)
        wait = last + config.SYNC_INTERVAL - time.time()
        if wait > 0:
            time.sleep(min(wait, 300))
            continue
        _start_sync(background=False)
        time.sleep(60)


def nightly_loop():
    """每天 03:30 之后推一次快照到数据仓库。"""
    import snapshot
    while True:
        now = time.localtime()
        if now.tm_hour > 3 or (now.tm_hour == 3 and now.tm_min >= 30):
            try:
                state = json.load(open(os.path.join(config.DATA, "nightly.json")))
                done = state.get("date")
            except Exception:
                done = None
            today = time.strftime("%F")
            if done != today:
                try:
                    last = (read_run() or {}).get("ts", 0)
                    if time.strftime("%F", time.localtime(last)) != today:
                        print("快照前先补一次同步", flush=True)
                        sync_mod.run()
                    snapshot.run()
                    with open(os.path.join(config.DATA, "nightly.json"), "w") as f:
                        json.dump({"date": today, "ts": int(time.time())}, f)
                except Exception as e:
                    print("snapshot failed:", repr(e), flush=True)
        time.sleep(300)


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="text/html; charset=utf-8"):
        b = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        try:
            self.wfile.write(b)
        except BrokenPipeError:
            pass

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False), "application/json; charset=utf-8")

    def do_GET(self):
        u = urlsplit(self.path)
        q = parse_qs(u.query)
        if u.path in ("/", "/index.html"):
            with open(os.path.join(config.ROOT, "index.html"), encoding="utf-8") as f:
                return self._send(200, f.read())
        if u.path == "/api/history":
            try:
                limit = max(1, min(1000, int(q.get("limit", ["300"])[0])))
            except Exception:
                limit = 300
            return self._json({"items": history(limit, q.get("q", [None])[0])})
        if u.path == "/api/stats":
            return self._json(stats())
        return self._send(404, "not found")

    def do_POST(self):
        u = urlsplit(self.path)
        if u.path == "/api/sync":
            return self._json({"ok": True, "started": _start_sync()})
        return self._send(404, "not found")


def main():
    os.makedirs(config.DATA, exist_ok=True)
    threading.Thread(target=scheduler, daemon=True).start()
    threading.Thread(target=nightly_loop, daemon=True).start()
    srv = ThreadingHTTPServer((config.HOST, config.PORT), H)
    print(f"xiaoyuzhou-river on http://{config.HOST}:{config.PORT}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
