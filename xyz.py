#!/usr/bin/env python3
"""小宇宙私有接口客户端：只读，token 从 DSH 插件那份文件读。"""
import json
import os
import time
import urllib.error
import urllib.request

import config

BASE = "https://api.xiaoyuzhoufm.com"
UA = "Xiaoyuzhou/2.57.1 (build:1576; iOS 17.4.1)"


class XYZError(Exception):
    pass


class XYZ:
    def __init__(self):
        if not os.path.exists(config.TOKEN):
            raise XYZError(f"token 文件不存在：{config.TOKEN}")
        with open(config.TOKEN, encoding="utf-8") as f:
            self.t = json.load(f)
        self.calls = 0

    # ---- 底层 ----
    def _headers(self):
        return {
            "Content-Type": "application/json",
            "x-jike-access-token": self.t["access"],
            "x-jike-refresh-token": self.t["refresh"],
            "x-jike-device-id": "dsh-river",
            "BundleID": "app.podcast.cosmos",
            "User-Agent": UA,
        }

    def _request(self, path, body=None, retry=True):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(BASE + path, data=data, headers=self._headers())
        self.calls += 1
        try:
            with urllib.request.urlopen(req, timeout=25) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:
            if e.code == 401 and retry:
                self.refresh()
                return self._request(path, body, False)
            raise XYZError(f"HTTP {e.code} {path}") from None
        except Exception as e:
            raise XYZError(f"{path}: {e!r}") from None

    def refresh(self):
        req = urllib.request.Request(BASE + "/app_auth_tokens.refresh", method="POST",
                                     headers=self._headers())
        try:
            with urllib.request.urlopen(req, timeout=25) as r:
                d = json.loads(r.read().decode("utf-8", "replace"))
        except Exception as e:
            raise XYZError(f"刷新 token 失败：{e!r}") from None
        access = d.get("x-jike-access-token")
        refresh = d.get("x-jike-refresh-token")
        if not access:
            raise XYZError("刷新 token 失败：返回里没有 access token")
        self.t["access"] = access
        if refresh:
            self.t["refresh"] = refresh
        self.t["updatedAt"] = int(time.time() * 1000)
        self._save()

    def _save(self):
        tmp = config.TOKEN + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.t, f, ensure_ascii=False)
        os.chmod(tmp, 0o600)
        os.replace(tmp, config.TOKEN)

    # ---- 业务 ----
    def profile(self):
        return (self._request("/v1/profile/get") or {}).get("data") or {}

    def history_page(self, cursor=None, limit=config.HISTORY_LIMIT):
        body = {"limit": limit}
        if cursor:
            body["loadMoreKey"] = cursor
        d = self._request("/v1/episode-played/list-history", body)
        return d.get("data") or [], d.get("loadMoreKey")

    def progress(self, eids):
        if not eids:
            return []
        d = self._request("/v1/playback-progress/list", {"eids": eids})
        return d.get("data") or []

    def subscriptions(self, cursor=None):
        body = {"sortBy": "subscribedAt"}
        if cursor:
            body["loadMoreKey"] = cursor
        d = self._request("/v1/subscription/list", body)
        return d.get("data") or [], d.get("loadMoreKey")
