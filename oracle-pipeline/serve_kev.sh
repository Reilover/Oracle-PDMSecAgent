#!/bin/bash
# serve_kev.sh — 启动 Kev-0.8B v3 serve（GPU 插空；<10GB 显存；绑核+nice+ionice）
# 用法: bash serve_kev.sh [port]   (默认 8021)
set -u
PORT=${1:-8021}
KEV=/home/xxl/Mylocllm/kev/kev-repo
LOG=/home/xxl/MySecAgent/oracle-pipeline/logs/serve_kev_${PORT}.log
mkdir -p "$(dirname "$LOG")"

FREE=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -1)
echo "[gpu] free ${FREE}MiB"
if [ "$FREE" -lt 8000 ]; then echo "[abort] 显存不足 8GB（kev-0.8B 推理预算）"; exit 1; fi

cd "$KEV"
export HF_HOME=/home/xxl/Mylocllm/kev/hf-cache HF_HUB_OFFLINE=1
# head.pt 内嵌拟合温度 T=1.9097 默认生效；KEV_TEMPERATURE=1.0 可还原 raw logits
nice -n 10 ionice -c3 taskset -c 0-15 .venv/bin/python -m kev.serve \
  --run runs/oracle-kev08-v3 --port "$PORT" > "$LOG" 2>&1 &
PID=$!
echo "[serve] pid=$PID port=$PORT log=$LOG"
for i in $(seq 1 40); do
  sleep 3
  curl -s -m 3 "http://127.0.0.1:$PORT/v1/models" >/dev/null 2>&1 && { echo "[serve] up"; exit 0; }
  kill -0 $PID 2>/dev/null || { echo "[abort] serve 进程退出"; exit 1; }
done
echo "[abort] 120s 未就绪"; exit 1
