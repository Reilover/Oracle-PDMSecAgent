#!/usr/bin/env python3
"""v3_baseline_runner.py — 批次1 1-1：oracle-v3 test 439 窗五方重评（统一口径）
方法: glm | dsk | g2v6-qwen | kev4b-zs | nanojev-v3
行格式与 RANGE-BASELINE 完全兼容（evaluate.py 可直接算），断点续跑按 id 去重追加。
凭据: 运行时读 ~/.dsh/.credentials.yaml，不入 git 不进报告。
"""
import argparse, json, math, os, re, sys, time, urllib.request
from pathlib import Path

HERE = Path(__file__).parent
SUITE = '/home/xxl/MySecAgent/lab/experiments/oracle/suites/oracle-v3'
sys.path.insert(0, '/home/xxl/MySecAgent/lab/experiments/oracle/code/suite')
from pack_suite import TACTIC_CRITERIA, TACTIC_INSTR, URGENT_INSTR, SEV_INSTR, SEV_CRIT, ACTION_CRITERIA, ACTION_INSTR

SEV = ['low', 'medium', 'high', 'critical']
QWEN_BASE = 'http://127.0.0.1:18083/v1'
GEN_SYS = 'You are a security alert triage assistant. Reply with ONLY a JSON object, nothing else.'


def load_split(split, limit=None):
    recs = [json.loads(l) for l in open(f'{SUITE}/{split}.jsonl')]
    return recs[:limit] if limit else recs


def out_path(method, split):
    return HERE / f'results_{method}_{split}.jsonl'


def resume(out):
    done = set()
    if Path(out).exists():
        for l in open(out):
            try:
                r = json.loads(l)
                if not r.get('error') and (r.get('pred') or {}).get('tactic') is not None:
                    done.add(r.get('id'))
            except Exception:
                pass
    return done


def emit(fh, rec, pred, probs=None, lat_ms=None, extra=None):
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


# ---------- 生成式 API (GLM / DeepSeek)，同 RANGE-BASELINE 模板 ----------

def api_cfg(which):
    import yaml
    creds = yaml.safe_load(open(os.path.expanduser('~/.dsh/.credentials.yaml')))['refs']
    if which == 'glm':
        return {'key': creds['ZAI_CODING_CN_API_KEY'],
                'url': 'https://open.bigmodel.cn/api/coding/paas/v4/chat/completions',
                'model': 'glm-5.3', 'glm': True}
    return {'key': creds['DEEPSEEK_API_KEY'],
            'url': 'https://api.deepseek.com/chat/completions', 'model': 'deepseek-chat'}


def chat(prov, prompt):
    payload = {'model': prov['model'], 'messages': [
        {'role': 'system', 'content': GEN_SYS},
        {'role': 'user', 'content': prompt}], 'max_tokens': 300, 'temperature': 0.1}
    if prov.get('glm'):
        payload['thinking'] = {'type': 'disabled'}
    req = urllib.request.Request(prov['url'], json.dumps(payload).encode(),
                                 {'Content-Type': 'application/json', 'Authorization': f"Bearer {prov['key']}"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=120) as r:
        d = json.loads(r.read())
    msg = d['choices'][0]['message']
    return (msg.get('content') or msg.get('reasoning_content') or ''), time.time() - t0


def parse_json(text):
    m = re.search(r'\{.*\}', text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group())
    except Exception:
        return None


def run_gen(which, recs, split, limit):
    prov = api_cfg(which)
    out = out_path(which, split)
    done = resume(out)
    n = err = 0
    with open(out, 'a') as fh:
        for rec in recs:
            rid = rec['_meta']['id']
            if rid in done:
                continue
            prompt = f"""Analyze this security log window. Answer as strict JSON with keys:
tactic (one of: {', '.join(TACTIC_CRITERIA)}), urgent (true/false), severity (one of: {', '.join(SEV)}), action (one of: {', '.join(ACTION_CRITERIA)}).

{rec['state']}

JSON:"""
            last = None
            for attempt in range(3):
                try:
                    content, dt = chat(prov, prompt)
                    j = parse_json(content) or {}
                    tac, urg = j.get('tactic'), j.get('urgent')
                    sev, act = j.get('severity'), j.get('action')
                    valid = tac in TACTIC_CRITERIA and sev in SEV and act in ACTION_CRITERIA and isinstance(urg, bool)
                    emit(fh, rec, {'tactic': tac if valid else None, 'urgent': urg if valid else None,
                                   'severity': sev if valid else None, 'action': act if valid else None},
                         None, dt * 1000, {'valid': valid, 'raw': content[:150] if not valid else ''})
                    n += 1
                    break
                except Exception as e:
                    last = e
                    time.sleep(2 * (attempt + 1))
            else:
                emit(fh, rec, None, None, None, {'error': str(last)[:150]})
                err += 1
            if (n + err) % 20 == 0:
                print(f'{which}/{split}: {n + err} done', flush=True)
    print(f'{which}/{split}: +{n} ok, {err} err -> {out}')


# ---------- G2v6 Qwen3-8B prefill+few-shot（vLLM @18083，同 range_extra_runner） ----------

def http_json(url, body, timeout=300):
    req = urllib.request.Request(url, json.dumps(body).encode(), {'Content-Type': 'application/json'})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.loads(r.read())
    return d, time.time() - t0


def run_g2v6(recs, split):
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained('/disk1/models/Qwen3-8B-SecAgent', trust_remote_code=True)

    def prefill_score(prefix, cand):
        full = prefix + cand
        body = {'model': 'qwen3-8b', 'prompt': full, 'max_tokens': 1,
                'temperature': 0, 'logprobs': 1, 'prompt_logprobs': 1}
        d, _ = http_json(f'{QWEN_BASE}/completions', body)
        ch = d['choices'][0]
        plp = ch.get('prompt_logprobs') or []
        cand_ids = set(tok.encode(' ' + cand, add_special_tokens=False) + tok.encode(cand, add_special_tokens=False))
        want = len(tok.encode(' ' + cand, add_special_tokens=False))
        hits = []
        for p in plp:
            if p is None:
                continue
            for tid_s, info in p.items():
                if int(tid_s) in cand_ids:
                    hits.append(info['logprob'])
                    break
        cand_toks = hits[-want:] if len(hits) >= want else hits
        return sum(cand_toks) / len(cand_toks) if cand_toks else -30.0

    FEWSHOT = """Example 1:
Security log window:
Failed password for root from 203.0.113.5 port 50022 ssh2
Failed password for root from 203.0.113.5 port 50024 ssh2
Context: 28 failed attempts in 5 minutes
Question: Which MITRE ATT&CK tactic matches this alert?
Answer: credential_access

Example 2:
Security log window:
Server listening on 0.0.0.0 port 22.
Accepted publickey for deploy from 10.0.0.5 port 41022 ssh2
Context: routine CI deployment, no failures
Question: Which MITRE ATT&CK tactic matches this alert?
Answer: benign

"""

    def score_candidates(state_text, question, candidates):
        prefix = f"""{FEWSHOT}Now analyze:
{state_text}

Question: {question}
Answer: """
        scores = {c: prefill_score(prefix, c) for c in candidates}
        mx = max(scores.values())
        exps = {c: math.exp(v - mx) for c, v in scores.items()}
        tot = sum(exps.values())
        return {c: e / tot for c, e in exps.items()}

    out = out_path('g2v6-qwen', split)
    done = resume(out)
    n = err = 0
    with open(out, 'a') as fh:
        for rec in recs:
            rid = rec['_meta']['id']
            if rid in done:
                continue
            st = rec['state']
            t0 = time.time()
            try:
                dists = {}
                for task, cands, q in [
                    ('tactic', list(TACTIC_CRITERIA), TACTIC_INSTR),
                    ('severity', SEV, SEV_INSTR['question']),
                    ('action', list(ACTION_CRITERIA), ACTION_INSTR)]:
                    dists[task] = score_candidates(st, q, cands)
                dists['urgent'] = score_candidates(st, URGENT_INSTR['question'], ['true', 'false'])
                pred = {'tactic': max(dists['tactic'], key=dists['tactic'].get),
                        'urgent': dists['urgent']['true'] >= 0.5,
                        'severity': max(dists['severity'], key=dists['severity'].get),
                        'action': max(dists['action'], key=dists['action'].get)}
                emit(fh, rec, pred, dists, (time.time() - t0) * 1000)
                n += 1
            except Exception as e:
                emit(fh, rec, None, None, (time.time() - t0) * 1000, {'error': f'{type(e).__name__}: {str(e)[:120]}'})
                err += 1
            if n % 10 == 0:
                print(f'g2v6-qwen/{split}: {n} done ({(time.time()-t0):.1f}s last)', flush=True)
    print(f'g2v6-qwen/{split}: +{n} ok, {err} err -> {out}')


# ---------- Kev-4B 官方零样本（kev.serve @独立端口 + range_eval_kev 协议） ----------

def run_kev4b_zs(recs, split, base_url):
    out = out_path('kev4b-zs', split)
    done = resume(out)
    n = err = 0

    def decide(state, questions):
        body = json.dumps({'state': state, 'model': 'kev-latest', 'questions': questions}).encode()
        req = urllib.request.Request(f'{base_url}/v1/systemone', body, {'Content-Type': 'application/json'})
        t0 = time.time()
        with urllib.request.urlopen(req, timeout=120) as r:
            d = json.loads(r.read())
        return d['answers'], d.get('latency_ms', (time.time() - t0) * 1000)

    with open(out, 'a') as fh:
        for rec in recs:
            rid = rec['_meta']['id']
            if rid in done:
                continue
            labels = rec['_meta']['labels_full']
            qs = {
                'tactic': {'type': 'choice', 'instructions': TACTIC_INSTR, 'criteria': TACTIC_CRITERIA},
                'urgent': {'type': 'noul', 'instructions': URGENT_INSTR['question']},
                'severity': {'type': 'score', 'instructions': SEV_INSTR['question'], 'criteria': SEV_CRIT},
                'action': {'type': 'choice', 'instructions': ACTION_INSTR, 'criteria': ACTION_CRITERIA},
            }
            try:
                ans, dt = decide(rec['state'], qs)
                sev_score = ans['severity'].get('score', 0)
                emit(fh, rec, {
                    'tactic': ans['tactic'].get('choice'),
                    'urgent': ans['urgent'].get('noul', 0) >= 0.5,
                    'severity': SEV[min(3, max(0, int(round(sev_score))))],
                    'action': ans['action'].get('choice'),
                }, {
                    'tactic': ans['tactic'].get('probabilities', {}),
                    'action': ans['action'].get('probabilities', {}),
                }, dt)
                n += 1
            except Exception as e:
                emit(fh, rec, None, None, None, {'error': f'{type(e).__name__}: {str(e)[:150]}'})
                err += 1
            if n % 20 == 0:
                print(f'kev4b-zs/{split}: {n} done', flush=True)
    print(f'kev4b-zs/{split}: +{n} ok, {err} err -> {out}')


def run_kev08_zs(recs, split, base_url):
    """kev-0.8B 官方零样本: 与 run_kev4b_zs 完全同协议/同模板/同四问 (REPORT-KEV08-ZS)."""
    out = out_path('kev08-zs', split)
    done = resume(out)
    n = err = 0

    def decide(state, questions):
        body = json.dumps({'state': state, 'model': 'kev-latest', 'questions': questions}).encode()
        req = urllib.request.Request(f'{base_url}/v1/systemone', body, {'Content-Type': 'application/json'})
        t0 = time.time()
        with urllib.request.urlopen(req, timeout=120) as r:
            d = json.loads(r.read())
        return d['answers'], d.get('latency_ms', (time.time() - t0) * 1000)

    with open(out, 'a') as fh:
        for rec in recs:
            rid = rec['_meta']['id']
            if rid in done:
                continue
            qs = {
                'tactic': {'type': 'choice', 'instructions': TACTIC_INSTR, 'criteria': TACTIC_CRITERIA},
                'urgent': {'type': 'noul', 'instructions': URGENT_INSTR['question']},
                'severity': {'type': 'score', 'instructions': SEV_INSTR['question'], 'criteria': SEV_CRIT},
                'action': {'type': 'choice', 'instructions': ACTION_INSTR, 'criteria': ACTION_CRITERIA},
            }
            try:
                ans, dt = decide(rec['state'], qs)
                sev_score = ans['severity'].get('score', 0)
                emit(fh, rec, {
                    'tactic': ans['tactic'].get('choice'),
                    'urgent': ans['urgent'].get('noul', 0) >= 0.5,
                    'severity': SEV[min(3, max(0, int(round(sev_score))))],
                    'action': ans['action'].get('choice'),
                }, {
                    'tactic': ans['tactic'].get('probabilities', {}),
                    'action': ans['action'].get('probabilities', {}),
                }, dt)
                n += 1
            except Exception as e:
                emit(fh, rec, None, None, None, {'error': f'{type(e).__name__}: {str(e)[:150]}'})
                err += 1
            if n % 20 == 0:
                print(f'kev08-zs/{split}: {n} done', flush=True)
    print(f'kev08-zs/{split}: +{n} ok, {err} err -> {out}')


# ---------- NanoJev v3 微调 checkpoint（官方 DecisionPredictor CUDA bf16，选项打分口径） ----------

def run_nanojev_v3(recs, split):
    ckpt = '/home/xxl/MySecAgent/lab/experiments/oracle/T3-NANOJEV/nanojev-oracle-v3'
    sys.path.insert(0, '/home/xxl/Mylocllm/NanoJev/scripts')
    import predict_toy_decisions as ptd
    eng = ptd.DecisionPredictor(ckpt, precision='bf16', disable_native_triton=True)
    out = out_path('nanojev-v3', split)
    done = resume(out)

    def qs():
        return {
            'tactic': {'type': 'choice', 'instructions': TACTIC_INSTR, 'criteria': dict(TACTIC_CRITERIA)},
            'urgent': {'type': 'boolean', 'instructions': URGENT_INSTR['question'],
                       'criteria': {'true': 'Act now: ongoing or imminent compromise',
                                    'false': 'Routine: can wait for normal triage'}},
            'severity': {'type': 'score', 'instructions': SEV_INSTR['question'], 'criteria': list(SEV_CRIT)},
            'action': {'type': 'choice', 'instructions': ACTION_INSTR, 'criteria': dict(ACTION_CRITERIA)},
        }

    n = err = 0
    t0all = time.time()
    with open(out, 'a') as fh:
        for rec in recs:
            rid = rec['_meta']['id']
            if rid in done:
                continue
            t0 = time.time()
            try:
                r = eng.predict({'states': [{'id': 's0', 'state': rec['state'], 'questions': qs()}]})
                ans = r['states'][0]['answers']
                emit(fh, rec, {
                    'tactic': ans['tactic'].get('choice'),
                    'urgent': bool(ans['urgent'].get('value')),
                    'severity': SEV[min(3, max(0, int(round(ans['severity'].get('score', 0)))))],
                    'action': ans['action'].get('choice'),
                }, {'tactic': ans['tactic'].get('probabilities', {}),
                    'action': ans['action'].get('probabilities', {})},
                    (time.time() - t0) * 1000)
                n += 1
            except Exception as e:
                emit(fh, rec, None, None, (time.time() - t0) * 1000,
                     {'error': f'{type(e).__name__}: {str(e)[:150]}'})
                err += 1
            if (n + err) % 10 == 0:
                print(f'nanojev-v3/{split}: {n + err} ({time.time() - t0all:.0f}s total)', flush=True)
    print(f'nanojev-v3/{split}: +{n} ok, {err} err -> {out}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('method', choices=['glm', 'dsk', 'g2v6-qwen', 'kev4b-zs', 'kev08-zs', 'nanojev-v3'])
    ap.add_argument('split', choices=['development', 'test'])
    ap.add_argument('--limit', type=int, default=None)
    ap.add_argument('--kev-base', default='http://127.0.0.1:8028')
    a = ap.parse_args()
    recs = load_split(a.split, a.limit)
    if a.method in ('glm', 'dsk'):
        run_gen(a.method, recs, a.split, a.limit)
    elif a.method == 'g2v6-qwen':
        run_g2v6(recs, a.split)
    elif a.method in ('kev4b-zs', 'kev08-zs'):
        run_kev4b_zs(recs, a.split, a.kev_base) if a.method == 'kev4b-zs' else run_kev08_zs(recs, a.split, a.kev_base)
    elif a.method == 'nanojev-v3':
        run_nanojev_v3(recs, a.split)


if __name__ == '__main__':
    main()
