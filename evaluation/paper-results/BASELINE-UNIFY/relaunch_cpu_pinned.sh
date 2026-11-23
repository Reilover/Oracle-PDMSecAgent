#!/bin/bash
# relaunch_cpu_pinned.sh — NanoJev 4分片+laya 绑定到空闲核段(0-17,36-53),与 llama-server 核段(18-35,54-71)隔离。断点续跑幂等。
cd /home/xxl/MySecAgent/lab/experiments/oracle/EVAL/BASELINE-UNIFY
count_done() { [ -f "$1" ] && grep -c '"pred": {' "$1" || echo 0; }
if [ "$(count_done results_nanojev-zs_test.jsonl)" -lt 439 ]; then
  for i in 0 1 2 3; do
    OMP_NUM_THREADS=4 taskset -c $((i*4))-$((i*4+3)) ~/spark2_5/bin/python baseline_unify_runner.py nanojev-zs test --shard $i/4 >> logs/nanojev_sh$i.log 2>&1 &
  done
fi
if [ "$(count_done results_laya-zs_test.jsonl)" -lt 439 ]; then
  OMP_NUM_THREADS=4 taskset -c 16-17,36-37 ~/spark2_5/bin/python baseline_unify_runner.py laya-zs test >> logs/laya.log 2>&1 &
fi
wait
echo "RELAUNCH DONE $(date)"
