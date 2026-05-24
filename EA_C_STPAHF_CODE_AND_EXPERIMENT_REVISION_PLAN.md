# EA-C-STPA-HF 代码与实验修订计划

日期：2026-05-03  
目标：将现有 STPA-HF LLM pipeline 修订为符合 EA-C-STPA-HF 论文叙事的代码、输出与实验体系  
主代码文件：`stpa_hf_dan_eswa_engine_final.py`  
数据摄入文件：`external_case_ingestion_final.py`

## 1. 当前代码状态判断

当前代码已经具备以下基础能力：

- functional case 构建；
- 5 轮 LLM 推理；
- boundary、vulnerability、UCA 输出；
- evidence packet；
- evidence audit；
- baseline suite；
- counterfactual generation / evaluation；
- feedback gap report；
- requirement candidates；
- paper manifest；
- 50-case mixed-source runner。

当前主要不足：

1. STPA-HF 的驾驶员过程模型尚未显式化。
2. `feedback_gap_report` 仍偏字段缺失，未升级为 STPA-HF 机制阻断分析。
3. `requirement_candidates` 容易被误解为最终 HMI 设计要求。
4. 缺少 `process_model_observability_report`。
5. 缺少 `claim_admissibility_report`。
6. 缺少 `conditional_scenario_bundle` 与条件化 HMI 改进输出。
7. baseline / ablation 尚未包含 “去掉 observability gate”。
8. human expert annotation 尚未围绕 EA-C-STPA-HF 新定义重写。
9. 结果目录仍带有 ESWA 旧叙事痕迹，需要新一轮 paper root。

## 2. 新一轮代码目标

代码要服务以下论文主张：

> EA-C-STPA-HF 不是从稀疏报告中推断真实驾驶员心理，而是判断公开证据是否足以支持 STPA-HF human-automation mechanism claims；当关键条件被显式注入时，再执行条件化驾驶员过程模型与 HMI 改进分析。

因此代码输出必须从：

```text
bundle + feedback gaps + requirement candidates
```

升级为：

```text
evidence-admissible accident factor coding bundle
+ process_model_observability_report
+ claim_admissibility_report
+ blocked_stpa_hf_claim_report
+ evidence_logging_requirement_candidates
+ conditional_scenario_bundle
+ conditional_hmi_improvement_candidates
```

## 3. 新结果目录

建议新建结果根目录：

```text
results/ea_c_stpahf_v1/
```

建议子目录：

```text
results/ea_c_stpahf_v1/
  manifest/
  input_audit/
  missingness/
  bundles/
  process_model_observability/
  claim_admissibility/
  blocked_claims/
  evidence_audit/
  evidence_logging_requirements/
  baseline_suite/
  ablations/
  conditional_scenarios/
  conditional_bundles/
  conditional_hmi_candidates/
  cf_eval/
  annotation_packets/
  expert_preview/
  tables/
  reports/
```

旧目录 `results/paper_v1_50_mixed_sources/` 保留为上一轮结果，不作为新叙事的最终目录。

## 4. 数据与 case schema 修订

### 4.1 新增 case-level 字段

在 functional case 中新增或标准化：

```json
{
  "source_regime": "official_ca_dmv_disengagement_csv",
  "reported_outcome": {
    "event_type": "disengagement",
    "collision": false,
    "intervention": true,
    "source_evidence_ids": []
  },
  "evidence_regime": {
    "has_hmi_evidence": false,
    "has_driver_state_evidence": false,
    "has_ads_transition_evidence": true,
    "has_internal_ads_evidence": false
  },
  "analysis_mode": "base_report"
}
```

### 4.2 provenance 约束

所有 evidence item 必须有：

```json
{
  "evidence_id": "E1",
  "field": "CAR.reported_intervention",
  "value": "...",
  "provenance": "reported",
  "source_text": "...",
  "source_regime": "..."
}
```

允许 provenance：

- `reported`；
- `derived`；
- `not_reported`；
- `counterfactual`。

### 4.3 条件化场景标记

conditional cases 必须显式标记：

```json
{
  "analysis_mode": "specified_scenario",
  "base_case_id": "...",
  "conditional_assumption_ids": [],
  "conditional_scope": "HMI takeover cue and driver time-budget awareness"
}
```

## 5. Bundle schema 修订

### 5.1 新 bundle 顶层结构

建议 bundle summary 增加：

```json
{
  "schema_version": "ea_c_stpahf_v1.0",
  "bundle_type": "evidence_admissible_accident_factor_coding_bundle",
  "analysis_mode": "base_report",
  "reported_outcome": {},
  "stpa_hf_boundary": {},
  "process_model_observability": {},
  "claim_admissibility": {},
  "blocked_mechanism_claims": [],
  "admissible_accident_factor_codes": [],
  "conditional_claims": [],
  "evidence_logging_requirements": []
}
```

### 5.2 保留旧字段

为了兼容上一轮结果，保留：

- `boundary_state`；
- `update_vulnerability`；
- `active_uca_set`；
- `dominant_uca`；
- `mechanism_trace`；
- `evidence_ids`。

但论文表格优先读取新字段。

## 6. 新模块 1：process_model_observability_report

### 6.1 功能

判断公开报告是否支持 7 个 STPA-HF 过程模型维度。

维度：

- `mode_awareness`；
- `capability_boundary_awareness`；
- `hazard_salience`；
- `time_budget_awareness`；
- `responsibility_allocation`；
- `expected_ads_action`；
- `intervention_feasibility`。

### 6.2 输出字段

每个 case 输出：

```json
{
  "case_id": "...",
  "source_regime": "...",
  "analysis_mode": "base_report",
  "dimensions": [
    {
      "dimension": "time_budget_awareness",
      "required_evidence": [
        "HMI.time_budget_indicator",
        "CAR.time_budget_to_handover"
      ],
      "observed_evidence_ids": [],
      "evidence_status": "not_reported",
      "observability_level": "not_observable",
      "blocked_claims": [
        "driver_had_clear_takeover_time_budget",
        "failed_takeover_despite_clear_time_budget"
      ],
      "minimal_evidence_to_unblock": [
        "timestamped takeover request",
        "displayed time budget",
        "driver response time"
      ]
    }
  ]
}
```

### 6.3 聚合输出

生成：

- `process_model_observability_report.json`；
- `process_model_observability_summary.csv`；
- `process_model_observability_by_source.json`；
- `process_model_observability_table.md`。

### 6.4 CLI 命令

新增：

```powershell
python stpa_hf_dan_eswa_engine_final.py process-model-observability `
  --cases data/cases/ea_c_stpahf_main_v1.jsonl `
  --bundle-dir results/ea_c_stpahf_v1/bundles `
  --out results/ea_c_stpahf_v1/process_model_observability
```

## 7. 新模块 2：claim_admissibility_report

### 7.1 功能

将 mechanism claim 分为：

- `admissible`；
- `weakly_supported`；
- `blocked`；
- `counterfactual_only`。

### 7.2 claim catalog

第一版 claim catalog：

```text
takeover_demand_occurred
driver_failed_to_take_over
hmi_ambiguity_contributed
hmi_capability_boundary_hint_missing_or_unclear
driver_process_model_update_failed
driver_misinterpreted_feedback
ads_support_withdrawal_occurred
responsibility_transfer_occurred
intervention_was_feasible
intervention_was_delayed
```

### 7.3 输出字段

```json
{
  "case_id": "...",
  "claims": [
    {
      "claim_id": "driver_failed_to_take_over",
      "admissibility": "blocked",
      "supporting_evidence_ids": [],
      "blocking_reason": "No reported takeover demand, time budget, driver response, or intervention timeline.",
      "required_evidence_to_support": [
        "reported takeover request",
        "handover time budget",
        "driver response evidence",
        "manual intervention timeline"
      ],
      "related_pm_dimensions": [
        "time_budget_awareness",
        "responsibility_allocation",
        "intervention_feasibility"
      ]
    }
  ]
}
```

### 7.4 CLI 命令

新增：

```powershell
python stpa_hf_dan_eswa_engine_final.py claim-admissibility-report `
  --cases data/cases/ea_c_stpahf_main_v1.jsonl `
  --bundle-dir results/ea_c_stpahf_v1/bundles `
  --observability results/ea_c_stpahf_v1/process_model_observability/process_model_observability_report.json `
  --out results/ea_c_stpahf_v1/claim_admissibility
```

## 8. 新模块 3：blocked_stpa_hf_claim_report

### 8.1 功能

将 feedback gaps 升级为 STPA-HF 机制阻断报告。

不只输出：

```text
HMI.time_budget_indicator missing
```

而输出：

```text
Because HMI.time_budget_indicator and CAR.time_budget_to_handover are not reported, claims about clear driver time-budget awareness and failed takeover despite adequate warning are blocked.
```

### 8.2 输出

- blocked claim counts；
- blocked claim by source regime；
- top evidence slots blocking stronger claims；
- blocked claim taxonomy；
- representative examples。

### 8.3 CLI 命令

新增：

```powershell
python stpa_hf_dan_eswa_engine_final.py blocked-stpahf-claim-report `
  --claim-admissibility results/ea_c_stpahf_v1/claim_admissibility/claim_admissibility_report.json `
  --observability results/ea_c_stpahf_v1/process_model_observability/process_model_observability_report.json `
  --out results/ea_c_stpahf_v1/blocked_claims
```

## 9. 修订模块 4：evidence_logging_requirement_candidates

### 9.1 命名修订

保留旧命令：

```text
requirement-candidates
```

新增推荐命令：

```text
evidence-logging-requirements
```

### 9.2 定义

Evidence/logging requirement candidates 是：

> 为支持未来更强 STPA-HF 机制 claim，事故报告、测试日志、HMI 日志或 ADS 内部日志应记录的证据项。

它们不是最终 HMI 设计要求。

### 9.3 输出字段

```json
{
  "case_id": "...",
  "missing_evidence_slot": "HMI.time_budget_indicator",
  "blocked_stronger_claim": "driver_had_clear_takeover_time_budget",
  "candidate_evidence_requirement": "Future reports should record whether a takeover time budget was displayed and the displayed duration.",
  "requirement_type": "hmi_log",
  "supports": [
    "time_budget_awareness",
    "responsibility_allocation"
  ],
  "priority": "high",
  "source_regime": "official_nhtsa_crash_csv"
}
```

### 9.4 汇总输出

- taxonomy summary；
- source-regime summary；
- top blocked claims；
- representative examples；
- table-ready CSV。

## 10. 新模块 5：conditional_scenario_bundle

### 10.1 功能

对显式注入条件的场景执行条件化 STPA-HF 分析。

### 10.2 输入模板

建议第一版模板：

```text
cf_hmi_takeover_demand
cf_hmi_ambiguous_degradation_no_transition
cf_hmi_ambiguous_degradation_with_transition_pressure
cf_hmi_full_support
cf_hmi_partial_support
cf_driver_distracted
cf_driver_attentive
cf_clear_time_budget
cf_absent_time_budget
cf_ads_perception_confidence_drop
cf_intervention_feasible
cf_intervention_not_feasible
```

### 10.3 输出字段

```json
{
  "case_id": "...",
  "base_case_id": "...",
  "analysis_mode": "specified_scenario",
  "injected_conditions": [],
  "conditional_pm_update": [],
  "conditional_boundary": "...",
  "conditional_uca_set": [],
  "conditional_hmi_improvement_candidates": [],
  "must_not_be_interpreted_as_real_event": true
}
```

### 10.4 新 evaluation

新增：

- process-model observability lift；
- boundary direction match；
- UCA direction match；
- conditional candidate consistency；
- invalid conditional bundle count。

## 11. Prompt 修订计划

### 11.1 system prompt 新增原则

必须加入：

```text
Do not infer true driver mental state from sparse public reports.
Do not infer HMI behavior unless reported or explicitly counterfactual.
Separate reported outcome from mechanism claims.
Classify process-model claims by admissibility.
Use conditional labels for injected scenario assumptions.
```

### 11.2 Base-report prompt

要求 LLM 输出：

- reported outcome；
- process-model observability；
- admissible claims；
- blocked claims；
- boundary；
- UCA；
- evidence ids；
- minimal evidence needed。

### 11.3 Conditional prompt

要求 LLM 输出：

- injected condition use；
- conditional PM update；
- conditional UCA；
- conditional HMI candidate；
- warning that output is not real accident inference。

## 12. Ablation 修订

新增 ablation 条件：

### 12.1 no_evidence_gate

去掉 claim admissibility gate，观察 outcome-to-mechanism overcoding 是否上升。

### 12.2 no_observability_gate

不做 process-model observability，直接让模型输出 driver/HMI mechanism。

预期：

- blocked claims 下降；
- unsupported strong-boundary warnings 上升；
- NS 边界可能上升。

### 12.3 no_update

保留上一轮 no_update，用于证明 process-model update stage 对 schema robustness 和 UCA consistency 有贡献。

### 12.4 conditional_without_label

不给 conditional 标签，让模型处理注入证据，检查是否会把 counterfactual 回写成 reported evidence。

这是检测 provenance leakage 的重要 ablation。

## 13. Human expert annotation 修订

### 13.1 新标注任务

人工专家不标注真实事故原因，而标注：

> Given the public evidence, which STPA-HF claims are admissible, weakly supported, blocked, or conditional?

### 13.2 标注字段

每个 case：

- reported outcome；
- boundary label；
- process-model observability level for 7 dimensions；
- admissible claims；
- blocked claims；
- active UCA set；
- dominant UCA；
- insufficient information flags；
- supporting evidence IDs；
- required evidence to unblock top claims。

### 13.3 标注者数量

最低：

- 2 名人工标注者；
- 1 名 adjudicator。

可先用 Codex Expert-0 做 preview，但不能作为 publication gold。

### 13.4 输出

```text
data/annotations/ea_c_stpahf_v1/raw_annotator_a.jsonl
data/annotations/ea_c_stpahf_v1/raw_annotator_b.jsonl
data/annotations/ea_c_stpahf_v1/adjudicated_gold.jsonl
results/ea_c_stpahf_v1/human_eval/agreement_summary.json
```

## 14. 数据计划

### 14.1 推荐主实验数据

优先使用自动驾驶相关度更强的数据：

- CA DMV collision：30-40；
- CA DMV disengagement：30-40；
- NHTSA SGO ADS-only：20，作为 sparse crash-report stress test。

如暂时不能解析更多 CA DMV collision PDF，可先保持：

- CA DMV disengagement 为主；
- NHTSA ADS-only 为辅助；
- third-party CA DMV collision augmented 标注为 supplemental。

### 14.2 数据边界

必须区分：

- official CA DMV disengagement；
- official CA DMV collision PDF derived；
- third-party CA DMV collision augmented；
- official NHTSA ADS；
- official NHTSA L2 ADAS。

不要把 L2 ADAS 与 ADS 混作同一机制 regime。

## 15. 新 pipeline 执行顺序

### Phase 0：数据冻结

```powershell
python stpa_hf_dan_eswa_engine_final.py sample-ea-cases `
  --out data/cases/ea_c_stpahf_main_v1.jsonl `
  --n-ca-collision 30 `
  --n-ca-disengagement 30 `
  --n-nhtsa-ads 20
```

如果该命令尚未实现，则先用现有 sampler 生成，并在 manifest 中记录 composition。

### Phase 1：输入审计

```powershell
python stpa_hf_dan_eswa_engine_final.py input-audit `
  --cases data/cases/ea_c_stpahf_main_v1.jsonl `
  --out results/ea_c_stpahf_v1/input_audit
```

### Phase 2：missingness profile

```powershell
python stpa_hf_dan_eswa_engine_final.py missingness-profile `
  --cases data/cases/ea_c_stpahf_main_v1.jsonl `
  --out results/ea_c_stpahf_v1/missingness
```

### Phase 3：full EA-C-STPA-HF run

```powershell
python stpa_hf_dan_eswa_engine_final.py run `
  --cases data/cases/ea_c_stpahf_main_v1.jsonl `
  --out results/ea_c_stpahf_v1/bundles
```

### Phase 4：process-model observability

```powershell
python stpa_hf_dan_eswa_engine_final.py process-model-observability `
  --cases data/cases/ea_c_stpahf_main_v1.jsonl `
  --bundle-dir results/ea_c_stpahf_v1/bundles `
  --out results/ea_c_stpahf_v1/process_model_observability
```

### Phase 5：claim admissibility

```powershell
python stpa_hf_dan_eswa_engine_final.py claim-admissibility-report `
  --cases data/cases/ea_c_stpahf_main_v1.jsonl `
  --bundle-dir results/ea_c_stpahf_v1/bundles `
  --observability results/ea_c_stpahf_v1/process_model_observability/process_model_observability_report.json `
  --out results/ea_c_stpahf_v1/claim_admissibility
```

### Phase 6：blocked STPA-HF claims

```powershell
python stpa_hf_dan_eswa_engine_final.py blocked-stpahf-claim-report `
  --claim-admissibility results/ea_c_stpahf_v1/claim_admissibility/claim_admissibility_report.json `
  --observability results/ea_c_stpahf_v1/process_model_observability/process_model_observability_report.json `
  --out results/ea_c_stpahf_v1/blocked_claims
```

### Phase 7：evidence audit

```powershell
python stpa_hf_dan_eswa_engine_final.py evidence-audit `
  --bundle-dir results/ea_c_stpahf_v1/bundles `
  --out results/ea_c_stpahf_v1/evidence_audit
```

### Phase 8：evidence/logging requirements

```powershell
python stpa_hf_dan_eswa_engine_final.py evidence-logging-requirements `
  --blocked-claims results/ea_c_stpahf_v1/blocked_claims/blocked_stpa_hf_claim_report.json `
  --observability results/ea_c_stpahf_v1/process_model_observability/process_model_observability_report.json `
  --out results/ea_c_stpahf_v1/evidence_logging_requirements
```

### Phase 9：baseline suite

```powershell
python stpa_hf_dan_eswa_engine_final.py baseline-suite `
  --cases data/cases/ea_c_stpahf_main_v1.jsonl `
  --out results/ea_c_stpahf_v1/baseline_suite
```

### Phase 10：new ablations

```powershell
python stpa_hf_dan_eswa_engine_final.py ablation-suite `
  --cases data/cases/ea_c_stpahf_main_v1.jsonl `
  --conditions no_update,no_evidence_gate,no_observability_gate,conditional_without_label `
  --out results/ea_c_stpahf_v1/ablations
```

### Phase 11：conditional scenario generation

```powershell
python stpa_hf_dan_eswa_engine_final.py generate-conditional-scenarios `
  --cases data/cases/ea_c_stpahf_main_v1.jsonl `
  --out results/ea_c_stpahf_v1/conditional_scenarios/conditional_cases.jsonl
```

### Phase 12：conditional run

```powershell
python stpa_hf_dan_eswa_engine_final.py run `
  --cases results/ea_c_stpahf_v1/conditional_scenarios/conditional_cases.jsonl `
  --out results/ea_c_stpahf_v1/conditional_bundles
```

### Phase 13：conditional evaluation

```powershell
python stpa_hf_dan_eswa_engine_final.py conditional-eval `
  --base-bundle-dir results/ea_c_stpahf_v1/bundles `
  --conditional-bundle-dir results/ea_c_stpahf_v1/conditional_bundles `
  --conditional-cases results/ea_c_stpahf_v1/conditional_scenarios/conditional_cases.jsonl `
  --out results/ea_c_stpahf_v1/cf_eval
```

### Phase 14：annotation packets

```powershell
python stpa_hf_dan_eswa_engine_final.py annotation-packets `
  --cases data/cases/ea_c_stpahf_main_v1.jsonl `
  --bundle-dir results/ea_c_stpahf_v1/bundles `
  --observability results/ea_c_stpahf_v1/process_model_observability/process_model_observability_report.json `
  --claim-admissibility results/ea_c_stpahf_v1/claim_admissibility/claim_admissibility_report.json `
  --out results/ea_c_stpahf_v1/annotation_packets
```

### Phase 15：paper summary

```powershell
python stpa_hf_dan_eswa_engine_final.py paper-summary `
  --root results/ea_c_stpahf_v1 `
  --out results/ea_c_stpahf_v1/reports/ea_c_stpahf_summary.json
```

## 16. 论文表格生成

新增或修订命令：

```powershell
python stpa_hf_dan_eswa_engine_final.py export-paper-tables `
  --root results/ea_c_stpahf_v1 `
  --out results/ea_c_stpahf_v1/tables
```

应生成：

- `table1_dataset_missingness.csv`；
- `table2_process_model_observability.csv`；
- `table3_generation_quality.csv`；
- `table4_baseline_overcoding.csv`；
- `table5_ablation.csv`；
- `table6_claim_admissibility.csv`；
- `table7_conditional_sensitivity.csv`；
- `table8_requirements_taxonomy.csv`；
- `table9_human_eval.csv`。

## 17. 验收标准

### 17.1 代码验收

- 新命令可运行；
- 输出 JSON schema 稳定；
- 所有 bundle 都包含 analysis_mode；
- base-report bundle 不包含未标注的 counterfactual evidence；
- conditional bundle 必须带 conditional label；
- old commands 仍可兼容。

### 17.2 主实验验收

最低标准：

- main cases >= 60；
- full system schema valid >= 95%；
- invalid evidence ID mean = 0；
- UCA catalog consistency = 1.0；
- unsupported strong-boundary warning 接近 0；
- direct baseline 的 NS/strong mechanism overcoding 明显高于 full system；
- process-model observability report 覆盖率 = 100% cases；
- claim admissibility report 覆盖率 = 100% cases；
- conditional scenario schema valid >= 95%；
- conditional directional consistency >= 90%。

### 17.3 论文验收

- 每个 contribution 都有对应实验；
- 每个 RQ 都有对应表格；
- 不出现真实事故因果重建 claim；
- 不出现真实驾驶员心理推断 claim；
- 不把 evidence/logging requirements 写成 final HMI design；
- conditional HMI candidates 全部标注 conditional。

## 18. 实施优先级

### P0：术语与报告层修订

1. 新增 `process-model-observability`。
2. 新增 `claim-admissibility-report`。
3. 新增 `blocked-stpahf-claim-report`。
4. 将 `requirement-candidates` 增加别名 `evidence-logging-requirements`。

### P1：bundle schema 与 prompt 修订

1. 增加 `schema_version = ea_c_stpahf_v1.0`。
2. 增加 `analysis_mode`。
3. 增加 outcome-mechanism separation。
4. 增加 process-model observability prompt。
5. 增加强 claim admissibility rules。

### P2：conditional scenario mode

1. 生成 conditional scenario cases。
2. conditional run。
3. conditional evaluation。
4. conditional HMI candidates。

### P3：new ablations

1. no_evidence_gate。
2. no_observability_gate。
3. conditional_without_label。
4. no_update 继续保留。

### P4：human annotation

1. 更新 annotation guide。
2. 生成 EA-C-STPA-HF 标注包。
3. Expert-0 preview。
4. 等待真实人工标注。

### P5：paper-ready summaries

1. paper manifest。
2. table export。
3. main run report。
4. limitation report。
5. appendix examples。

## 19. 下一轮执行建议

第一轮不要直接跑 80-case 主实验。先做一个 15-case repair pilot：

- 5 CA DMV disengagement；
- 5 CA DMV collision；
- 5 NHTSA ADS-only。

确认：

- process-model observability 输出是否合理；
- claim admissibility 是否保守但不空洞；
- blocked claims 是否能解释清楚；
- conditional scenario 是否能生成有用 HMI candidates。

通过后再扩展到 60-80 cases。

## 20. 关键风险与对策

### 风险 1：结果显得只是“证据不足”

对策：

- 把 missingness 解释为 process-model observability 与 blocked mechanism claim；
- 展示不同数据源证据制度差异；
- 展示 conditional scenario 中补入条件后的分析能力。

### 风险 2：HMI 改进建议被质疑无效

对策：

- Base-report mode 只输出 evidence/logging requirements；
- HMI improvement candidates 只在 conditional mode 输出；
- 所有 HMI candidates 需要引用 injected condition。

### 风险 3：STPA-HF 特色不明显

对策：

- 显式输出 7 个 process-model observability dimensions；
- 显示 update vulnerability 与 UCA 如何由这些维度约束；
- 加入 no_observability_gate ablation。

### 风险 4：LLM 仍然 hallucinate

对策：

- evidence audit；
- provenance leakage audit；
- claim admissibility report；
- unsupported strong-boundary warning；
- conditional label audit。

## 21. 最终代码目标

下一轮完成后，代码应能回答：

1. 公开报告支持哪些 STPA-HF 驾驶员过程模型维度？
2. 哪些事故因素 claim 是 admissible？
3. 哪些强机制 claim 被阻断？
4. 直接 LLM 是否会 overcode？
5. 去掉 STPA-HF evidence/process-model gate 后会发生什么？
6. 显式补入 HMI/driver/ADS 条件后，系统是否能执行条件化驾驶员模型分析？
7. 哪些证据/日志记录能让未来分析更强？

这些答案共同支撑 EA-C-STPA-HF 论文叙事。
