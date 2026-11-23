#!/usr/bin/env python3
"""ModernBERT 四头基线 Method-A 分桶温度校准（与 ORACLE 线同口径）——R2 审稿补强。

协议（与 ORACLE kev 线方法 A 完全同口径，见 code/eval/methodA_test_formal.py + kev/metrics.py）：
  - 数据：suites/oracle-v3，calibration.jsonl(55 窗) 拟合，test.jsonl(439 窗) 出数；checkpoint 用
    EVAL/BATCH2-TRAIN/bert-baseline/bert_baseline.pt（不重训）。
  - 分桶：按题型各一桶（tactic/urgent/severity/action 四头各一个单参数温度 T）。
  - 拟合：kev.metrics.fit_temperature(**TEMPERATURE_FIT)——calib split raw logits 上
    min micro NLL，121 点 log 网格 0.25..4（与 kev 主线 head.pt T=2.047 同一实现）。
  - 指标：四头 acc / exact（温度不变）；ECE 15 等频桶（train_bert_baseline.py / evaluate.py 口径）；
    NLL 逐头 + 全题 micro 均值。校准前(T=1) vs 校准后(逐头 T)。
  - 复核：development.jsonl(55 窗) 推理应复现 bert-baseline/metrics.json（tactic 0.6909 / ECE15 0.2955）。

用法（GPU 推理 + CPU 拟合一次跑完；logits 落盘后可 --replay 纯 CPU 复算指标）：
  CUDA_MPS_PIPE_DIRECTORY=/tmp/no-mps-xyz taskset -c 48-63 nice -n 10 \
    /home/xxl/Mylocllm/kev/kev-repo/.venv/bin/python bert_calib_eval.py
  .../python bert_calib_eval.py --replay   # 跳过推理，读 logits JSON 复算
"""
import argparse, json, sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent          # 真实路径（/home/xxl/MySecAgent 为映射，偶发解析失败，统一走 realpath）
BASE = HERE.parents[1]                          # .../lab/experiments/oracle
SUITE = BASE / "suites/oracle-v3"
CKPT = BASE / "EVAL/BATCH2-TRAIN/bert-baseline/bert_baseline.pt"
assert CKPT.is_file(), f"checkpoint missing: {CKPT}"
sys.path.insert(0, "/home/xxl/Mylocllm/kev/kev-repo")  # kev.metrics: 方法 A 同款拟合实现
from kev.metrics import TEMPERATURE_FIT, fit_temperature, nll_at_temperature  # noqa: E402

HEADS = ["tactic", "urgent", "severity", "action"]

# ---------- 数据（与 train_bert_baseline.py WinDS 完全一致的标签映射） ----------
TACTICS = ['benign', 'reconnaissance', 'initial_access', 'execution', 'persistence',
           'privilege_escalation', 'defense_evasion', 'credential_access',
           'discovery', 'command_and_control', 'exfiltration']
SEV = ['low', 'medium', 'high', 'critical']
ACTIONS = ['no_action', 'monitor', 'investigate', 'escalate', 'contain',
           'isolate_host', 'block_ip', 'disable_user', 'reset_credentials', 'quarantine_message']
LABEL_SPACE = {"tactic": TACTICS, "urgent": [False, True], "severity": [0, 1, 2, 3], "action": ACTIONS}


def load_split(name):
    recs = [json.loads(l) for l in open(SUITE / f"{name}.jsonl") if l.strip()]
    out = []
    for i, r in enumerate(recs):
        qs = r["questions"]
        out.append({
            "id": r.get("_meta", {}).get("id", f"{name}-{i}"),
            "state": r["state"],
            "tactic": TACTICS.index(qs["tactic"]["label"]),
            "urgent": int(bool(qs["urgent"]["label"])),
            "severity": int(qs["severity"]["label"]),
            "action": ACTIONS.index(qs["action"]["label"]),
        })
    return out


# ---------- 推理（仅在非 --replay 时） ----------
def run_inference(splits):
    import torch
    from torch.utils.data import DataLoader
    from transformers import AutoTokenizer, AutoModel
    from torch import nn

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
    model.eval()
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"inference device: {dev}", flush=True)
    model.to(dev)

    all_logits = {}
    for name, recs in splits.items():
        enc_all = tok([r["state"] for r in recs], truncation=True, max_length=1024,
                      padding="max_length", return_tensors="pt")
        from torch.utils.data import TensorDataset
        ds = TensorDataset(enc_all["input_ids"], enc_all["attention_mask"])
        dl = DataLoader(ds, batch_size=16, shuffle=False, num_workers=2)
        outs = {h: [] for h in HEADS}
        with torch.no_grad():
            for ids, mask in dl:
                lt, lu, ls, la = model(ids.to(dev), mask.to(dev))
                for h, lg in zip(HEADS, (lt, lu, ls, la)):
                    outs[h].append(lg.float().cpu().numpy())
        all_logits[name] = {
            "ids": [r["id"] for r in recs],
            "labels": {h: [r[h] for r in recs] for h in HEADS},
            "logits": {h: np.concatenate(outs[h]).tolist() for h in HEADS},
        }
        print(f"  {name}: {len(recs)} 窗推理完成", flush=True)
    return all_logits


# ---------- kev row 构造（喂 kev.metrics.fit_temperature 的最小字段） ----------
def kev_rows(logits_list, labels):
    rows = []
    for z, y in zip(logits_list, labels):
        z = np.asarray(z, dtype=float)
        p = np.exp(z - z.max()); p = (p / p.sum()).tolist()
        rows.append({"p": p, "logits": z.tolist(), "label": int(y),
                     "variant": "clean", "source": "calib", "task": "fit",
                     "type": "choice", "id": "x", "keys": [], "question": "q"})
    return rows


# ---------- 指标（ECE 15 等频桶：train_bert_baseline.py:123-126 同款） ----------
def ece15_eqfreq(conf, correct, bins=15):
    conf = np.asarray(conf, dtype=float); correct = np.asarray(correct, dtype=float)
    order = np.argsort(-conf); conf, correct = conf[order], correct[order]
    splits = np.array_split(np.arange(len(conf)), bins)
    return float(sum(abs(correct[b].mean() - conf[b].mean()) * len(b) / len(conf)
                     for b in splits if len(b)))


def softmax_T(z, T):
    z = np.asarray(z, dtype=float) / T
    z = z - z.max(); e = np.exp(z); return e / e.sum()


def head_metrics(logits_list, labels, T=1.0):
    acc, conf, corr, nll = [], [], [], []
    for z, y in zip(logits_list, labels):
        p = softmax_T(z, T)
        ok = int(p.argmax() == y)
        acc.append(ok); corr.append(ok); conf.append(float(p.max()))
        zz = np.asarray(z, float) / T; zz = zz - zz.max()
        nll.append(float(np.log(np.exp(zz).sum()) - zz[y]))
    return {"n": len(labels), "acc": float(np.mean(acc)), "ece15": ece15_eqfreq(conf, corr),
            "nll": float(np.mean(nll)), "mean_conf": float(np.mean(conf))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--replay", action="store_true", help="跳过推理，用已落盘 logits 复算")
    a = ap.parse_args()

    if a.replay:
        splits = {n: json.loads((HERE / f"logits_{n}.json").read_text())
                  for n in ("calibration", "test", "development")}
    else:
        splits = run_inference({n: load_split(n) for n in ("calibration", "test", "development")})
        for n, d in splits.items():
            (HERE / f"logits_{n}.json").write_text(json.dumps(d))
            print(f"  logits_{n}.json 落盘", flush=True)

    L = {n: {h: np.asarray(d["logits"][h]) for h in HEADS} for n, d in splits.items()}
    Y = {n: {h: d["labels"][h] for h in HEADS} for n, d in splits.items()}

    # ---- 0. dev 复核（应复现训练时 metrics.json）----
    ck = json.loads((CKPT.parent / "metrics.json").read_text())
    dm = {h: head_metrics(L["development"][h], Y["development"][h]) for h in HEADS}
    exact_d = float(np.mean([all(int(L["development"][h][i].argmax() == Y["development"][h][i])
                                 for h in HEADS) for i in range(len(splits["development"]["ids"]))]))
    print(f"[dev 复核] tactic {dm['tactic']['acc']:.4f} (训练报告 {ck['tactic']:.4f}) | "
          f"exact {exact_d:.4f} ({ck['exact']:.4f}) | tactic ECE15 {dm['tactic']['ece15']:.4f} "
          f"({ck['tactic_ece15']:.4f})")

    # ---- 1. calib split 逐头拟合温度（方法 A：min micro NLL, 121 点 log 网格 0.25..4）----
    temps = {}
    for h in HEADS:
        temps[h] = fit_temperature(kev_rows(L["calibration"][h], Y["calibration"][h]), **TEMPERATURE_FIT)
        print(f"[fit] {h:9s} T = {temps[h]:.4f}  (calib 55 窗, {TEMPERATURE_FIT})")

    # ---- 2. test 439 窗：校准前 vs 校准后 ----
    def test_arm(T_map):
        per = {h: head_metrics(L["test"][h], Y["test"][h], T_map[h]) for h in HEADS}
        exact = float(np.mean([all(int(softmax_T(L["test"][h][i], T_map[h]).argmax() == Y["test"][h][i])
                                   for h in HEADS) for i in range(len(splits["test"]["ids"]))]))
        micro_nll = float(np.mean([per[h]["nll"] for h in HEADS]))  # 220/439*4 题 etc. 每头 n 相等→算术平均=micro
        return per, exact, micro_nll

    raw_per, raw_exact, raw_nll = test_arm({h: 1.0 for h in HEADS})
    cal_per, cal_exact, cal_nll = test_arm(temps)

    result = {
        "task": "TASK-MODERNBERT-CALIB-20261111",
        "checkpoint": str(CKPT),
        "suite": str(SUITE),
        "protocol": {
            "fit": "Method A (ORACLE 同口径): per-question-type bucket (4 heads, one scalar T each), "
                   "fitted on oracle-v3 calibration split (55 windows), min micro NLL over 121-point "
                   "log grid 0.25..4 (kev.metrics.fit_temperature, TEMPERATURE_FIT)",
            "eval": "oracle-v3 test split, 439 windows; ECE = 15 equal-frequency bins "
                    "(train_bert_baseline.py convention); argmax/exact are temperature-invariant",
            "no_retrain": True,
        },
        "fitted_temperatures": temps,
        "dev_sanity": {"tactic_acc": dm["tactic"]["acc"], "exact": exact_d,
                       "tactic_ece15": dm["tactic"]["ece15"],
                       "matches_train_metrics_json": abs(dm["tactic"]["acc"] - ck["tactic"]) < 1e-9
                       and abs(exact_d - ck["exact"]) < 1e-9
                       and abs(dm["tactic"]["ece15"] - ck["tactic_ece15"]) < 1e-6},
        "test": {
            "n_windows": len(splits["test"]["ids"]),
            "raw_T1": {"per_head": raw_per, "exact": raw_exact, "micro_nll": raw_nll},
            "methodA_calibrated": {"per_head": cal_per, "exact": cal_exact, "micro_nll": cal_nll},
        },
    }
    (HERE / "bert_calib_result.json").write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print("\n[test 439 窗] 校准前 → 校准后（逐头 T）")
    print(f"{'head':10s}{'acc':>8s}{'ECE15':>9s}{'NLL':>8s}{'mean_conf':>11s}   →   "
          f"{'acc':>8s}{'ECE15':>9s}{'NLL':>8s}{'mean_conf':>11s}")
    for h in HEADS:
        r, c = raw_per[h], cal_per[h]
        print(f"{h:10s}{r['acc']:8.4f}{r['ece15']:9.4f}{r['nll']:8.4f}{r['mean_conf']:11.4f}   →   "
              f"{c['acc']:8.4f}{c['ece15']:9.4f}{c['nll']:8.4f}{c['mean_conf']:11.4f}  (T={temps[h]:.3f})")
    print(f"{'exact':10s}{raw_exact:8.4f}{'':9s}{'':8s}   →   {cal_exact:8.4f}")
    print(f"{'micro NLL':10s}{'':8s}{'':9s}{raw_nll:8.4f}   →   {'':8s}{'':9s}{cal_nll:8.4f}")
    print("\nwrote", HERE / "bert_calib_result.json")


if __name__ == "__main__":
    main()
