"""oracle-pipeline — ORACLE 双层 PDM 置信升级管线（论文 §4 代码落地）

分层：
  Tier 0 规则   judge/rules.py（凭据填充阈值/工具指纹）          ~0ms
  Tier 1 轻层   laya-421M v3 (lab/experiments/oracle/T4-LAYA)   CPU, 单次前向
  Tier 2 重层   Kev-0.8B v3 (kev-repo runs/oracle-kev08-v3)     GPU serve
  Tier 3 人工   CLI 叙述 + y/n 确认

置信门：逐题型 conf = max softmax(校准温度后的概率)。模型概率即校准概率
（laya ckpt 内嵌按题类温度 / kev head.pt 内嵌全局拟合温度 T=1.91，
serve 端默认应用；两个 ckpt 的原始 logits 各自缓存，用于二次缩放实验）。
"""
