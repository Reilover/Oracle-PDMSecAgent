#!/usr/bin/env python3
"""coldstart_http.py — 记录一个 HTTP 推理服务从进程启动到 ready 的墙钟冷启动。

用法: coldstart_http.py <name> <ready_url> <timeout_s> <logfile> -- <cmd> [args...]
行为: spawn cmd（继承 env），轮询 ready_url（HTTP 200 即 ready），写 coldstart/<name>.json，
      子进程保持运行（服务由调用方后续管理，PID 落盘）。
"""
import json, os, subprocess, sys, time, urllib.request
from pathlib import Path

COLD = Path(__file__).parent / 'coldstart'
COLD.mkdir(exist_ok=True)


def main():
    name, ready_url, timeout_s, logfile = sys.argv[1:5]
    assert sys.argv[5] == '--'
    cmd = sys.argv[6:]
    env = dict(os.environ)
    t_launch = time.time()
    fh = open(logfile, 'ab', buffering=0)
    p = subprocess.Popen(cmd, stdout=fh, stderr=subprocess.STDOUT, env=env,
                         start_new_session=True)
    ready = None
    last_err = None
    while time.time() - t_launch < float(timeout_s):
        if p.poll() is not None:
            print(f'{name}: process exited rc={p.returncode}', file=sys.stderr)
            break
        try:
            with urllib.request.urlopen(ready_url, timeout=3) as r:
                if r.status == 200:
                    ready = time.time()
                    break
        except Exception as e:
            last_err = str(e)[:120]
        time.sleep(0.5)
    rec = {
        'name': name, 'pid': p.pid, 'cmd': cmd,
        'launch_ts': t_launch, 'ready_ts': ready,
        'cold_start_ms': round((ready - t_launch) * 1000, 1) if ready else None,
        'timeout': ready is None, 'last_err': last_err,
        'env_CUDA_VISIBLE_DEVICES': env.get('CUDA_VISIBLE_DEVICES'),
    }
    (COLD / f'{name}.json').write_text(json.dumps(rec, indent=1, ensure_ascii=False))
    print(json.dumps(rec, ensure_ascii=False))
    sys.exit(0 if ready else 4)


if __name__ == '__main__':
    main()
