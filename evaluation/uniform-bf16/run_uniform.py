#!/usr/bin/env python3
"""run_uniform.py — 计划A：表2统一重测 runner（docs/02-执行交接/表2配置统一补测方案.md v3.1 A.2）

协议模板逐字复用：
  - baseline_unify_runner.py：GEN_SYS/gen_prompt/parse_json/norm、C 行零样本指令、
    nanojev-zs / laya-zs 装载与四问协议、minicpm-opt 计数协议
  - v3_baseline_runner.py：api_cfg()（云凭据只从 ~/.dsh/.credentials.yaml 读）、
    G 行 prefill-logprobs 打分机制（本 runner 的 C 行按方案 A.2 用 ΣlogP+softmax）
行 schema 与原 results 完全一致（evaluate.py 可直接算）；断点续跑按 id 去重追加。

方法（Plan A）:
  e2-laya        laya-421M GPU bf16 autocast（LAYA_GPU_FP32=0）dev+test
  e1-nanojev     NanoJev-unified GPU bf16 dev+test
  mb-bf16        ModernBERT 四头 GPU bf16（dev only，probs 全量输出供 ECE）
  verdict        Verdict-151M test（补 P50；rlcd DecisionEngine）
  c-logprobs     MiniCPM bf16 vLLM prefill-logprobs 选项打分（C 行新协议）
  b-gen          MiniCPM bf16 vLLM greedy（temp 0）
  h-gen          Spark-X2.5-4B bf16 vLLM greedy（~/spark2_5 venv serve）
  f-glm / f-dsk  云 API temp 0（GLM thinking disabled）
方法（Plan B，--outdir 指到 EVAL/CONFIG-SENSITIVITY/）:
  kev08          kev.serve /v1/systemone（噪声底座/双精度）
  b-q8-greedy / c-q8-greedy / c-q8-5sam / h-q8-greedy / h-bf16gguf-greedy  llama.cpp GPU
  e1-nanojev-fp32 / mb-cpu
用法: run_uniform.py <method> <development|test> [--limit N] [--tag T] [--outdir D] [--kev-base URL]
"""
import argparse, json, math, os, re, sys, time, urllib.request
from pathlib import Path

HERE = Path(__file__).parent
ORACLE = Path('/home/xxl/MySecAgent/lab/experiments/oracle')
SUITE = ORACLE / 'suites/oracle-v3'
sys.path.insert(0, str(ORACLE / 'code/suite'))
from pack_suite import (TACTIC_CRITERIA, TACTIC_INSTR, URGENT_INSTR, SEV_INSTR,
                        SEV_CRIT, ACTION_CRITERIA, ACTION_INSTR)

SEV = ['low', 'medium', 'high', 'critical']
TACTICS = list(TACTIC_CRITERIA)
ACTIONS = list(ACTION_CRITERIA)
GEN_SYS = 'You are a security alert triage assistant. Reply with ONLY a JSON object, nothing else.'

# 端口约定（18483-18489 逐行分配）
URL_MINICPM_VLLM = 'http://127.0.0.1:18485/v1/chat/completions'
URL_SPARK_VLLM = 'http://127.0.0.1:18486/v1/chat/completions'
BASE_MINICPM_VLLM = 'http://127.0.0.1:18485/v1'
URL_MINICPM_LLAMA = 'http://127.0.0.1:18481/v1/chat/completions'
URL_SPARK_LLAMA = 'http://127.0.0.1:18487/v1/chat/completions'

TASKS = ('tactic', 'urgent', 'severity', 'action')


def load_split(split, limit=None):
    recs = [json.loads(l) for l in open(f'{SUITE}/{split}.jsonl')]
    return recs[:limit] if limit else recs


def out_path(method, split, tag, outdir):
    d = Path(outdir) if outdir else HERE
    suffix = f'_{tag}' if tag else ''
    return d / f'results_{method}{suffix}_{split}.jsonl'


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
        'label': {k: labels.get(k) for k in TASKS},
        'pred': pred, 'probs': probs,
        'latency_ms': round(lat_ms, 1) if lat_ms is not None else None,
    }
    if extra:
        row.update(extra)
    fh.write(json.dumps(row, ensure_ascii=False) + '\n')
    fh.flush()


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


# ==================== E2 laya GPU bf16（模板：GPU-LATENCY Laya 类，LAYA_GPU_FP32=0 保 bf16 autocast） ====================

def run_e2_laya(recs, split, tag, outdir):
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ.setdefault('LAYA_GPU_FP32', '0')
    sys.path.insert(0, '/home/xxl/Mylocllm')
    from laya import Agent
    agent = Agent('/home/xxl/Mylocllm/laya-family/laya-base', device='cuda', token=None, subfolder=None)
    out = out_path('e2-laya', split, tag, outdir)
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
                a = r.get('answers') or r
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
                print(f'e2-laya/{split}: {n + err} ({time.time() - t0all:.0f}s)', flush=True)
    print(f'e2-laya/{split}: +{n} ok, {err} err -> {out}', flush=True)


# ==================== E1 NanoJev GPU bf16（模板：GPU-LATENCY NanoJev 类，dtype=bfloat16） ====================

class _NanoJevCore:
    def load(self, dtype):
        sys.path.insert(0, '/home/xxl/Mylocllm/NanoJev/scripts')
        os.environ.update(TRANSFORMERS_OFFLINE='1', HF_HUB_OFFLINE='1', HF_HUB_DISABLE_TELEMETRY='1')
        import torch
        from safetensors.torch import load_file
        from transformers import AutoConfig, AutoModel, AutoTokenizer
        import predict_toy_decisions as ptd
        self.torch = torch
        self.ptd = ptd
        CKPT = '/home/xxl/Mylocllm/NanoJev/checkpoints/NanoJev-unified'
        ck = Path(CKPT)
        run_config = json.loads((ck / 'config.json').read_text())
        tokenizer = AutoTokenizer.from_pretrained(str(ck / 'tokenizer'), local_files_only=True, trust_remote_code=False)
        if tokenizer.pad_token_id is None:
            tokenizer.pad_token = tokenizer.eos_token
        body_config = AutoConfig.from_pretrained(str(ck / 'backbone_config'), local_files_only=True, trust_remote_code=False)
        body_config.use_cache = False
        self.limit = run_config.get('max_length', 512)
        body = AutoModel.from_config(body_config, attn_implementation='sdpa', trust_remote_code=False).float()
        DecisionModel = ptd.load_decision_model_class()
        model = DecisionModel(body, run_config['set_head'])
        weights = load_file(str(ck / 'best.safetensors'), device='cpu')
        model.load_state_dict(weights, strict=True)
        del weights
        self.model = model.to(device='cuda', dtype=dtype).eval()
        self.tokenizer = tokenizer

    def qs(self):
        return {
            'tactic': {'type': 'choice', 'instructions': TACTIC_INSTR, 'criteria': dict(TACTIC_CRITERIA)},
            'urgent': {'type': 'boolean', 'instructions': URGENT_INSTR['question'],
                       'criteria': {'true': 'Act now: ongoing or imminent compromise',
                                    'false': 'Routine: can wait for normal triage'}},
            'severity': {'type': 'score', 'instructions': SEV_INSTR['question'], 'criteria': list(SEV_CRIT)},
            'action': {'type': 'choice', 'instructions': ACTION_INSTR, 'criteria': dict(ACTION_CRITERIA)},
        }

    def predict(self, rec):
        torch, ptd = self.torch, self.ptd
        payload = {'states': [{'id': 's0', 'state': rec['state'], 'questions': self.qs()}]}
        states = ptd.validate_request(payload)
        examples = ptd.prepare_examples(payload, self.tokenizer, self.limit)
        outputs = {s['id']: {'id': s['id'], 'answers': {}} for s in states}
        with torch.inference_mode():
            logits, _ = self.model(examples, self.tokenizer.pad_token_id)
            for ex, values in zip(examples, logits):
                k = len(ex['candidate_ids'])
                scores = values[:k].float()
                if not torch.isfinite(scores).all():
                    raise ValueError('模型产生非有限 logits')
                probs = (scores / 1.0).softmax(-1).cpu().tolist()
                outputs[ex['state_id']]['answers'][ex['qid']] = ptd.answer_from_probabilities(ex, probs)
        ans = outputs['s0']['answers']
        return ({
            'tactic': ans['tactic'].get('choice'),
            'urgent': bool(ans['urgent'].get('value')),
            'severity': SEV[min(3, max(0, int(round(ans['severity'].get('score', 0)))))],
            'action': ans['action'].get('choice'),
        }, {'tactic': ans['tactic'].get('probabilities', {}),
            'action': ans['action'].get('probabilities', {})})


def run_e1_nanojev(recs, split, tag, outdir, dtype_name, method_name):
    import torch
    core = _NanoJevCore()
    core.load(torch.bfloat16 if dtype_name == 'bf16' else torch.float32)
    out = out_path(method_name, split, tag, outdir)
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
                pred, probs = core.predict(rec)
                emit(fh, rec, pred, probs, (time.time() - t0) * 1000)
                n += 1
            except Exception as e:
                emit(fh, rec, None, None, (time.time() - t0) * 1000,
                     {'error': f'{type(e).__name__}: {str(e)[:150]}'})
                err += 1
            if (n + err) % 10 == 0:
                print(f'{method_name}/{split}: {n + err} ({time.time() - t0all:.0f}s)', flush=True)
    print(f'{method_name}/{split}: +{n} ok, {err} err -> {out}', flush=True)


# ==================== MB ModernBERT 四头（GPU bf16 / CPU fp32；模板：GPU-LATENCY ModernBERT 类） ====================

B_TACTICS = ['benign', 'reconnaissance', 'initial_access', 'execution', 'persistence',
             'privilege_escalation', 'defense_evasion', 'credential_access',
             'discovery', 'command_and_control', 'exfiltration']
B_SEV = ['low', 'medium', 'high', 'critical']
B_ACTIONS = ['no_action', 'monitor', 'investigate', 'escalate', 'contain',
             'isolate_host', 'block_ip', 'disable_user', 'reset_credentials', 'quarantine_message']


def run_mb(recs, split, tag, outdir, device_dtype):
    import torch
    from torch import nn
    from transformers import AutoTokenizer, AutoModel
    tok = AutoTokenizer.from_pretrained('answerdotai/ModernBERT-base')

    class MultiHead(nn.Module):
        def __init__(self):
            super().__init__()
            self.enc = AutoModel.from_pretrained('answerdotai/ModernBERT-base')
            self.dropout = nn.Dropout(0.1)
            self.head_t = nn.Linear(768, len(B_TACTICS))
            self.head_u = nn.Linear(768, 2)
            self.head_s = nn.Linear(768, len(B_SEV))
            self.head_a = nn.Linear(768, len(B_ACTIONS))

        def forward(self, ids, mask):
            h = self.enc(input_ids=ids, attention_mask=mask).last_hidden_state[:, 0]
            h = self.dropout(h)
            return self.head_t(h), self.head_u(h), self.head_s(h), self.head_a(h)

    model = MultiHead()
    model.load_state_dict(torch.load(ORACLE / 'EVAL/BATCH2-TRAIN/bert-baseline/bert_baseline.pt',
                                     map_location='cpu', weights_only=True))
    model.eval()
    method = 'mb-bf16' if device_dtype == 'cuda-bf16' else 'mb-cpu'
    dev, dt = ('cuda', torch.bfloat16) if device_dtype == 'cuda-bf16' else ('cpu', torch.float32)
    model = model.to(dev, dt)
    out = out_path(method, split, tag, outdir)
    done = resume(out)
    n = 0
    t0all = time.time()
    with open(out, 'a') as fh:
        for rec in recs:
            rid = rec['_meta']['id']
            if rid in done:
                continue
            enc = tok(rec['state'], truncation=True, max_length=1024,
                      padding='max_length', return_tensors='pt')
            t0 = time.time()
            with torch.no_grad():
                lt, lu, ls, la = model(enc['input_ids'].to(dev), enc['attention_mask'].to(dev))
            lt, lu, ls, la = lt.float(), lu.float(), ls.float(), la.float()
            pt = torch.softmax(lt[0], -1).tolist()
            pu = torch.softmax(lu[0], -1).tolist()
            ps = torch.softmax(ls[0], -1).tolist()
            pred = {
                'tactic': B_TACTICS[int(lt[0].argmax())],
                'urgent': bool(int(lu[0].argmax())),
                'severity': B_SEV[int(ls[0].argmax())],
                'action': B_ACTIONS[int(la[0].argmax())],
            }
            probs = {'tactic': dict(zip(B_TACTICS, pt)),
                     'urgent': {'false': pu[0], 'true': pu[1]},
                     'severity': dict(zip(B_SEV, ps))}
            emit(fh, rec, pred, probs, (time.time() - t0) * 1000)
            n += 1
            if n % 10 == 0:
                print(f'{method}/{split}: {n} ({time.time() - t0all:.0f}s)', flush=True)
    print(f'{method}/{split}: +{n} ok -> {out}', flush=True)


# ==================== V Verdict-151M（模板：eval_verdict151.py，补逐窗延迟） ====================

def run_verdict(recs, split, tag, outdir):
    from rlcd import DecisionEngine, Choice, Option, Score, Level
    engine = DecisionEngine()
    SEV_LV = [("low", "benign or informational, no response needed", 0.0),
              ("medium", "suspicious, needs investigation soon", 1.0),
              ("high", "likely incident, respond promptly", 2.0),
              ("critical", "active breach, immediate response", 3.0)]
    SEV_KEYS = [s[0] for s in SEV_LV]
    out = out_path('verdict', split, tag, outdir)
    done = resume(out)
    n = err = 0
    with open(out, 'a') as fh:
        for rec in recs:
            rid = rec['_meta']['id']
            if rid in done:
                continue
            st = rec['state']
            state_text = "\n".join(st["raw_log_lines"]) if isinstance(st, dict) else str(st)
            ch_t = Choice(id="tactic", question="Which MITRE ATT&CK tactic best matches this security alert?",
                          options=[Option(id=t, description=(t.replace("_", " ") + " attack activity") if t != "benign" else "normal business or administrative behavior") for t in TACTICS])
            ch_u = Choice(id="urgent", question="Does this alert require immediate human intervention?",
                          options=[Option(id="true", description="yes, urgent intervention needed"),
                                   Option(id="false", description="no, not urgent")])
            sc_s = Score(id="severity", question="Rate the severity of this security alert",
                         levels=[Level(id=sid, description=d, value=v) for sid, d, v in SEV_LV])
            ch_a = Choice(id="action", question="What is the best immediate response action?",
                          options=[Option(id=a, description=a.replace("_", " ")) for a in ACTIONS])
            t0 = time.time()
            try:
                res = engine.evaluate(context=state_text, queries=[ch_t, ch_u, sc_s, ch_a])
                got = {rr.id: rr for rr in res.results}
                sv = getattr(got["severity"], "selected_value", None)
                pred = {
                    'tactic': got["tactic"].selected_id,
                    'urgent': got["urgent"].selected_id == "true",
                    'severity': SEV_KEYS[min(int(round(sv)), 3)] if sv is not None else 'low',
                    'action': got["action"].selected_id,
                }
                conf = {k: getattr(got[k], "selected_probability", None) for k in got}
                emit(fh, rec, pred, conf, (time.time() - t0) * 1000)
                n += 1
            except Exception as e:
                emit(fh, rec, None, None, (time.time() - t0) * 1000, {'error': f'{type(e).__name__}: {str(e)[:120]}'})
                err += 1
            if (n + err) % 20 == 0:
                print(f'verdict/{split}: {n + err}', flush=True)
    print(f'verdict/{split}: +{n} ok, {err} err -> {out}', flush=True)


# ==================== B/H 生成式 greedy（vLLM bf16 或 llama.cpp；模板：run_gen_local，temp=0） ====================

def chat_greedy(url, model, prompt, max_tokens=300):
    body = {'model': model, 'messages': [
        {'role': 'system', 'content': GEN_SYS},
        {'role': 'user', 'content': prompt}], 'max_tokens': max_tokens, 'temperature': 0,
        'chat_template_kwargs': {'enable_thinking': False}}
    d, dt = http_json(url, body)
    msg = d['choices'][0]['message']
    return (msg.get('content') or msg.get('reasoning_content') or ''), dt


def run_gen_greedy(method, url, model, recs, split, tag, outdir):
    out = out_path(method, split, tag, outdir)
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
                    content, dt = chat_greedy(url, model, gen_prompt(rec))
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
                print(f'{method}/{split}: {n + err} done ({el:.0f}s, ~{el / (n + err):.2f}s/win, invalid={n_invalid})', flush=True)
    print(f'{method}/{split}: +{n} ok ({n_invalid} invalid-json), {err} err -> {out}', flush=True)


# ==================== C 行 logprobs 打分（方案 A.2 新协议；机制模板：G 行 prefill_score） ====================

def run_c_logprobs(recs, split, tag, outdir):
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained('/disk1/models/xxl-model/uniform-bf16/MiniCPM5-2B', trust_remote_code=True)

    def prefill_sumlogp(prefix, cand):
        """ΣlogP(ci tokens)：/completions temp0 + logprobs + prompt_logprobs + max_tokens 1。
        取 prompt_logprobs 中命中候选 token id 的最后 want 个（G 行机制，防前文同词干扰）。"""
        full = prefix + cand
        body = {'model': 'minicpm', 'prompt': full, 'max_tokens': 1,
                'temperature': 0, 'logprobs': 1, 'prompt_logprobs': 1}
        d, _ = http_json(f'{BASE_MINICPM_VLLM}/completions', body)
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
        if len(cand_toks) < want:
            return None  # 候选 token 边界异常，记 error
        return sum(cand_toks)

    def score(state_text, cand_list, question):
        prefix = f"""Security log analysis. Answer with EXACTLY one of [{','.join(cand_list)}], nothing else.

{state_text}

Answer: """
        scores = {}
        for c in cand_list:
            s = prefill_sumlogp(prefix, c)
            if s is None:
                raise ValueError(f'logprob 边界异常: {c!r}')
            scores[c] = s
        mx = max(scores.values())
        exps = {c: math.exp(v - mx) for c, v in scores.items()}
        tot = sum(exps.values())
        return {c: e / tot for c, e in exps.items()}

    out = out_path('c-logprobs', split, tag, outdir)
    done = resume(out)
    n = err = 0
    t0all = time.time()
    with open(out, 'a') as fh:
        for rec in recs:
            rid = rec['_meta']['id']
            if rid in done:
                continue
            st = rec['state']
            t0 = time.time()
            try:
                dists = {}
                dists['tactic'] = score(st, TACTICS, 'tactic')
                dists['severity'] = score(st, SEV, 'severity')
                dists['action'] = score(st, ACTIONS, 'action')
                dists['urgent'] = score(st, ['true', 'false'], 'urgent')
                # 分布合法性：有限、和≈1（试点 gate 同款检查）
                for task, dd in dists.items():
                    if not all(math.isfinite(v) and v >= 0 for v in dd.values()) or not math.isclose(sum(dd.values()), 1.0, rel_tol=1e-6, abs_tol=1e-4):
                        raise ValueError(f'分布非法: {task} sum={sum(dd.values()):.6f}')
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
                print(f'c-logprobs/{split}: {n} done ({(time.time() - t0all):.0f}s)', flush=True)
    print(f'c-logprobs/{split}: +{n} ok, {err} err -> {out}', flush=True)


# ==================== C 行 5 采样计数（llama.cpp；模板：run_minicpm_opt，温度可配） ====================

def run_c_opt(recs, split, tag, outdir, temperature, nsample, url, method):
    out = out_path(method, split, tag, outdir)
    done = resume(out)
    n = err = 0
    t0all = time.time()

    def ask(prompt, max_tokens):
        body = {'model': 'minicpm', 'messages': [
            {'role': 'system', 'content': GEN_SYS},
            {'role': 'user', 'content': prompt}], 'max_tokens': max_tokens, 'temperature': temperature,
            'chat_template_kwargs': {'enable_thinking': False}}
        d, dt = http_json(url, body)
        msg = d['choices'][0]['message']
        return (msg.get('content') or msg.get('reasoning_content') or ''), dt

    with open(out, 'a') as fh:
        for rec in recs:
            rid = rec['_meta']['id']
            if rid in done:
                continue
            t0 = time.time()
            try:
                dists = {}
                for task, cands in [('tactic', TACTICS), ('severity', SEV), ('action', ACTIONS)]:
                    cand_list = ','.join(cands)
                    prompt = f"""Security log analysis. Answer with EXACTLY one of [{cand_list}], nothing else.

{rec['state']}

Answer:"""
                    counts = {c: 0 for c in cands}
                    for _ in range(nsample):
                        try:
                            content, _ = ask(prompt, 12)
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
                for _ in range(nsample):
                    try:
                        content, _ = ask(uprompt, 6)
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
                print(f'{method}/{split}: {n} done ({el:.0f}s, ~{el / n:.1f}s/win)', flush=True)
    print(f'{method}/{split}: +{n} ok, {err} err -> {out}', flush=True)


# ==================== kev08 HTTP（噪声底座/双精度；模板：run_kev08_zs） ====================

def run_kev08(recs, split, tag, outdir, base):
    out = out_path('kev08', split, tag, outdir)
    done = resume(out)
    n = err = 0

    def decide(state, questions):
        body = json.dumps({'state': state, 'model': 'kev-latest', 'questions': questions}).encode()
        req = urllib.request.Request(f'{base}/v1/systemone', body, {'Content-Type': 'application/json'})
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
                print(f'kev08/{split}: {n} done', flush=True)
    print(f'kev08/{split}: +{n} ok, {err} err -> {out}', flush=True)


# ==================== F1/F2 云 API temp 0（模板：v3_baseline_runner run_gen + api_cfg） ====================

def api_cfg(which):
    import yaml
    creds = yaml.safe_load(open(os.path.expanduser('~/.dsh/.credentials.yaml')))['refs']
    if which == 'glm':
        return {'key': creds['ZAI_CODING_CN_API_KEY'],
                'url': 'https://open.bigmodel.cn/api/coding/paas/v4/chat/completions',
                'model': 'glm-5.3', 'glm': True}
    return {'key': creds['DEEPSEEK_API_KEY'],
            'url': 'https://api.deepseek.com/chat/completions', 'model': 'deepseek-chat'}


def run_cloud(which, method, recs, split, tag, outdir):
    prov = api_cfg(which)

    def chat(prompt):
        payload = {'model': prov['model'], 'messages': [
            {'role': 'system', 'content': GEN_SYS},
            {'role': 'user', 'content': prompt}], 'max_tokens': 300, 'temperature': 0}
        if prov.get('glm'):
            payload['thinking'] = {'type': 'disabled'}
        req = urllib.request.Request(prov['url'], json.dumps(payload).encode(),
                                     {'Content-Type': 'application/json', 'Authorization': f"Bearer {prov['key']}"})
        t0 = time.time()
        with urllib.request.urlopen(req, timeout=120) as r:
            d = json.loads(r.read())
        msg = d['choices'][0]['message']
        return (msg.get('content') or msg.get('reasoning_content') or ''), time.time() - t0

    out = out_path(method, split, tag, outdir)
    done = resume(out)
    n = err = n_invalid = 0
    with open(out, 'a') as fh:
        for rec in recs:
            rid = rec['_meta']['id']
            if rid in done:
                continue
            last = None
            for attempt in range(3):
                try:
                    content, dt = chat(gen_prompt(rec))
                    j = parse_json(content) or {}
                    tac, urg = j.get('tactic'), j.get('urgent')
                    sev, act = j.get('severity'), j.get('action')
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
                print(f'{method}/{split}: {n + err} done (invalid={n_invalid})', flush=True)
    print(f'{method}/{split}: +{n} ok ({n_invalid} invalid-json), {err} err -> {out}', flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('method')
    ap.add_argument('split', choices=['development', 'test'])
    ap.add_argument('--limit', type=int, default=None)
    ap.add_argument('--tag', default=None)
    ap.add_argument('--outdir', default=None)
    ap.add_argument('--kev-base', default='http://127.0.0.1:18428')
    a = ap.parse_args()
    recs = load_split(a.split, a.limit)
    m = a.method
    if m == 'e2-laya':
        run_e2_laya(recs, a.split, a.tag, a.outdir)
    elif m == 'e1-nanojev':
        run_e1_nanojev(recs, a.split, a.tag, a.outdir, 'bf16', 'e1-nanojev')
    elif m == 'e1-nanojev-fp32':
        run_e1_nanojev(recs, a.split, a.tag, a.outdir, 'fp32', 'e1-nanojev-fp32')
    elif m == 'mb-bf16':
        run_mb(recs, a.split, a.tag, a.outdir, 'cuda-bf16')
    elif m == 'mb-cpu':
        run_mb(recs, a.split, a.tag, a.outdir, 'cpu-fp32')
    elif m == 'verdict':
        run_verdict(recs, a.split, a.tag, a.outdir)
    elif m == 'c-logprobs':
        run_c_logprobs(recs, a.split, a.tag, a.outdir)
    elif m == 'b-gen':
        run_gen_greedy('b-gen', URL_MINICPM_VLLM, 'minicpm', recs, a.split, a.tag, a.outdir)
    elif m == 'h-gen':
        run_gen_greedy('h-gen', URL_SPARK_VLLM, 'spark25', recs, a.split, a.tag, a.outdir)
    elif m == 'b-q8-greedy':
        run_gen_greedy('b-q8-greedy', URL_MINICPM_LLAMA, 'minicpm', recs, a.split, a.tag, a.outdir)
    elif m == 'h-q8-greedy':
        run_gen_greedy('h-q8-greedy', URL_SPARK_LLAMA, 'spark25', recs, a.split, a.tag, a.outdir)
    elif m == 'h-bf16gguf-greedy':
        run_gen_greedy('h-bf16gguf-greedy', URL_SPARK_LLAMA, 'spark25', recs, a.split, a.tag, a.outdir)
    elif m == 'c-q8-greedy':
        run_c_opt(recs, a.split, a.tag, a.outdir, 0.0, 1, URL_MINICPM_LLAMA, 'c-q8-greedy')
    elif m == 'c-q8-5sam':
        run_c_opt(recs, a.split, a.tag, a.outdir, 0.1, 5, URL_MINICPM_LLAMA, 'c-q8-5sam')
    elif m == 'kev08':
        run_kev08(recs, a.split, a.tag, a.outdir, a.kev_base)
    elif m in ('f-glm', 'f-dsk'):
        run_cloud('glm' if m == 'f-glm' else 'dsk',
                  'f1-glm' if m == 'f-glm' else 'f2-dsk', recs, a.split, a.tag, a.outdir)
    else:
        ap.error(f'unknown method {m}')


if __name__ == '__main__':
    main()
