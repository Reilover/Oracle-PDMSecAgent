#!/bin/bash
# phase1_inproc.sh — 计划A 步骤1-3：E2 laya bf16 → E1 NanoJev bf16 → MB bf16(dev) → Verdict(test)
# 纪律：GPU0 启前查卡；systemd-run MemoryMax=infinity；每行先 1 窗冒烟（兼冷启动计时）；skip-if-done。
set -u
cd "$(dirname "$0")"
mkdir -p logs
LOG=logs/phase1.log
exec >> "$LOG" 2>&1
echo "=== phase1 start $(date) ==="

PY25=/home/xxl/spark2_5/bin/python
PYKEV=/home/xxl/Mylocllm/kev/kev-repo/.venv/bin/python
R="$(pwd)/run_uniform.py"

gpu0_busy() {
  nvidia-smi --query-compute-apps=pid,gpu_uuid --format=csv,noheader | \
    grep -q "$(nvidia-smi --query-gpu=uuid --format=csv,noheader -i 0)" && return 0 || return 1
}
wait_gpu0() {
  local W=0
  while gpu0_busy; do
    sleep 60; W=$((W+60))
    [ $((W % 1800)) -eq 0 ] && echo "$(date) waiting GPU0 free (${W}s)"
    [ $W -ge 28800 ] && { echo "TIMEOUT GPU0"; return 5; }
  done
}

done_n() {  # $1=file $2=期望行（仅计有效行：pred.tactic 非空且无 error）
  [ -f "$1" ] && [ "$(python3 -c "
import json,sys
n=0
try:
    for l in open(sys.argv[1]):
        try:
            r=json.loads(l)
            if not r.get('error') and (r.get('pred') or {}).get('tactic') is not None: n+=1
        except Exception: pass
except FileNotFoundError: pass
print(n)" "$1" 2>/dev/null || echo 0)" -ge "$2" ]
}

coldstart_rec() {  # $1=row $2=val  追加 json 片段
  python3 - "$1" "$2" << 'PY'
import json, sys
p = 'coldstart.json'
d = json.load(open(p)) if __import__('os').path.exists(p) else {}
d.setdefault(sys.argv[1], {})['launch_to_first_row_s'] = float(sys.argv[2])
json.dump(d, open(p, 'w'), ensure_ascii=False, indent=1)
PY
}

run_inproc() {  # $1=unit $2=python $3=method $4=split $5=期望行 $6=extra_env...
  local UNIT=$1 PY=$2 METHOD=$3 SPLIT=$4 WANT=$5; shift 5
  local OUT=results_${METHOD}_${SPLIT}.jsonl
  if done_n "$OUT" "$WANT"; then echo "--- skip $METHOD/$SPLIT (done)"; return 0; fi
  wait_gpu0 || return 5
  systemctl --user stop "$UNIT" 2>/dev/null
  local T0=$(date +%s)
  systemd-run --user --collect --unit="$UNIT" -p MemoryMax=infinity \
    env CUDA_VISIBLE_DEVICES=0 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_HOME=/home/xxl/.cache/huggingface "$@" \
    "$PY" "$R" "$METHOD" "$SPLIT" --limit 1
  # 等 1 窗冒烟产物
  for i in $(seq 1 240); do
    sleep 5
    if done_n "$OUT" 1 && tail -1 "$OUT" | python3 -c "import json,sys; r=json.loads(sys.stdin.read()); exit(0 if (r.get('pred') or {}).get('tactic') is not None and not r.get('error') else 1)" 2>/dev/null; then
      break
    fi
    systemctl --user is-active "$UNIT" >/dev/null 2>&1 || { echo "UNIT $UNIT died during smoke"; journalctl --user -u "$UNIT" -n 30 --no-pager; return 6; }
  done
  if ! done_n "$OUT" 1; then echo "SMOKE FAIL $METHOD/$SPLIT"; journalctl --user -u "$UNIT" -n 40 --no-pager; systemctl --user stop "$UNIT" 2>/dev/null; return 7; fi
  coldstart_rec "$METHOD" "$(( $(date +%s) - T0 ))"
  echo "--- smoke ok $METHOD/$SPLIT after $(($(date +%s)-T0))s; full run"
  systemd-run --user --collect --unit="$UNIT" -p MemoryMax=infinity \
    env CUDA_VISIBLE_DEVICES=0 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_HOME=/home/xxl/.cache/huggingface "$@" \
    "$PY" "$R" "$METHOD" "$SPLIT"
  # 等全量
  for i in $(seq 1 2400); do
    sleep 15
    done_n "$OUT" "$WANT" && { echo "--- done $METHOD/$SPLIT"; break; }
    systemctl --user is-active "$UNIT" >/dev/null 2>&1 || { done_n "$OUT" "$WANT" && break; echo "UNIT $UNIT exited early"; journalctl --user -u "$UNIT" -n 20 --no-pager; break; }
  done
  systemctl --user stop "$UNIT" 2>/dev/null
  done_n "$OUT" "$WANT" && echo "--- OK $METHOD/$SPLIT ($(grep -c '"pred"' "$OUT"))" || echo "--- INCOMPLETE $METHOD/$SPLIT ($(grep -c '"pred"' "$OUT" 2>/dev/null || echo 0)/$WANT)"
}

# 1) E2 laya bf16（5min）
run_inproc ua-e2 "$PY25" e2-laya development 55 LAYA_GPU_FP32=0
run_inproc ua-e2 "$PY25" e2-laya test 439 LAYA_GPU_FP32=0
# 2) E1 NanoJev bf16（~50min）
run_inproc ua-e1 "$PY25" e1-nanojev development 55
run_inproc ua-e1 "$PY25" e1-nanojev test 439
# 3) MB bf16 dev + Verdict P50（~10min）
run_inproc ua-mb "$PYKEV" mb-bf16 development 55
run_inproc ua-v "$PY25" verdict test 439
echo "=== phase1 end $(date) ==="
