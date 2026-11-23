#!/usr/bin/env bash
set -u
cd "$(dirname "$0")"
ADDR=$(python3 -c 'import config;print(f"{config.HOST}:{config.PORT}")')
if curl -s -m 2 "http://$ADDR/api/stats" >/dev/null 2>&1; then echo "已经在跑：http://$ADDR"; exit 0; fi
setsid nohup python3 server.py >> river.log 2>&1 < /dev/null &
sleep 2
curl -s -m 2 "http://$ADDR/api/stats" >/dev/null 2>&1 && echo "已拉起：http://$ADDR" || { echo 起不来; tail -5 river.log; exit 1; }
