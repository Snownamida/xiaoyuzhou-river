# xiaoyuzhou-river

小宇宙收听史的本地归档：每小时同步收听记录、播放进度、订阅，落 SQLite，每天快照到私有数据仓库。

页面只绑 tailnet：`http://100.87.197.52:8101`
数据仓库：`git@github.com:Snownamida/xiaoyuzhou-data.git`（私有）

## token

复用 DSH 插件 `dsh-xiaoyuzhou` 扫码登录后写入的 `~/.dsh/xiaoyuzhou/token.json`。
token 过期时脚本会调 `app_auth_tokens.refresh` 刷新，并把轮换后的新 token 写回同一个文件。

## 数据

`data/xyz.db`：

- `plays`：听过的单集 + 精确 `playedAt` + 进度秒数
- `episodes`：单集元数据（标题、时长、发布日期、封面）
- `podcasts`：播客元数据
- `subscriptions`：当前订阅的 83 个播客

## 跑

```bash
./run.sh
systemctl status xiaoyuzhou-river
```

## 恢复

```bash
git clone git@github.com:Snownamida/xiaoyuzhou-data.git ~/xiaoyuzhou-data
# 用 restore 逻辑把 JSONL 灌回 SQLite（尚未提供脚本，可参照 bilibili-river/restore.py）
```

## 已知限制

- 依赖小宇宙私有接口，改版会失效
- `feed.xyzfm.space` 对境外 IP 403，但 `api.xiaoyuzhoufm.com` 没有地理封锁
- 第三方登录可能触发风控
