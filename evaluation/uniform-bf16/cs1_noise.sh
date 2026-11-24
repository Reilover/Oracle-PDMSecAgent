#!/bin/bash
# cs1_noise.sh — 计划B 因素0 噪声底座（最先跑）：kev bf16 ×2(30窗) + llama.cpp greedy ×2(30窗, B/H)
# vLLM 底座复用 GPU-LATENCY repro2（26/30）；云底座 = phase4 的 temp0 r2 复跑。
set -u
cd "$(dirname "$0")/../UNIFORM-BF16"
mkdir -p logs ../CONFIG-SENSITIVITY
LOG=logs/cs1.log
exec >> "$LOG" 2>&1
echo "=== cs1 noise start $(date) ==="
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

launch_llama() {  # $1=name $2=gguf $3=port $4=extra-args
  systemctl --user stop cs-$1 2>/dev/null
  wait_gpu0 || return 5
  systemd-run --user --collect --unit=cs-$1 -p MemoryMax=infinity \
    env CUDA_VISIBLE_DEVICES=0 "$LLBIN" -m "$2" --host 127.0.0.1 --port $3 -t 18 -ngl 99 --no-cache-prompt $4
  local T0=$(date +%s)
  for i in $(seq 1 120); do
    curl -sf --max-time 2 http://127.0.0.1:$3/health >/dev/null 2>&1 && break
    sleep 2
  done
  curl -sf --max-time 2 http://127.0.0.1:$3/health >/dev/null || { echo "launch fail $1"; return 1; }
  echo "llama $1 ready after $(( $(date +%s) - T0 ))s"
}

# ---- kev08 bf16 ×2（30 窗） ----
wait_gpu0 || exit 5
systemctl --user stop cs-kev 2>/dev/null
T0=$(date +%s)
systemd-run --user --collect --unit=cs-kev -p MemoryMax=infinity \
  env CUDA_VISIBLE_DEVICES=0 HF_HOME=/home/xxl/Mylocllm/kev/hf-cache HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 KEV_DTYPE=bf16 \
  /home/xxl/Mylocllm/kev/kev-repo/.venv/bin/python -m kev.serve --run jaredpalmer/kev-0.8b --port 18428
for i in $(seq 1 180); do
  curl -sf --max-time 2 http://127.0.0.1:18428/v1/models >/dev/null 2>&1 && break
  sleep 5
done
curl -sf --max-time 2 http://127.0.0.1:18428/v1/models >/dev/null || { echo KEV_SERVE_FAIL; systemctl --user stop cs-kev; exit 1; }
echo "kev08 bf16 ready after $(( $(date +%s) - T0 ))s"
python3 run_uniform.py kev08 test --limit 30 --tag r1 --outdir $OUTD --kev-base http://127.0.0.1:18428
python3 run_uniform.py kev08 test --limit 30 --tag r2 --outdir $OUTD --kev-base http://127.0.0.1:18428
systemctl --user stop cs-kev

# ---- llama.cpp MiniCPM Q8 GPU greedy ×2（30 窗） ----
launch_llama mcp /home/xxl/minicpm5-cpu/MiniCPM5-2B-Q8_0.gguf 18481 "-c 8192 --jinja" || exit 1
python3 run_uniform.py b-q8-greedy test --limit 30 --tag r1 --outdir $OUTD
python3 run_uniform.py b-q8-greedy test --limit 30 --tag r2 --outdir $OUTD
systemctl --user stop cs-mcp

# ---- llama.cpp Spark Q8 GPU greedy ×2（30 窗） ----
launch_llama spk /home/xxl/spark-cpu/models/Spark-X2.5-4B-GGUF/Spark-X2.5-4B-Q8_0.gguf 18487 "-c 32768" || exit 1
python3 run_uniform.py h-q8-greedy test --limit 30 --tag r1 --outdir $OUTD
python3 run_uniform.py h-q8-greedy test --limit 30 --tag r2 --outdir $OUTD
systemctl --user stop cs-spk

echo "kev r1=$(valid_n $OUTD/results_kev08_r1_test.jsonl) r2=$(valid_n $OUTD/results_kev08_r2_test.jsonl)"
echo "mcp r1=$(valid_n $OUTD/results_b-q8-greedy_r1_test.jsonl) r2=$(valid_n $OUTD/results_b-q8-greedy_r2_test.jsonl)"
echo "spk r1=$(valid_n $OUTD/results_h-q8-greedy_r1_test.jsonl) r2=$(valid_n $OUTD/results_h-q8-greedy_r2_test.jsonl)"
echo "=== cs1 end $(date) ==="
