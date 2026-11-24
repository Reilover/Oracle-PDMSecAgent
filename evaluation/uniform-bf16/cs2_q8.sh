#!/bin/bash
# cs2_q8.sh — 计划B 因素1/6/7：Q8-GPU greedy 439（B/C/H）+ Spark-BF16-gguf greedy 439（因素7）+ C 5采样 GPU 439（因素6）
# llama.cpp 长服务泄漏 → 分块重启+断点续跑（--limit 递增 + resume 去重）。
set -u
cd "$(dirname "$0")/../UNIFORM-BF16"
mkdir -p logs ../CONFIG-SENSITIVITY
LOG=logs/cs2.log
exec >> "$LOG" 2>&1
echo "=== cs2 start $(date) ==="
LLBIN=/home/xxl/spark-cpu/llama.cpp-spark/build-cuda/bin/llama-server
OUTD=../CONFIG-SENSITIVITY

valid_n() {
  python3 -c "
import json,sys
n=0
for l in open(sys.argv[1]):
    try:
        r=json.loads(l)
        if not r.get('error') and (r.get('pred') or {}).get('tactic') is not None: n+=1
    except Exception: pass
print(n)" "$1" 2>/dev/null || echo 0
}
gpu0_busy() {
  nvidia-smi --query-compute-apps=pid,gpu_uuid --format=csv,noheader | \
    grep -q "$(nvidia-smi --query-gpu=uuid --format=csv,noheader -i 0)" && return 0 || return 1
}
wait_gpu0() { local W=0; while gpu0_busy; do sleep 60; W=$((W+60)); [ $W -ge 28800 ] && return 5; done; }

launch_llama() {  # $1=name $2=gguf $3=port（额外参数取全局 $EXTRA）
  for u in cs-b cs-c cs-h; do systemctl --user stop $u 2>/dev/null; done
  wait_gpu0 || return 5
  systemd-run --user --collect --unit=cs-$1 -p MemoryMax=infinity \
    env CUDA_VISIBLE_DEVICES=0 "$LLBIN" -m "$2" --host 127.0.0.1 --port $3 -t 18 -ngl 99 --no-cache-prompt $EXTRA
  local T0=$(date +%s)
  for i in $(seq 1 120); do
    curl -sf --max-time 2 http://127.0.0.1:$3/health >/dev/null 2>&1 && break
    sleep 2
  done
  curl -sf --max-time 2 http://127.0.0.1:$3/health >/dev/null || { echo "launch fail $1"; return 1; }
  echo "llama $1 ready after $(( $(date +%s) - T0 ))s"
}

chunked() {  # $1=method $2=chunk $3=total
  local M=$1 CHUNK=$2 TOTAL=$3
  local OUT=$OUTD/results_${M}_test.jsonl
  local ROUND=0 LIM=$CHUNK
  while [ "$(valid_n "$OUT")" -lt "$TOTAL" ]; do
    ROUND=$((ROUND+1)); [ $ROUND -gt 80 ] && { echo "too many rounds $M"; break; }
    launch_llama "${M%%-*}" "$GGUF" "$PORT" || { echo "relaunch fail round $ROUND"; continue; }
    echo "--- $M round $ROUND (have $(valid_n "$OUT")/$TOTAL) $(date)"
    python3 run_uniform.py "$M" test --limit "$LIM" --outdir $OUTD
    LIM=$((LIM+CHUNK))
  done
}

# ---- MiniCPM Q8：B greedy（1 调/窗，块 150）→ C greedy（1 采样/窗 4 调，块 100）→ C 5采样（20 调/窗，块 60） ----
GGUF=/home/xxl/minicpm5-cpu/MiniCPM5-2B-Q8_0.gguf
PORT=18481
EXTRA="-c 8192 --jinja"
chunked b-q8-greedy 150 439
EXTRA="-c 8192 --jinja"
chunked c-q8-greedy 100 439
chunked c-q8-5sam 60 439
systemctl --user stop cs-b 2>/dev/null; systemctl --user stop cs-c 2>/dev/null

# ---- Spark Q8 greedy（块 150）→ Spark BF16 gguf greedy（因素7，块 150） ----
GGUF=/home/xxl/spark-cpu/models/Spark-X2.5-4B-GGUF/Spark-X2.5-4B-Q8_0.gguf
PORT=18487
EXTRA="-c 32768"
chunked h-q8-greedy 150 439
GGUF=/disk1/models/xxl-model/uniform-bf16/Spark-X2.5-4B-BF16.gguf
chunked h-bf16gguf-greedy 150 439
systemctl --user stop cs-h 2>/dev/null

echo "b-q8-greedy=$(valid_n $OUTD/results_b-q8-greedy_test.jsonl) c-q8-greedy=$(valid_n $OUTD/results_c-q8-greedy_test.jsonl)"
echo "c-q8-5sam=$(valid_n $OUTD/results_c-q8-5sam_test.jsonl) h-q8-greedy=$(valid_n $OUTD/results_h-q8-greedy_test.jsonl)"
echo "h-bf16gguf-greedy=$(valid_n $OUTD/results_h-bf16gguf-greedy_test.jsonl)"
echo "=== cs2 end $(date) ==="
