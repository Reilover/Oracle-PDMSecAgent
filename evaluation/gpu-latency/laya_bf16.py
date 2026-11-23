#!/usr/bin/env python3
"""E2 laya-zs bf16(部署精度)延迟补测:150 窗采样,与 LAYA-FAMILY 同协议"""
import json, os, sys, time
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['LAYA_GPU_FP32'] = '0'   # bf16 autocast = 部署精度
sys.path.insert(0, '/home/xxl/Mylocllm')
sys.path.insert(0, '/home/xxl/MySecAgent/lab/experiments/oracle/EVAL/GPU-LATENCY')
import gpu_latency_runner as g

m = g.Laya()
t0 = time.time()
m.load()
load_s = round(time.time() - t0, 1)
suite = [json.loads(l) for l in open('/home/xxl/MySecAgent/lab/experiments/oracle/suites/oracle-v3/test.jsonl')][:150]
res = m.predict(suite[0]); pred = res[0] if isinstance(res, tuple) else res
assert pred['tactic'], 'smoke fail'
print('smoke ok; load', load_s, 's')
lat = []
for rec in suite[1:]:
    t1 = time.time()
    try:
        m.predict(rec); lat.append((time.time() - t1) * 1000)
    except Exception as e:
        print('err', str(e)[:60])
lat.sort()
out = {'method': 'laya-zs-bf16', 'load_s': load_s, 'n': len(lat),
       'p50_ms': round(lat[len(lat) // 2], 1), 'p95_ms': round(lat[int(len(lat) * .95)], 1)}
print('RESULT', json.dumps(out))
d = json.load(open('/home/xxl/MySecAgent/lab/experiments/oracle/EVAL/GPU-LATENCY/coldstart/oracle_p50.json'))
d['laya-zs-bf16'] = out
d['laya-oracle'] = {'method': 'laya-oracle', 'note': 'adopted from LAYA-FAMILY zeroshot_ours_v3.jsonl: 439 windows, Agent cuda, P50 25ms'}
json.dump(d, open('/home/xxl/MySecAgent/lab/experiments/oracle/EVAL/GPU-LATENCY/coldstart/oracle_p50.json', 'w'), indent=1)
print('json updated')
