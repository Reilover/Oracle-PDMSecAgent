#!/usr/bin/env bash
# B/H greedy 试点(计划A前置gate):各30窗,JSON合法率对照Q8基线
set -u
cd /home/xxl/MySecAgent/lab/experiments/oracle
LOG=EVAL/UNIFORM-BF16/logs/pilot.log
mkdir -p EVAL/UNIFORM-BF16/logs
exec >> "$LOG" 2>&1
echo "=== pilot start $(date) ==="

MODEL=$1   # minicpm | spark
PORT=18485
if [ "$MODEL" = minicpm ]; then DIR=/disk1/models/xxl-model/uniform-bf16/MiniCPM5-2B; else DIR=/disk1/models/xxl-model/uniform-bf16/Spark-X2.5-4B; fi
[ -f "$DIR/model.safetensors.index.json" ] || { echo "weights incomplete"; exit 1; }

systemd-run --user --unit=pilot-vllm --collect -p MemoryMax=infinity env CUDA_VISIBLE_DEVICES=0 \
  python3 -m vllm.entrypoints.openai.api_server --model "$DIR" --served-model-name m \
  --max-model-len 8192 --gpu-memory-utilization 0.35 --dtype bfloat16 --port $PORT
t0=$(date +%s)
until curl -sf --max-time 2 http://127.0.0.1:$PORT/v1/models >/dev/null 2>&1; do
  [ $(( $(date +%s)-t0 )) -ge 600 ] && { echo SERVE_TIMEOUT; systemctl --user stop pilot-vllm; exit 1; }
  sleep 5
done
echo "serve ready after $(( $(date +%s)-t0 ))s"
python3 - "$MODEL" "$PORT" << 'PY'
import json, sys, urllib.request, time
model, port = sys.argv[1], sys.argv[2]
sys.path.insert(0, '/home/xxl/MySecAgent/lab/experiments/oracle/EVAL/V3-TEST-BASELINE')
import v3_baseline_runner as vbr
recs = [json.loads(l) for l in open('/home/xxl/MySecAgent/lab/experiments/oracle/suites/oracle-v3/test.jsonl')][:30]
sys.path.insert(0, '/home/xxl/MySecAgent/lab/experiments/oracle/EVAL/BASELINE-UNIFY')
import baseline_unify_runner as bur
GEN_SYS = bur.GEN_SYS
def mk_prompt(rec):
    return bur.gen_prompt(rec)
ok = bad = 0
for rec in recs:
    prompt = mk_prompt(rec)
    body = {'model': 'm', 'messages': [{'role': 'system', 'content': GEN_SYS}, {'role': 'user', 'content': prompt}],
            'max_tokens': 300, 'temperature': 0}
    req = urllib.request.Request(f'http://127.0.0.1:{port}/v1/chat/completions', json.dumps(body).encode(), {'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            c = json.loads(r.read())['choices'][0]['message'].get('content') or ''
        ok += 1
    except Exception as e:
        bad += 1; print('err', str(e)[:60])
print(json.dumps({'model': model, 'n': ok+bad, 'ok': ok, 'err': bad, 'json_note': 'greedy 30窗完成'}))
PY
systemctl --user stop pilot-vllm
echo "=== pilot done $(date) ==="
