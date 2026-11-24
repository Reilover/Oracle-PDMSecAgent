#!/bin/bash
# phase4_cloud.sh — 计划A 步骤7：F1 GLM / F2 DSK 云 API temp 0（dev+test）+ 计划B 噪声底座 r2 复跑（test）
# 云 key 只经 api_cfg() 从 ~/.dsh/.credentials.yaml 读，不入日志。
set -u
cd "$(dirname "$0")"
mkdir -p logs ../CONFIG-SENSITIVITY
LOG=logs/phase4.log
exec >> "$LOG" 2>&1
echo "=== phase4 start $(date) ==="

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

echo "--- f-glm run1 $(date)"
python3 run_uniform.py f-glm development
python3 run_uniform.py f-glm test
echo "--- f-dsk run1 $(date)"
python3 run_uniform.py f-dsk development
python3 run_uniform.py f-dsk test
echo "--- cloud noise floor r2 $(date)"
python3 run_uniform.py f-glm test --tag r2 --outdir ../CONFIG-SENSITIVITY
python3 run_uniform.py f-dsk test --tag r2 --outdir ../CONFIG-SENSITIVITY
echo "f1 dev=$(valid_n results_f1-glm_development.jsonl) test=$(valid_n results_f1-glm_test.jsonl)"
echo "f2 dev=$(valid_n results_f2-dsk_development.jsonl) test=$(valid_n results_f2-dsk_test.jsonl)"
echo "r2 f1=$(valid_n ../CONFIG-SENSITIVITY/results_f1-glm_r2_test.jsonl) f2=$(valid_n ../CONFIG-SENSITIVITY/results_f2-dsk_r2_test.jsonl)"
echo "=== phase4 end $(date) ==="
