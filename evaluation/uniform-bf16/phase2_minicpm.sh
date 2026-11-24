#!/bin/bash
# phase2_minicpm.sh — 计划A 步骤4-5：MiniCPM bf16 vLLM @18485 → C 行 logprobs(试点30→全量) + B 行 greedy
set -u
cd "$(dirname "$0")"
mkdir -p logs ../CONFIG-SENSITIVITY
LOG=logs/phase2.log
exec >> "$LOG" 2>&1
echo "=== phase2 start $(date) ==="
PORT=18485
UNIT=ua-vllm-mcp
DIR=/disk1/models/xxl-model/uniform-bf16/MiniCPM5-2B

PY3=/usr/bin/python3   # 系统 vllm/transformers 所在解释器（anaconda python3 缺 transformers）
gpu0_busy() {
  nvidia-smi --query-compute-apps=pid,gpu_uuid --format=csv,noheader | \
    grep -q "$(nvidia-smi --query-gpu=uuid --format=csv,noheader -i 0)" && return 0 || return 1
}
while gpu0_busy; do sleep 60; done
echo "$(date) GPU0 free — launching vLLM MiniCPM"

systemctl --user stop $UNIT 2>/dev/null
T0=$(date +%s)
systemd-run --user --collect --unit=$UNIT -p MemoryMax=infinity \
  env CUDA_VISIBLE_DEVICES=0 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  $PY3 -m vllm.entrypoints.openai.api_server --model "$DIR" --served-model-name minicpm \
  --max-model-len 8192 --gpu-memory-utilization 0.35 --dtype bfloat16 --port $PORT
for i in $(seq 1 240); do
  curl -sf --max-time 2 http://127.0.0.1:$PORT/v1/models >/dev/null 2>&1 && break
  sleep 5
done
READY=$(( $(date +%s) - T0 ))
curl -sf --max-time 2 http://127.0.0.1:$PORT/v1/models >/dev/null || { echo SERVE_TIMEOUT; systemctl --user stop $UNIT; exit 1; }
echo "serve ready after ${READY}s"
$PY3 - "$READY" << 'PY'
import json, sys
p='coldstart.json'
import os
d=json.load(open(p)) if os.path.exists(p) else {}
d.setdefault('c-logprobs',{})['launch_to_ready_s']=float(sys.argv[1])
d.setdefault('b-gen',{})['launch_to_ready_s']=float(sys.argv[1])
json.dump(d,open(p,'w'),ensure_ascii=False,indent=1)
PY

# 1 窗真实请求冒烟（生成式）
curl -sf --max-time 120 http://127.0.0.1:$PORT/v1/chat/completions -H 'Content-Type: application/json' \
  -d '{"model":"minicpm","messages":[{"role":"system","content":"You are a security alert triage assistant. Reply with ONLY a JSON object, nothing else."},{"role":"user","content":"Analyze: Failed password for root from 203.0.113.5 x3. Answer as strict JSON with keys tactic, urgent, severity, action."}],"max_tokens":60,"temperature":0,"chat_template_kwargs":{"enable_thinking":false}}' \
  | python3 -c "import json,sys; c=json.load(sys.stdin)['choices'][0]['message'].get('content') or ''; print('smoke:', c[:80])" || { echo SMOKE_FAIL; systemctl --user stop $UNIT; exit 1; }

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

# ---- C 行 logprobs：30 窗试点 gate ----
echo "--- c-logprobs pilot 30 $(date)"
$PY3 run_uniform.py c-logprobs development --limit 30
P=$(valid_n results_c-logprobs_development.jsonl)
echo "pilot valid rows: $P/30"
[ "$P" -ge 30 ] || { echo "PILOT GATE FAIL (C logprobs)"; systemctl --user stop $UNIT; exit 2; }
# 试点分布合法性复核（sum≈1 已在 runner 断言；此处抽验 probs 键齐）
python3 - << 'PY'
import json
rows=[json.loads(l) for l in open('results_c-logprobs_development.jsonl') if '"pred"' in l]
assert len(rows)>=30
for r in rows:
    p=r.get('probs') or {}
    for t in ('tactic','urgent','severity','action'):
        assert p.get(t) and abs(sum(p[t].values())-1)<1e-3, (r['id'], t)
print('pilot distribution check OK (30 rows, 4 tasks, sum~=1)')
PY
[ $? -eq 0 ] || { echo "PILOT DIST CHECK FAIL"; systemctl --user stop $UNIT; exit 3; }

# ---- C 全量 + B greedy ----
echo "--- c-logprobs full $(date)"
$PY3 run_uniform.py c-logprobs development
$PY3 run_uniform.py c-logprobs test
echo "--- b-gen $(date)"
$PY3 run_uniform.py b-gen development
$PY3 run_uniform.py b-gen test

systemctl --user stop $UNIT
echo "c-logprobs dev=$( [ -f results_c-logprobs_development.jsonl ] && valid_n results_c-logprobs_development.jsonl) test=$(valid_n results_c-logprobs_test.jsonl)"
echo "b-gen dev=$(valid_n results_b-gen_development.jsonl) test=$(valid_n results_b-gen_test.jsonl)"
echo "=== phase2 end $(date) ==="
