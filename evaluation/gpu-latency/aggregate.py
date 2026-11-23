#!/usr/bin/env python3
"""aggregate.py — 汇总 GPU-LATENCY：新旧 P50 对照 + 冷启动表 -> summary.json / summary.md

口径：
  P50 = 全窗 latency_ms 中位数（逐窗、无批合并、含模板，与原 runner 计时位置一致）
  旧 CPU 值 = 归档 results 文件按 id 去重后的中位数（与论文精度格同源的文件）
  论文印刷值 = tex tab:main 中的现值（参考列）
  首次可用延迟 = cold_start_ms + first_window_ms
"""
import json, statistics, sys
from pathlib import Path

HERE = Path(__file__).parent
ORACLE = Path('/home/xxl/MySecAgent/lab/experiments/oracle')

PAPER = {  # tab:main 印刷值（ms 字符串）
    'minicpm-gen': '1800', 'minicpm-opt': '1400', 'nanojev-zs': '35000-38000',
    'laya-zs': '113', 'g2v6-qwen': '4600', 'spark-gen': '400', 'kev08-zs': '190',
    'kev4b-zs': '342', 'modernbert': '--',
}
ROW = {  # 论文行号
    'minicpm-gen': 'B', 'minicpm-opt': 'C', 'nanojev-zs': 'E1', 'laya-zs': 'E2',
    'g2v6-qwen': 'G', 'spark-gen': 'H', 'kev08-zs': 'I1', 'kev4b-zs': 'I2', 'modernbert': 'ModernBERT',
}
SPLIT = {'modernbert': 'development'}
INFRA = {
    'nanojev-zs': 'HF fp32 CUDA', 'laya-zs': 'HF CUDA', 'modernbert': 'HF CUDA',
    'kev08-zs': 'kev.serve bf16 CUDA', 'kev4b-zs': 'kev.serve bf16 CUDA',
    'g2v6-qwen': 'vLLM bf16 CUDA', 'minicpm-gen': 'llama.cpp Q8 CUDA',
    'minicpm-opt': 'llama.cpp Q8 CUDA', 'spark-gen': 'llama.cpp Q8 CUDA',
}
OLD_FILES = {
    'nanojev-zs': [('test', ORACLE / 'EVAL/BASELINE-UNIFY/results_nanojev-zs_test.jsonl')],
    'laya-zs': [('test', ORACLE / 'EVAL/BASELINE-UNIFY/results_laya-zs_test.jsonl'),
                ('development', ORACLE / 'EVAL/BASELINE-UNIFY/dev-supplement/results_laya-zs_development.jsonl')],
    'minicpm-gen': [('test', ORACLE / 'EVAL/BASELINE-UNIFY/results_minicpm-gen_test.jsonl')],
    'minicpm-opt': [('test', ORACLE / 'EVAL/BASELINE-UNIFY/results_minicpm-opt_test.jsonl')],
    'spark-gen': [('test', ORACLE / 'EVAL/BASELINE-UNIFY/results_spark-gen_test.jsonl')],
    'g2v6-qwen': [('test', ORACLE / 'EVAL/V3-TEST-BASELINE/results_g2v6-qwen_test.jsonl')],
    'kev08-zs': [('test', ORACLE / 'EVAL/V3-TEST-BASELINE/results_kev08-zs_test.jsonl')],
    'kev4b-zs': [('test', ORACLE / 'EVAL/V3-TEST-BASELINE/results_kev4b-zs_test.jsonl')],
}


def latencies(path, dedupe=True):
    rows, seen = [], set()
    for l in open(path):
        r = json.loads(l)
        if r.get('error') or r.get('latency_ms') is None:
            continue
        if dedupe:
            if r['id'] in seen:
                continue
            seen.add(r['id'])
        rows.append(r['latency_ms'])
    return rows


def q(vals, p):
    if not vals:
        return None
    s = sorted(vals)
    import math
    k = (len(s) - 1) * p
    f, c = math.floor(k), math.ceil(k)
    return s[f] if f == c else s[f] * (c - k) + s[c] * (k - f)


def main():
    out = {}
    for m in ROW:
        split = SPLIT.get(m, 'test')
        rec = {'row': ROW[m], 'infra_gpu': INFRA[m], 'paper_ms': PAPER[m]}
        f = HERE / f'results/results_{m}_{split}_gpu.jsonl'
        if f.exists():
            vals = latencies(f)
            if not vals:
                print('skip(no latencies):', f); continue
            rec.update(n_gpu=len(vals), gpu_p50=round(q(vals, .5), 1),
                       gpu_p95=round(q(vals, .95), 1), gpu_split=split)
        # 冷启动
        cf = HERE / f'coldstart/{m}_inprocess.json'
        hf = HERE / f'coldstart/{m}.json'
        cs = None
        for src in (cf, hf):
            if src.exists():
                d = json.loads(src.read_text())
                cs = d
                break
        if cs:
            fw = None
            ff = HERE / f'coldstart/{m}_firstwindow.json'
            if ff.exists():
                fw = json.loads(ff.read_text())['first_window_ms']
            if fw is None and f.exists():
                for l in open(f):
                    r = json.loads(l)
                    if r.get('latency_ms') is not None:
                        fw = r['latency_ms']
                        break
            cold = cs.get('cold_start_ms')
            rec.update(cold_start_ms=cold, first_window_ms=fw,
                       first_available_ms=round((cold or 0) + (fw or 0), 1) if cold is not None and fw is not None else None,
                       coldstart_src=str(cs.get('cmd', 'in-process') if isinstance(cs.get('cmd'), list) else 'in-process')[:80])
        # 旧 CPU/归档 P50
        for sp, path in OLD_FILES.get(m, []):
            if path.exists():
                vals = latencies(path)
                rec[f'old_{sp}_p50'] = round(q(vals, .5), 1)
                rec[f'old_{sp}_n'] = len(vals)
        cons = HERE / f'consistency/{m}_consistency.json'
        if cons.exists():
            c = json.loads(cons.read_text())
            rec['consistency'] = f"{c['match']}/{c['sampled']}"
            rec['consistency_mismatch'] = c['mismatch']
        out[m] = rec
    (HERE / 'summary.json').write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(json.dumps(out, indent=1, ensure_ascii=False))


if __name__ == '__main__':
    main()
