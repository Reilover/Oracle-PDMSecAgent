#!/bin/bash
# launch_llamacpp.sh — llama.cpp-spark CUDA build 启动 + 冷启动计时（GPU 全卸载 / 纯 CPU 两档）
# 用法: launch_llamacpp.sh <spark|minicpm> <gpu|cpu> <port>
# 说明: 与原 CPU 轮同源码 checkout（b1-4a3635c）、同 Q8 权重、同 ctx/线程/jinja 标志；
#       gpu 档 CUDA_VISIBLE_DEVICES=1 -ngl 99；cpu 档 -ngl 0（冷启动对照，测完即停）。
set -u
cd "$(dirname "$0")"
WHAT=$1; MODE=$2; PORT=$3
BIN=/home/xxl/spark-cpu/llama.cpp-spark/build-cuda/bin/llama-server
if [ "$WHAT" = spark ]; then
  MODEL=/home/xxl/spark-cpu/models/Spark-X2.5-4B-GGUF/Spark-X2.5-4B-Q8_0.gguf
  EXTRA="-c 32768 -t 18"                    # 与 Spark服务管理手册 CPU 版一致（原版无 --jinja）
else
  MODEL=/home/xxl/minicpm5-cpu/MiniCPM5-2B-Q8_0.gguf
  EXTRA="-c 8192 -t 18 --jinja"             # 与 minicpm start.sh 一致
fi
if [ "$MODE" = gpu ]; then
  FREE=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits -i 0)
  echo "GPU0 free ${FREE} MiB (需 ~6000)"
  [ "$FREE" -lt 6000 ] && { echo "GPU0 显存不足，拒绝启动"; exit 1; }
  export CUDA_VISIBLE_DEVICES=0
  NGL=99
else
  unset CUDA_VISIBLE_DEVICES
  NGL=0
fi
NAME="llamacpp-${WHAT}-${MODE}"
mkdir -p logs
exec python3 coldstart_http.py "$NAME" "http://127.0.0.1:${PORT}/health" 900 "logs/${NAME}.log" -- \
  "$BIN" -m "$MODEL" --host 127.0.0.1 --port "$PORT" $EXTRA -ngl $NGL
