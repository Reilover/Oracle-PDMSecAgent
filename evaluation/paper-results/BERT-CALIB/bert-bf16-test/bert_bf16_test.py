#!/usr/bin/env python3
"""D9: ModernBERT 温度阶段 bf16 复测（test 439 窗，与 fp32 存档同口径对照）。

协议与 ../bert_calib_eval.py 完全一致（不重拟合温度）：
  - checkpoint: EVAL/BATCH2-TRAIN/bert-baseline/bert_baseline.pt（四头，加载 fp32 后转 cuda bf16）
  - 数据: suites/oracle-v3/test.jsonl（439 窗），tokenize 同款（truncation 1024, padding max_length, bs16）
  - 温度: 直接采用 fp32 已拟合值（tactic 1.8661 / urgent 2.0000 / severity 2.1435 / action 1.6625）
  - 指标: ECE 15 等频桶；argmax/exact 温度不变；NLL/mean_conf 逐头 + micro 平均
  - 对照: ../bert_calib_result.json + ../logits_test.json（fp32 logits，逐窗 argmax 一致性检查）

用法:
  CUDA_VISIBLE_DEVICES=0 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  CUDA_MPS_PIPE_DIRECTORY=/tmp/no-mps-bf16d9 \
  /home/xxl/Mylocllm/kev/kev-repo/.venv/bin/python bert_bf16_test.py
"""
import json, sys, time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
BASE = HERE.parents[2]                      # .../lab/experiments/oracle
SUITE = BASE / "suites/oracle-v3"
CKPT = BASE / "EVAL/BATCH2-TRAIN/bert-baseline/bert_baseline.pt"
FP32_RESULT = HERE.parent / "bert_calib_result.json"
FP32_LOGITS = HERE.parent / "logits_test.json"
assert CKPT.is_file() and FP32_RESULT.is_file() and FP32_LOGITS.is_file()

HEADS = ["tactic", "urgent", "severity", "action"]
TACTICS = ['benign', 'reconnaissance', 'initial_access', 'execution', 'persistence',
           'privilege_escalation', 'defense_evasion', 'credential_access',
           'discovery', 'command_and_control', 'exfiltration']
SEV = ['low', 'medium', 'high', 'critical']
ACTIONS = ['no_action', 'monitor', 'investigate', 'escalate', 'contain',
           'isolate_host', 'block_ip', 'disable_user', 'reset_credentials', 'quarantine_message']

TEMPS = {"tactic": 1.8660659830736146, "urgent": 1.9999999999999998,
         "severity": 2.1435469250725863, "action": 1.6624757922855755}


def load_test():
    recs = [json.loads(l) for l in open(SUITE / "test.jsonl") if l.strip()]
    out = []
    for i, r in enumerate(recs):
        qs = r["questions"]
        out.append({
            "id": r.get("_meta", {}).get("id", f"test-{i}"),
            "state": r["state"],
            "tactic": TACTICS.index(qs["tactic"]["label"]),
            "urgent": int(bool(qs["urgent"]["label"])),
            "severity": int(qs["severity"]["label"]),
            "action": ACTIONS.index(qs["action"]["label"]),
        })
    return out


def run_inference_bf16(recs):
    import torch
    from torch import nn
    from torch.utils.data import DataLoader, TensorDataset
    from transformers import AutoTokenizer, AutoModel

    class MultiHead(nn.Module):
        def __init__(self):
            super().__init__()
            self.enc = AutoModel.from_pretrained("answerdotai/ModernBERT-base")
            self.dropout = nn.Dropout(0.1)
            self.head_t = nn.Linear(768, len(TACTICS))
            self.head_u = nn.Linear(768, 2)
            self.head_s = nn.Linear(768, len(SEV))
            self.head_a = nn.Linear(768, len(ACTIONS))

        def forward(self, ids, mask):
            h = self.enc(input_ids=ids, attention_mask=mask).last_hidden_state[:, 0]
            h = self.dropout(h)
            return self.head_t(h), self.head_u(h), self.head_s(h), self.head_a(h)

    tok = AutoTokenizer.from_pretrained("answerdotai/ModernBERT-base")
    model = MultiHead()
    model.load_state_dict(torch.load(CKPT, map_location="cpu", weights_only=True))
    model.eval()          # eval 模式 dropout 关闭（与 fp32 推理一致）
    dev, dt = "cuda", torch.bfloat16
    model = model.to(dev, dt)
    print(f"inference device: {dev} dtype: {dt}", flush=True)

    enc_all = tok([r["state"] for r in recs], truncation=True, max_length=1024,
                  padding="max_length", return_tensors="pt")
    ds = TensorDataset(enc_all["input_ids"], enc_all["attention_mask"])
    dl = DataLoader(ds, batch_size=16, shuffle=False, num_workers=2)
    outs = {h: [] for h in HEADS}
    t0 = time.time()
    with torch.no_grad():
        for ids, mask in dl:
            lt, lu, ls, la = model(ids.to(dev), mask.to(dev))
            for h, lg in zip(HEADS, (lt, lu, ls, la)):
                outs[h].append(lg.float().cpu().numpy())   # 立即转 fp32 落盘
    L = {h: np.concatenate(outs[h]) for h in HEADS}
    print(f"  bf16 inference: {len(recs)} windows in {time.time()-t0:.1f}s", flush=True)
    return L


# ---------- 指标（与 bert_calib_eval.py 逐字节同款） ----------
def ece15_eqfreq(conf, correct, bins=15):
    conf = np.asarray(conf, dtype=float); correct = np.asarray(correct, dtype=float)
    order = np.argsort(-conf); conf, correct = conf[order], correct[order]
    splits = np.array_split(np.arange(len(conf)), bins)
    return float(sum(abs(correct[b].mean() - conf[b].mean()) * len(b) / len(conf)
                     for b in splits if len(b)))


def softmax_T(z, T):
    z = np.asarray(z, dtype=float) / T
    z = z - z.max(); e = np.exp(z); return e / e.sum()


def head_metrics(logits, labels, T=1.0):
    acc, conf, corr, nll = [], [], [], []
    for z, y in zip(logits, labels):
        p = softmax_T(z, T)
        ok = int(p.argmax() == y)
        acc.append(ok); corr.append(ok); conf.append(float(p.max()))
        zz = np.asarray(z, float) / T; zz = zz - zz.max()
        nll.append(float(np.log(np.exp(zz).sum()) - zz[y]))
    return {"n": len(labels), "acc": float(np.mean(acc)), "ece15": ece15_eqfreq(conf, corr),
            "nll": float(np.mean(nll)), "mean_conf": float(np.mean(conf))}


def main():
    recs = load_test()
    assert len(recs) == 439, f"expected 439 windows, got {len(recs)}"
    Y = {h: [r[h] for r in recs] for h in HEADS}
    ids = [r["id"] for r in recs]

    L = run_inference_bf16(recs)
    (HERE / "logits_test_bf16.json").write_text(json.dumps(
        {"ids": ids, "labels": Y, "logits": {h: L[h].tolist() for h in HEADS}}))

    # ---- 指标: raw (T=1) vs tempered (fp32 已拟合 T) ----
    def arm(T_map):
        per = {h: head_metrics(L[h], Y[h], T_map[h]) for h in HEADS}
        exact = float(np.mean([all(int(softmax_T(L[h][i], T_map[h]).argmax() == Y[h][i])
                                   for h in HEADS) for i in range(len(ids))]))
        micro_nll = float(np.mean([per[h]["nll"] for h in HEADS]))
        micro_ece = float(np.mean([per[h]["ece15"] for h in HEADS]))
        micro_conf = float(np.mean([per[h]["mean_conf"] for h in HEADS]))
        return per, exact, micro_nll, micro_ece, micro_conf

    raw_per, raw_exact, raw_nll, raw_mice, raw_micf = arm({h: 1.0 for h in HEADS})
    cal_per, cal_exact, cal_nll, cal_mice, cal_micf = arm(TEMPS)

    # ---- 与 fp32 存档逐项对照 ----
    fp = json.loads(FP32_RESULT.read_text())["test"]
    fpL = json.loads(FP32_LOGITS.read_text())
    assert fpL["ids"] == ids, "fp32 logits id order mismatch"

    argmax_match = {}
    for h in HEADS:
        m = [int(a == b) for a, b in zip(L[h].argmax(axis=1), np.asarray(fpL["logits"][h]).argmax(axis=1))]
        argmax_match[h] = float(np.mean(m))

    result = {
        "task": "TASK-MODERNBERT-CALIB-BF16-TEST-20261125",
        "checkpoint": str(CKPT),
        "suite": str(SUITE),
        "protocol": {
            "inference": "GPU cuda bf16 (model.eval(), dropout off), logits cast fp32 on output; "
                         "tokenization/batching identical to fp32 run (bs16, max_length 1024)",
            "temperatures": "adopted from fp32 Method-A fit (calib 55 windows), NOT refitted",
            "eval": "oracle-v3 test split, 439 windows; ECE = 15 equal-frequency bins; "
                    "argmax/exact temperature-invariant",
            "fp32_reference": str(FP32_RESULT),
        },
        "fitted_temperatures_adopted": TEMPS,
        "test": {
            "n_windows": len(ids),
            "raw_T1": {"per_head": raw_per, "exact": raw_exact, "micro_nll": raw_nll,
                       "micro_ece15": raw_mice, "micro_mean_conf": raw_micf},
            "tempered": {"per_head": cal_per, "exact": cal_exact, "micro_nll": cal_nll,
                         "micro_ece15": cal_mice, "micro_mean_conf": cal_micf},
        },
        "argmax_match_vs_fp32_per_head": argmax_match,
    }
    (HERE / "bert_bf16_test_result.json").write_text(json.dumps(result, indent=2, ensure_ascii=False))

    # ---- 逐窗 results jsonl ----
    with open(HERE / "results_bf16_test.jsonl", "w") as fh:
        for i, rid in enumerate(ids):
            row = {"id": rid, "y": {h: Y[h][i] for h in HEADS},
                   "pred": {h: int(L[h][i].argmax()) for h in HEADS}}
            for h in HEADS:
                pr = softmax_T(L[h][i], 1.0); pt = softmax_T(L[h][i], TEMPS[h])
                zz = np.asarray(L[h][i], float) / TEMPS[h]; zz = zz - zz.max()
                row[h] = {"conf_raw": float(pr.max()), "correct_raw": int(pr.argmax() == Y[h][i]),
                          "conf_tempered": float(pt.max()), "correct_tempered": int(pt.argmax() == Y[h][i]),
                          "nll_raw": -float(np.log(softmax_T(L[h][i], 1.0)[Y[h][i]])),
                          "nll_tempered": float(np.log(np.exp(zz).sum()) - zz[Y[h][i]])}
            fh.write(json.dumps(row) + "\n")

    # ---- gate: tempered micro/tactic ECE vs fp32 ----
    fp_tactic_tempered_ece = fp["methodA_calibrated"]["per_head"]["tactic"]["ece15"]
    fp_micro_ece = float(np.mean([fp["methodA_calibrated"]["per_head"][h]["ece15"] for h in HEADS]))
    d_tactic = abs(cal_per["tactic"]["ece15"] - fp_tactic_tempered_ece)
    d_micro = abs(cal_mice - fp_micro_ece)
    gate = {
        "fp32_tactic_tempered_ece": fp_tactic_tempered_ece,
        "bf16_tactic_tempered_ece": cal_per["tactic"]["ece15"],
        "abs_delta_tactic": d_tactic,
        "fp32_micro_tempered_ece": fp_micro_ece,
        "bf16_micro_tempered_ece": cal_mice,
        "abs_delta_micro": d_micro,
        "pass": (d_tactic <= 0.02) and (d_micro <= 0.02),
    }
    (HERE / "gate.json").write_text(json.dumps(gate, indent=2))
    print(json.dumps(gate, indent=2))
    print(f"\nargmax match vs fp32: {argmax_match}")
    print("wrote", HERE)


if __name__ == "__main__":
    main()
