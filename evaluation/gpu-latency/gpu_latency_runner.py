#!/usr/bin/env python3
"""gpu_latency_runner.py — GPU-LATENCY：tab:main 9 个本地行 GPU 推理延迟重测

背景：论文 tab:main 延迟列（P50）此前为 CPU 推理口径。用户要求本地模型统一 GPU 推理重测延迟。
精度格不动：本 runner 仅重测延迟；每模型先做 30 窗（dev+test 混合）预测一致性抽检。

方法（9 行，A rules 除外）：
  HF 原生（GPU 同精度，pred 必须逐窗一致，不一致即停该模型）：
    nanojev-zs  E1  NanoJev-unified 0.6B, fp32（同 CPU 轮精度）
    laya-zs     E2  laya 421M（laya-family/laya-base 同 sha256 副本）
    modernbert      ModernBERT-base 四头（EVAL/BATCH2-TRAIN/bert-baseline, dev-only）
    kev08-zs    I1  jaredpalmer/kev-0.8b via kev.serve bf16（GPU）
    kev4b-zs    I2  jaredpalmer/kev-4b via kev.serve bf16（GPU）
  llama.cpp Q8（必须 CUDA build + 同 Q8 权重，不得换 vLLM bf16）：
    minicpm-gen B / minicpm-opt C  MiniCPM5-2B-Q8_0.gguf
    spark-gen   H  Spark-X2.5-4B-Q8_0.gguf
  vLLM bf16（原轮即 GPU vLLM，本轮 GPU1 复测统一口径）：
    g2v6-qwen   G   /disk1/models/Qwen3-8B-SecAgent

协议与模板逐字复用 baseline_unify_runner.py / v3_baseline_runner.py / bert_calib_eval.py，
仅换推理设备与输出路径。行 schema 与原 results 完全一致（evaluate.py 可直接算）。

用法：
  <python> gpu_latency_runner.py consistency <method>   # 30 窗抽检（seed 42）
  <python> gpu_latency_runner.py full <method> [split]  # 全量重测（默认 test；modernbert 为 development）
  <python> gpu_latency_runner.py sample                 # 重生成抽样 id（幂等，seed 42）
"""
import argparse, json, math, os, re, sys, time, urllib.request, random
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

# GPU llama.cpp CUDA 端点（llama.cpp-spark build-cuda，同 Q8 权重，-ngl 99 全卸载 GPU1）
SPARK_URL = os.environ.get('GLR_SPARK_URL', 'http://127.0.0.1:18480/v1/chat/completions')
MINICPM_URL = os.environ.get('GLR_MINICPM_URL', 'http://127.0.0.1:18481/v1/chat/completions')
QWEN_BASE = os.environ.get('GLR_QWEN_BASE', 'http://127.0.0.1:18483/v1')
KEV08_BASE = os.environ.get('GLR_KEV08_BASE', 'http://127.0.0.1:18428')
KEV4B_BASE = os.environ.get('GLR_KEV4B_BASE', 'http://127.0.0.1:18429')
GEN_SYS = 'You are a security alert triage assistant. Reply with ONLY a JSON object, nothing else.'

RES = HERE / 'results'
CONS = HERE / 'consistency'
COLD = HERE / 'coldstart'

# 旧 CPU（或既有）results 位置 —— 一致性比对基准，只读
OLD = {
    'nanojev-zs': {'test': ORACLE / 'EVAL/BASELINE-UNIFY/results_nanojev-zs_test.jsonl'},
    'laya-zs': {'test': ORACLE / 'EVAL/BASELINE-UNIFY/results_laya-zs_test.jsonl',
                'development': ORACLE / 'EVAL/BASELINE-UNIFY/dev-supplement/results_laya-zs_development.jsonl'},
    'minicpm-gen': {'test': ORACLE / 'EVAL/BASELINE-UNIFY/results_minicpm-gen_test.jsonl',
                    'development': ORACLE / 'EVAL/BASELINE-UNIFY/dev-supplement/results_minicpm-gen_development.jsonl'},
    'minicpm-opt': {'test': ORACLE / 'EVAL/BASELINE-UNIFY/results_minicpm-opt_test.jsonl',
                    'development': ORACLE / 'EVAL/BASELINE-UNIFY/dev-supplement/results_minicpm-opt_development.jsonl'},
    'spark-gen': {'test': ORACLE / 'EVAL/BASELINE-UNIFY/results_spark-gen_test.jsonl',
                  'development': ORACLE / 'EVAL/BASELINE-UNIFY/dev-supplement/results_spark-gen_development.jsonl'},
    'g2v6-qwen': {'test': ORACLE / 'EVAL/V3-TEST-BASELINE/results_g2v6-qwen_test.jsonl',
                  'development': ORACLE / 'EVAL/BASELINE-UNIFY/dev-supplement/results_g2v6-qwen_development.jsonl'},
    'kev08-zs': {'test': ORACLE / 'EVAL/V3-TEST-BASELINE/results_kev08-zs_test.jsonl'},
    'kev4b-zs': {'test': ORACLE / 'EVAL/V3-TEST-BASELINE/results_kev4b-zs_test.jsonl'},
    'modernbert': {'development': ORACLE / 'EVAL/BERT-CALIB/logits_development.json'},
}
HF_STRICT = {'nanojev-zs', 'laya-zs', 'modernbert', 'kev08-zs', 'kev4b-zs'}  # 红线①：不一致即停
DEFAULT_SPLIT = {'modernbert': 'development'}

TASKS = ('tactic', 'urgent', 'severity', 'action')


def proc_start_ts():
    """本进程启动的墙钟时间（用于 in-process 冷启动计时）。"""
    with open(f'/proc/self/stat') as f:
        parts = f.read().split()
    return int(parts[21]) / os.sysconf('SC_CLK_TCK')


def load_split(split):
    return [json.loads(l) for l in open(f'{SUITE}/{split}.jsonl')]


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


def chat_local(url, model, prompt, max_tokens=300):
    body = {'model': model, 'messages': [
        {'role': 'system', 'content': GEN_SYS},
        {'role': 'user', 'content': prompt}], 'max_tokens': max_tokens, 'temperature': 0.1,
        'chat_template_kwargs': {'enable_thinking': False},
        'cache_prompt': False}
    d, dt = http_json(url, body)
    msg = d['choices'][0]['message']
    return (msg.get('content') or msg.get('reasoning_content') or ''), dt


# ==================== 模型装载（lazy import，进程内冷启动计时包裹） ====================

class NanoJev:
    name = 'nanojev-zs'
    env_note = 'spark2_5 python, GPU fp32（同 CPU 轮精度）'

    def load(self):
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
        self.model = model.to(device='cuda', dtype=torch.float32).eval()
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
            # 与 CPU 轮完全一致：同窗 4 问一次性前向（跨窗不合并）
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
        }, {'tactic': ans['tactic'].get('probabilities', {}), 'action': ans['action'].get('probabilities', {})})


class Laya:
    name = 'laya-zs'
    env_note = 'spark2_5 python, Agent device=cuda（laya-family/laya-base 同 sha256 副本）'

    def load(self):
        os.environ['HF_HUB_OFFLINE'] = '1'
        sys.path.insert(0, '/home/xxl/Mylocllm')
        import torch
        from laya import Agent
        self.agent = Agent('/home/xxl/Mylocllm/laya-family/laya-base', device='cuda', token=None, subfolder=None)
        # 红线①同精度：checkpoint cfg amp_dtype=bf16 会使 CUDA 走 bf16 autocast（CPU 轮为 fp32）。
        # 显式覆盖 dtype=fp32（autocast(fp32, enabled=True) 为 fp32 执行），使 GPU 与 CPU 同精度。
        if os.environ.get('LAYA_GPU_FP32', '1') == '1':
            self.agent.dtype = torch.float32

    def predict(self, rec):
        questions = {
            'tactic': {'type': 'choice', 'instructions': TACTIC_INSTR, 'criteria': dict(TACTIC_CRITERIA)},
            'urgent': {'type': 'noul', 'instructions': URGENT_INSTR['question']},
            'severity': {'type': 'choice', 'instructions': SEV_INSTR['question'],
                         'criteria': {sv: SEV_CRIT[i] for i, sv in enumerate(SEV)}},
            'action': {'type': 'choice', 'instructions': ACTION_INSTR, 'criteria': dict(ACTION_CRITERIA)},
        }
        r = self.agent.system_one(rec['state'], questions)
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
        return pred, {'tactic': tac_p, 'urgent': a['urgent'].get('noul'), 'severity': sev_p, 'action': act_p}


# ModernBERT 训练时的标签空间（与 bert_calib_eval.py / train_bert_baseline.py WinDS 完全一致；
# 注意 action 为 10 类，与 suite 的 8-action 约定不同；tactic 顺序为其训练顺序）
B_TACTICS = ['benign', 'reconnaissance', 'initial_access', 'execution', 'persistence',
             'privilege_escalation', 'defense_evasion', 'credential_access',
             'discovery', 'command_and_control', 'exfiltration']
B_SEV = ['low', 'medium', 'high', 'critical']
B_ACTIONS = ['no_action', 'monitor', 'investigate', 'escalate', 'contain',
             'isolate_host', 'block_ip', 'disable_user', 'reset_credentials', 'quarantine_message']


class ModernBERT:
    name = 'modernbert'
    env_note = 'kev-repo/.venv python, GPU（bert_baseline.pt；dev-only，tokenize 同 bert_calib_eval：1024 截断）'

    def load(self):
        import torch
        from torch import nn
        from transformers import AutoTokenizer, AutoModel
        self.torch = torch
        self.tok = AutoTokenizer.from_pretrained('answerdotai/ModernBERT-base')

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
        assert torch.cuda.is_available(), 'ModernBERT 需要 GPU'
        self.model = model.to('cuda')

    def predict(self, rec):
        torch = self.torch
        enc = self.tok(rec['state'], truncation=True, max_length=1024,
                       padding='max_length', return_tensors='pt')
        with torch.no_grad():
            lt, lu, ls, la = self.model(enc['input_ids'].to('cuda'), enc['attention_mask'].to('cuda'))
        # 注意：eval 时 model.eval() 已关 dropout；heads 与 bert_calib_eval 相同
        return ({
            'tactic': B_TACTICS[lt[0].argmax().item()],
            'urgent': bool(lu[0].argmax().item()),
            'severity': B_SEV[ls[0].argmax().item()],
            'action': B_ACTIONS[la[0].argmax().item()],
        }, None)


class Kev:
    def __init__(self, name, base):
        self.name = name
        self.base = base
        self.env_note = f'kev.serve bf16 GPU @ {base}'

    def load(self):
        pass  # HTTP 服务，由外部启动

    def predict(self, rec):
        qs = {
            'tactic': {'type': 'choice', 'instructions': TACTIC_INSTR, 'criteria': TACTIC_CRITERIA},
            'urgent': {'type': 'noul', 'instructions': URGENT_INSTR['question']},
            'severity': {'type': 'score', 'instructions': SEV_INSTR['question'], 'criteria': SEV_CRIT},
            'action': {'type': 'choice', 'instructions': ACTION_INSTR, 'criteria': ACTION_CRITERIA},
        }
        body = json.dumps({'state': rec['state'], 'model': 'kev-latest', 'questions': qs}).encode()
        req = urllib.request.Request(f'{self.base}/v1/systemone', body, {'Content-Type': 'application/json'})
        t0 = time.time()
        with urllib.request.urlopen(req, timeout=120) as r:
            d = json.loads(r.read())
        dt = d.get('latency_ms', (time.time() - t0) * 1000)
        ans = d['answers']
        sev_score = ans['severity'].get('score', 0)
        return ({
            'tactic': ans['tactic'].get('choice'),
            'urgent': ans['urgent'].get('noul', 0) >= 0.5,
            'severity': SEV[min(3, max(0, int(round(sev_score))))],
            'action': ans['action'].get('choice'),
        }, {
            'tactic': ans['tactic'].get('probabilities', {}),
            'action': ans['action'].get('probabilities', {}),
        }, dt)


class G2v6Qwen:
    name = 'g2v6-qwen'
    env_note = 'vLLM 0.28.0 bf16 GPU @ GLR_QWEN_BASE（prefill+few-shot 打分，同 v3_baseline_runner run_g2v6）'

    def load(self):
        from transformers import AutoTokenizer
        self.tok = AutoTokenizer.from_pretrained('/disk1/models/Qwen3-8B-SecAgent', trust_remote_code=True)

    def prefill_score(self, prefix, cand):
        full = prefix + cand
        body = {'model': 'qwen3-8b', 'prompt': full, 'max_tokens': 1,
                'temperature': 0, 'logprobs': 1, 'prompt_logprobs': 1}
        d, _ = http_json(f'{QWEN_BASE}/completions', body, timeout=300)
        ch = d['choices'][0]
        plp = ch.get('prompt_logprobs') or []
        cand_ids = set(self.tok.encode(' ' + cand, add_special_tokens=False) + self.tok.encode(cand, add_special_tokens=False))
        want = len(self.tok.encode(' ' + cand, add_special_tokens=False))
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

    def predict(self, rec):
        st = rec['state']

        def score_candidates(state_text, question, candidates):
            prefix = f"""{self.FEWSHOT}Now analyze:
{state_text}

Question: {question}
Answer: """
            scores = {c: self.prefill_score(prefix, c) for c in candidates}
            mx = max(scores.values())
            exps = {c: math.exp(v - mx) for c, v in scores.items()}
            tot = sum(exps.values())
            return {c: e / tot for c, e in exps.items()}

        dists = {}
        for task, cands, q in [
                ('tactic', TACTICS, TACTIC_INSTR),
                ('severity', SEV, SEV_INSTR['question']),
                ('action', ACTIONS, ACTION_INSTR)]:
            dists[task] = score_candidates(st, q, cands)
        dists['urgent'] = score_candidates(st, URGENT_INSTR['question'], ['true', 'false'])
        pred = {'tactic': max(dists['tactic'], key=dists['tactic'].get),
                'urgent': dists['urgent']['true'] >= 0.5,
                'severity': max(dists['severity'], key=dists['severity'].get),
                'action': max(dists['action'], key=dists['action'].get)}
        return pred, dists


class GenLocal:
    """B/H 生成式：llama.cpp CUDA build（同 Q8 权重）。"""

    def __init__(self, name, url, model_alias):
        self.name = name
        self.url = url
        self.alias = model_alias
        self.env_note = f'llama.cpp CUDA build Q8 @ {url}'

    def load(self):
        pass

    def predict(self, rec):
        content, dt = chat_local(self.url, self.alias, gen_prompt(rec))
        j = parse_json(content) or {}
        tac, urg = norm(j.get('tactic')), j.get('urgent')
        if isinstance(urg, str):
            urg = urg.strip().lower() == 'true'
        sev, act = norm(j.get('severity')), norm(j.get('action'))
        valid = tac in TACTIC_CRITERIA and sev in SEV and act in ACTION_CRITERIA and isinstance(urg, bool)
        pred = {'tactic': tac if valid else None, 'urgent': urg if valid else None,
                'severity': sev if valid else None, 'action': act if valid else None}
        return pred, None, dt * 1000, {'valid': valid, 'raw': content[:150] if not valid else ''}


class MiniCPMOpt:
    """C option-scored：每任务 5 次温度采样计数（同 baseline_unify_runner.run_minicpm_opt）。"""
    name = 'minicpm-opt'

    def __init__(self, url):
        self.url = url
        self.env_note = f'llama.cpp CUDA build Q8 @ {url}（20 问/窗）'

    def load(self):
        pass

    def predict(self, rec):
        dists = {}
        for task, cands in [('tactic', TACTICS), ('severity', SEV), ('action', ACTIONS)]:
            cand_list = ','.join(cands)
            prompt = f"""Security log analysis. Answer with EXACTLY one of [{cand_list}], nothing else.

{rec['state']}

Answer:"""
            counts = {c: 0 for c in cands}
            for _ in range(5):
                try:
                    content, _ = chat_local(self.url, 'minicpm', prompt, max_tokens=12)
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
                content, _ = chat_local(self.url, 'minicpm', uprompt, max_tokens=6)
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
        return pred, dists


MODELS = {
    'nanojev-zs': NanoJev,
    'laya-zs': Laya,
    'modernbert': ModernBERT,
    'kev08-zs': lambda: Kev('kev08-zs', KEV08_BASE),
    'kev4b-zs': lambda: Kev('kev4b-zs', KEV4B_BASE),
    'g2v6-qwen': G2v6Qwen,
    'minicpm-gen': lambda: GenLocal('minicpm-gen', MINICPM_URL, 'minicpm'),
    'spark-gen': lambda: GenLocal('spark-gen', SPARK_URL, 'spark25'),
    'minicpm-opt': lambda: MiniCPMOpt(MINICPM_URL),
}


# ==================== 抽样 ====================

def build_sample():
    """seed 42：有 dev+test 双卷旧结果的取 15+15，单卷取 30。落盘 consistency/sampled_ids.json。"""
    rng = random.Random(42)
    out = {}
    for m, splits in OLD.items():
        picks = {}
        avail = {s: p for s, p in splits.items() if p.exists()}
        if len(avail) >= 2:
            dev_ids = [r['_meta']['id'] for r in load_split('development')]
            test_ids = [r['_meta']['id'] for r in load_split('test')]
            picks['development'] = sorted(rng.sample(dev_ids, 15))
            picks['test'] = sorted(rng.sample(test_ids, 15))
        else:
            s = list(avail)[0]
            ids = [r['_meta']['id'] for r in load_split(s)]
            picks[s] = sorted(rng.sample(ids, 30))
        out[m] = picks
    (CONS / 'sampled_ids.json').write_text(json.dumps(out, indent=1, ensure_ascii=False))
    return out


def load_sample():
    f = CONS / 'sampled_ids.json'
    if not f.exists():
        return build_sample()
    return json.loads(f.read_text())


# ==================== 旧预测读取 ====================

def load_old_preds(method):
    out = {}
    for split, path in OLD[method].items():
        if not path.exists():
            continue
        if path.suffix == '.json':  # ModernBERT logits
            d = json.loads(path.read_text())
            import numpy as np
            for i, rid in enumerate(d['ids']):
                pred = {
                    'tactic': B_TACTICS[int(np.argmax(d['logits']['tactic'][i]))],
                    'urgent': bool(int(np.argmax(d['logits']['urgent'][i]))),
                    'severity': B_SEV[int(np.argmax(d['logits']['severity'][i]))],
                    'action': B_ACTIONS[int(np.argmax(d['logits']['action'][i]))],
                }
                out[rid] = {'pred': pred, 'split': split, 'latency_ms': None}
        else:
            for l in open(path):
                r = json.loads(l)
                if r.get('error') or (r.get('pred') or {}).get('tactic') is None:
                    continue
                out[r['id']] = {'pred': r['pred'], 'split': split, 'latency_ms': r.get('latency_ms')}
    return out


# ==================== 主流程 ====================

def run_model(method, split, ids_filter, out_file, record_coldstart=False):
    """通用执行：装载（计冷启动）→ 逐窗推理（计延迟+首窗）。返回统计。"""
    m = MODELS[method]()
    t_proc0 = proc_start_ts()
    t_load0 = time.time()
    m.load()
    t_ready = time.time()
    recs = load_split(split)
    if ids_filter is not None:
        want = set(ids_filter)
        recs = [r for r in recs if r['_meta']['id'] in want]
    n = err = 0
    first_lat = None
    cold = {'method': method, 'split': split, 'env_note': m.env_note,
            'proc_start_ts': t_proc0, 'ready_ts': t_ready,
            'cold_start_ms': round((t_ready - t_proc0) * 1000, 1),
            'load_wall_ms': round((t_ready - t_load0) * 1000, 1)}
    done_ids = set()
    if os.path.exists(out_file):
        for l in open(out_file):
            try:
                r = json.loads(l)
                # 假行(<50ms 的全失败兜底)不算完成,重测
                if not r.get('error') and (r.get('latency_ms') or 0) >= 50:
                    done_ids.add(r['id'])
            except Exception: pass
    print(f'resume: {len(done_ids)} done, skip')
    with open(out_file, 'a') as fh:
        for rec in recs:
            if rec['_meta']['id'] in done_ids:
                continue
            rid = rec['_meta']['id']
            t0 = time.time()
            try:
                res = m.predict(rec)
                if method in ('kev08-zs', 'kev4b-zs') or isinstance(m, Kev):
                    pred, probs, lat = res
                    extra = None
                elif isinstance(m, GenLocal):
                    pred, probs, lat, extra = res
                else:
                    pred, probs = res
                    lat = (time.time() - t0) * 1000
                    extra = None
                emit(fh, rec, pred, probs, lat, extra)
                if first_lat is None:
                    first_lat = lat
                n += 1
            except Exception as e:
                emit(fh, rec, None, None, (time.time() - t0) * 1000,
                     {'error': f'{type(e).__name__}: {str(e)[:150]}'})
                err += 1
            if (n + err) % 20 == 0:
                print(f'{method}/{split}: {n + err} done', flush=True)
    cold['first_window_ms'] = first_lat
    if record_coldstart:
        (COLD / f'{method}_inprocess.json').write_text(json.dumps(cold, indent=1))
    print(f'{method}/{split}: +{n} ok, {err} err -> {out_file}', flush=True)
    return n, err


def do_consistency(method):
    tag = os.environ.get('GLR_TAG', 'gpu')  # gpu=正式 GPU 抽检；cpuctl=CPU-vs-CPU 非确定性对照
    sample = load_sample()[method]
    old = load_old_preds(method)
    mismatch = []
    rows = 0
    detail_path = CONS / f'{method}_gpu_vs_old.jsonl' if tag == 'gpu' else CONS / f'{method}_{tag}_vs_old.jsonl'
    with open(detail_path, 'w') as fh:
        for split, ids in sample.items():
            out_file = CONS / f'{method}_{split}_{tag}.jsonl'
            if out_file.exists():
                out_file.unlink()
            run_model(method, split, ids, out_file)
            for l in open(out_file):
                r = json.loads(l)
                rid = r['id']
                o = old.get(rid)
                rows += 1
                if o is None:
                    rec = {'id': rid, 'split': split, 'status': 'NO_OLD'}
                    mismatch.append(rec)
                elif r.get('error'):
                    rec = {'id': rid, 'split': split, 'status': 'GPU_ERROR', 'error': r['error']}
                    mismatch.append(rec)
                else:
                    diffs = {t: {'gpu': r['pred'].get(t), 'old': o['pred'].get(t)}
                             for t in TASKS if r['pred'].get(t) != o['pred'].get(t)}
                    if diffs:
                        mismatch.append({'id': rid, 'split': split, 'status': 'PRED_MISMATCH', 'diff': diffs})
                        rec = {'id': rid, 'split': split, 'status': 'PRED_MISMATCH', 'diff': diffs}
                    else:
                        rec = {'id': rid, 'split': split, 'status': 'MATCH'}
                fh.write(json.dumps(rec, ensure_ascii=False) + '\n')
    ok = rows - len(mismatch)
    summary = {
        'method': method, 'tag': tag, 'sampled': rows, 'match': ok, 'mismatch': len(mismatch),
        'strict': method in HF_STRICT and tag == 'gpu', 'mismatches': mismatch,
        'detail': str(detail_path),
        'note': 'HF 原生权重 GPU 同精度：不一致即停（红线①）' if method in HF_STRICT and tag == 'gpu'
                else 'llama.cpp Q8 CUDA vs CPU：温度 0.1 采样非逐位确定，报告一致率（红线②：同 Q8 权重 CUDA build）'
                if tag == 'gpu' else '对照实验：原 CPU 二进制重跑同 30 窗 vs 旧 results（量化温度采样固有非确定性）',
    }
    (CONS / f'{method}_consistency.json').write_text(json.dumps(summary, indent=1, ensure_ascii=False))
    if tag != 'gpu':
        (CONS / f'{method}_consistency_{tag}.json').write_text(json.dumps(summary, indent=1, ensure_ascii=False))
    print(json.dumps({k: summary[k] for k in ('method', 'tag', 'sampled', 'match', 'mismatch')}, ensure_ascii=False))
    if tag == 'gpu' and method in HF_STRICT and mismatch:
        print(f'STOP: {method} 一致性抽检未全过（红线①），不进行全量延迟重测', file=sys.stderr)
        sys.exit(3)
    return summary


def do_full(method):
    split = DEFAULT_SPLIT.get(method, 'test')
    out_file = RES / f'results_{method}_{split}_gpu.jsonl'
    # 分块续跑:不再 unlink,run_model 内 done_ids 跳过已完成窗
    return run_model(method, split, None, out_file, record_coldstart=True)


def do_firstwindow(method):
    """HTTP 服务 ready 后的第一窗真实决策延迟（在任何一致性/全量流量之前探测）。"""
    split = DEFAULT_SPLIT.get(method, 'test')
    m = MODELS[method]()
    m.load()
    rec = load_split(split)[0]
    t0 = time.time()
    res = m.predict(rec)
    if method in ('kev08-zs', 'kev4b-zs') or isinstance(m, Kev):
        lat = res[2]
    elif isinstance(m, GenLocal):
        lat = res[2]
    else:
        lat = (time.time() - t0) * 1000
    (COLD / f'{method}_firstwindow.json').write_text(json.dumps(
        {'method': method, 'split': split, 'id': rec['_meta']['id'], 'first_window_ms': lat}, ensure_ascii=False))
    print(json.dumps({'method': method, 'first_window_ms': lat}))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('mode', choices=['consistency', 'full', 'firstwindow', 'sample'])
    ap.add_argument('method', nargs='?', choices=sorted(MODELS))
    a = ap.parse_args()
    if a.mode == 'sample':
        build_sample()
        print('sampled_ids.json written')
        return
    assert a.method
    if a.mode == 'consistency':
        do_consistency(a.method)
    elif a.mode == 'firstwindow':
        do_firstwindow(a.method)
    else:
        do_full(a.method)


if __name__ == '__main__':
    main()
