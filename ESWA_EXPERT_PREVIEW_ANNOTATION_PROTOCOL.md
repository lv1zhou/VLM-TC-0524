# ESWA Expert-0 预标注协议

版本：v1.0  
用途：真实人工标注前的流程预演与争议样例挖掘  
状态：非发表 gold label

## 1. 定位

Expert-0 预标注由 Codex 按 `ESWA_HUMAN_ANNOTATION_GUIDE.md` 执行，用于检查 annotation packet、label schema、评估脚本和潜在争议案例。

它不是 human-gold evaluation，不能在论文中写成真实人工标注结果。

所有输出必须带有：

```json
"label_scope": "expert_preview_not_publication_gold"
```

## 2. 标注原则

- 只看 functional case 中 reported、derived、not_reported evidence。
- 不看 full system、baseline 或 counterfactual 模型输出。
- 不从 crash/collision outcome 推断真实 takeover failure。
- 不补齐真实 HMI、驾驶员心理或 ADS 内部状态。
- `not_supported_transfer` 需要 explicit transition/intervention/support-withdrawal evidence。
- 如果 evidence 不足以支持更强 claim，优先保留 `contingent_readiness` 并标注 blocked stronger claim。

## 3. 输出字段

每条 JSONL 包含：

- `case_id`
- `annotator_id`
- `label_scope`
- `source_regime`
- `boundary_label`
- `update_vulnerability`
- `dominant_uca`
- `active_uca_set`
- `supporting_evidence_ids`
- `insufficient_information_flags`
- `blocked_stronger_claims`
- `rationale_short`
- `confidence`
- `needs_human_adjudication`

## 4. 使用方式

生成 50-case 预标注：

```powershell
python stpa_hf_dan_eswa_engine_final.py expert-preview-labels --cases data/cases/paper_50_mixed_sources_v1.jsonl --out-labels data/annotations/expert_preview_not_publication_gold_50.jsonl --out-report results/paper_v1_50_mixed_sources/expert_preview_eval/expert_preview_annotation_report.json
```

## 5. 论文写作边界

可写：

> We used Expert-0 preview labels only to debug the annotation protocol and identify cases likely to require adjudication.

不可写：

> Expert-0 labels are human gold labels.

