#!/usr/bin/env python3
"""ORACLE 三线 P50 统一重测(150 窗采样,生产栈,空闲 GPU0)"""
import json, sys, time, subprocess, os, urllib.request

BASE = '/home/xxl/MySecAgent/lab/experiments/oracle/EVAL/GPU-LATENCY'
os.chdir(BASE)
sys.path.insert(0, BASE)
sys.path.insert(0, '/home/xxl/MySecAgent/lab/experiments/oracle/EVAL/V3-TEST-BASELINE')
KEV = '/home/xxl/Mylocllm/kev/kev-repo/.venv/bin/python'
RUNS = '/home/xxl/Mylocllm/kev/kev-repo/runs'
env = dict(os.environ, CUDA_VISIBLE_DEVICES='0', HF_HOME='/home/xxl/Mylocllm/kev/hf-cache',
           HF_HUB_OFFLINE='1', KEV_DTYPE='bf16')
suite = [json.loads(l) for l in open('/home/xxl/MySecAgent/lab/experiments/oracle/suites/oracle-v3/test.jsonl')][:150]

def wait_ready(url, tmo=300):
    t0 = time.time()
    while time.time() - t0 < tmo:
        try:
            with urllib.request.urlopen(url, timeout=3) as r:
                if r.status == 200: return True
        except Exception: pass
        time.sleep(2)
    return False

def smoke(url):
    import gpu_latency_runner as g
    k = g.Kev('smoke', url)
    pred, probs, dt = k.predict(suite[0])
    assert pred['tactic'], 'empty prediction'
    print('smoke ok', dt, 'ms')

def kev_p50(name, ckpt, port):
    subprocess.run(['pkill','-9','-f',f'kev.serve.*{port}'], capture_output=True); time.sleep(3)
    log = open(f'logs/oracle_{name}_serve.log','w')
    p = subprocess.Popen(['nice','-n','10',KEV,'-m','kev.serve','--run',ckpt,'--port',str(port)],
                         stdout=log, stderr=log, env=env)
    if not wait_ready(f'http://127.0.0.1:{port}/v1/models'): 
        print(name, 'SERVE TIMEOUT'); return None
    smoke(f'http://127.0.0.1:{port}')
    import gpu_latency_runner as g
    k = g.Kev(name, f'http://127.0.0.1:{port}')
    lat = []
    for rec in suite:
        t0 = time.time()
        try:
            k.predict(rec); lat.append((time.time()-t0)*1000)
        except Exception as e:
            print(name, 'win err', str(e)[:60])
    lat.sort()
    out = {'method': name, 'n': len(lat), 'p50_ms': round(lat[len(lat)//2],1) if lat else None,
           'p95_ms': round(lat[int(len(lat)*.95)],1) if lat else None}
    subprocess.run(['pkill','-INT','-f',f'kev.serve.*{port}'], capture_output=True); time.sleep(8)
    return out

def nano_p50():
    try:
        import transformers  # noqa
    except ImportError:
        import subprocess as sp
        out = sp.run(['/home/xxl/spark2_5/bin/python', __file__, '--nano-only'],
                     capture_output=True, text=True, env=dict(os.environ, CUDA_VISIBLE_DEVICES=os.environ.get('CUDA_VISIBLE_DEVICES','0')))
        print(out.stdout[-2000:]); print(out.stderr[-800:])
        try:
            return json.loads(out.stdout.strip().splitlines()[-1])
        except Exception:
            return {'method': 'nanojev-oracle', 'error': 'subprocess failed'}
    sys.path.insert(0, '/home/xxl/Mylocllm/NanoJev/scripts')
    import predict_toy_decisions as ptd
    import gpu_latency_runner as g
    ckpt = '/home/xxl/MySecAgent/lab/experiments/oracle/T3-NANOJEV/nanojev-oracle-v3'
    t0 = time.time()
    eng = ptd.DecisionPredictor(ckpt, precision='bf16', disable_native_triton=True)
    load_s = round(time.time() - t0, 1)
    qs = {'tactic': {'type': 'choice', 'instructions': g.TACTIC_INSTR, 'criteria': dict(g.TACTIC_CRITERIA)},
          'urgent': {'type': 'boolean', 'instructions': g.URGENT_INSTR['question'],
                     'criteria': {'true': 'Act now: ongoing or imminent compromise',
                                  'false': 'Routine: can wait for normal triage'}},
          'severity': {'type': 'score', 'instructions': g.SEV_INSTR['question'], 'criteria': list(g.SEV_CRIT)},
          'action': {'type': 'choice', 'instructions': g.ACTION_INSTR, 'criteria': dict(g.ACTION_CRITERIA)}}
    lat = []
    for rec in suite:
        t1 = time.time()
        try:
            eng.predict({'states': [{'id': 's0', 'state': rec['state'], 'questions': qs}]})
            lat.append((time.time() - t1) * 1000)
        except Exception as e:
            print('nano win err', str(e)[:60])
    lat.sort()
    return {'method': 'nanojev-oracle', 'load_s': load_s, 'n': len(lat),
            'p50_ms': round(lat[len(lat) // 2], 1) if lat else None,
            'p95_ms': round(lat[int(len(lat) * .95)], 1) if lat else None}


if __name__ == '__main__' and '--nano-only' in sys.argv:
    print(json.dumps(nano_p50())); sys.exit(0)

if __name__ == '__main__':
    results = {}
    r = kev_p50('kev08-oracle', f'{RUNS}/oracle-kev08-v3', 18428)
    results['kev08-oracle'] = r
    json.dump(results, open('coldstart/oracle_p50_partial.json','w'), indent=1)
    results['kev4b-oracle'] = {'method':'kev4b-oracle','note':'serve hangs at weights loading (3rd attempt, local ckpt); P50 adopted from T1 artifact kev-4b-zs 342ms (same stack/size)'}
    results['nanojev-oracle'] = nano_p50()
    json.dump(results, open('coldstart/oracle_p50.json','w'), indent=1)
    print(json.dumps(results, indent=1))
