# AAP-STPA-HF 论文叙事对齐后的代码与实验完整修改计划

日期：2026-05-10  
目标期刊定位：优先面向 Accident Analysis & Prevention，ESWA 作为技术专家系统备选  
主代码文件：`stpa_hf_dan_eswa_engine_final.py`  
数据摄入文件：`external_case_ingestion_final.py`  
当前方法名建议：STPA-HF-guided LLM Reasoning Graph for Human-Supervised Automated-Driving Incidents  
中文简称：STPA-HF 约束的事故文本解释链生成方法

---

## 1. 当前核心判断

当前旧叙事存在一个关键理论问题：系统把驾驶员过程模型的四象限、update vulnerability 和 UCA 之间做成了过于固定的链条，容易变成：

```text
某个四象限标签 -> 某个 vulnerability -> 某个 UCA
```

这不符合 STPA-HF。更严格的 STPA-HF 链条应为：

```text
事故文本证据
-> narrative propositions
-> driver process-model context:
   CPS / CPB / OPS / OPB
-> process-model update analysis
-> other factors analysis
-> control-action selection
-> UCA-in-context classification
-> ranked explanatory pathways
```

因此，下一轮代码目标不是扩大样本，而是先把理论链条改正确。

---

## 2. 新论文落点

本文不主张：

- 还原真实事故原因。
- 推断真实驾驶员心理。
- 证明真实 HMI 导致事故。
- 验证某个最终 HMI 设计方案有效。

本文主张：

> 提出一种 STPA-HF 约束的 LLM reasoning graph 方法，将人机共驾自动驾驶事故/接管文本转化为 evidence-conditioned driver process-model context、process-model update vulnerability、other-factor-conditioned control-action selection，以及 UCA-in-context ranked explanatory pathways。

更直白地说：

> 我们不是让 LLM 猜事故真因，而是让 LLM 在 STPA-HF 的结构和证据边界内，生成多条可审计、可排序、可反事实检验的驾驶员控制行为解释链。

---

## 3. 论文核心贡献

### Contribution 1：面向稀疏事故文本的 STPA-HF 方法适配

传统 STPA-HF 通常需要较完整的系统设计、反馈、驾驶员状态、HMI、日志和时序信息。公开事故报告往往只有 ENV、ACTOR、CAR、outcome 和少量 narrative。

本文将 STPA-HF 从完整事故建模方法适配为：

```text
evidence-conditioned explanatory pathway analysis under sparse incident text
```

核心不是补出缺失事实，而是判断：

- 哪些 process-model context 有文本证据支持？
- 哪些 update process 能够被文本支持？
- 哪些 other factors 能够影响动作选择？
- 哪些 UCA-in-context 解释链是可接受、弱支持或被阻断的？

### Contribution 2：LLM 结构化 reasoning graph，而不是单链 CoT

系统不输出一条不可审计的自然语言推理，而是输出 typed reasoning graph：

```text
Evidence Node
-> PM Context Node
-> Update Process Node
-> Other Factors Node
-> Control Action Selection Node
-> UCA Context Node
-> Outcome Compatibility Node
-> Pathway Score Node
```

每个 node 和 edge 都必须有：

- evidence IDs
- internal reasoning text
- claim strength
- missingness notes
- STPA-HF type constraint

### Contribution 3：UCA-in-context 的多路径解释与排序

一个事故文本可以支持多条解释路径。本文不强制一个 case 对应一个 quadrant 或一个唯一 UCA，而是生成多个 candidate pathways，并用 LLM judge 按结构化 rubric 排序。

路径得分解释为：

```text
evidence-conditioned explanatory plausibility
```

不是：

```text
真实因果概率
```

### Contribution 4：HMI feedback injection sensitivity

真实事故报告中 HMI 证据很少。本文不把 HMI 缺失当作失败，而是设计指定条件实验：

```text
在同一事故文本场景中，显式注入不同 HMI feedback cues，
观察 process-model update、control-action selection、UCA pathway score 如何变化。
```

该实验的作用是 mechanism sensitivity，不是真实 HMI 因果验证。

---

## 4. 研究问题

### RQ1：可审计解释链生成能力

系统能否从人机共驾自动驾驶事故/接管文本中生成 schema-valid、evidence-grounded、STPA-HF-consistent 的 reasoning graph 和 ranked explanatory pathways？

对应指标：

- schema valid rate
- invalid evidence ID count
- graph node completeness
- graph edge evidence coverage
- UCA catalog consistency
- unsupported strong-claim warning count

### RQ2：STPA-HF 结构约束是否减少过度推断

相比 direct LLM 和 generic CoT，STPA-HF reasoning graph 是否减少从 collision/disengagement outcome 直接升级到 takeover failure、HMI failure 或 driver failure 的过度推断？

对应指标：

- outcome-to-mechanism overcoding rate
- not_supported_transfer over-escalation rate
- unsupported UCA activation rate
- direct/generic/full comparison
- no_update/no_other_factors/no_action_selection ablation

### RQ3：HMI feedback 在解释链中作用于哪些环节

在同一事故文本 seed 下，注入不同 HMI feedback cues 后，系统是否能按 STPA-HF 理论方向改变：

- process-model update clarity
- update vulnerability
- control-action selection clarity
- UCA activation/suppression
- unsafe pathway score

对应指标：

- unsafe pathway score delta
- vulnerability shift
- action selection clarity lift
- UCA activation/suppression change
- judge directional consistency

---

## 5. 代码修改总原则

### 5.1 内部传输必须是详细文本

代码中必须区分：

```text
internal_reasoning_text
display_summary
```

规则：

- `internal_reasoning_text` 给下一轮 LLM、judge、pathway builder 使用，必须详细。
- `display_summary` 只用于外部展示、表格、简短报告。
- 下游 prompt 禁止把 `display_summary` 当作主要推理输入。
- 如果只有 yes/no 或短标签，不允许进入下一阶段推理。

每个 reasoning node 至少包含：

```json
{
  "node_id": "...",
  "node_type": "...",
  "internal_reasoning_text": "...",
  "display_summary": "...",
  "supporting_evidence_ids": [],
  "claim_strength": "supported | weakly_supported | blocked",
  "missingness_notes": []
}
```

### 5.2 不允许固定 quadrant-to-UCA 映射

必须删除或废弃：

- `primary_quadrant`
- `pm_quadrant_mismatch`
- `quadrant -> vulnerability -> UCA` 固定链条

改为：

```text
CPS / CPB / OPS / OPB 共同形成 process-model context；
process-model update 和 other factors 共同影响 control-action selection；
UCA 只在 action + context 下被分类。
```

### 5.3 UCA 必须是 action-in-context

每个 UCA 必须表达为：

```text
controller + control action + unsafe context + STPA UCA type + hazard link
```

禁止：

```text
collision happened -> driver failed to takeover
```

允许：

```text
The test driver did not initiate manual takeover when the text-supported context indicates explicit autonomy disengagement and feasible intervention; this is classified as not_provided_when_required only if intervention/timing evidence supports that context.
```

---

## 6. 新 Bundle Schema

建议 schema version：

```text
stpa_hf_reasoning_graph_v2.0
```

顶层结构：

```json
{
  "schema_version": "stpa_hf_reasoning_graph_v2.0",
  "case_id": "...",
  "analysis_mode": "base_report | hmi_injection",
  "source_regime": "...",
  "reported_outcome": {},
  "evidence_packet": {},
  "narrative_propositions": [],
  "pm_context_synthesis": {},
  "process_model_update_analysis": {},
  "other_factors_analysis": {},
  "commitment_boundary": {},
  "control_action_selection": {},
  "uca_context_classification": {},
  "reasoning_graph": {},
  "ranked_explanatory_pathways": {},
  "evidence_audit": {},
  "display_summary": {}
}
```

---

## 7. 关键模块修改

### 7.1 Narrative Evidence Mining

当前已有 narrative mining，但输出仍可能太短。下一轮要改成：

```json
{
  "proposition_id": "N1",
  "source_span": "...",
  "normalized_proposition": "...",
  "stpa_hf_relevance": {
    "pm_dimensions": ["CPS", "CPB"],
    "possible_update_trigger": true,
    "possible_other_factor": false,
    "possible_control_action_evidence": true
  },
  "internal_reasoning_text": "...",
  "display_summary": "..."
}
```

要求：

- 从事故文本中抽取具体句子和事实命题。
- 不把命题压缩成 yes/no。
- 必须保留原文 span 或 source text。
- 必须说明该命题可能支持哪个 STPA-HF 环节。

### 7.2 PM Context Synthesis

新增或重写 `pm_context_synthesis`。

输出：

```json
{
  "pm_context_nodes": [
    {
      "node_id": "PM-CPS-1",
      "dimension": "CPS",
      "dimension_definition": "Controlled Process States",
      "context_hypothesis": "...",
      "internal_reasoning_text": "...",
      "display_summary": "...",
      "supporting_evidence_ids": [],
      "contradicting_evidence_ids": [],
      "missing_evidence_ids": [],
      "claim_strength": "supported | weakly_supported | blocked"
    }
  ],
  "integrated_pm_context_text": "..."
}
```

注意：

- 四象限都要被考虑。
- 一个 case 可以有多个象限共同贡献。
- 不选 `top quadrant` 作为主要解释。
- 每个象限不是标签，而是驾驶员过程模型上下文的一部分。

### 7.3 Process Model Update Analysis

新增 `process_model_update_analysis`。

作用：

```text
分析事故文本中哪些 feedback/input 可能触发驾驶员过程模型更新，
以及更新是否存在 missed/ambiguous/misinterpreted vulnerability。
```

输出：

```json
{
  "update_process_nodes": [
    {
      "node_id": "UPD-1",
      "target_pm_dimensions": ["CPS", "CPB"],
      "triggering_evidence_ids": [],
      "feedback_or_input_text": "...",
      "update_need": "...",
      "update_path": {
        "availability": "reported | not_reported | unclear",
        "salience": "high | medium | low | not_reported",
        "timing": "reported | not_reported | unclear",
        "interpretability": "clear | partial | ambiguous | not_reported",
        "consistency": "consistent | conflicting | not_reported"
      },
      "update_vulnerability_type": "none | missed_feedback | ambiguous_feedback | misinterpreted_feedback",
      "internal_reasoning_text": "...",
      "display_summary": "...",
      "claim_strength": "supported | weakly_supported | blocked",
      "missingness_notes": []
    }
  ]
}
```

定义：

- `missed_feedback`：需要反馈但反馈缺失、未报告、不可得，导致更新不能被支持。
- `ambiguous_feedback`：反馈存在或场景存在退化压力，但反馈不足以区分具体状态/责任/时序。
- `misinterpreted_feedback`：文本支持反馈与后续动作/状态之间存在冲突或错误解释可能。

### 7.4 Other Factors Analysis

新增 `other_factors_analysis`。

定义：

```text
Other factors 是影响驾驶员 control-action selection 的条件，
但不是驾驶员过程模型内容本身。
```

候选类型：

- time pressure
- workload
- driver role
- test protocol
- manual fallback availability
- traffic pressure
- maneuver constraint
- safe stop target
- control authority availability
- distraction or impairment if reported

输出：

```json
{
  "other_factor_nodes": [
    {
      "node_id": "OF-1",
      "factor_type": "time_pressure",
      "description": "...",
      "supporting_evidence_ids": [],
      "effect_on_action_selection": "...",
      "internal_reasoning_text": "...",
      "display_summary": "...",
      "claim_strength": "supported | weakly_supported | blocked"
    }
  ],
  "missing_other_factors": [
    {
      "factor_type": "driver_distraction",
      "missing_reason": "not reported in source text"
    }
  ]
}
```

禁止：

- 把 other factors 直接变成 UCA。
- 把缺失的 distraction、pressure、workload 补成事实。

### 7.5 Commitment Boundary

保留三类 boundary，但重新定位为 responsibility/readiness rating：

```text
supported_monitoring
contingent_readiness
not_supported_transfer
```

解释：

- `supported_monitoring`：文本支持 ADS 仍处于可监控支持状态。
- `contingent_readiness`：文本支持存在退化、风险或不确定性，需要形成接管准备。
- `not_supported_transfer`：文本明确报告接管、干预、脱离、控制权转移或支持撤回。

注意：

- boundary 是控制责任/准备度状态，不是事故严重度。
- collision alone 不得推出 `not_supported_transfer`。
- disengagement 也要看是否是安全干预、测试流程、系统脱离、手动清除错误等具体文本。

### 7.6 Control Action Selection

新增 `control_action_selection`。

作用：

```text
在 PM context、update process、other factors 和 boundary 的共同条件下，
分析驾驶员可能/期望/实际采取的控制动作。
```

输出：

```json
{
  "action_selection_nodes": [
    {
      "node_id": "ACT-1",
      "candidate_action": "continue_monitoring | prepare_takeover | initiate_takeover | brake | steer | safe_stop | manual_fallback | no_action_reported",
      "action_role": "observed | expected | omitted | alternative",
      "selection_context": "...",
      "pm_context_inputs": ["PM-CPS-1", "PM-CPB-1"],
      "update_process_inputs": ["UPD-1"],
      "other_factor_inputs": ["OF-1"],
      "supporting_evidence_ids": [],
      "internal_reasoning_text": "...",
      "display_summary": "...",
      "claim_strength": "supported | weakly_supported | blocked"
    }
  ]
}
```

这是 STPA-HF 中从人类控制器模型进入 UCA 的关键中间层。

### 7.7 UCA Context Classification

重写 `uca_context_classification`。

输出：

```json
{
  "uca_context_nodes": [
    {
      "node_id": "UCACTX-1",
      "uca_id": "UCA-...",
      "controller": "test_driver | safety_operator | driver",
      "control_action": "...",
      "stpa_uca_type": "not_provided_when_required | provided_when_not_appropriate | too_early_too_late_or_wrong_order | wrong_duration_or_stopped_too_soon",
      "unsafe_context_text": "...",
      "hazard_link": "...",
      "action_selection_node_ids": ["ACT-1"],
      "supporting_evidence_ids": [],
      "internal_reasoning_text": "...",
      "display_summary": "...",
      "classification": "activated | suppressed | blocked",
      "claim_strength": "supported | weakly_supported | blocked"
    }
  ]
}
```

要求：

- UCA 必须引用 action selection node。
- UCA 必须说明 unsafe context。
- UCA 必须区分 activated、suppressed、blocked。
- 安全接管、安全停车、手动清除错误等文本要能抑制 failure-oriented UCA。

---

## 8. Reasoning Graph 结构

新增 `reasoning_graph`：

```json
{
  "nodes": [],
  "edges": [
    {
      "edge_id": "EDGE-1",
      "from_node_id": "PM-CPS-1",
      "to_node_id": "UPD-1",
      "relation_type": "conditions_update_process",
      "supporting_evidence_ids": [],
      "internal_reasoning_text": "...",
      "display_summary": "...",
      "claim_strength": "supported | weakly_supported | blocked",
      "missingness_notes": []
    }
  ]
}
```

允许的 edge types：

```text
evidence_supports_pm_context
evidence_triggers_update_need
pm_context_conditions_update_process
update_process_conditions_action_selection
other_factor_conditions_action_selection
boundary_conditions_action_selection
action_selection_instantiates_uca_context
uca_context_links_to_outcome
hmi_feedback_modifies_update_process
hmi_feedback_modifies_action_selection
```

验证规则：

- 每条 pathway 必须是一条可追踪的 graph path。
- 没有 evidence 的边不得是 `supported`。
- 缺失证据必须进入 `missingness_notes`。
- 禁止出现 outcome 直接连到 UCA 的边。

---

## 9. Ranked Explanatory Pathways

路径结构：

```json
{
  "pathway_id": "P1",
  "pathway_status": "supported | weakly_supported | blocked",
  "pathway_type": "unsafe_control_pathway | safe_fallback_pathway | blocked_pathway",
  "pathway_score": 0.0,
  "pathway_score_interpretation": "evidence-conditioned explanatory plausibility, not true causal probability",
  "graph_node_ids": [],
  "graph_edge_ids": [],
  "pm_context_contribution": {
    "CPS": {},
    "CPB": {},
    "OPS": {},
    "OPB": {}
  },
  "update_process_contribution": {},
  "other_factors_contribution": {},
  "control_action_selection": {},
  "uca_context_classification": {},
  "outcome_compatibility": {},
  "internal_reasoning_text": "...",
  "display_summary": "..."
}
```

要求：

- 一个 case 可以输出多个 pathway。
- 一个 pathway 可以包含多个 PM dimensions。
- 不再输出 `top quadrant` 作为理论结论。
- 可以保留 summary 中的 dominant pathway，但必须说明它只是排序最高的解释路径。

---

## 10. LLM Judge 修改

Judge prompt 改为评价 reasoning graph 和 pathway，而不是评价单条 CoT。

Rubric：

```json
{
  "evidence_grounding": 0.0,
  "pm_context_validity": 0.0,
  "update_process_validity": 0.0,
  "other_factors_validity": 0.0,
  "action_selection_validity": 0.0,
  "uca_context_validity": 0.0,
  "outcome_compatibility": 0.0,
  "missingness_penalty": 0.0,
  "overclaim_penalty": 0.0,
  "safe_intervention_consistency": 0.0
}
```

Node-level scores：

```json
{
  "evidence_to_pm_context": 0.0,
  "pm_context_to_update_process": 0.0,
  "update_process_to_action_selection": 0.0,
  "other_factors_to_action_selection": 0.0,
  "action_selection_to_uca_context": 0.0,
  "uca_context_to_outcome": 0.0
}
```

原则：

- 不使用单一 1-5 总分。
- 使用 0-1 分项评分。
- 报告 pathway score 和 judge rationale。
- 后续主实验可做重复 judge 或 pairwise ranking 稳健性检查。

---

## 11. HMI Injection Experiment

### 11.1 实验定位

HMI injection 不是证明真实 HMI 因果效果，而是：

```text
mechanism sensitivity experiment
```

它回答：

> 当 HMI feedback cue 被显式给定时，STPA-HF reasoning graph 中哪些环节发生变化？

### 11.2 HMI 注入类型

第一版建议：

```text
hmi_none_baseline
hmi_mode_state_display
hmi_capability_boundary_hint
hmi_time_budget_indicator
hmi_directional_instruction
hmi_actor_trajectory_cue
hmi_multimodal_salient_takeover_request
hmi_ambiguous_degradation_cue
hmi_clear_safe_fallback_instruction
```

### 11.3 注入内容必须是文本证据

不能只注入标签：

```json
{"HMI.time_budget_indicator": true}
```

必须注入文本：

```text
The HMI displayed a takeover request with a 5-second countdown and indicated that the ADS could no longer maintain lane control due to sensor uncertainty.
```

### 11.4 HMI 作用点

| HMI cue | STPA-HF 作用点 | 预期影响 |
|---|---|---|
| mode/state display | CPS update | 明确当前自动/手动/接管状态 |
| capability boundary hint | CPB update | 明确 ADS 能力边界或退化原因 |
| actor/trajectory cue | OPB update | 明确他车/行人行为风险 |
| road/environment cue | OPS update | 明确道路、施工、车道线、可见性 |
| time-budget indicator | update timing + action selection | 明确还有多少接管/干预时间 |
| directional instruction | action selection | 明确该刹车、转向、保持还是接管 |
| acknowledgement requirement | update verification | 明确驾驶员是否接收并确认反馈 |

### 11.5 HMI sensitivity 指标

```text
unsafe pathway score delta
update vulnerability shift
action selection clarity lift
UCA activation/suppression change
blocked pathway reduction
missingness reduction
judge directional consistency
```

---

## 12. Baseline 与 Ablation

### 12.1 Baselines

保留：

- direct LLM
- generic CoT

新增或重写：

- direct outcome-to-UCA inference baseline
- generic accident explanation baseline

关注：

- 是否从 collision/disengagement 直接推 takeover failure
- 是否补 HMI
- 是否补驾驶员心理
- 是否输出无证据 UCA

### 12.2 Ablations

必须包含：

```text
no_pm_context
no_update_process
no_other_factors
no_action_selection
no_evidence_gate
no_hmi_injection_label
no_llm_judge
```

解释：

- `no_update_process`：检验 update process 是否必要。
- `no_other_factors`：检验 other factors 是否影响动作选择。
- `no_action_selection`：检验是否会退化成 quadrant-to-UCA 直连。
- `no_evidence_gate`：检验是否增加 outcome-to-mechanism overcoding。
- `no_hmi_injection_label`：检验 counterfactual provenance leakage。

---

## 13. Evidence Audit 扩展

新增检查：

```text
node_without_evidence
edge_without_evidence
outcome_to_uca_direct_edge
display_summary_used_as_internal_input
counterfactual_used_as_reported
missingness_claimed_as_absence
uca_without_action_selection
uca_without_unsafe_context
pathway_without_graph_path
```

输出：

```json
{
  "invalid_evidence_ids": 0,
  "unsupported_nodes": [],
  "unsupported_edges": [],
  "direct_outcome_to_uca_edges": [],
  "provenance_leakage_cases": [],
  "uca_context_violations": [],
  "graph_path_violations": []
}
```

---

## 14. 数据计划

短期 pilot：

```text
10 CA DMV disengagement / takeover-related cases
10 AV collision cases
```

中期主实验：

```text
40-60 human-supervised automated-driving incident texts
```

优先级：

1. CA DMV disengagement reports：更适合接管/干预/人机共驾。
2. CA DMV collision reports：更适合 collision outcome 和事故文本。
3. NHTSA ADS-only：作为稀疏报告 stress test。
4. NHTSA L2 ADAS：必须单独标注 source regime，不与 ADS 混用。

数据边界：

- 只采用人机共驾或有人类安全员/测试员相关事故文本作为主实验。
- 不再把普通 highway crash 数据作为主证据。
- 视频数据暂作为后续扩展，不进入当前第一版主实验。

---

## 15. Human Expert Preview 与正式标注

### 15.1 标注目标

人工专家不标真实事故原因，而标：

```text
Given the source text, which STPA-HF reasoning graph claims are admissible, weakly supported, blocked, or conditional?
```

### 15.2 标注字段

每个 case：

- narrative proposition quality
- PM context support for CPS/CPB/OPS/OPB
- process-model update validity
- other factors validity
- control-action selection validity
- UCA-in-context validity
- pathway ranking reasonableness
- overclaim warnings
- missing information flags
- supporting evidence IDs

### 15.3 Codex Expert-0

短期可由 Codex 扮演 Expert-0 做 preview annotation。

注意：

- Expert-0 只用于 debug 和示例。
- 不能作为 publication human gold。

---

## 16. 新执行顺序

### Phase 0：准备输入数据

```powershell
python stpa_hf_dan_eswa_engine_final.py sample-human-supervised-cases `
  --out data/cases/aap_stpahf_pilot_20.jsonl `
  --n-ca-disengagement 10 `
  --n-av-collision 10
```

如果该命令尚未实现，先用现有 curated JSONL：

```text
data/cases/ads_takeover_text_10_v1.jsonl
data/cases/av_collision_text_10_v1.jsonl
```

### Phase 1：Narrative evidence mining

```powershell
python stpa_hf_dan_eswa_engine_final.py mine-narrative-evidence `
  --cases data/cases/aap_stpahf_pilot_20.jsonl `
  --out data/cases/aap_stpahf_pilot_20_narrative_mined.jsonl `
  --report results/aap_stpahf_graph_v2/narrative_mining_report.json
```

### Phase 2：Full reasoning graph run

```powershell
python stpa_hf_dan_eswa_engine_final.py run `
  --cases data/cases/aap_stpahf_pilot_20_narrative_mined.jsonl `
  --out results/aap_stpahf_graph_v2/bundles
```

### Phase 3：Graph evidence audit

```powershell
python stpa_hf_dan_eswa_engine_final.py evidence-audit `
  --bundle-dir results/aap_stpahf_graph_v2/bundles `
  --out results/aap_stpahf_graph_v2/evidence_audit
```

### Phase 4：Baseline suite

```powershell
python stpa_hf_dan_eswa_engine_final.py baseline-suite `
  --cases data/cases/aap_stpahf_pilot_20_narrative_mined.jsonl `
  --out results/aap_stpahf_graph_v2/baseline_suite
```

### Phase 5：Ablation suite

```powershell
python stpa_hf_dan_eswa_engine_final.py ablation-suite `
  --cases data/cases/aap_stpahf_pilot_20_narrative_mined.jsonl `
  --conditions no_pm_context,no_update_process,no_other_factors,no_action_selection,no_evidence_gate `
  --out results/aap_stpahf_graph_v2/ablations
```

### Phase 6：HMI injection cases

```powershell
python stpa_hf_dan_eswa_engine_final.py generate-hmi-injection-cases `
  --cases data/cases/aap_stpahf_pilot_20_narrative_mined.jsonl `
  --templates hmi_mode_state_display,hmi_capability_boundary_hint,hmi_time_budget_indicator,hmi_directional_instruction,hmi_multimodal_salient_takeover_request,hmi_ambiguous_degradation_cue `
  --out results/aap_stpahf_graph_v2/hmi_injection_cases/hmi_injection_cases.jsonl
```

### Phase 7：HMI injection run

```powershell
python stpa_hf_dan_eswa_engine_final.py run `
  --cases results/aap_stpahf_graph_v2/hmi_injection_cases/hmi_injection_cases.jsonl `
  --out results/aap_stpahf_graph_v2/hmi_injection_bundles
```

### Phase 8：HMI sensitivity evaluation

```powershell
python stpa_hf_dan_eswa_engine_final.py hmi-sensitivity-eval `
  --base-bundle-dir results/aap_stpahf_graph_v2/bundles `
  --hmi-bundle-dir results/aap_stpahf_graph_v2/hmi_injection_bundles `
  --out results/aap_stpahf_graph_v2/hmi_sensitivity
```

### Phase 9：Expert preview packets

```powershell
python stpa_hf_dan_eswa_engine_final.py annotation-packets `
  --cases data/cases/aap_stpahf_pilot_20_narrative_mined.jsonl `
  --bundle-dir results/aap_stpahf_graph_v2/bundles `
  --out results/aap_stpahf_graph_v2/annotation_packets
```

### Phase 10：Paper summary

```powershell
python stpa_hf_dan_eswa_engine_final.py paper-summary `
  --root results/aap_stpahf_graph_v2 `
  --out results/aap_stpahf_graph_v2/reports/pilot_summary.json
```

---

## 17. 论文表格设计

### Table 1：Dataset and evidence regime

- source regime
- event type
- narrative length
- HMI evidence coverage
- driver-state evidence coverage
- ADS transition evidence coverage

### Table 2：Reasoning graph generation quality

- schema valid rate
- node completeness
- edge completeness
- evidence citation validity
- UCA context validity

### Table 3：Full system vs baselines

- direct LLM
- generic CoT
- full STPA-HF graph
- outcome-to-mechanism overcoding rate
- unsupported UCA activation rate

### Table 4：Ablation

- no_pm_context
- no_update_process
- no_other_factors
- no_action_selection
- no_evidence_gate

### Table 5：Ranked pathway quality

- supported / weakly_supported / blocked pathway counts
- average pathway score
- top pathway type
- safe fallback suppression cases

### Table 6：HMI injection sensitivity

- HMI template
- update vulnerability shift
- action clarity lift
- unsafe pathway score delta
- UCA activation/suppression change

### Table 7：Expert preview / human evaluation

- expert agreement on PM context
- update process validity
- action selection validity
- UCA-in-context validity
- pathway ranking reasonableness

---

## 18. 验收标准

### 18.1 代码验收

- 新 bundle schema valid rate >= 95%。
- 每个 pathway 都有 graph node/edge path。
- 每个 UCA 都引用 action selection node。
- 每个 UCA 都有 unsafe context。
- 不再出现 `primary_quadrant` 作为理论核心输出。
- 不再出现固定 `pm_quadrant_mismatch -> UCA` 逻辑。
- `internal_reasoning_text` 不为空。
- `display_summary` 不作为下游推理输入。

### 18.2 理论验收

- 四象限作为共同 context，而不是单一主因。
- update process 是显式中间层。
- other factors 是显式中间层。
- control action selection 是 UCA 前置层。
- UCA 是 action-in-context，而不是 outcome label。

### 18.3 实验验收

- 20-case pilot 能跑通。
- baseline 显示 direct/generic 更容易过度机制化。
- ablation 显示去掉 update/other/action 后链路质量下降。
- HMI injection 显示不同 feedback cues 在不同 STPA-HF 环节产生可解释变化。
- evidence audit 无 invalid IDs、无 outcome-to-UCA direct edge。

---

## 19. 主要风险与应对

### 风险 1：结果仍像“证据不足报告”

应对：

- 输出不是单纯 missingness，而是 typed reasoning graph 中哪些 node/edge 被阻断。
- 展示 blocked pathway、weakly supported pathway 和 supported pathway 的差异。

### 风险 2：HMI 注入被误解为真实因果

应对：

- 所有 HMI injection case 标记 `analysis_mode = hmi_injection`。
- 所有 injected evidence provenance 标记为 `counterfactual` 或 `specified_scenario`。
- 论文中只称 mechanism sensitivity，不称 causal effect。

### 风险 3：STPA-HF 特色仍不明显

应对：

- 强制输出 PM context、update process、other factors、control action selection、UCA-in-context。
- 用 ablation 证明每个中间层必要。

### 风险 4：LLM judge 不稳定

应对：

- 用分项 0-1 rubrics。
- 保留 judge rationale。
- 主实验阶段做重复 judge 或 pairwise ranking。

---

## 20. 下一轮具体代码任务清单

### P0：删除旧理论错误

- 删除或废弃 `pm_quadrant_mismatch`。
- 删除 `primary_quadrant` 理论输出。
- 删除固定 `quadrant_contribution` 权重。
- 修改 `UCA_CATALOG`，只保留 action/context/hazard 信息。

### P1：新增核心中间层

- 新增 `PM_CONTEXT_SYNTHESIS_PROMPT`。
- 新增 `PROCESS_MODEL_UPDATE_ANALYSIS_PROMPT`。
- 新增 `OTHER_FACTORS_ANALYSIS_PROMPT`。
- 新增 `CONTROL_ACTION_SELECTION_PROMPT`。
- 新增 `UCA_CONTEXT_CLASSIFICATION_PROMPT`。

### P2：重写 run_case flow

目标流程：

```text
evidence packet
-> narrative propositions
-> PM context synthesis
-> process-model update analysis
-> other factors analysis
-> commitment boundary
-> control action selection
-> UCA context classification
-> reasoning graph
-> pathway judge
```

### P3：重写 pathway builder

- 从 graph nodes/edges 生成 candidate pathways。
- 每条 pathway 保留详细文本。
- 每条 pathway 可包含多个 PM dimensions。
- 支持 safe fallback pathway。

### P4：重写 judge

- 新 rubric。
- 新 node-level score。
- 新 validator。

### P5：新增 HMI injection

- 生成文本化 HMI cue。
- 标记 provenance。
- 输出 sensitivity eval。

### P6：扩展 audit

- graph integrity audit。
- provenance leakage audit。
- UCA context audit。
- display/internal separation audit。

### P7：跑 20-case pilot

- 10 takeover/disengagement。
- 10 AV collision。
- 输出两个完整例子。
- 总结 boundary/pathway/UCA/HMI sensitivity 分布。

---

## 21. 最终判断

这轮修改完成后，论文叙事将从：

```text
缺失感知 safety-case bundle generation
```

升级为：

```text
STPA-HF-guided LLM reasoning graph for evidence-conditioned accident explanation pathways
```

这是更适合 AAP 的落点，因为它直接服务事故分析：

- 从事故文本抽取证据。
- 构造驾驶员过程模型上下文。
- 分析过程模型更新与 other factors。
- 推理控制动作选择。
- 判定 UCA-in-context。
- 输出多条可审计解释链并排序。
- 通过 HMI 注入实验分析 feedback 在链路中的作用点。

该方案能够保留 STPA-HF 的人因特色，同时避免“缺失证据下伪造完整事故模型”的理论风险。

---

## 22. AAP 9+ 叙事加固层

这一层不是增加实验量，而是把论文前半段的主张钉得更紧。

### 22.1 论文一句话主张

> 本文使用 STPA-HF 作为证据约束框架，从稀疏的人机共驾事故/接管文本中估计驾驶员在事故链条中的参与度、受影响方式与控制动作选择，并生成可审计、可排序、可反事实敏感分析的事故解释路径。

这里的关键词是：

- estimate participation
- affected by what
- control-action selection
- auditability
- sensitivity analysis

不是：

- reconstruct true causality
- infer true driver cognition
- prove HMI effect

### 22.2 论文真正要回答的问题

把核心问题收束为一个：

> 在缺少 HMI、driver-state 和 internal ADS transition evidence 的公开事故文本中，如何用 STPA-HF 约束的 LLM 推理，给出关于驾驶员是否参与接管、如何参与、受哪些因素影响、以及其控制动作是否构成 UCA 的可接受判断？

这个问题比“安全 case 生成”更像 AAP。

### 22.3 STPA-HF 的角色要说清楚

STPA-HF 在本文中不是装饰性框架，也不是简单标签器，而是四层约束器：

1. 约束过程模型上下文，区分 CPS / CPB / OPS / OPB。
2. 约束 update process，解释为什么过程模型可能更新不足、误更新或无法验证。
3. 约束 other factors，说明哪些条件影响控制动作选择。
4. 约束 UCA 判定，只有 action-in-context 才能进入 UCA。

这四层共同决定：

```text
driver participation estimate
driver influence estimate
control-action selection
uca-in-context
```

### 22.4 HMI 的位置

HMI 不再是主叙事中心，而是一个可选的敏感性变量。

它的作用只有两个：

1. 作为 feedback cue，改变 process-model update 和 action selection 的可解释方向。
2. 作为 sensitivity axis，测试某条解释路径是否对反馈信息变化敏感。

因此，HMI 不是要被“纠结是否真实存在”，而是被用来说明：

> 如果这些反馈存在，STPA-HF 链条会如何变化；如果这些反馈缺失，哪些更强主张就会被阻断。

### 22.5 论文输出的三层结果

建议在叙事里固定成三层输出：

1. **Primary output**: ranked explanatory pathways  
2. **Secondary output**: blocked / weakly supported claims  
3. **Tertiary output**: analysis-derived evidence/logging requirements

这样 AAP 读者会很容易理解：

- 这不是纯分类；
- 这不是纯生成；
- 这是事故分析中的证据边界 + 解释路径 + 预防性记录要求。

### 22.6 你可以直接放进 Introduction 的贡献句

建议把贡献写成这三句的风格：

1. We formalize sparse accident text analysis as an evidence-admissible accident explanation problem under STPA-HF.
2. We model driver involvement in takeover/collision chains through process-model context, update process, other factors, and action selection rather than direct outcome labeling.
3. We use HMI as a sensitivity variable to test how feedback cues shift explanation pathways, not as a claim of real causal intervention.

### 22.7 不能再写成什么

论文里不要再把自己写成：

- “我们证明了 HMI 导致事故”
- “我们还原了真实驾驶员心理”
- “我们从事故结果推断 takeover failure”
- “我们输出最终 HMI 设计方案”

这些都会把 AAP 叙事拉回不稳的位置。

### 22.8 这条叙事的审稿人友好点

这条主线更容易过审的原因是：

- 事故分析问题明确；
- STPA-HF 结构明确；
- 证据边界明确；
- 输出是事故分析可用的，不是单纯 AI demo；
- HMI 只作为敏感性分析，不承担过强因果负担。

---

## 23. AAP投稿用正文骨架

这一节是对前面全部 plan 的压缩版，目标是直接转成论文正文。

### 23.1 Introduction

第一段：

自动驾驶/人机共驾事故文本往往只报告 ENV、ACTOR、CAR 和 outcome，而 HMI、driver-state 和 internal ADS transition 证据经常缺失。

第二段：

直接 LLM 往往会从 collision / disengagement 结果过度升级为 takeover failure、HMI failure 或 driver failure，但这种升级在证据上并不总是成立。

第三段：

因此，核心问题不是事故还原，而是在稀疏文本条件下，如何给出 evidence-admissible 的事故解释，并明确哪些更强主张被证据阻断。

第四段：

本文提出 STPA-HF-guided LLM reasoning graph，将事故文本转化为可审计的解释路径，估计驾驶员在接管/碰撞链条中的参与度、受影响方式与控制动作选择，并通过 HMI 注入做机制敏感性分析。

### 23.2 Contributions

建议压缩成 4 点：

1. 我们把稀疏事故文本分析重新定义为 evidence-admissible accident explanation problem。
2. 我们将 STPA-HF 的 driver process model 显式拆成 PM context、update process、other factors、action selection 和 UCA-in-context。
3. 我们构建 typed reasoning graph 和 ranked explanatory pathways，避免 outcome-to-mechanism 过度推断。
4. 我们把 HMI 作为 sensitivity axis，用于测试反馈变化对解释链和 UCA 路径的影响。

### 23.3 Method spine

可直接按以下 6 步写方法：

1. **Evidence extraction**  
   从事故文本提取 evidence packet，并标注 provenance。

2. **PM context synthesis**  
   生成 CPS / CPB / OPS / OPB 上下文，而不是直接定一个主 quadrant。

3. **Update process analysis**  
   判断哪些反馈/输入会触发过程模型更新，以及更新是否存在 missed / ambiguous / misinterpreted vulnerability。

4. **Other factors analysis**  
   抽取时间压力、任务角色、手动接管可行性、交通压力等影响动作选择的条件。

5. **Control action selection and UCA-in-context**  
   先分析可能的控制动作，再在上下文中判定 UCA。

6. **Pathway ranking and sensitivity analysis**  
   用 LLM judge 对候选解释链排序；在 HMI 注入条件下做机制敏感性分析。

### 23.4 一句话摘要

> We propose an evidence-admissible STPA-HF-guided reasoning graph that estimates driver involvement and control-action pathways in sparse automated-driving incident texts, suppresses outcome-to-mechanism overreach, and uses HMI only as a sensitivity axis for explanation pathways.

---

## 24. 代码修改建议补充

这部分是给后续实现直接用的，避免论文叙事和代码落点分离。

### 24.1 必须新增的输出层

代码里要把输出固定成四层：

1. `evidence_packet`
2. `reasoning_graph`
3. `ranked_explanatory_pathways`
4. `display_summary`

其中：

- `evidence_packet` 和 `reasoning_graph` 供内部推理和审计；
- `ranked_explanatory_pathways` 供论文主结果；
- `display_summary` 只给图表和报告展示。

### 24.2 必须新增的中间节点

不要再把四象限直接接到 UCA。  
必须显式保留：

- `pm_context`
- `update_process`
- `other_factors`
- `control_action_selection`
- `uca_context`

### 24.3 必须新增的审计规则

建议把 validator 再增强三条：

- `display_summary` 不能被下游 prompt 重新喂回去。
- `UCA` 必须有 `action_selection` 前置节点。
- `pathway` 必须能追溯到完整 graph path，不能是孤立标签链。

### 24.4 必须新增的纸面产物目录

建议最终目录中至少保留：

```text
results/aap_stpahf_graph_v2/
  bundles/
  baseline_suite/
  ablations/
  hmi_injection_bundles/
  hmi_sensitivity/
  evidence_audit/
  annotation_packets/
  tables/
  reports/
```

### 24.5 代码层面的一个关键建议

`update process` 和 `other factors` 的输出不要做成布尔开关。  
它们应是**文本化、可引用、可审计的 node**，否则论文会退回成“字段编码器”，而不是“事故解释链生成器”。

---

## 25. Claim Boundary and Non-Claims

这一节必须写进论文前半段，也必须在代码注释和报告口径里一致出现。

### 25.1 We can claim

本文可以主张：

- 在稀疏事故文本下，系统能够生成 evidence-admissible 的事故解释路径。
- 系统能够把驾驶员在接管/碰撞链条中的参与度表示为过程模型上下文、更新过程、动作选择和 UCA-in-context。
- 系统能够识别哪些更强机制主张被证据阻断。
- 系统能够给出 analysis-derived evidence/logging requirement candidates。
- 系统能够在 HMI 注入下表现出机制敏感性。

### 25.2 We cannot claim

本文不能主张：

- 还原真实事故因果。
- 推断真实驾驶员心理状态。
- 证明真实 HMI 设计有效性。
- 证明 HMI 在真实事故中的因果作用。
- 把 collision/disengagement 结果直接等同于 takeover failure。

### 25.3 Admissibility levels

论文里建议固定三档：

- `admissible`
- `weakly_supported`
- `blocked`

如果保留 counterfactual mode，再额外标记：

- `conditional_only`

这部分要和代码 schema 完全一致。

---

## 26. Operational Definition of Driver Participation

“驾驶员参与度”必须被操作化，否则审稿人会认为这是模糊词。

### 26.1 推荐定义

本文中的 driver participation 不是心理量表，而是证据约束下的控制链参与程度，体现在：

- 是否存在控制责任转移迹象；
- 是否存在可识别的 control-action selection；
- 是否存在接管准备或手动 fallback 行为；
- 是否存在延迟、遗漏或错误的控制动作；
- 是否存在能够支持/阻断更强 takeover 主张的 evidence chain。

### 26.2 对应到代码对象

建议把这个概念映射到以下结构：

- `commitment_boundary`
- `control_action_selection`
- `uca_context_classification`
- `pathway_status`

### 26.3 可报告的参与度维度

可以在论文中写成四个可解释维度：

1. `responsibility_transfer evidence`
2. `takeover readiness evidence`
3. `control action evidence`
4. `unsafe action context evidence`

这样“参与了多少”就不是抽象口号，而是可审计的解释对象。

---

## 27. Influence Mapping: HMI / Other Factors -> Update / Action / UCA

这一节建议做成方法图或表格。

### 27.1 映射原则

HMI 和 other factors 不直接生成结论，它们只通过以下环节影响解释链：

```text
HMI / other factors
-> process-model update
-> control-action selection
-> UCA-in-context
```

### 27.2 建议在论文中明确列出的映射

| 输入条件 | 影响环节 | 可能表现 |
|---|---|---|
| mode-state display | PM update | 更新是否更清晰 |
| capability-boundary hint | PM update | 能力边界是否更明确 |
| time-budget indicator | PM update + action selection | 接管时间是否更可见 |
| ambiguous degradation cue | PM update | 更新是否更易歧义 |
| driver distraction | action selection | 控制动作是否更迟缓或更弱 |
| manual fallback availability | action selection | 备用动作是否可行 |
| traffic pressure | action selection | 是否增加准备/接管压力 |
| safe stop target | action selection + UCA context | 是否改变 unsafe context |

### 27.3 论文叙事里的作用

这张映射表的作用是让审稿人看到：

- HMI 不是独立主角；
- HMI 只在 STPA-HF 链条中起到约束或敏感性作用；
- other factors 不是杂项，而是动作选择条件。

---

## 28. Related-Work Positioning

这一节建议单独写在 Introduction 末尾或 Related Work 开头。

### 28.1 和传统 STPA-HF 的差异

传统 STPA-HF 往往依赖较完整的系统反馈和场景信息。  
本文的改进点是：

- 面向公开事故文本的稀疏证据；
- 将 process-model update、other factors 和 action selection 显式化；
- 将 UCA 改写为 action-in-context；
- 用 evidence admissibility 约束 claims。

### 28.2 和事故分类/文本挖掘方法的差异

一般事故文本分类更关注：

- 分类标签；
- 主题抽取；
- 事故因素统计。

本文更关注：

- 解释链；
- claim boundary；
- blocked mechanism；
- action selection；
- UCA context。

### 28.3 和纯 LLM / CoT 的差异

纯 LLM / CoT 容易：

- 从 outcome 直接过度推断；
- 补齐缺失 HMI / driver-state；
- 输出不可审计的自然语言链条。

本文通过 STPA-HF 结构和 evidence gate 把这些风险压住。

### 28.4 和手工事故分析的差异

手工分析更强，但不可扩展。  
本文的定位不是替代专家，而是：

> 在证据边界内，生成可审计、可排序、可复核的候选解释路径。

---

## 29. Limitations

这三条建议作为正式 limitation，不能太多，也不能太虚。

### 29.1 Sparse-text limitation

公开事故文本的证据不完整，很多 HMI、driver-state 和 internal ADS 变量不可观测，因此本文输出的是 evidence-admissible judgement，而不是完整因果复原。

### 29.2 Counterfactual limitation

HMI injection 只用于 mechanism sensitivity，不用于真实 HMI 因果结论。

### 29.3 Human-gold limitation

在没有大规模 human-gold 的情况下，本文的主张以结构一致性、证据可接受性和路径排序为主，不声称提供最终事故真值。

---

## 30. Contribution-to-Section Mapping

为了符合 `Supervisor-Skills`，建议在 plan 和论文里都明确映射。

| Contribution | Main Section | Key Artifact |
|---|---|---|
| Evidence-admissible accident explanation | Introduction + Method | reasoning graph |
| STPA-HF stage decomposition | Method | pm/update/action/UCA modules |
| Ranked explanatory pathways | Method + Results | pathway ranking |
| HMI sensitivity analysis | Method + Results | injection bundles |
| Evidence/logging requirement candidates | Results + Discussion | blocked claim report |
