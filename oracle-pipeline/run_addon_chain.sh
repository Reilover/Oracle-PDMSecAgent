#!/bin/bash
# C1 双协议探针 + 选项翻转 + Verdict-151M 重跑（修 422 schema + out 路径 + 双协议）
set -u
BASE=/home/xxl/MySecAgent/lab/experiments/oracle
PY=/home/xxl/Mylocllm/kev/kev-repo/.venv/bin/python
SPARK_PY=/home/xxl/spark2_5/bin/python
QLOG=$BASE/EVAL/BATCH3-ADDON/queue
mkdir -p "$QLOG" "$BASE/EVAL/OPTION-ORDER" "$BASE/EVAL/VERDICT-151M"
export HF_ENDPOINT=https://hf-mirror.com

echo "[$(date '+%F %T')] === ①对抗探针 v3(双协议) 开始 ===" >> "$QLOG/probe.log"
nice -n 10 ionice -c3 taskset -c 0-15 "$PY" "$BASE/code/eval/eval_adversarial_probe_v3.py" \
  --port 8018 --probe "$BASE/EVAL/ADVERSARIAL-PROBE" \
  --out "$BASE/EVAL/ADVERSARIAL-PROBE/results_kev4b_dual.jsonl" >> "$QLOG/probe_eval.log" 2>&1
echo "[$(date '+%F %T')] ①对抗探针 v3 退出 RC=$?" >> "$QLOG/probe.log"

echo "[$(date '+%F %T')] === ②选项顺序翻转(kev-4B v3, 修 out) 开始 ===" >> "$QLOG/probe.log"
nice -n 10 ionice -c3 taskset -c 0-15 "$PY" "$BASE/code/eval/eval_option_order.py" \
  --port 8018 --suite "$BASE/suites/oracle-v3/development.jsonl" --tag kev4b-v3 \
  --n 55 --out "$BASE/EVAL/OPTION-ORDER/results_kev4b_v3.jsonl" >> "$QLOG/order_eval.log" 2>&1
echo "[$(date '+%F %T')] ②选项翻转退出 RC=$?" >> "$QLOG/probe.log"

echo "[$(date '+%F %T')] === ③Verdict-151M test 卷 开始 ===" >> "$QLOG/probe.log"
HF_HOME=/home/xxl/.cache/huggingface nice -n 10 ionice -c3 taskset -c 0-15 \
  "$SPARK_PY" "$BASE/code/eval/eval_verdict151.py" \
  --test "$BASE/suites/oracle-v3/test.jsonl" \
  --out "$BASE/EVAL/VERDICT-151M/results.jsonl" >> "$QLOG/verdict_eval.log" 2>&1
echo "[$(date '+%F %T')] ③Verdict 退出 RC=$?" >> "$QLOG/probe.log"
echo "[$(date '+%F %T')] 附加实验链 v2 全部完成" >> "$QLOG/probe.log"
