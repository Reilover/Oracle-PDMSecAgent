#!/bin/bash
# D1 全量串联实测启动器（GPU/资源纪律：nice 10 + ionice c3 + 绑核 0-15，kev serve 已由 serve_kev.sh 以同款纪律启动）
set -u
KEV_URL=${KEV_URL:-http://127.0.0.1:8023}
OUT=${1:-/home/xxl/MySecAgent/lab/experiments/oracle/EVAL/D1-E2E/raw}
LIMIT=${2:-0}
cd /home/xxl/MySecAgent/oracle-pipeline
exec nice -n 10 ionice -c3 taskset -c 0-15 /home/xxl/spark2_5/bin/python run_d1_full.py \
  --kev-url "$KEV_URL" --out-dir "$OUT" --limit "$LIMIT"
