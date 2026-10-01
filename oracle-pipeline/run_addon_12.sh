#!/bin/bash
# 单独重跑 ①双协议探针 + ②选项翻转（③verdict 已有进程在跑，勿动）
set -u
BASE=/home/xxl/MySecAgent/lab/experiments/oracle
PY=/home/xxl/Mylocllm/kev/kev-repo/.venv/bin/python
QLOG=$BASE/EVAL/BATCH3-ADDON/queue
mkdir -p "$BASE/EVAL/OPTION-ORDER"

echo "[$(date '+%F %T')] === ①对抗探针 v3(双协议) 开始 ===" >> "$QLOG/probe.log"
nice -n 10 ionice -c3 taskset -c 0-15 "$PY" "$BASE/code/eval/eval_adversarial_probe_v3.py" \
  --port 8018 --probe "$BASE/EVAL/ADVERSARIAL-PROBE" \
  --out "$BASE/EVAL/ADVERSARIAL-PROBE/results_kev4b_dual.jsonl" >> "$QLOG/probe_eval.log" 2>&1
echo "[$(date '+%F %T')] ①v3 退出" >> "$QLOG/probe.log"

echo "[$(date '+%F %T')] === ②选项顺序翻转(kev-4B v3) 开始 ===" >> "$QLOG/probe.log"
nice -n 10 ionice -c3 taskset -c 0-15 "$PY" "$BASE/code/eval/eval_option_order.py" \
  --port 8018 --suite "$BASE/suites/oracle-v3/development.jsonl" --tag kev4b-v3 \
  --n 55 --out "$BASE/EVAL/OPTION-ORDER/results_kev4b_v3.jsonl" >> "$QLOG/order_eval.log" 2>&1
echo "[$(date '+%F %T')] ②退出" >> "$QLOG/probe.log"
