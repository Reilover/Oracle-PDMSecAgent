#!/bin/bash
# launch_unify.sh — 启动基线统一重测批A+B本地6条(全CPU)。幂等:每段先查是否已完成(行数>=439)则跳过。
cd /home/xxl/MySecAgent/lab/experiments/oracle/EVAL/BASELINE-UNIFY
mkdir -p logs

count_done() { [ -f "$1" ] && grep -c '"pred": {' "$1" || echo 0; }

# A2 NanoJev: 4 shard 并行(各 ~10 线程, spark2_5 python)
if [ "$(count_done results_nanojev-zs_test.jsonl)" -lt 439 ]; then
  for i in 0 1 2 3; do
    OMP_NUM_THREADS=10 ~/spark2_5/bin/python baseline_unify_runner.py nanojev-zs test --shard $i/4 > logs/nanojev_sh$i.log 2>&1 &
  done
fi

# A3 laya: 单进程 8 线程
if [ "$(count_done results_laya-zs_test.jsonl)" -lt 439 ]; then
  OMP_NUM_THREADS=8 ~/spark2_5/bin/python baseline_unify_runner.py laya-zs test > logs/laya.log 2>&1 &
fi

# B1 Spark gen @18080
if [ "$(count_done results_spark-gen_test.jsonl)" -lt 439 ]; then
  python3 baseline_unify_runner.py spark-gen test > logs/spark.log 2>&1 &
fi

# B2 MiniCPM gen @18081
if [ "$(count_done results_minicpm-gen_test.jsonl)" -lt 439 ]; then
  python3 baseline_unify_runner.py minicpm-gen test > logs/minicpm_gen.log 2>&1 &
fi

# B3 MiniCPM option-scored @18081(与 B2 同端点排队执行:先等 B2 完)
( while [ "$(count_done results_minicpm-gen_test.jsonl)" -lt 439 ]; do sleep 60; done
  python3 baseline_unify_runner.py minicpm-opt test > logs/minicpm_opt.log 2>&1 ) &

wait
echo "ALL DONE $(date)"
for f in results_*_test.jsonl; do echo "$f: $(count_done $f)"; done
