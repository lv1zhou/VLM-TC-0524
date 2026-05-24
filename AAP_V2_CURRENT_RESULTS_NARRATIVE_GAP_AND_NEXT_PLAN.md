# AAP V2 当前测试结果、论文叙事差距与下一轮 Plan

Date: 2026-05-16

## 1. 当前论文叙事基准

当前论文不应再被表述为一般的 STPA-HF safety-case generation，也不应被表述为事故真因还原。更合适的 AAP 叙事是：

> Evidence-Bounded Driver Process-Model Tabletop Replay for Automated-Driving Incidents.

核心链条固定为：

```text
incident report
-> provenance-aware evidence packet
-> CPS / CPB / OPS / OPB driver process-model variables
-> process-model formation/update analysis
-> candidate driver actions
-> UCA-in-context pathways
-> outcome compatibility check
-> LLM judge ranking
-> tabletop replay package
-> blocked claims + replay questions + minimum reporting/logging requirements
```

论文的落点是：把稀疏的人机共驾事故/接管文本转化为可审计的驾驶员过程模型桌面推演产物，用于事故后安全复盘和最小报告/日志需求设计。

明确不能声称：

- 真实事故因果还原；
- 真实驾驶员心理推断；
- HMI 对真实事故的因果作用；
- 法律责任或责任分配；
- pathway score 是真实因果概率。

## 2. 当前结果分层

### 2.1 最贴合 V2 叙事的结果

当前最贴合新叙事的是：

- `results/aap_v243_10case_full/`
- `results/aap_v243_10case_replay_audit/tabletop_replay_audit.json`
- `results/aap_v243_10case_audit/evidence_support_audit.json`
- `results/aap_v2_codecheck_ablation_2case/`
- `results/aap_v2_codecheck_richer_compare/`
- `results/aap_v2_codecheck_replay_alignment/`

这些结果已经使用或围绕 `driver_pm_tabletop_replay_v2.4.3`，包含 `tabletop_replay_package`、replay audit、evidence audit、ablation、richer-evidence comparison 和 RIMS protocol check。

### 2.2 有规模但不能直接作为 V2 主结论的结果

`results/aap_30_exact_run_combined/` 有 30 case，且包含 15 collision + 15 disengagement 的更好配比，但其 `paper_manifest.json` 仍显示：

- `schema_version = stpa_hf_reasoning_graph_v2.0`
- `claim_boundary` 仍写着 safety-case generation 和 feedback-boundary sensitivity
- bundle 指标仍使用 `commitment_state_fsm`、旧 UCA 分布和旧命名

因此该目录目前只能作为数据规模和缺失分布的参考证据，不能作为 AAP V2 的主实验结果。下一轮必须用 v2.4.3 重新跑 20-case 或 30-case mixed pilot。

## 3. 当前测试结果细读

### 3.1 10-case V2 replay package 结果

`results/aap_v243_10case_replay_audit/tabletop_replay_audit.json` 显示：

| 指标 | 当前结果 |
|---|---:|
| case 数 | 10 |
| replay package generation rate | 1.0 |
| quadrant coverage rate | 1.0 |
| update process present rate | 1.0 |
| review ready case rate | 1.0 |
| mean candidate action count | 3 |
| mean UCA pathway count | 5.6 |
| mean ranked pathway count | 5.6 |
| mean replay question count | 4 |
| mean missing requirement count | 12 |
| mean blocked claim count | 3.2 |
| source regime | 10 个 third-party CA DMV collision augmented CSV |

这说明当前代码已经能把每个 collision case 生成一个结构完整的 `e*_tabletop_replay_package.json`。每个包中包含：

- evidence profile；
- CPS/CPB/OPS/OPB 四象限；
- process-model formation/update source；
- candidate actions；
- UCA pathways；
- outcome compatibility block；
- LLM judge ranking；
- blocked claims；
- replay questions；
- missing reporting/logging requirements。

这支持 RQ1 的技术可行性，但只是在 10 个 collision case 上成立。它还没有覆盖 disengagement，也没有形成 mixed source regime 的 V2 主结果。

### 3.2 10-case evidence audit 结果

`results/aap_v243_10case_audit/evidence_support_audit.json` 显示：

| 指标 | 当前结果 |
|---|---:|
| num_cases | 10 |
| mean invalid evidence ID count | 0 |
| UCA catalog consistency | 1.0 |
| not_reported used as observed update fact | 0 |
| outcome-only UCA activation | 0 |
| HMI absence inferred from nonreporting | 0 |
| psychological overclaim warning | 0 |
| generic UCA expansion warning | 2 |
| mean candidate pathways per case | 5.6 |
| pathway status distribution | 14 weakly_supported / 42 blocked |
| UCA claim status distribution | 14 abductive_candidate / 42 blocked |
| G7 outcome gate distribution | 56 weak |

这个结果对论文很关键：系统没有把 `not_reported` 当作事实，没有把 collision outcome 直接当作 UCA activation evidence，也没有输出真实心理判断。这正好支撑“evidence-bounded replay”的红线。

但也暴露出两个问题：

1. `claims_without_supporting_evidence_count = 1.8` 仍然混合了不同性质的 claim。这里很多是 `observed_update_vulnerability = none` 或 `uca_activation_status = no_activated_uca` 这类负向/未激活状态，不应和 unsupported positive claim 混为一谈。
2. `generic_uca_expansion_warning_count = 2` 说明仍有少数 UCA candidate-space expansion 太宽，下一轮需要让 UCA 生成更贴近“candidate action + unsafe context + outcome compatibility”的严格链条。

### 3.3 2-case ablation codecheck 结果

`results/aap_v2_codecheck_ablation_2case/ablation_suite_summary.json` 显示：

| 条件 | outcome-only overreach | complete chain | blocked-claim transparency | mean ranked pathways |
|---|---:|---:|---:|---:|
| direct LLM | 2/2 | 0.0 | 0.0 | 0 |
| generic CoT | 2/2 | 0.0 | 0.0 | 0 |
| structured prompt only | 2/2 | 0.0 | 0.0 | 0 |
| no-update | 0/2 | 0.0 | 1.0 | 1 |
| no-evidence-gate | 0/2 | 1.0 | 0.0 | 6 |
| full replay | 0/2 | 1.0 | 1.0 | 6 |

这是目前最能支撑“driver process model 是必要中介层”的证据：

- direct / generic CoT / structured prompt only 都会把 collision 或高风险上下文推向 `not_supported_transfer`，并且没有 PM-update-action-UCA 完整链；
- no-update 不再过度推断，但 ranked pathways 从 6 降到 1，说明 update process 不只是装饰；
- full replay 同时做到 overreach suppression、完整链条和 blocked claim transparency。

但是这只是 2-case codecheck，不能作为正式实验表的最终证据。下一步要在 20-case mixed pilot 上重跑。

### 3.4 Richer-evidence / HMI injection 结果

`results/aap_v2_codecheck_richer_compare/richer_evidence_pair_comparison.json` 显示 1 个 sparse-vs-richer pair：

| 指标 | 当前结果 |
|---|---:|
| blocked claim reduction rate | 1.0 |
| missing requirement reduction rate | 1.0 |
| update source completeness increase rate | 1.0 |
| PM specificity increase rate | 0.0 |

解释：

- richer HMI evidence 能减少 blocked claims；
- 能减少 missing requirements；
- 能增加 update source completeness；
- 能改变 pathway rank；
- 但当前 PM specificity 指标是错误的，因为它用文本长度/词数近似 specificity。 richer evidence 可能让不确定性文字变短，不代表 PM 更不具体。

因此该实验的叙事应改为：

> richer evidence narrows replay uncertainty and changes ranked pathways.

不能写成：

> HMI caused better safety outcome.

下一轮要把 specificity 改成结构化指标，而不是文本长度。

### 3.5 RIMS / Expert-0 结果

`results/aap_v2_codecheck_replay_alignment/replay_alignment_eval.json` 显示：

- mean RIMS total = 1.0；
- top1 match rate = 1.0；
- mean top3 recall = 1.0；
- blocked claim recall = 1.0；
- requirement relevance = 1.0。

这个结果目前只能证明协议跑通，不能作为专家一致性证据。原因是 Expert-0 preview labels 仍然高度依赖系统输出，RIMS 接近自我一致性测试。

论文中不能把它写成 human expert validation。更准确的定位是：

> protocol-debug preview for the planned human-review workflow.

正式论文需要至少 2 名真实标注者，或者至少一套独立于系统 ranking 的严格 Expert-0 预标注流程。

### 3.6 30-case 旧结果可继承的信息

`results/aap_30_exact_run_combined/` 虽不能作为 V2 主结论，但有两个可继承价值：

1. 数据配比已经接近论文需要：15 collision + 15 disengagement。
2. 缺失结构非常稳定：

| 指标 | 当前结果 |
|---|---:|
| num_cases | 30 |
| aggregate missingness mean | 0.7441 |
| total feedback gaps | 330 |
| HMI feedback gaps | 150 |
| driver-state gaps | 60 |
| internal ADS / transition gaps | 120 |
| requirement candidates | 330 |

这说明公共事故/接管文本确实大量缺少 HMI、driver-state、internal ADS 和 transition evidence。这个现象可以支撑论文动机，但必须用 v2.4.3 重新生成正式表格。

## 4. 和论文叙事的匹配程度

### 4.1 RQ1: Replay Package Generation

当前状态：部分支持，工程上较强。

支持证据：

- 10/10 v2.4.3 replay package generated；
- quadrant coverage = 1.0；
- update process present = 1.0；
- review ready = 1.0；
- evidence ID invalid mean = 0。

缺口：

- 当前 V2 主线只有 10 个 collision；
- 30-case mixed 是旧 schema；
- 还缺 20-case mixed v2.4.3 pilot；
- 还缺 per-case package completeness 的紧凑论文表。

### 4.2 RQ2: PM Mediation / Overreach Suppression

当前状态：机制上支持很强，但样本规模不足。

支持证据：

- 2-case ablation 中 direct / CoT / structured 都发生 outcome-only overreach；
- full replay 没有 outcome-only overreach；
- no-update chain rate = 0，full replay chain rate = 1；
- full replay 有 blocked-claim transparency。

缺口：

- 2-case 太小；
- no-evidence-gate 还不够尖锐；
- 需要在 20-case mixed 上重复 direct / CoT / structured / no-update / no-evidence-gate / full replay。

### 4.3 RQ3: Review Utility and Richer-Evidence Sensitivity

当前状态：方向上支持，指标还没成熟。

支持证据：

- 1 pair 中 richer evidence 减少 blocked claims；
- 减少 missing requirements；
- 增加 update source completeness；
- 改变 pathway rank。

缺口：

- 只有 1 pair；
- specificity metric 不可靠；
- HMI injection 还需明确“重新走 CPS/CPB/OPS/OPB -> update -> action -> UCA -> ranking”，而不是只改 boundary；
- requirement candidates 仍偏模板化，缺少 pathway-critical / claim-blocking 的细分。

## 5. 当前代码与叙事的主要差距

### Gap 1: 新旧命名仍混在一起

代码中还保留大量 `commitment_boundary`、`final_commitment_state_fsm`、`round2b_commitment` 等内部字段。内部兼容可以保留，但 paper-facing 输出必须统一为：

- `driver_replay_posture`
- `tabletop_replay_package`
- `driver_process_model_tabletop_replay_bundle`
- `post-incident safety review artifact`

不建议再在论文结果表里出现 `commitment boundary`。

### Gap 2: 30-case 结果不是 V2 主线

30-case 目录仍是 `stpa_hf_reasoning_graph_v2.0`。它的结果不能直接支持 AAP V2 的主 claim。必须重跑 mixed pilot，并生成：

- `tabletop_replay_audit.json`
- `evidence_support_audit.json`
- `ablation_suite_summary.json`
- `richer_evidence_pair_comparison.json`
- `paper_result_manifest.json`

### Gap 3: no-evidence-gate ablation 没有真正显示“门控移除后的风险”

当前 `no_evidence_gate` 只是 diagnostic projection，输出仍没有：

- would_promote_blocked_pathway_count
- would_promote_outcome_only_pathway_count
- would_promote_no_action_evidence_pathway_count
- would_promote_not_reported_supported_pathway_count
- promoted_pathway_examples

所以它还不能有力证明 evidence gate 的必要性。

### Gap 4: RIMS 仍是自确认

当前 RIMS = 1.0 不能用于论文验证。需要：

- strict Expert-0 labels 不复制 system top ranking；
- 或真实人工专家标签；
- 增加 Top-1、Top-3、Spearman/Kendall、Jaccard、tier distribution distance；
- 在结果里明确 preview labels 仅为 protocol-debug。

### Gap 5: PM specificity 指标错误

当前 richer-evidence compare 的 `pm_node_specificity` 使用文本长度，导致 richer evidence 反而可能得分更低。应替换成：

- reported update source count；
- direct PM node support count；
- missing PM evidence count；
- blocked PM claim count；
- pathway status entropy；
- top-pathway margin；
- number of pathway status upgrades。

### Gap 6: requirement candidates 仍偏清单化

现在 sparse case 经常固定输出 12 个 missing requirements。这能说明缺失，但容易被审稿人认为是 checklist generation。

下一步每条 requirement 应增加：

- criticality class: `global_missing_logging_field` / `pathway_critical` / `claim_blocking` / `lower_priority_completeness`
- triggering pathway IDs
- blocked claims
- priority reason
- whether richer evidence would remove/reduce it

### Gap 7: evidence audit 混合了不同 claim 类型

当前 `claims_without_supporting_evidence_count` 混合正向无证据 claim、负向状态 claim、gap claim。应拆成：

- positive_claims_without_supporting_evidence_count
- negative_status_claims_without_supporting_evidence_count
- gap_claims_without_positive_support_count

只有第一类才是严重问题。

### Gap 8: UCA candidate expansion 仍有少量过宽

`generic_uca_expansion_warning_count = 2` 说明某些 UCA pathway 虽然被 blocking policy 控住，但 candidate 生成阶段仍可能太泛。下一轮要加强：

- UCA 必须从 candidate driver action 正向生成；
- outcome 只能作为 compatibility；
- 无 action evidence 时只能是 abductive 或 blocked；
- timing UCA 必须有 timing gate；
- manual-control UCA 必须有 manual-control evidence；
- fallback UCA 必须有 fallback/transfer context。

## 6. 下一轮代码修改 Plan

### Phase A: 指标与审计修正

1. 修改 `no_evidence_gate` diagnostic projection。
   - 增加 promoted-risk 计数。
   - 输出 promoted pathway examples。
   - 明确该条件不是合法 replay output。

2. 修改 evidence audit。
   - 拆分 positive / negative / gap claim coverage。
   - 保留 not_reported gap citation，但不得计作 positive support。
   - 新增 `positive_unsupported_claim_warning_case_ids`。

3. 修改 richer-evidence compare。
   - 删除或弃用 word-count PM specificity。
   - 新增 structured specificity metrics。
   - 输出 pathway status upgrade / downgrade / rank margin change。

4. 修改 requirement candidates。
   - 增加 criticality class。
   - 增加 triggering pathway IDs。
   - 增加 blocked claims。
   - 增加 priority reason 和 specificity level。

5. 修改 RIMS / Expert-0。
   - strict Expert-0 不直接复制系统 top pathway。
   - 允许 Expert-0 选择 “no admissible top pathway”。
   - 增加 ranking/distribution metrics。
   - 所有报告中写明 preview labels are not human-gold。

### Phase B: 输出命名收束

1. paper-facing bundle summary 中新增或强化：
   - `final_driver_replay_posture`
   - `final_tabletop_replay_package_path`
   - `final_replay_question_count`
   - `final_missing_requirement_count`
   - `final_blocked_claim_count`
   - `final_replay_ready`

2. 保留旧字段作为兼容，但论文导出和 manifest 不再使用旧字段。

3. manifest schema 必须为 `driver_pm_tabletop_replay_v2.4.3` 或更新版本。

### Phase C: 20-case mixed pilot

在 Phase A/B 完成后，重跑：

- 10 CA DMV collision；
- 10 CA DMV disengagement。

建议输出目录：

```text
results/aap_v244_20case_mixed_full/
results/aap_v244_20case_mixed_audit/
results/aap_v244_20case_mixed_replay_audit/
results/aap_v244_20case_mixed_ablation/
results/aap_v244_20case_mixed_requirements/
results/aap_v244_20case_mixed_feedback_gaps/
results/aap_v244_20case_mixed_rims_preview/
```

必须运行：

```powershell
python .\stpa_hf_dan_eswa_engine_final.py run --cases .\data\cases\aap_v22_20case_runset.jsonl --out .\results\aap_v244_20case_mixed_full --case-limit 20 --temperature 0
python .\stpa_hf_dan_eswa_engine_final.py evidence-audit --bundle-dir .\results\aap_v244_20case_mixed_full --out .\results\aap_v244_20case_mixed_audit
python .\stpa_hf_dan_eswa_engine_final.py tabletop-replay-audit --bundle-dir .\results\aap_v244_20case_mixed_full --out .\results\aap_v244_20case_mixed_replay_audit
python .\stpa_hf_dan_eswa_engine_final.py feedback-gap-report --bundle-dir .\results\aap_v244_20case_mixed_full --out .\results\aap_v244_20case_mixed_feedback_gaps
python .\stpa_hf_dan_eswa_engine_final.py requirement-candidates --bundle-dir .\results\aap_v244_20case_mixed_full --out .\results\aap_v244_20case_mixed_requirements
python .\stpa_hf_dan_eswa_engine_final.py run-ablation-suite --cases .\data\cases\aap_v22_20case_runset.jsonl --out .\results\aap_v244_20case_mixed_ablation --case-limit 20 --temperature 0
```

### Phase D: richer-evidence / HMI sensitivity

HMI injection 不能只改 boundary。必须重新走完整链条：

```text
injected evidence
-> evidence packet
-> CPS/CPB/OPS/OPB
-> update process
-> candidate actions
-> UCA pathways
-> LLM judge ranking
-> replay package comparison
```

建议先做 5 个 case，每个 case 3 类 injection：

1. explicit mode + capability boundary cue；
2. takeover demand + time budget + acknowledgement；
3. manual intervention / driver response trace。

比较指标：

- reported update source count change；
- direct PM node support count change；
- missing PM evidence count reduction；
- blocked PM claim count reduction；
- candidate action rank change；
- UCA pathway rank change；
- blocked claim reduction；
- missing requirement reduction；
- top-pathway margin change。

### Phase E: 人工标注准备

当前 Expert-0 只能用于调试。正式论文至少需要：

- 2 名标注者；
- 20-case 子集；
- 标注 top pathway / admissible pathway set / blocked claims / critical missing evidence / requirement relevance；
- 计算 Top-1、Top-3、Jaccard、Kendall 或 Spearman；
- 报告 agreement 和 adjudication。

## 7. 论文结果表建议

### Table 1: Dataset and Missingness

使用 v2.4.3 mixed pilot 重新统计：

- source regime；
- collision/disengagement；
- reported / derived / not_reported；
- HMI / driver-state / internal ADS missingness；
- source field coverage。

### Table 2: Replay Package Generation

- schema valid；
- replay package generation；
- quadrant coverage；
- update process present；
- review-ready rate；
- mean pathways；
- mean replay questions。

### Table 3: Mediation and Overreach Suppression

比较：

- direct LLM；
- generic CoT；
- structured prompt only；
- no-update；
- no-evidence-gate；
- full replay。

核心指标：

- outcome-only overreach；
- unsupported takeover failure；
- complete PM-update-action-UCA chain；
- blocked claim transparency；
- evidence-cited pathway rate。

### Table 4: Evidence Audit

- invalid evidence ID；
- not_reported-as-fact；
- outcome-only activation；
- positive unsupported claim；
- negative status unsupported claim；
- UCA catalog consistency；
- generic UCA expansion warning。

### Table 5: Richer-Evidence Sensitivity

- update source completeness；
- PM node support；
- pathway rank change；
- blocked claim reduction；
- missing requirement reduction；
- top-pathway margin。

### Table 6: Minimum Reporting / Logging Requirements

- requirement criticality class；
- target field；
- pathway-critical count；
- claim-blocking count；
- source regime difference；
- representative examples。

## 8. 当前评分

按当前叙事与结果对齐程度：

| 维度 | 分数 | 理由 |
|---|---:|---|
| 论文叙事清晰度 | 9.1/10 | AAP 落点已经清楚：driver-centered tabletop replay，而非真因还原 |
| 方法链条完整性 | 8.6/10 | v2.4.3 已有完整链条，但旧命名和旧字段仍混入 |
| 代码-叙事对齐 | 8.2/10 | 10-case 新结果对齐，30-case 旧结果不对齐 |
| 实验证据强度 | 7.0/10 | 有 strong codecheck，但正式 mixed pilot 和人类标签不足 |
| AAP 投稿准备度 | 7.6/10 | 叙事可推进，实验还需要 v2.4.3 mixed pilot 和更严格指标 |

预期：

- 完成 Phase A/B 后：代码-叙事对齐可到 8.8-9.0；
- 完成 20-case mixed pilot 后：实验证据强度可到 8.2；
- 完成人工标注和 40-50 case 主实验后：AAP 投稿准备度可到 9.0+。

## 9. 立即建议

不要直接把当前 30-case combined 写进论文主实验。

下一步应先完成 Phase A/B 的代码收束和指标修正，然后用 v2.4.3 或 v2.4.4 重跑 20-case mixed pilot。当前最强的论文句子应是：

> In pilot codechecks, full replay generated complete auditable replay packages and suppressed outcome-only overreach compared with direct LLM, generic CoT, and structured-prompt-only baselines. However, publication-scale claims require a mixed collision/disengagement run under the same V2 schema and independent human review labels.

