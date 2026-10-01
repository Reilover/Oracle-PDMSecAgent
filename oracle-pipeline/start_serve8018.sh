#!/bin/bash
# kev-4B v3 serve @8018（C1 对抗探针 + 选项翻转链）· nohup + systemd scope 由外层包
set -u
PORT=8018
KEV=/home/xxl/Mylocllm/kev/kev-repo
LOG=/home/xxl/MySecAgent/lab/experiments/oracle/EVAL/BATCH3-ADDON/queue/kev4b_serve.log
mkdir -p "$(dirname "$LOG")"
cd "$KEV"
export HF_HOME=/home/xxl/Mylocllm/kev/hf-cache HF_HUB_OFFLINE=1
exec nice -n 10 ionice -c3 taskset -c 0-15 .venv/bin/python -m kev.serve \
  --run runs/oracle-kev4b-v3 --port "$PORT" > "$LOG" 2>&1
