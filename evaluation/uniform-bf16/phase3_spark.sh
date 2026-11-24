#!/bin/bash
# phase3_spark.sh — 计划A 步骤6：Spark-X2.5-4B bf16 vLLM（~/spark2_5 venv 0.28.0）@18486 → H 行 greedy
# 系统 vllm 不支持 Spark2_5ForCausalLM（报错为证），必须 spark2_5 venv。
set -u
cd "$(dirname "$0")"
mkdir -p logs
LOG=logs/phase3.log
exec >> "$LOG" 2>&1
echo "=== phase3 start $(date) ==="
PORT=18486
UNIT=ua-vllm-spark
DIR=/disk1/models/xxl-model/uniform-bf16/Spark-X2.5-4B

gpu0_busy() {
  nvidia-smi --query-compute-apps=pid,gpu_uuid --format=csv,noheader | \
    grep -q "$(nvidia-smi --query-gpu=uuid --format=csv,noheader -i 0)" && return 0 || return 1
}
while gpu0_busy; do sleep 60; done
echo "$(date) GPU0 free — launching vLLM Spark (spark2_5 venv)"

systemctl --user stop $UNIT 2>/dev/null
T0=$(date +%s)
systemd-run --user --collect --unit=$UNIT -p MemoryMax=infinity \
  env CUDA_VISIBLE_DEVICES=0 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  /home/xxl/spark2_5/bin/python -m vllm.entrypoints.openai.api_server --model "$DIR" --served-model-name spark25 \
  --max-model-len 8192 --gpu-memory-utilization 0.35 --dtype bfloat16 --port $PORT --trust-remote-code
for i in $(seq 1 240); do
  curl -sf --max-time 2 http://127.0.0.1:$PORT/v1/models >/dev/null 2>&1 && break
  sleep 5
done
READY=$(( $(date +%s) - T0 ))
curl -sf --max-time 2 http://127.0.0.1:$PORT/v1/models >/dev/null || { echo SERVE_TIMEOUT; journalctl --user -u $UNIT -n 40 --no-pager; systemctl --user stop $UNIT; exit 1; }
echo "serve ready after ${READY}s"
python3 - "$READY" << 'PY'
import json, sys, os
p='coldstart.json'
d=json.load(open(p)) if os.path.exists(p) else {}
d.setdefault('h-gen',{})['launch_to_ready_s']=float(sys.argv[1])
json.dump(d,open(p,'w'),ensure_ascii=False,indent=1)
PY

# 1 窗真实请求冒烟
curl -sf --max-time 180 http://127.0.0.1:$PORT/v1/chat/completions -H 'Content-Type: application/json' \
  -d '{"model":"spark25","messages":[{"role":"system","content":"You are a security alert triage assistant. Reply with ONLY a JSON object, nothing else."},{"role":"user","content":"Analyze: Failed password for root from 203.0.113.5 x3. Answer as strict JSON with keys tactic, urgent, severity, action."}],"max_tokens":60,"temperature":0,"chat_template_kwargs":{"enable_thinking":false}}' \
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

echo "--- h-gen $(date)"
python3 run_uniform.py h-gen development
python3 run_uniform.py h-gen test
systemctl --user stop $UNIT
echo "h-gen dev=$(valid_n results_h-gen_development.jsonl) test=$(valid_n results_h-gen_test.jsonl)"
echo "=== phase3 end $(date) ==="
