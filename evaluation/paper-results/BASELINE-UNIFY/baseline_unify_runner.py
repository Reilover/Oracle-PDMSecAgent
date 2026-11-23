#!/usr/bin/env python3
"""baseline_unify_runner.py — P0-1 基线统一重测（批A+B本地6条，全部CPU）

目标: 把早期 4-opt 约定(dev+470窗test)的 6 条基线统一到 oracle-v3 test 439 窗(11选项/8action/4sev/noul urgent)重测。
方法与早期 runner 一模一样(EVAL/RANGE-BASELINE/range_baseline_runner.py + range_extra_runner.py),
仅换卷 oracle-v1 -> oracle-v3 test。行格式与 V3-TEST-BASELINE 完全一致(evaluate.py 可直接算)。

方法: rule | nanojev-zs | laya-zs | spark-gen | minicpm-gen | minicpm-opt
用法: python3 baseline_unify_runner.py <method> test [--limit N]
断点续跑: 按 id 去重追加; 失败重试 3 次落 error 行。
零 GPU: laya 走 SDK CPU(device='cpu'); NanoJev 走 CPU 适配器(复用官方 prepare_examples/answer_from_probabilities);
Spark/MiniCPM 走 llama.cpp CPU 端点 18080/18081。
"""
import argparse, json, os, re, sys, time, urllib.request
from pathlib import Path

HERE = Path(__file__).parent
SUITE = '/home/xxl/MySecAgent/lab/experiments/oracle/suites/oracle-v3'
sys.path.insert(0, '/home/xxl/MySecAgent/lab/experiments/oracle/code/suite')
from pack_suite import TACTIC_CRITERIA, TACTIC_INSTR, URGENT_INSTR, SEV_INSTR, SEV_CRIT, ACTION_CRITERIA, ACTION_INSTR

SEV = ['low', 'medium', 'high', 'critical']
SPARK_URL = 'http://127.0.0.1:18080/v1/chat/completions'
MINICPM_URL = 'http://127.0.0.1:18081/v1/chat/completions'
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


# ---------- A1 规则基线(与 RANGE-BASELINE run_rule 逐字一致,仅换卷) ----------

def run_rule(recs, split):
    out = out_path('rule', split)
    done = resume(out)
    n = 0
    with open(out, 'a') as fh:
        for rec in recs:
            rid = rec['_meta']['id']
            if rid in done:
                continue
            t0 = time.time()
            state = rec['state']
            lines = '\n'.join(state.split('\n')[1:-1])  # 去头尾(Context 行)
            ctx = state.split('\n')[-1]
            n_fail = len(re.findall(r'Failed (none|password|publickey)|Invalid user', lines))
            n_fail_ctx = int(re.search(r'failed_logins=(\d+)', ctx).group(1)) if re.search(r'failed_logins=(\d+)', ctx) else 0
            accepted = 'Accepted password' in lines or 'Accepted publickey' in lines
            sqlmap = 'sqlmap' in lines
            attack_ip = re.search(r'172\.28\.0\.2', lines) is not None
            web_atk = bool(re.search(r'(sqlmap|/vulnerabilities/|SELECT|UNION|<script|../|\bexec\b|cmd=|shell)', lines, re.I))
            if sqlmap:
                tac, urgent, sev, act = 'initial_access', True, 'high', 'block_ip'
            elif accepted and attack_ip:
                tac, urgent, sev, act = 'credential_access', True, 'critical', 'block_ip'
            elif n_fail >= 3 or n_fail_ctx >= 5:
                tac, urgent, sev, act = 'credential_access', True, 'high', 'block_ip'
            elif n_fail > 0 or n_fail_ctx > 0:
                tac, urgent, sev, act = 'credential_access', False, 'medium', 'monitor'
            elif web_atk and attack_ip:
                tac, urgent, sev, act = 'initial_access', True, 'high', 'block_ip'
            else:
                tac, urgent, sev, act = 'benign', False, 'low', 'no_action'
            emit(fh, rec, {'tactic': tac, 'urgent': urgent, 'severity': sev, 'action': act}, None, (time.time() - t0) * 1000)
            n += 1
    print(f'rule/{split}: +{n} -> {out}', flush=True)


# ---------- A2 NanoJev-0.6B zero-shot(官方 unified ckpt,CPU 适配器,同 RANGE-BASELINE nanojev_cpu.py) ----------

def run_nanojev_zs(recs, split):
    sys.path.insert(0, '/home/xxl/Mylocllm/NanoJev/scripts')
    os.environ['TRANSFORMERS_OFFLINE'] = '1'
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
    import torch
    from safetensors.torch import load_file
    from transformers import AutoConfig, AutoModel, AutoTokenizer
    import predict_toy_decisions as ptd
    CKPT = '/home/xxl/Mylocllm/NanoJev/checkpoints/NanoJev-unified'
    ck = Path(CKPT)
    run_config = json.loads((ck / 'config.json').read_text())
    tokenizer = AutoTokenizer.from_pretrained(str(ck / 'tokenizer'), local_files_only=True, trust_remote_code=False)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    body_config = AutoConfig.from_pretrained(str(ck / 'backbone_config'), local_files_only=True, trust_remote_code=False)
    body_config.use_cache = False
    limit = run_config.get('max_length', 512)
    body = AutoModel.from_config(body_config, attn_implementation='sdpa', trust_remote_code=False).float()
    DecisionModel = ptd.load_decision_model_class()
    model = DecisionModel(body, run_config['set_head'])
    weights = load_file(str(ck / 'best.safetensors'), device='cpu')
    model.load_state_dict(weights, strict=True)
    del weights
    model = model.to(device='cpu', dtype=torch.float32).eval()

    def qs():
        return {
            'tactic': {'type': 'choice', 'instructions': TACTIC_INSTR, 'criteria': dict(TACTIC_CRITERIA)},
            'urgent': {'type': 'boolean', 'instructions': URGENT_INSTR['question'],
                       'criteria': {'true': 'Act now: ongoing or imminent compromise',
                                    'false': 'Routine: can wait for normal triage'}},
            'severity': {'type': 'score', 'instructions': SEV_INSTR['question'], 'criteria': list(SEV_CRIT)},
            'action': {'type': 'choice', 'instructions': ACTION_INSTR, 'criteria': dict(ACTION_CRITERIA)},
        }

    def predict_cpu(payload):
        states = ptd.validate_request(payload)
        examples = ptd.prepare_examples(payload, tokenizer, limit)
        outputs = {s['id']: {'id': s['id'], 'answers': {}} for s in states}
        with torch.inference_mode():
            logits, _ = model(examples, tokenizer.pad_token_id)
            for ex, values in zip(examples, logits):
                k = len(ex['candidate_ids'])
                scores = values[:k].float()
                if not torch.isfinite(scores).all():
                    raise ValueError('模型产生非有限 logits')
                probs = (scores / 1.0).softmax(-1).cpu().tolist()
                outputs[ex['state_id']]['answers'][ex['qid']] = ptd.answer_from_probabilities(ex, probs)
        return {'states': list(outputs.values())}

    out = out_path('nanojev-zs', split)
    done = resume(out)
    n = err = 0
    t0all = time.time()
    with open(out, 'a') as fh:
        for rec in recs:
            rid = rec['_meta']['id']
            if rid in done:
                continue
            t0 = time.time()
            try:
                r = predict_cpu({'states': [{'id': 's0', 'state': rec['state'], 'questions': qs()}]})
                ans = r['states'][0]['answers']
                emit(fh, rec, {
                    'tactic': ans['tactic'].get('choice'),
                    'urgent': bool(ans['urgent'].get('value')),
                    'severity': SEV[min(3, max(0, int(round(ans['severity'].get('score', 0)))))],
                    'action': ans['action'].get('choice'),
                }, {'tactic': ans['tactic'].get('probabilities', {}),
                    'action': ans['action'].get('probabilities', {})}, (time.time() - t0) * 1000)
                n += 1
            except Exception as e:
                emit(fh, rec, None, None, (time.time() - t0) * 1000,
                     {'error': f'{type(e).__name__}: {str(e)[:150]}'})
                err += 1
            if (n + err) % 10 == 0:
                print(f'nanojev-zs/{split}: {n + err} ({time.time() - t0all:.0f}s)', flush=True)
    print(f'nanojev-zs/{split}: +{n} ok, {err} err -> {out}', flush=True)


# ---------- A3 laya-421M zero-shot(SDK CPU,choice 协议同 RANGE-BASELINE run_laya,severity 走 choice) ----------
# Router() 走 hub 在线解析(本机离线报 Incompatible model),改用本地 snapshot 直建 Agent ——
# 与 2026-09-24 RANGE-BASELINE 跑的是同一 checkpoint(HF cache 快照,english 421M)。
LAYA_SNAPSHOT = '/home/xxl/.cache/huggingface/hub/models--convaiinnovations--laya/snapshots/1c5edc17a7acd8701df6fc341c0d179f1c62c982'

def run_laya_zs(recs, split):
    os.environ['HF_HUB_OFFLINE'] = '1'
    sys.path.insert(0, '/home/xxl/Mylocllm')
    from laya import Agent
    agent = Agent(LAYA_SNAPSHOT, device='cpu', token=None, subfolder=None)
    out = out_path('laya-zs', split)
    done = resume(out)
    n = err = 0
    t0all = time.time()
    with open(out, 'a') as fh:
        for rec in recs:
            rid = rec['_meta']['id']
            if rid in done:
                continue
            questions = {
                'tactic': {'type': 'choice', 'instructions': TACTIC_INSTR, 'criteria': dict(TACTIC_CRITERIA)},
                'urgent': {'type': 'noul', 'instructions': URGENT_INSTR['question']},
                'severity': {'type': 'choice', 'instructions': SEV_INSTR['question'],
                             'criteria': {sv: SEV_CRIT[i] for i, sv in enumerate(SEV)}},
                'action': {'type': 'choice', 'instructions': ACTION_INSTR, 'criteria': dict(ACTION_CRITERIA)},
            }
            t0 = time.time()
            try:
                r = agent.system_one(rec['state'], questions)
                a = r.get('answers') or r  # system_one 直接返回 answers dict(冒烟实测)
                tac_p = a['tactic'].get('probabilities') or {}
                act_p = a['action'].get('probabilities') or {}
                sev_p = a['severity'].get('probabilities') or {}
                pred = {
                    'tactic': a['tactic'].get('choice') or (max(tac_p, key=tac_p.get) if tac_p else None),
                    'urgent': (a['urgent'].get('noul') or 0) >= 0.5,
                    'severity': a['severity'].get('choice') or (max(sev_p, key=sev_p.get) if sev_p else None),
                    'action': a['action'].get('choice') or (max(act_p, key=act_p.get) if act_p else None),
                }
                emit(fh, rec, pred, {'tactic': tac_p, 'urgent': a['urgent'].get('noul'),
                                     'severity': sev_p, 'action': act_p}, (time.time() - t0) * 1000)
                n += 1
            except Exception as e:
                emit(fh, rec, None, None, (time.time() - t0) * 1000, {'error': f'{type(e).__name__}: {str(e)[:120]}'})
                err += 1
            if (n + err) % 20 == 0:
                print(f'laya-zs/{split}: {n + err} ({time.time() - t0all:.0f}s)', flush=True)
    print(f'laya-zs/{split}: +{n} ok, {err} err -> {out}', flush=True)


# ---------- B1/B2 生成式(Spark @18080 / MiniCPM @18081 llama.cpp CPU),同 range_extra_runner gen 协议 ----------

def gen_prompt(rec):
    return f"""Analyze this security log window. Answer as strict JSON with keys:
tactic (one of: {', '.join(TACTIC_CRITERIA)}), urgent (true/false), severity (one of: {', '.join(SEV)}), action (one of: {', '.join(ACTION_CRITERIA)}).

{rec['state']}

JSON:"""


def norm(v):
    return str(v).strip().strip('.,`"\' ').lower().replace(' ', '_') if v is not None else None


def parse_json(text):
    m = re.search(r'\{.*\}', text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group())
    except Exception:
        return None


def http_json(url, body, timeout=600):
    req = urllib.request.Request(url, json.dumps(body).encode(), {'Content-Type': 'application/json'})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.loads(r.read())
    return d, time.time() - t0


def chat_local(url, model, prompt, max_tokens=300):
    body = {'model': model, 'messages': [
        {'role': 'system', 'content': GEN_SYS},
        {'role': 'user', 'content': prompt}], 'max_tokens': max_tokens, 'temperature': 0.1,
        'chat_template_kwargs': {'enable_thinking': False}}
    d, dt = http_json(url, body)
    msg = d['choices'][0]['message']
    return (msg.get('content') or msg.get('reasoning_content') or ''), dt


def run_gen_local(method, url, model, recs, split):
    out = out_path(method, split)
    done = resume(out)
    n = err = n_invalid = 0
    t0all = time.time()
    with open(out, 'a') as fh:
        for rec in recs:
            rid = rec['_meta']['id']
            if rid in done:
                continue
            last = None
            for attempt in range(3):
                try:
                    content, dt = chat_local(url, model, gen_prompt(rec))
                    j = parse_json(content) or {}
                    tac, urg = norm(j.get('tactic')), j.get('urgent')
                    if isinstance(urg, str):
                        urg = urg.strip().lower() == 'true'
                    sev, act = norm(j.get('severity')), norm(j.get('action'))
                    valid = tac in TACTIC_CRITERIA and sev in SEV and act in ACTION_CRITERIA and isinstance(urg, bool)
                    emit(fh, rec, {'tactic': tac if valid else None, 'urgent': urg if valid else None,
                                   'severity': sev if valid else None, 'action': act if valid else None},
                         None, dt * 1000, {'valid': valid, 'raw': content[:150] if not valid else ''})
                    n += 1
                    n_invalid += (not valid)
                    break
                except Exception as e:
                    last = e
                    time.sleep(2 * (attempt + 1))
            else:
                emit(fh, rec, None, None, None, {'error': str(last)[:150]})
                err += 1
            if (n + err) % 20 == 0:
                el = time.time() - t0all
                print(f'{method}/{split}: {n + err} done ({el:.0f}s, ~{el / (n + err):.1f}s/win, invalid={n_invalid})', flush=True)
    print(f'{method}/{split}: +{n} ok ({n_invalid} invalid-json), {err} err -> {out}', flush=True)


# ---------- B3 MiniCPM option-scored(每任务独立问,温度采样5次计数->分布,同 range_extra_runner C 模式) ----------

def run_minicpm_opt(recs, split):
    out = out_path('minicpm-opt', split)
    done = resume(out)
    n = err = 0
    t0all = time.time()
    with open(out, 'a') as fh:
        for rec in recs:
            rid = rec['_meta']['id']
            if rid in done:
                continue
            t0 = time.time()
            try:
                dists = {}
                for task, cands in [('tactic', list(TACTIC_CRITERIA)), ('severity', SEV), ('action', list(ACTION_CRITERIA))]:
                    cand_list = ','.join(cands)
                    prompt = f"""Security log analysis. Answer with EXACTLY one of [{cand_list}], nothing else.

{rec['state']}

Answer:"""
                    counts = {c: 0 for c in cands}
                    for _ in range(5):
                        try:
                            content, _ = chat_local(MINICPM_URL, 'minicpm', prompt, max_tokens=12)
                            c = content.strip().strip('.,`"\' ').lower()
                            for cand in cands:
                                if c.startswith(cand) or cand in c[:len(cand) + 5]:
                                    counts[cand] += 1
                                    break
                        except Exception:
                            pass
                    tot = sum(counts.values()) or 1
                    dists[task] = {c: v / tot for c, v in counts.items()}
                uprompt = f"""Security log analysis. Answer with EXACTLY one word: true or false. Does this alert need immediate human intervention?

{rec['state']}

Answer:"""
                cu = {'true': 0, 'false': 0}
                for _ in range(5):
                    try:
                        content, _ = chat_local(MINICPM_URL, 'minicpm', uprompt, max_tokens=6)
                        c = content.strip().lower()
                        if c.startswith('true'):
                            cu['true'] += 1
                        elif c.startswith('false'):
                            cu['false'] += 1
                    except Exception:
                        pass
                tu = sum(cu.values()) or 1
                dists['urgent'] = {'true': cu['true'] / tu, 'false': cu['false'] / tu}
                pred = {
                    'tactic': max(dists['tactic'], key=dists['tactic'].get),
                    'urgent': dists['urgent']['true'] >= 0.5,
                    'severity': max(dists['severity'], key=dists['severity'].get),
                    'action': max(dists['action'], key=dists['action'].get),
                }
                emit(fh, rec, pred, dists, (time.time() - t0) * 1000)
                n += 1
            except Exception as e:
                emit(fh, rec, None, None, (time.time() - t0) * 1000, {'error': f'{type(e).__name__}: {str(e)[:120]}'})
                err += 1
            if n % 10 == 0:
                el = time.time() - t0all
                print(f'minicpm-opt/{split}: {n} done ({el:.0f}s, ~{el / n:.1f}s/win)', flush=True)
    print(f'minicpm-opt/{split}: +{n} ok, {err} err -> {out}', flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('method', choices=['rule', 'nanojev-zs', 'laya-zs', 'spark-gen', 'minicpm-gen', 'minicpm-opt'])
    ap.add_argument('split', choices=['development', 'test'])
    ap.add_argument('--limit', type=int, default=None)
    ap.add_argument('--shard', default=None, help='i/n 如 0/4;各 shard 写同一输出文件(O_APPEND 单行原子,断点续跑按 id 去重)')
    a = ap.parse_args()
    recs = load_split(a.split, a.limit)
    if a.shard:
        i, n = (int(x) for x in a.shard.split('/'))
        recs = recs[i::n]
    if a.method == 'rule':
        run_rule(recs, a.split)
    elif a.method == 'nanojev-zs':
        run_nanojev_zs(recs, a.split)
    elif a.method == 'laya-zs':
        run_laya_zs(recs, a.split)
    elif a.method == 'spark-gen':
        run_gen_local('spark-gen', SPARK_URL, 'spark25', recs, a.split)
    elif a.method == 'minicpm-gen':
        run_gen_local('minicpm-gen', MINICPM_URL, 'minicpm', recs, a.split)
    elif a.method == 'minicpm-opt':
        run_minicpm_opt(recs, a.split)


if __name__ == '__main__':
    main()
