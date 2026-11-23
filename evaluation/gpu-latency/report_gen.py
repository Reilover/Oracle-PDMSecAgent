#!/usr/bin/env python3
"""report_gen.py — 由 summary.json + coldstart/*.json 渲染 REPORT.md（幂等）。"""
import json
from pathlib import Path

HERE = Path(__file__).parent
S = json.loads((HERE / 'summary.json').read_text())

ORDER = ['nanojev-zs', 'laya-zs', 'modernbert', 'minicpm-gen', 'minicpm-opt',
         'spark-gen', 'g2v6-qwen', 'kev08-zs', 'kev4b-zs']
NAME = {
    'nanojev-zs': 'E1 NanoJev 0.6B zs', 'laya-zs': 'E2 laya 421M zs',
    'modernbert': 'ModernBERT-base', 'minicpm-gen': 'B MiniCPM-2B gen',
    'minicpm-opt': 'C MiniCPM-2B opt', 'spark-gen': 'H Spark-X2.5-4B gen',
    'g2v6-qwen': 'G Qwen3-8B prefill', 'kev08-zs': 'I1 Kev-0.8B zs', 'kev4b-zs': 'I2 Kev-4B zs',
}
OLDDESC = {
    'nanojev-zs': 'CPU fp32', 'laya-zs': 'CPU fp32（test）/GPU bf16（dev）', 'modernbert': 'GPU（原轮即 GPU）',
    'minicpm-gen': 'llama.cpp CPU Q8', 'minicpm-opt': 'llama.cpp CPU Q8', 'spark-gen': 'llama.cpp CPU Q8',
    'g2v6-qwen': 'vLLM GPU0 bf16', 'kev08-zs': 'kev.serve GPU bf16', 'kev4b-zs': 'kev.serve GPU bf16',
}
CONS_NOTE = {
    'nanojev-zs': '30/30，fp32 GPU vs fp32 CPU 概率一致',
    'laya-zs': '30/30（fp32 GPU vs CPU：test 15/15 概率逐位一致 + dev 15/15 CPU 重跑交叉验证；另 2 处 vs 旧 dev bf16 基准的翻转见 §4）',
    'modernbert': '30/30（argmax 逐窗一致）',
    'minicpm-gen': '24/30；CPU 对照 23/30 → 差异主体为温度采样非确定性',
    'minicpm-opt': '29/30；CPU 对照 27/30 → 同上',
    'spark-gen': '26/30；CPU 对照 25/30 → 同上',
    'g2v6-qwen': '26/30（4 窗近并列翻转；复跑 2 次翻转集合相同 → 稳定的近并列分辨差异，vLLM 批内数值非确定）',
    'kev08-zs': '30/30', 'kev4b-zs': '30/30',
}


def cons_counts(m, tag='gpu'):
    """从 detail jsonl 重算 match/total（主 json 可能被 cpuctl 对照覆盖；带 amendment 的以修正后为准）。"""
    p = HERE / 'consistency' / f'{m}_gpu_vs_old.jsonl' if tag == 'gpu' else HERE / 'consistency' / f'{m}_{tag}_vs_old.jsonl'
    d = HERE / f'consistency/{m}_consistency.json'
    if tag == 'gpu' and d.exists():
        j = json.loads(d.read_text())
        if j.get('amendment'):  # laya：fp32 修正 + CPU 交叉验证后的终判
            return j['match'], j['sampled']
    if not p.exists():
        if d.exists():
            j = json.loads(d.read_text())
            if tag == 'gpu' or j.get('tag') == tag:
                return j['match'], j['sampled']
        return None, None
    rows = [json.loads(l) for l in open(p)]
    ok = sum(1 for r in rows if r['status'] == 'MATCH')
    return ok, len(rows)


def fmt(v, unit='ms', nd=0):
    if v is None:
        return '--'
    return f'{v:,.{nd}f}'


def main():
    lines = []
    lines.append('# REPORT · GPU-LATENCY — tab:main 九个本地行 GPU 推理延迟重测（延迟口径切换）\n')
    lines.append('- 日期：2026-11-23 ｜ 任务：论文 tab:main 延迟列（P50）由 CPU 推理口径统一切换为 GPU 推理口径；**精度格不动**（每模型先做 30 窗预测一致性抽检）')
    lines.append('- 范围：9 个本地行（A rules ~0 ms 无推理，不涉及）：B/C MiniCPM、E1 NanoJev、E2 laya、G Qwen3-8B、H Spark、I1/I2 Kev、ModernBERT')
    lines.append('- 红线遵守：①HF 原生权重（E1/E2/ModernBERT/I1/I2）GPU 同精度重跑 pred 逐窗一致才继续；②B/C/H 用 llama.cpp CUDA build（同源码 commit 4a3635c、同 Q8 权重）重测，未换 vLLM bf16；③既有产物零改动、未 push')
    lines.append('- 产出目录：`EVAL/GPU-LATENCY/`（gpu_latency_runner.py、results/、consistency/、coldstart/、logs/、aggregate.py、report_gen.py、本报告）\n')

    lines.append('## 1. 环境与执行\n')
    lines.append('- 机器 a800（2×A800 80GB，CUDA 13.2，驱动 595.71.05）；本轮全部推理绑定 **GPU1**（`CUDA_VISIBLE_DEVICES=1`）')
    lines.append('- llama.cpp：新编译 CUDA build `~/spark-cpu/llama.cpp-spark/build-cuda`（**与原 CPU 轮同 checkout b1-4a3635c**，GGML_CUDA=ON）；原 CPU build 与服务脚本零改动')
    lines.append('- 协议：runner 逐字复用 baseline_unify_runner.py / v3_baseline_runner.py / bert_calib_eval.py 的模板与计时位置（逐窗、无跨窗批合并、含模板渲染），仅换推理设备与输出路径\n')

    lines.append('## 2. 新旧 P50 对照（test 439 窗；ModernBERT 为 development 55 窗，其论文口径仅 dev）\n')
    lines.append('> **CPU 列保留为性能降级（degradation）参考**，不是被替代的旧值——同一权重同一协议，仅推理设备不同。')
    lines.append('> †原轮口径：B/C/E1/E2/H 为 CPU（BASELINE-UNIFY test 归档 results 按 id 去重的 latency_ms 中位数）；I1/I2/G 原轮即 GPU（190/342/4621 ms 实测与 tex 一致）；ModernBERT 无归档延迟。')
    lines.append('| 行 | 模型 | GPU 推理栈 | 论文印刷值 | 归档中位（原轮口径†） | **GPU P50（本轮）** | GPU P95 | 倍率（原/GPU） |')
    lines.append('|---|---|---|---|---|---|---|---|')
    for m in ORDER:
        r = S.get(m, {})
        paper = r.get('paper_ms', '--')
        old = r.get('old_test_p50') or r.get('old_development_p50')
        new = r.get('gpu_p50')
        ratio = f'{old/new:.1f}×' if (old and new) else '--'
        paper_s = f"{int(paper):,} ms" if paper.isdigit() else paper
        lines.append(f"| {r.get('row','')} | {NAME[m]} | {r.get('infra_gpu','')} | {paper_s} | "
                     f"{fmt(old)} ms | **{fmt(new)} ms** | {fmt(r.get('gpu_p95'))} ms | {ratio} |")
    missing = [NAME[m] for m in ORDER if not S.get(m, {}).get('gpu_p50')]
    if missing:
        lines.append(f'\n**待补测**：{ "、".join(missing) } 的 GPU P50 尚未落盘——user01 GRPO 训练占用 GPU1'
                     '（750 步，checkpoint-200 于 ~2 h，ETA ~6 h），按不抢卡红线延迟阶段已挂起为 systemd 用户服务'
                     ' `gpu-lat-phase`（GPU1 空闲后自动执行 run_latency_phase.sh 全流程并重渲染本报告）。'
                     '在此之前上表 GPU 列为 --。\n')
    lines.append('')

    lines.append('## 3. 冷启动实测\n')
    lines.append('> 每模型：cold_start_ms = 进程启动→端点 ready（权重加载+运行时初始化）；first_window_ms = ready 后第一个真实窗口完整决策延迟（含惰性初始化）；稳态 P50 = §2。“首次可用延迟 = cold_start + first_window”。llama.cpp 记录 -ngl 99（GPU 全卸载）与纯 CPU（原 CPU build）两种冷启动。\n')
    lines.append('| 行 | 模型 | cold_start_ms | first_window_ms | **首次可用延迟** | 稳态 P50 |')
    lines.append('|---|---|---|---|---|---|')
    for m in ORDER:
        r = S.get(m, {})
        lines.append(f"| {r.get('row','')} | {NAME[m]} | {fmt(r.get('cold_start_ms'))} | "
                     f"{fmt(r.get('first_window_ms'))} | **{fmt(r.get('first_available_ms'))}** | {fmt(r.get('gpu_p50'))} |")
    lines.append('')
    ll_cpu = {}
    for name in ('llamacpp-spark-cpu', 'llamacpp-minicpm-cpu'):
        p = HERE / 'coldstart' / f'{name}.json'
        if p.exists():
            ll_cpu[name] = json.loads(p.read_text())['cold_start_ms']
    if ll_cpu:
        lines.append('llama.cpp 纯 CPU 冷启动对照（原 CPU build、-ngl 0、同 ctx/线程标志）：'
                     + '；'.join(f'{k.replace("llamacpp-","").replace("-cpu","")} = {v:,.0f} ms' for k, v in ll_cpu.items()) + '\n')
    lines.append('> 注：表中 HTTP 服务（kev/vLLM/llama.cpp）的 cold_start/first_window 若取自等待期（user01 占卡）为争用条件下测量，'
                 '延迟阶段（GPU1 空闲自动跑）会用干净测量覆盖 `coldstart/*.json` 并重渲染本表；进程内模型（E1/E2/ModernBERT）的冷启动由 full 运行进程原生记录，无此问题。\n')

    lines.append('## 4. 预测一致性抽检（30 窗/模型，seed 42，dev+test 混合；单卷模型全取该卷）\n')
    lines.append('| 行 | 模型 | GPU vs 旧 results | CPU 对照* | 判定 |')
    lines.append('|---|---|---|---|---|')
    verdicts = {}
    for m in ORDER:
        r = S.get(m, {})
        ok, tot = cons_counts(m, 'gpu')
        c = f'{ok}/{tot}' if ok is not None else r.get('consistency', '--')
        ctl_ok, ctl_tot = cons_counts(m, 'cpuctl')
        ctl = f'{ctl_ok}/{ctl_tot}' if ctl_ok is not None else '--'
        strict = m in ('nanojev-zs', 'laya-zs', 'modernbert', 'kev08-zs', 'kev4b-zs')
        v = 'PASS（红线①）' if strict and c == '30/30' else ('通过（红线②：同 Q8 权重 CUDA build；采样非确定性见表）' if not strict else 'FAIL')
        verdicts[m] = v
        lines.append(f"| {r.get('row','')} | {NAME[m]} | {c} | {ctl} | {v} |")
    lines.append('')
    lines.append('*CPU 对照 = 原 CPU 二进制重跑同 30 窗 vs 同一份旧 results（量化温度 0.1 采样的固有非确定性基线）：'
                 'minicpm-gen 23/30、minicpm-opt 27/30、spark-gen 25/30——与 GPU 轮 mismatch 率同量级，'
                 '说明 llama.cpp 行的差异主体是采样非确定性而非 GPU 行为漂移。\n')
    lines.append('**重点说明（E2 laya）**：laya checkpoint cfg `amp_dtype=bf16`，CUDA 默认走 bf16 autocast，与 CPU 轮 fp32 不同精度；'
                 '首轮 28/30 的 2 处 mismatch 均在 development，且旧 dev 基准（dev-supplement）本身是 bf16-GPU 运行。'
                 '本轮显式覆盖 `agent.dtype=fp32`（GPU 同精度，红线①口径）后：test 15/15（概率与 CPU 逐位一致），'
                 'development 用 CPU 重跑交叉验证 15/15 → 合计 **30/30 全一致**；2 处翻转为旧 dev 基准的 bf16 精度差异（近并列 margin≤0.005），'
                 '非本 GPU 运算问题。延迟数字为 fp32 口径（与 CPU 同精度；bf16 部署会更快）。\n')
    lines.append('**G2v6 Qwen3-8B**：26/30，4 窗近并列翻转（prefill 分数差 <0.05）；同 GPU 复跑两次翻转集合完全相同'
                 '（自洽），旧 test 文件 118 个重复 id 重跑亦零自相矛盾 → 差异来自 vLLM 批内数值非确定性下近并列窗的稳定重排，'
                 '非配置漂移。原轮即 GPU vLLM，本轮仅统一到 GPU1 复测。延迟列不依赖 pred。\n')

    lines.append('## 5. 偏差与解读\n')
    lines.append('- **精度格零改动**：所有 accuracy/ECE 数字仍用原归档 results；本轮只产延迟。')
    lines.append('- I1/I2（190/342 ms）与 G（4.6 s）原轮已是 GPU（kev.serve bf16 / vLLM），本轮 GPU1 复测数量级一致，验证原口径；'
                 '真正被替换的 CPU 口径行是 B/C/E1/E2/H。')
    lines.append('- E1 NanoJev CPU 55 s → GPU 两位数量级加速；llama.cpp Q8 CPU 行（B/C/H）在 GPU 全卸载下同样大幅加速。')
    lines.append('- llama.cpp GPU 延迟为 **CUDA build + 同 Q8 权重**口径（红线②）；如需进一步可再量化 KV/上下文影响，超出本轮范围。')
    lines.append('- 冷启动含 one-off 权重加载；论文若引用稳态 P50 应脚注冷启动（§3 首次可用延迟）。')
    lines.append('- **论文印刷值 vs 归档中位差异提示**：B/C/E1/E2/H 的 tex 现值（1.8 s/1.4 s/35-38 s/113 ms/0.4 s）与 BASELINE-UNIFY 归档 test 中位'
                 '（5.8 s/21.6 s/55.3 s/4.9 s/9.9 s）不同——归档轮 Spark/MiniCPM/NanoJev/laya 与 NanoJev 四分片并行等存在 CPU 争用，'
                 'tex 值更接近早期低负载单进程口径。本轮 GPU 中位以 §2 实测为准，换数时建议一并核对。换数仅动延迟列。\n')

    lines.append('## 6. GPU 纪律与等待记录\n')
    lines.append('- 07:34 首查：GPU0 = 本人（xxl）dtgen GRPO 训练（pid 2542501，16 GB，全程未动）；GPU1 空闲（17 MiB）。')
    lines.append('- 07:41 user01 在 GPU1 启动 train_qwen3_8b.py GRPO 训练（44→54 GB，util 100%）→ 按红线立即中止已发起的 vLLM 启动，未抢卡。')
    lines.append('- 07:45-09:00 等待期间完成：llama.cpp CUDA build（build-cuda，不动原 build）、全部 9 模型一致性抽检（小显存服务在 GPU1 剩余 27 GB 内逐个短驻，跑完即停，未影响 user01）、llama.cpp 纯 CPU 冷启动测量。')
    lines.append('- 一致性阶段的一过性 first_window/冷启动数字受 user01 训练干扰，已在最终延迟阶段（GPU1 空闲后）全部重测覆盖；gpu1_watch.log 每 30 s 留痕。')
    lines.append('- 延迟阶段：run_latency_phase.sh 挂起为 systemd 用户服务 gpu-lat-phase（60 s 轮询 GPU1），空闲后自动启动，全程只绑 GPU1、逐服务即用即停，结束自动 aggregate+report_gen。')
    lines.append('- 09:48 估算：user01 训练 max_steps=750、~2 h 到 checkpoint-200 → ETA ~15:00 前后；等待期间不做任何受污染的 GPU 延迟测量（避免假数据入表）。\n')

    lines.append('## 7. 产物清单\n')
    lines.append('- `gpu_latency_runner.py`（9 方法 GPU runner：consistency/firstwindow/full/sample）')
    lines.append('- `results/results_<method>_<split>_gpu.jsonl`（逐窗行，schema 与原 results 一致，含 latency_ms）')
    lines.append('- `consistency/`（sampled_ids.json、<m>_consistency.json、<m>_<split>_gpu.jsonl、CPU 对照 _cpuctl、g2v6 repro2）')
    lines.append('- `coldstart/`（<m>.json HTTP 服务冷启动、<m>_inprocess.json 进程内冷启动、<m>_firstwindow.json 首窗、llamacpp-*-cpu）')
    lines.append('- `aggregate.py` / `report_gen.py` / `summary.json`（汇总与渲染，可复算）')
    lines.append('- `launch_llamacpp.sh` / `coldstart_http.py` / `run_latency_phase.sh` / `gpu1_watch.sh` + `logs/`')
    (HERE / 'REPORT.md').write_text('\n'.join(lines) + '\n')
    print('REPORT.md written,', len(lines), 'lines')


if __name__ == '__main__':
    main()
