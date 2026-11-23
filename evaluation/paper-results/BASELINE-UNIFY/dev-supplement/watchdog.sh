#!/bin/bash
# dev-supplement 看门狗（2026-11-20）:监控 8 基线 dev 重评的进度与停滞
SUP=/home/xxl/MySecAgent/lab/experiments/oracle/EVAL/BASELINE-UNIFY/dev-supplement
LOG=$SUP/watchdog.log
TRANSCRIPT=/home/xxl/.hermes/cache/delegation/live/deleg_ef96aca2/task-0.log
STALL_MIN=25   # 子代理转录无更新且无新产物的分钟数
CHECK_INT=120  # 检查间隔(秒)

log(){ echo "[$(date '+%m-%d %H:%M:%S')] $*" >> $LOG; }
log "watchdog started (pid $$)"

while true; do
  sleep $CHECK_INT
  # 完成判据:REPORT.md 出现且含 8 个基线或 DONE 标记
  if [ -f "$SUP/REPORT.md" ] && grep -q 'DONE\|8/8' "$SUP/REPORT.md" 2>/dev/null; then
    log "COMPLETE: REPORT.md done marker found"
    echo "COMPLETE: dev-supplement finished, REPORT.md in place"
    exit 0
  fi
  N_ANA=$(ls $SUP/analysis_*_dev*.json 2>/dev/null | wc -l)
  # 停滞判据:转录 25 分钟未动 且 25 分钟无新产物
  T_AGE=$(( ($(date +%s) - $(stat -c %Y "$TRANSCRIPT" 2>/dev/null || echo $(date +%s))) / 60 ))
  F_AGE=$(( ($(date +%s) - $(stat -c %Y "$SUP" 2>/dev/null || echo $(date +%s))) / 60 ))
  GPU_N=$(nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>/dev/null | grep -c .)
  log "check: analyses=$N_ANA transcript_age=${T_AGE}min dir_age=${F_AGE}min gpu_procs=$GPU_N"
  if [ "$T_AGE" -ge "$STALL_MIN" ] && [ "$F_AGE" -ge "$STALL_MIN" ]; then
    log "STALL DETECTED: no transcript/dir update in ${STALL_MIN}m (analyses=$N_ANA gpu=$GPU_N)"
    echo "STALL: dev-supplement 疑似停滞 ${STALL_MIN} 分钟 (analyses=$N_ANA, gpu_procs=$GPU_N) — 需人工介入/重派"
    exit 2
  fi
done
