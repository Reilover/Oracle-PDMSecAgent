#!/bin/bash
# cs3_kev_e1_mb.sh — 计划B 因素2/3：kev08 fp32 全量 439 + E1 NanoJev GPU-fp32 test + MB CPU 延迟（dev）
set -u
cd "$(dirname "$0")/../UNIFORM-BF16"
mkdir -p logs ../CONFIG-SENSITIVITY
LOG=logs/cs3.log
exec >> "$LOG" 2>&1
echo "=== cs3 start $(date) ==="
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

# ---- kev08 fp32 @18489（KEV_DTYPE=fp32；对照 I1 现值 = V3-TEST-BASELINE bf16 439） ----
wait_gpu0 || exit 5
systemctl --user stop cs-kevfp32 2>/dev/null
T0=$(date +%s)
systemd-run --user --collect --unit=cs-kevfp32 -p MemoryMax=infinity \
  env CUDA_VISIBLE_DEVICES=0 HF_HOME=/home/xxl/Mylocllm/kev/hf-cache HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 KEV_DTYPE=fp32 \
  /home/xxl/Mylocllm/kev/kev-repo/.venv/bin/python -m kev.serve --run jaredpalmer/kev-0.8b --port 18489
for i in $(seq 1 180); do
  curl -sf --max-time 2 http://127.0.0.1:18489/v1/models >/dev/null 2>&1 && break
  sleep 5
done
curl -sf --max-time 2 http://127.0.0.1:18489/v1/models >/dev/null || { echo KEV_FP32_SERVE_FAIL; journalctl --user -u cs-kevfp32 -n 30 --no-pager; systemctl --user stop cs-kevfp32; exit 1; }
echo "kev08 fp32 ready after $(( $(date +%s) - T0 ))s"
python3 run_uniform.py kev08 test --tag fp32 --outdir /home/xxl/MySecAgent/lab/experiments/oracle/EVAL/CONFIG-SENSITIVITY --kev-base http://127.0.0.1:18489
systemctl --user stop cs-kevfp32

# ---- E1 NanoJev GPU-fp32 test（因素3：CPU-fp32(旧) vs GPU-fp32(新) 成对） ----
systemctl --user stop cs-e1fp32 2>/dev/null
systemd-run --user --collect --unit=cs-e1fp32 -p MemoryMax=infinity \
  env CUDA_VISIBLE_DEVICES=0 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  /home/xxl/spark2_5/bin/python "$(pwd)/run_uniform.py" e1-nanojev-fp32 test --limit 1 --outdir /home/xxl/MySecAgent/lab/experiments/oracle/EVAL/CONFIG-SENSITIVITY
sleep 5
for i in $(seq 1 240); do
  sleep 5
  [ "$(valid_n $OUTD/results_e1-nanojev-fp32_test.jsonl)" -ge 1 ] && break
  systemctl --user is-active cs-e1fp32 >/dev/null 2>&1 || break
done
[ "$(valid_n $OUTD/results_e1-nanojev-fp32_test.jsonl)" -ge 1 ] || { echo E1FP32_SMOKE_FAIL; journalctl --user -u cs-e1fp32 -n 30 --no-pager; exit 1; }
systemd-run --user --collect --unit=cs-e1fp32 -p MemoryMax=infinity \
  env CUDA_VISIBLE_DEVICES=0 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  /home/xxl/spark2_5/bin/python "$(pwd)/run_uniform.py" e1-nanojev-fp32 test --outdir /home/xxl/MySecAgent/lab/experiments/oracle/EVAL/CONFIG-SENSITIVITY
for i in $(seq 1 1200); do
  sleep 15
  [ "$(valid_n $OUTD/results_e1-nanojev-fp32_test.jsonl)" -ge 439 ] && break
  systemctl --user is-active cs-e1fp32 >/dev/null 2>&1 || break
done
systemctl --user stop cs-e1fp32

# ---- MB CPU 延迟（dev 55，fp32 CPU；对照 GPU 25ms/bf16） ----
systemd-run --user --collect --unit=cs-mbcpu -p MemoryMax=infinity \
  env HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  /home/xxl/Mylocllm/kev/kev-repo/.venv/bin/python "$(pwd)/run_uniform.py" mb-cpu development --outdir /home/xxl/MySecAgent/lab/experiments/oracle/EVAL/CONFIG-SENSITIVITY
for i in $(seq 1 600); do
  sleep 10
  [ "$(valid_n $OUTD/results_mb-cpu_development.jsonl)" -ge 55 ] && break
  systemctl --user is-active cs-mbcpu >/dev/null 2>&1 || { journalctl --user -u cs-mbcpu -n 20 --no-pager; break; }
done
systemctl --user stop cs-mbcpu

echo "kev-fp32=$(valid_n $OUTD/results_kev08_fp32_test.jsonl) e1-fp32=$(valid_n $OUTD/results_e1-nanojev-fp32_test.jsonl) mb-cpu=$(valid_n $OUTD/results_mb-cpu_development.jsonl)"
echo "=== cs3 end $(date) ==="
