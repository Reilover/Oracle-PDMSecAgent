#!/bin/bash
# kev serve 8023 nohup 启动（脱离终端会话存活，资源纪律同 serve_kev.sh）
set -u
PORT=8023
KEV=/home/xxl/Mylocllm/kev/kev-repo
LOG=/home/xxl/MySecAgent/oracle-pipeline/logs/serve_kev_${PORT}.log
cd "$KEV"
export HF_HOME=/home/xxl/Mylocllm/kev/hf-cache HF_HUB_OFFLINE=1
nohup nice -n 10 ionice -c3 taskset -c 0-15 .venv/bin/python -m kev.serve \
  --run runs/oracle-kev08-v3 --port "$PORT" >> "$LOG" 2>&1 &
echo "serve pid=$!"
