#!/usr/bin/env python3
"""run_cloud_jev.py — CLOUD-JEV-439 第二步: 云 Jev 1.13 经 jev-agent 网关跑 oracle-v3 test 439 窗.

通路(主会话已冒烟验证): POST https://jev-agent.com/api/v1/systemone
  头: Authorization: Bearer $JEV_AGENT_KEY + X-TypeSafe-Key: $TYPESAFE_API_KEY
  体: model=jev-1.13.0, state=窗口文本, questions=四题(套件 schema)
行格式: 与 v3_baseline_runner.emit() 兼容(id/group/source/label/pred/probs/latency_ms),
        附 answers 原始响应与 model 字段; 断点续跑按 id 去重追加.
红线: 只写本目录; key 运行时读 .env, 不入日志/报告.
"""
import json, os, random, sys, time, urllib.request, urllib.error
from pathlib import Path

HERE = Path(__file__).parent
SUITE = '/home/xxl/MySecAgent/lab/experiments/oracle/suites/oracle-v3/test.jsonl'
ENVF = Path.home() / 'MySecAgent/lab/experiments/jev-exp/.env'
OUT = HERE / 'predictions.jsonl'
ENDPOINT = 'https://jev-agent.com/api/v1/systemone'
MODEL = 'jev-1.13.0'
SEV = ['low', 'medium', 'high', 'critical']


def load_env():
    env = {}
    for l in ENVF.read_text().splitlines():
        l = l.strip()
        if l and not l.startswith('#') and '=' in l:
            k, v = l.split('=', 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


ENV = load_env()
JEV_KEY = ENV['JEV_AGENT_KEY']
TS_KEY = ENV['TYPESAFE_API_KEY']


def load_suite():
    recs = [json.loads(l) for l in open(SUITE)]
    assert len(recs) == 439, f'suite size {len(recs)} != 439'
    return recs


def build_questions(rec):
    """按 test.jsonl 的 questions 字段构造(去 label/src), noul 保留 criteria{true,false}."""
    qs = {}
    for qk, q in rec['questions'].items():
        if qk == 'action' and q is None:
            continue
        qq = {k: v for k, v in q.items() if k not in ('label', 'src')}
        # 网关要求 instructions 为非空字符串; 套件里 urgent/severity 是 {question,focus} dict,
        # 取 question 字段(= v3_baseline_runner 的 URGENT_INSTR['question']/SEV_INSTR['question'] 同文案)
        if isinstance(qq.get('instructions'), dict):
            qq['instructions'] = qq['instructions']['question']
        qs[qk] = qq
    return qs


def call(rec):
    body = json.dumps({'model': MODEL, 'state': rec['state'],
                       'questions': build_questions(rec)}).encode()
    req = urllib.request.Request(ENDPOINT, body, {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {JEV_KEY}',
        'X-TypeSafe-Key': TS_KEY,
    })
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=120) as r:
        d = json.loads(r.read())
    return d, (time.time() - t0) * 1000


def quota_err(e):
    txt = ''
    if isinstance(e, urllib.error.HTTPError):
        txt = f'{e.code} ' + e.read()[:200].decode(errors='ignore')
    else:
        txt = str(e)
    low = txt.lower()
    return any(k in low for k in ('quota', 'billing', 'balance', 'insufficient', '402',
                                  'payment', 'arrears', 'exceeded your current quota'))


def emit(fh, rec, pred, probs, lat_ms, extra):
    labels = rec['_meta']['labels_full']
    row = {
        'id': rec['_meta']['id'], 'group': rec['_meta']['group_id'], 'source': rec['_meta']['source'],
        'label': {k: labels.get(k) for k in ('tactic', 'urgent', 'severity', 'action')},
        'pred': pred, 'probs': probs,
        'latency_ms': round(lat_ms, 1) if lat_ms is not None else None,
    }
    if extra:
        row.update(extra)
    fh.write(json.dumps(row, ensure_ascii=False) + '\n')
    fh.flush()


def resume():
    done = set()
    if OUT.exists():
        for l in open(OUT):
            try:
                r = json.loads(l)
                if not r.get('error') and (r.get('pred') or {}).get('tactic') is not None:
                    done.add(r['id'])
            except Exception:
                pass
    return done


def main(limit=None):
    recs = load_suite()
    done = resume()
    todo = [r for r in recs if r['_meta']['id'] not in done]
    if limit:
        todo = todo[:limit]
    print(f'total={len(recs)} done={len(done)} todo={len(todo)}', flush=True)
    n = err = consec_fail = 0
    with open(OUT, 'a') as fh:
        for rec in todo:
            rid = rec['_meta']['id']
            last = None
            ok = False
            for attempt in range(3):
                try:
                    d, ms = call(rec)
                    m = d.get('model')
                    if m != MODEL:
                        print(f'FATAL {rid}: model={m!r} != {MODEL!r}, 停止', flush=True)
                        emit(fh, rec, None, None, ms, {'error': f'model_mismatch:{m}', 'answers': d.get('answers')})
                        sys.exit(2)
                    a = d['answers']
                    sev_raw = a['severity'].get('score', 0)
                    emit(fh, rec, {
                        'tactic': a['tactic'].get('choice'),
                        'urgent': a['urgent'].get('noul', 0) >= 0.5,
                        'severity': SEV[min(3, max(0, int(round(sev_raw))))],
                        'action': a['action'].get('choice'),
                    }, {
                        'tactic': a['tactic'].get('probabilities', {}),
                        'urgent': a['urgent'].get('noul'),
                        'severity': a['severity'].get('probabilities', {}),
                        'action': a['action'].get('probabilities', {}),
                    }, ms, {'model': m, 'sev_raw': sev_raw, 'answers': a})
                    n += 1
                    ok = True
                    break
                except Exception as e:
                    last = e
                    if quota_err(e):
                        print(f'FATAL {rid}: quota/billing 错误, 立即停止. 剩余窗数(含本窗): '
                              f'{len(todo) - n - err}', flush=True)
                        raise
                    time.sleep(2 * (attempt + 1))
            if not ok:
                emit(fh, rec, None, None, None,
                     {'error': f'{type(last).__name__}: {str(last)[:150]}'})
                err += 1
                consec_fail += 1
                if consec_fail >= 10:
                    print(f'FATAL: 连续 10 窗失败, 停止. 已完成 {len(done) + n}, 剩余 {len(todo) - n - err}', flush=True)
                    sys.exit(3)
            else:
                consec_fail = 0
            if (n + err) % 20 == 0 and (n + err):
                print(f'progress: +{n} ok +{err} err / {len(todo)}', flush=True)
            time.sleep(random.uniform(0.5, 1.0))
    print(f'DONE: +{n} ok, {err} err -> {OUT}', flush=True)


if __name__ == '__main__':
    lim = None
    if len(sys.argv) > 1:
        lim = int(sys.argv[1])
    main(lim)
