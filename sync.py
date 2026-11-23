#!/usr/bin/env python3
"""把收听历史、播放进度、订阅同步进本地 SQLite。"""
import json
import os
import sqlite3
import time

import config
from xyz import XYZ, XYZError

SCHEMA = """
CREATE TABLE IF NOT EXISTS podcasts(
    pid TEXT PRIMARY KEY, title TEXT, author TEXT, brief TEXT, image TEXT,
    episode_count INTEGER, subscription TEXT, updated INTEGER
);
CREATE TABLE IF NOT EXISTS episodes(
    eid TEXT PRIMARY KEY, pid TEXT, title TEXT, duration INTEGER,
    pub_date TEXT, image TEXT, media_key TEXT, updated INTEGER
);
CREATE TABLE IF NOT EXISTS plays(
    eid TEXT PRIMARY KEY, pid TEXT, played_at TEXT, progress INTEGER,
    ord INTEGER, fetched_at INTEGER
);
CREATE TABLE IF NOT EXISTS subscriptions(
    pid TEXT PRIMARY KEY, title TEXT, author TEXT, image TEXT, updated INTEGER
);
CREATE TABLE IF NOT EXISTS profile(k TEXT PRIMARY KEY, v TEXT, updated INTEGER);
CREATE TABLE IF NOT EXISTS mileage(
    pid TEXT PRIMARY KEY, title TEXT, author TEXT, image TEXT,
    played_seconds INTEGER, updated INTEGER
);
CREATE TABLE IF NOT EXISTS monthly(
    year INTEGER, month INTEGER, played_days INTEGER, played_seconds INTEGER,
    updated INTEGER, PRIMARY KEY(year, month)
);
"""


def db():
    os.makedirs(config.DATA, exist_ok=True)
    con = sqlite3.connect(config.DB, timeout=20)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA busy_timeout=20000")
    con.executescript(SCHEMA)
    cols = [r[1] for r in con.execute("PRAGMA table_info(episodes)")]
    if "shownotes" not in cols:
        con.execute("ALTER TABLE episodes ADD COLUMN shownotes TEXT")
    if "description" not in cols:
        con.execute("ALTER TABLE episodes ADD COLUMN description TEXT")
    return con


def _img(p):
    im = p.get("image") or {}
    return im.get("picUrl") or im.get("thumbnailUrl") or ""


def _upsert_podcast(cur, p, now):
    if not p or not p.get("pid"):
        return
    cur.execute(
        "INSERT INTO podcasts(pid,title,author,brief,image,episode_count,subscription,updated)"
        " VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(pid) DO UPDATE SET"
        " title=excluded.title, author=excluded.author, brief=excluded.brief,"
        " image=excluded.image, episode_count=excluded.episode_count,"
        " subscription=excluded.subscription, updated=excluded.updated",
        (p["pid"], p.get("title") or "", p.get("author") or "", p.get("brief") or "",
         _img(p), p.get("episodeCount") or 0, p.get("subscriptionStatus") or "", now))


def _upsert_episode(cur, e, now):
    if not e or not e.get("eid"):
        return
    cur.execute(
        "INSERT INTO episodes(eid,pid,title,duration,pub_date,image,media_key,shownotes,description,updated)"
        " VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(eid) DO UPDATE SET"
        " title=excluded.title, duration=excluded.duration, pub_date=excluded.pub_date,"
        " image=excluded.image, media_key=excluded.media_key,"
        " shownotes=excluded.shownotes, description=excluded.description, updated=excluded.updated",
        (e["eid"], e.get("pid") or "", e.get("title") or "", e.get("duration") or 0,
         e.get("pubDate") or "", _img(e), e.get("mediaKey") or "",
         e.get("shownotes") or "", e.get("description") or "", now))


def run():
    t0 = time.time()
    x = XYZ()
    con = db()
    cur = con.cursor()
    now = int(time.time())
    stats = {"history": 0, "progress": 0, "subs": 0, "errors": []}

    try:
        prof = x.profile()
        cur.execute("INSERT OR REPLACE INTO profile(k,v,updated) VALUES('me',?,?)",
                    (json.dumps(prof, ensure_ascii=False), now))
    except XYZError as e:
        stats["errors"].append(f"profile: {e}")

    # 收听历史
    cursor = None
    seen = []
    for page in range(config.MAX_PAGES):
        try:
            items, cursor = x.history_page(cursor)
        except XYZError as e:
            stats["errors"].append(f"history: {e}")
            break
        if not items:
            break
        for it in items:
            e = it.get("episode") or {}
            if not e.get("eid"):
                continue
            _upsert_podcast(cur, e.get("podcast") or {}, now)
            _upsert_episode(cur, e, now)
            seen.append(e["eid"])
            cur.execute(
                "INSERT INTO plays(eid,pid,played_at,progress,ord,fetched_at)"
                " VALUES(?,?,NULL,NULL,?,?) ON CONFLICT(eid) DO UPDATE SET"
                " ord=excluded.ord, fetched_at=excluded.fetched_at",
                (e["eid"], e.get("pid") or "", len(seen), now))
            stats["history"] += 1
        con.commit()
        if not cursor:
            break
        time.sleep(config.GAP)

    # 播放进度（顺带拿精确的 playedAt）
    for i in range(0, len(seen), 20):
        chunk = seen[i:i + 20]
        try:
            rows = x.progress(chunk)
        except XYZError as e:
            stats["errors"].append(f"progress: {e}")
            break
        for r in rows:
            cur.execute("UPDATE plays SET played_at=?, progress=? WHERE eid=?",
                        (r.get("playedAt"), r.get("progress") or 0, r.get("eid")))
            stats["progress"] += 1
        con.commit()
        time.sleep(config.GAP)

    # 每播客累计收听
    cursor = None
    stats["mileage"] = 0
    for page in range(100):
        try:
            items, cursor = x.mileage(cursor)
        except XYZError as e:
            stats["errors"].append(f"mileage: {e}")
            break
        if not items:
            break
        for it in items:
            p = it.get("podcast") or {}
            if not p.get("pid"):
                continue
            cur.execute("INSERT OR REPLACE INTO mileage(pid,title,author,image,played_seconds,updated)"
                        " VALUES(?,?,?,?,?,?)",
                        (p["pid"], p.get("title") or "", p.get("author") or "",
                         _img(p), it.get("playedSeconds") or 0, now))
            stats["mileage"] += 1
        con.commit()
        if not cursor:
            break
        time.sleep(config.GAP)

    # 月度统计：从最早一条播放记录所在月开始
    stats["months"] = 0
    try:
        prof = x.profile()
        uid = prof.get("uid")
        first = cur.execute("SELECT MIN(played_at) FROM plays").fetchone()[0]
        if uid and first:
            y, m = int(first[0:4]), int(first[5:7])
            ty, tm = time.localtime().tm_year, time.localtime().tm_mon
            while (y, m) <= (ty, tm):
                try:
                    w = x.wrapped(uid, y, m)
                    if w:
                        cur.execute("INSERT OR REPLACE INTO monthly(year,month,played_days,played_seconds,updated)"
                                    " VALUES(?,?,?,?,?)",
                                    (y, m, w.get("playedDays") or 0, w.get("playedSeconds") or 0, now))
                        stats["months"] += 1
                except XYZError as e:
                    stats["errors"].append(f"wrapped {y}-{m}: {e}")
                con.commit()
                m += 1
                if m > 12:
                    y, m = y + 1, 1
                time.sleep(config.GAP)
    except XYZError as e:
        stats["errors"].append(f"wrapped: {e}")

    # 订阅
    cursor = None
    for page in range(50):
        try:
            items, cursor = x.subscriptions(cursor)
        except XYZError as e:
            stats["errors"].append(f"subs: {e}")
            break
        if not items:
            break
        for it in items:
            p = it.get("podcast") or it
            if not p.get("pid"):
                continue
            _upsert_podcast(cur, p, now)
            cur.execute("INSERT OR REPLACE INTO subscriptions(pid,title,author,image,updated)"
                        " VALUES(?,?,?,?,?)",
                        (p["pid"], p.get("title") or "", p.get("author") or "", _img(p), now))
            stats["subs"] += 1
        con.commit()
        if not cursor:
            break
        time.sleep(config.GAP)

    total = cur.execute("SELECT COUNT(*) FROM plays").fetchone()[0]
    con.close()
    run = {"ts": now, "seconds": round(time.time() - t0, 1), "plays": total, **stats}
    tmp = config.RUN + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(run, f, ensure_ascii=False)
    os.replace(tmp, config.RUN)
    print(json.dumps(run, ensure_ascii=False), flush=True)
    return run


if __name__ == "__main__":
    run()
