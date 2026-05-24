# ESWA 下一轮代码执行与实验计划：30-case 问题修复后进入 50-case 主实验

版本：v1.0  
日期：2026-04-29  
状态：待用户审核同意后执行  
上位纲领：`ESWA_CHINESE_NARRATIVE_AND_NEXT_PLAN.md`

## 1. 本轮执行目标

本轮不是单纯“再跑一次实验”，而是把上一轮 30-case mixed-source pilot 暴露的问题逐一转化为代码修复、审计增强、人工专家预标注和 50-case 主实验准备。

核心目标：

1. 修复 crash/collision case 中仍可能出现的 unsupported strong-boundary escalation。
2. 重构 ambiguous degradation counterfactual，使 HMI sensitivity 实验的理论方向更清楚。
3. 固化 50-case mixed-source 主实验数据、目录、manifest 和 pipeline。
4. 由 Codex 先扮演“人工专家预标注者”，生成非发表用 expert-preview labels，用于检查 annotation guide、label schema 和评估脚本。
5. 为后续真实双人 human-gold annotation 准备接口、模板和争议样例。

必须坚持的论文边界：

- 不还原真实事故因果。
- 不推断真实驾驶员心理。
- 不证明真实 HMI 因果效果。
- 不把 evidence/logging requirement candidates 写成最终 HMI 设计要求。
- 所有强 boundary claim 必须有 explicit transition/intervention/support-withdrawal evidence。

## 2. 上一轮问题到本轮动作的映射

| 上一轮问题 | 风险 | 本轮代码/实验动作 | 验收标准 |
| --- | --- | --- | --- |
| 1 个 unsupported strong-boundary warning | 系统仍可能从 crash-only evidence 过度推断 NS | Prompt guardrail + audit evidence-strength 分级 + warning 汇总 | 30-case rerun warning 为 0，或所有 warning 都可解释且被标红 |
| ambiguous degradation CF 一致性 0.7667 | CF 理论口径不清，审稿人会质疑 | 拆分 CF 模板与 expected direction | ambiguous 类 >= 0.90，或形成单独解释性结果 |
| AI-pilot labels 非 human gold | 不能支撑主实验评价 | Codex 作为 Expert-0 生成 preview labels，真实论文仍需 2 名人类标注者 | 产物明确标注 not_publication_gold |
| standalone 和 baseline-suite full run 分布不同 | LLM 非严格确定性影响表格 | manifest 加强 run hash/source hash；表格只读 frozen outputs | paper result manifest 可追踪模型、输入、输出、hash |
| requirement candidates 太多 | 主文会显得堆砌 | taxonomy summarizer，按 evidence type/source/blocked claim 汇总 | 主表只报 taxonomy，附录保留 JSON |
| UCA/vulnerability 标签偏细 | 人工一致性风险 | annotation guide 增加 tie-break；主指标优先 boundary/blocked claim | expert-preview 能暴露分歧样例 |
| CA DMV collision source 边界 | 数据可信性写法风险 | metadata/report 中明确 third-party augmented | 所有 summary 均写 source_regime |
| pipeline 分散 | 复现实验困难 | 新建 paper pipeline PowerShell 脚本 | 一条命令能跑 audit/profile/run/baseline/CF/audit/gaps/manifest |

## 3. 代码撰写原则

执行时遵循以下规则：

1. 不重写主架构，继续使用 `stpa_hf_dan_eswa_engine_final.py` 和 `external_case_ingestion_final.py`。
2. 每个 patch 只解决一个明确问题，优先小改、可审计。
3. 保留旧 CLI，新增 alias 或新字段时兼容历史结果。
4. 输出文件全部落在 `results/paper_v1_*`，不再把 `results/verify/` 当作论文主结果。
5. 每个论文表格来源必须有 frozen input、output path、created_at、model、hash。
6. 人工专家预标注必须写清楚：`expert_preview_not_publication_gold`。
7. 不把 API key 写进计划文件或结果报告；执行时沿用当前环境配置。

## 4. 待修改文件清单

预计修改：

- `stpa_hf_dan_eswa_engine_final.py`
- 新增 `run_paper_v1_50_pipeline.ps1`
- 新增或更新 `ESWA_HUMAN_ANNOTATION_GUIDE.md`
- 新增 `ESWA_EXPERT_PREVIEW_ANNOTATION_PROTOCOL.md`
- 新增 `ESWA_50_CASE_MAIN_EXPERIMENT_REPORT_TEMPLATE.md`

预计新增结果目录：

- `results/paper_v1_30_mixed_sources_repair/`
- `results/paper_v1_50_mixed_sources/`

预计新增数据文件：

- `data/cases/paper_50_mixed_sources_v1.jsonl`
- `data/annotations/expert_preview_not_publication_gold_50.jsonl`
- `data/annotations/expert_preview_adjudicated_not_publication_gold_50.jsonl`

## 5. Phase A：代码审计与当前状态冻结

目的：执行前先记录当前代码和结果状态，避免后续结果混淆。

动作：

1. 检查主 CLI 是否存在：
   - `run`
   - `baseline-suite`
   - `missingness-profile`
   - `evidence-audit`
   - `feedback-gap-report`
   - `evidence-requirement-candidates`
   - `generate-cf-specs`
   - `generate-counterfactual`
   - `counterfactual-eval`
   - `paper-manifest`
2. 读取 30-case summary 和 manifest。
3. 记录当前 warning case：
   - `external_nhtsa_sgo_882f14ad142c`
4. 输出 pre-repair audit note。

产物：

- `results/paper_v1_30_mixed_sources_repair/pre_repair_state.json`
- `results/paper_v1_30_mixed_sources_repair/pre_repair_issue_register.md`

验收：

- issue register 能逐项对应上一轮问题。

## 6. Phase B：Prompt guardrail 与 strong-boundary audit 增强

目的：解决 crash/collision case 中的 unsupported NS 过度升级。

代码动作：

1. 在 STPA-HF 主 prompt 中新增 boundary guardrail：

   > For crash/collision cases, do not assign `not_supported_transfer` from crash outcome, collision severity, actor conflict, or deceleration alone. `not_supported_transfer` requires explicit source-reported transition/intervention evidence, such as disengagement, takeover demand, driver/operator intervention, support withdrawal, or transition requirement.

2. 在 evidence audit 中新增 evidence strength 分类：
   - `explicit_transition_or_intervention`
   - `explicit_hmi_takeover_or_support_withdrawal`
   - `reported_system_issue_or_disengagement_cause`
   - `indirect_event_pressure`
   - `outcome_only`
   - `not_reported_used_as_boundary_support`

3. 新增 audit 字段：
   - `strong_boundary_evidence_strength`
   - `strong_boundary_supporting_fields`
   - `outcome_only_escalation_warning`
   - `not_reported_boundary_support_warning`

4. paper summary 中汇总：
   - warning count；
   - warning case IDs；
   - source regime；
   - boundary；
   - dominant UCA；
   - supporting evidence fields。

验收：

- 30-case repair rerun 中不再出现 crash-only NS。
- 如果出现 NS，必须能在 audit 中看到 explicit transition/intervention/support evidence。

## 7. Phase C：Counterfactual HMI 模板重构

目的：解决 ambiguous degradation 模板不稳定。

代码动作：

1. 将原 `cf_hmi_ambiguous_degradation` 拆分为：
   - `cf_hmi_ambiguous_degradation_no_transition`
   - `cf_hmi_ambiguous_degradation_with_transition_pressure`

2. 修改 expected direction：
   - `no_transition`：不应强行推到 NS；可保持 CR 或较弱边界。
   - `with_transition_pressure`：允许向 NS 方向移动，但必须有 transition cue。

3. CF eval 输出新增：
   - `per_source_regime`
   - `per_template`
   - `expected_direction_rule`
   - `mismatch_case_ids`

4. CF specs 中保留 provenance：
   - `assumed_for_counterfactual`
   - `counterfactual_template_id`
   - `not_real_world_evidence: true`

验收：

- 所有 CF bundles schema valid。
- overall directional consistency `>= 0.90`。
- ambiguous 子类结果可解释，不再混成一个含糊模板。

## 8. Phase D：Evidence requirement taxonomy 汇总

目的：把 340/更多 requirement candidates 变成论文可读的应用价值结果。

代码动作：

1. 新增 taxonomy summary 输出：
   - by `source_regime`
   - by `requirement_type`
   - by `missing_evidence_slot`
   - by `blocked_stronger_claim`
   - by `supports`
   - by priority

2. 每类保留 representative examples，避免主文列几百条。

3. 输出文件：
   - `evidence_requirement_candidates.json`
   - `evidence_requirement_taxonomy_summary.json`
   - `evidence_requirement_taxonomy_summary.csv`
   - `evidence_requirement_representative_examples.md`

验收：

- 论文 Table 6 可直接从 taxonomy summary 生成。
- 主文能解释：这不是 HMI design requirement，而是 future reporting/logging evidence need。

## 9. Phase E：50-case deterministic sampler

目的：从 30-case pilot 进入主实验。

数据配比：

- NHTSA SGO official crash/collision：20
- CA DMV collision augmented：15
- CA DMV official disengagement：15

采样规则：

1. 固定 random seed。
2. 保证 source regime 数量符合配比。
3. 尽量覆盖 actor diversity：
   - vehicle
   - pedestrian
   - cyclist
   - parked vehicle/object
   - two-wheeler
4. 尽量覆盖 scene diversity：
   - intersection
   - lane change
   - straight road
   - parking/curb
   - low-speed maneuver
5. 保证 disengagement cases 中有 reported intervention/system issue。
6. 不允许 gold label 或 model output 泄漏进 case file。

产物：

- `data/cases/paper_50_mixed_sources_v1.jsonl`
- `results/paper_v1_50_mixed_sources/sample_summary.json`
- `results/paper_v1_50_mixed_sources/input_audit/no_label_leakage_report.json`

验收：

- case count = 50。
- source composition = 20/15/15。
- forbidden label leakage = 0。
- missingness/source regime summary 可读。

## 10. Phase F：Codex 扮演人工专家进行预标注

目的：在真实人类标注前，由我作为“Expert-0”按 annotation guide 做一轮预标注，用于预览论文评价形态、发现指南歧义和脚本问题。

重要边界：

- 这不是 publication human gold。
- 这不能写成真实人类标注结果。
- 这只能作为 protocol debugging、preview evaluation 和 disagreement mining。

标注输入：

- 50-case annotation packets。
- 只看 case evidence，不看 full system/baseline/counterfactual 输出。

标注输出字段：

- `case_id`
- `annotator_id: Expert0_Codex`
- `label_scope: expert_preview_not_publication_gold`
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

预期产物：

- `data/annotations/expert_preview_not_publication_gold_50.jsonl`
- `data/annotations/expert_preview_adjudicated_not_publication_gold_50.jsonl`
- `results/paper_v1_50_mixed_sources/expert_preview_eval/`
- `results/paper_v1_50_mixed_sources/expert_preview_disagreement_cases.md`

验收：

- 50 个 case 都有 expert preview label。
- 输出中清楚标注 not_publication_gold。
- 能列出最需要真实人类裁决的 10 个 case。

## 11. Phase G：30-case repair rerun

目的：先在旧 30-case 上验证修复是否有效，再扩大到 50-case。

执行顺序：

```powershell
python stpa_hf_dan_eswa_engine_final.py run --cases data/cases/paper_30_mixed_nhtsa10_ca_collision10_ca_disengagement10.jsonl --out results/paper_v1_30_mixed_sources_repair/bundles
python stpa_hf_dan_eswa_engine_final.py baseline-suite --cases data/cases/paper_30_mixed_nhtsa10_ca_collision10_ca_disengagement10.jsonl --out results/paper_v1_30_mixed_sources_repair/baseline_suite
python stpa_hf_dan_eswa_engine_final.py evidence-audit --bundle-dir results/paper_v1_30_mixed_sources_repair/bundles --out results/paper_v1_30_mixed_sources_repair/audit/evidence_support_audit
python stpa_hf_dan_eswa_engine_final.py feedback-gap-report --bundle-dir results/paper_v1_30_mixed_sources_repair/bundles --out results/paper_v1_30_mixed_sources_repair/feedback_gaps
python stpa_hf_dan_eswa_engine_final.py evidence-requirement-candidates --gap-report results/paper_v1_30_mixed_sources_repair/feedback_gaps/feedback_gap_report.json --out results/paper_v1_30_mixed_sources_repair/evidence_requirements
python stpa_hf_dan_eswa_engine_final.py generate-cf-specs --cases data/cases/paper_30_mixed_nhtsa10_ca_collision10_ca_disengagement10.jsonl --out results/paper_v1_30_mixed_sources_repair/cf_specs.jsonl
python stpa_hf_dan_eswa_engine_final.py generate-counterfactual --cases data/cases/paper_30_mixed_nhtsa10_ca_collision10_ca_disengagement10.jsonl --specs results/paper_v1_30_mixed_sources_repair/cf_specs.jsonl --out results/paper_v1_30_mixed_sources_repair/cf_cases.jsonl
python stpa_hf_dan_eswa_engine_final.py run --cases results/paper_v1_30_mixed_sources_repair/cf_cases.jsonl --out results/paper_v1_30_mixed_sources_repair/cf_bundles
python stpa_hf_dan_eswa_engine_final.py counterfactual-eval --base-bundle-dir results/paper_v1_30_mixed_sources_repair/bundles --cf-bundle-dir results/paper_v1_30_mixed_sources_repair/cf_bundles --specs results/paper_v1_30_mixed_sources_repair/cf_specs.jsonl --out results/paper_v1_30_mixed_sources_repair/cf_eval
```

验收：

- full system schema valid `30/30`。
- invalid evidence ID mean = `0`。
- UCA catalog consistency = `1.0`。
- unsupported strong-boundary warning = `0` 或有清楚解释。
- direct baseline 仍显示明显 over-escalation。
- CF directional consistency `>= 0.90`。

## 12. Phase H：50-case 主实验执行

目的：生成 ESWA 主实验候选结果。

执行顺序：

```powershell
python stpa_hf_dan_eswa_engine_final.py audit-case-input --cases data/cases/paper_50_mixed_sources_v1.jsonl --out results/paper_v1_50_mixed_sources/input_audit
python stpa_hf_dan_eswa_engine_final.py missingness-profile --cases data/cases/paper_50_mixed_sources_v1.jsonl --out results/paper_v1_50_mixed_sources/table1/missingness_profile
python stpa_hf_dan_eswa_engine_final.py export-annotation-packets --cases data/cases/paper_50_mixed_sources_v1.jsonl --out data/annotation_packets/paper_50_v1
python stpa_hf_dan_eswa_engine_final.py run --cases data/cases/paper_50_mixed_sources_v1.jsonl --out results/paper_v1_50_mixed_sources/bundles
python stpa_hf_dan_eswa_engine_final.py baseline-suite --cases data/cases/paper_50_mixed_sources_v1.jsonl --out results/paper_v1_50_mixed_sources/baseline_suite
python stpa_hf_dan_eswa_engine_final.py evidence-audit --bundle-dir results/paper_v1_50_mixed_sources/bundles --out results/paper_v1_50_mixed_sources/audit/evidence_support_audit
python stpa_hf_dan_eswa_engine_final.py feedback-gap-report --bundle-dir results/paper_v1_50_mixed_sources/bundles --out results/paper_v1_50_mixed_sources/feedback_gaps
python stpa_hf_dan_eswa_engine_final.py evidence-requirement-candidates --gap-report results/paper_v1_50_mixed_sources/feedback_gaps/feedback_gap_report.json --out results/paper_v1_50_mixed_sources/evidence_requirements
python stpa_hf_dan_eswa_engine_final.py generate-cf-specs --cases data/cases/paper_50_mixed_sources_v1.jsonl --out results/paper_v1_50_mixed_sources/cf_specs.jsonl
python stpa_hf_dan_eswa_engine_final.py generate-counterfactual --cases data/cases/paper_50_mixed_sources_v1.jsonl --specs results/paper_v1_50_mixed_sources/cf_specs.jsonl --out results/paper_v1_50_mixed_sources/cf_cases.jsonl
python stpa_hf_dan_eswa_engine_final.py run --cases results/paper_v1_50_mixed_sources/cf_cases.jsonl --out results/paper_v1_50_mixed_sources/cf_bundles
python stpa_hf_dan_eswa_engine_final.py counterfactual-eval --base-bundle-dir results/paper_v1_50_mixed_sources/bundles --cf-bundle-dir results/paper_v1_50_mixed_sources/cf_bundles --specs results/paper_v1_50_mixed_sources/cf_specs.jsonl --out results/paper_v1_50_mixed_sources/cf_eval
```

验收：

- full system schema valid rate `>= 95%`。
- invalid evidence ID mean = `0`。
- UCA catalog consistency = `1.0`。
- direct baseline 的 NS 比例显著高于 full system。
- generic CoT 仍弱于 STPA-HF full system。
- no-update ablation 显示 update stage 的贡献。
- source-regime missingness 和 gap profile 能支撑论文 Table 1/Table 6。

## 13. Phase I：Expert-preview evaluation

目的：用 Codex Expert-0 预标注结果检查主实验形态。

评估对象：

- full system vs expert-preview labels。
- direct baseline vs expert-preview labels。
- generic CoT vs expert-preview labels。

必须标注：

> These labels are expert-preview labels generated by Codex for protocol debugging only and are not publication human-gold labels.

输出：

- boundary accuracy / macro-F1 / balanced accuracy。
- confusion matrix。
- strongest disagreement cases。
- annotation-guide ambiguity notes。

验收：

- 能预览 Table 2 的形态。
- 能识别真实人类标注最需要关注的争议点。

## 14. Phase J：生成本轮复盘报告

目的：把代码修复、30-case repair、50-case 主实验、expert-preview 预标注整合成一个论文进展报告。

产物：

- `results/paper_v1_50_mixed_sources/ESWA_50_CASE_MAIN_RUN_REPORT.md`
- `results/paper_v1_50_mixed_sources/paper_v1_50_mixed_summary.json`
- `results/paper_v1_50_mixed_sources/paper_result_manifest.json`
- `ESWA_AFTER_50CASE_REVISION_NOTES.md`

报告必须回答：

1. 修复是否解决 crash-only over-escalation？
2. ambiguous CF 是否稳定？
3. 50-case source regime 是否支撑论文叙事？
4. feedback gaps 和 evidence requirements 是否有应用价值？
5. expert-preview 显示哪些标签最不稳？
6. 下一步真实 human-gold annotation 应如何部署？

## 15. 执行前需要用户确认的点

我建议默认采用以下设定，除非你修改：

1. 50-case 配比固定为 `20 NHTSA + 15 CA DMV collision augmented + 15 CA DMV disengagement`。
2. Codex Expert-0 预标注用于 preview，不写入 publication gold。
3. 先修代码并跑 30-case repair，通过后再跑 50-case。
4. 结果目录使用：
   - `results/paper_v1_30_mixed_sources_repair/`
   - `results/paper_v1_50_mixed_sources/`
5. 不把 API key 写入任何新增 MD 或结果报告。

## 16. 最小成功标准

本轮完成后，至少应达到：

- 30-case repair：schema valid `30/30`。
- 30-case repair：unsupported strong-boundary warning `0` 或全部可解释。
- 50-case main：schema valid rate `>= 95%`。
- 50-case main：invalid evidence ID mean = `0`。
- 50-case main：UCA catalog consistency = `1.0`。
- CF overall directional consistency `>= 0.90`。
- requirement candidates 以 taxonomy 形式汇总。
- expert-preview labels 覆盖 50 cases。
- 明确列出进入真实 human annotation 的争议案例。

## 17. 同意执行后的第一步

用户同意后，我将按以下顺序开始：

1. 修改 `stpa_hf_dan_eswa_engine_final.py` 的 prompt guardrail、audit strength 和 CF template。
2. 新增 taxonomy summary 和 50-case sampler。
3. 新增 PowerShell paper pipeline。
4. 跑 30-case repair。
5. 若 repair 通过，再构建并跑 50-case。
6. 作为 Expert-0 生成 preview annotation。
7. 输出完整复盘报告。

