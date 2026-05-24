# ESWA Paper V1 代码修改与 Case 执行总计划

日期：2026-05-11  
目标：ESWA 投稿用  
主线：`evidence -> PM context -> update process -> other factors -> boundary -> action selection -> UCA-in-context -> ranked explanatory pathways`

## 0. 计划目标

本计划只服务一件事：

> 在稀疏自动驾驶事故文本下，生成 evidence-admissible 的 STPA-HF 解释路径，并用 HMI 注入做机制敏感性分析，而不是做事故真因还原。

本计划的输出必须同时满足：

1. 代码可跑。
2. 输出可审计。
3. 叙事可投稿。
4. 结果可复核。

---

## 1. 当前基线

当前已验证的稳定状态：

- `30/30 schema valid`
- `invalid evidence ID = 0`
- `catalog consistency = 1.0`
- `unsupported strong boundary warning = 2`
- `outcome-only escalation warning = 2`
- `mean claims without supporting evidence = 0`

当前仍然缺的东西：

1. 主实验样本层次还不够丰富。
2. HMI 只在 counterfactual 分支里出现，尚未形成完整的成套统计。
3. 人工标注只有 protocol，没有完整的 adjudicated gold。
4. `feedback_gap_report` 和 `analysis-derived evidence/logging requirement candidates` 还需要作为正式论文产物稳定落盘。
5. `paper_v1` 结果目录需要冻结，避免后续结果口径漂移。

---

## 2. 代码修改总则

所有改动必须遵守以下红线：

1. 不硬编码 HMI / driver-state / internal ADS 缺失值。
2. 不用 semantic fallback 修补证据缺口。
3. 不把 `display_summary` 反灌为推理主输入。
4. 不把 collision 直接等同于 takeover failure。
5. 不把 disengagement 直接等同于事故真因。
6. 不把 counterfactual HMI 注入写回 base branch 事实。
7. 不删除 `not_reported`，而是显式保留其缺失语义。
8. 不让旧的 quadrant-to-UCA 直连逻辑重新混入主线。

---

## 3. 需要修改的代码文件

### 3.1 `stpa_hf_dan_eswa_engine_final.py`

这是一号主文件，修改优先级最高。

需要确认或补强的点：

1. `SCHEMA_VERSION` 固定为 `stpa_hf_reasoning_graph_v2.0`。
2. `PM context` 只能输出 `CPS / CPB / OPS / OPB` 四个过程模型节点。
3. `update process` 必须显式输出 `missed_feedback / ambiguous_feedback / misinterpreted_feedback / none`。
4. `other factors` 必须独立于 PM，不可反向充当 UCA。
5. `commitment boundary` 必须只保留：
   - `supported_monitoring`
   - `contingent_readiness`
   - `not_supported_transfer`
6. `control action selection` 必须显式输出候选动作，不可只输出标签。
7. `UCA context` 必须基于 `action + context` 判定，不可直接由 outcome 反推。
8. `reasoning graph` 必须是可追溯 path，不可只输出孤立 label。
9. `judge` 必须评分 path，而不是评分单句 CoT。
10. `feedback_gap_report` 和 `requirement_candidates` 必须保持“analysis-derived”定位。

建议核查项：

- 去掉任何残留的 `pm_quadrant_mismatch` 依赖。
- 去掉任何把 `outcome` 直接映射成 `takeover failure` 的分支。
- 保留 `internal_reasoning_text` 和 `display_summary` 的分层。
- 保留 `reported / derived / not_reported / assumed_for_counterfactual` provenance 区分。
- 保留 `unsupported_strong_boundary_warning` 与 `outcome_only_escalation_warning`。

### 3.2 `run_paper_pipeline.sh`

作为 paper-facing 默认管线，建议继续作为主执行脚本。

需要确认：

1. 默认输出根目录固定为 `results/paper_v1`。
2. 默认 case 集使用 paper-facing 冻结输入。
3. audit-only 模式不跑 LLM，但仍生成可发表的 manifest / audit / gap 报告。
4. LLM 模式下严格按以下顺序执行：
   - input audit
   - missingness profile
   - annotation packets
   - full system
   - baseline suite
   - evidence audit
   - feedback gaps
   - evidence requirement candidates
   - counterfactual specs
   - counterfactual cases
   - counterfactual full system
   - counterfactual eval
   - paper manifest

### 3.3 `run_paper_v1_50_pipeline.ps1`

Windows 侧执行脚本。

需要保证：

1. 相同的阶段顺序。
2. 相同的结果目录。
3. 不把旧 verify 目录混入 paper_v1 主结果。

### 3.4 标注协议文件

建议同步检查：

- `ESWA_HUMAN_ANNOTATION_GUIDE.md`
- `ESWA_EXPERT_PREVIEW_ANNOTATION_PROTOCOL.md`

目的：

1. 统一字段定义。
2. 统一 label 语义。
3. 统一“人工代理标注”和“正式人工标注”的边界。

---

## 4. 代码修改任务拆解

### Task A: 结果口径冻结

目标：

- 所有论文表格和 manifest 都从 `results/paper_v1/` 读取。
- `verify` 只作为 smoke / repair 参考，不作为主文结论。

产物：

- `results/paper_v1/paper_result_manifest.json`
- `results/paper_v1/table1/missingness_profile/...`
- `results/paper_v1/audit/evidence_support_audit/...`

### Task B: PM / update / action / UCA 四层链条固化

目标：

- 让每个 bundle 都必须显式包含：
  - `pm_context`
  - `process_model_update_analysis`
  - `other_factors_analysis`
  - `commitment_boundary`
  - `control_action_selection`
  - `uca_context_classification`
  - `reasoning_graph`
  - `ranked_explanatory_pathways`

约束：

- 不能跳层。
- 不能把 summary 当输入。
- 不能把 outcome 直接升级成 UCA。

### Task C: feedback gap 和 requirement candidates

目标：

- 把“缺什么”改写成论文中的正式可发表输出。

建议命名：

- `feedback_gap_report`
- `analysis-derived evidence/logging requirement candidates`

每条 candidate 必须包含：

1. gap field
2. blocked stronger claim
3. candidate logging/evidence need
4. evidence type
5. priority
6. supported STPA-HF stage

### Task D: HMI 注入 runner

目标：

- 在同一 base case 上做 paired counterfactual。

固定四类模板：

1. `takeover_demand`
2. `ambiguous_degradation`
3. `full_support`
4. `partial_support`

每个模板都重新跑完整链条：

`PM -> update -> other factors -> boundary -> action -> UCA -> pathway ranking`

### Task E: audit 增强

目标：

- 把“为什么不能强断言”变成可见的审计结果。

必须保留：

- `unsupported_strong_boundary_warning`
- `outcome_only_escalation_warning`
- `not_reported_boundary_support_warning`
- `strong_boundary_evidence_strength`

---

## 5. Case 执行计划

### Phase 0: 输入冻结与检查

先对所有 case 输入做一次 leakage audit。

命令：

```powershell
python stpa_hf_dan_eswa_engine_final.py audit-case-input --cases <cases.jsonl> --out results/paper_v1/input_audit.json
```

检查点：

- 不得出现 gold label 混入 case input。
- 不得出现 expected axis 混入 case input。

### Phase 1: Missingness profile

命令：

```powershell
python stpa_hf_dan_eswa_engine_final.py missingness-profile --cases <cases.jsonl> --out results/paper_v1/table1/missingness_profile
```

论文用途：

- Table 1
- 证据缺口统计
- HMI / driver-state / internal ADS 不报告的比例

### Phase 2: Annotation packets

命令：

```powershell
python stpa_hf_dan_eswa_engine_final.py export-annotation-packets --cases <cases.jsonl> --out results/paper_v1/annotation_packets --csv results/paper_v1/annotation_packets/annotation_sheet.csv
```

用途：

- 人工标注接口
- 代理标注接口
- 后续 human-gold 数据准备

### Phase 3: Expert preview labels

目的：

- 让系统先代替人工做一轮可解释标注，检查逻辑是否闭合。

命令：

```powershell
python stpa_hf_dan_eswa_engine_final.py expert-preview-labels --cases <cases.jsonl> --out-labels results/paper_v1/expert_preview_labels.jsonl --out-report results/paper_v1/expert_preview_eval/expert_preview_annotation_report.json
```

需要统计：

- `boundary_label`
- `update_vulnerability`
- `dominant_uca`
- `active_uca_set`
- `supporting_evidence_ids`
- `insufficient_information_flags`

### Phase 4: Full system

命令：

```powershell
python stpa_hf_dan_eswa_engine_final.py run --cases <cases.jsonl> --out results/paper_v1/bundles
```

必须检查：

- schema valid
- reasoning graph path completeness
- unsupported strong boundary warning
- evidence grounding

### Phase 5: Baselines

命令：

```powershell
python stpa_hf_dan_eswa_engine_final.py baseline-suite --cases <cases.jsonl> --out results/paper_v1/baseline_suite
```

预期对比：

- direct baseline 更容易 outcome-to-mechanism overreach
- generic CoT 次之
- full system 最保守且最审计友好

### Phase 6: Evidence audit

命令：

```powershell
python stpa_hf_dan_eswa_engine_final.py evidence-audit --bundle-dir results/paper_v1/bundles --out results/paper_v1/audit/evidence_support_audit
```

必须检查：

- invalid evidence ID
- catalog consistency
- claims without supporting evidence
- unsupported strong boundary warning

### Phase 7: Feedback gaps

命令：

```powershell
python stpa_hf_dan_eswa_engine_final.py feedback-gap-report --bundle-dir results/paper_v1/bundles --out results/paper_v1/feedback_gaps
```

输出必须明确：

- 哪个缺口阻断了更强 boundary claim
- 哪个缺口阻断了更强 UCA claim
- 哪个缺口只影响 audit，不影响结论

### Phase 8: Requirement candidates

命令：

```powershell
python stpa_hf_dan_eswa_engine_final.py evidence-requirement-candidates --gap-report results/paper_v1/feedback_gaps/feedback_gap_report.json --out results/paper_v1/requirements
```

要求：

- 不写成 HMI 设计结论
- 只写成 evidence/logging requirement candidates

### Phase 9: Counterfactual HMI injection

命令链：

```powershell
python stpa_hf_dan_eswa_engine_final.py generate-cf-specs --cases <cases.jsonl> --out results/paper_v1/cf_specs.jsonl
python stpa_hf_dan_eswa_engine_final.py generate-counterfactual --cases <cases.jsonl> --specs results/paper_v1/cf_specs.jsonl --out results/paper_v1/cf_cases.jsonl
python stpa_hf_dan_eswa_engine_final.py run --cases results/paper_v1/cf_cases.jsonl --out results/paper_v1/cf_bundles
python stpa_hf_dan_eswa_engine_final.py counterfactual-eval --base-bundle-dir results/paper_v1/bundles --cf-bundle-dir results/paper_v1/cf_bundles --specs results/paper_v1/cf_specs.jsonl --out results/paper_v1/cf_eval
```

四类模板必须覆盖：

1. takeover demand
2. ambiguous degradation
3. full support
4. partial support

每类必须单独统计：

- boundary shift rate
- UCA flip rate
- pathway score delta
- judge directional consistency
- warning delta

### Phase 10: Paper manifest

命令：

```powershell
python stpa_hf_dan_eswa_engine_final.py paper-manifest --cases <cases.jsonl> --bundle-dir results/paper_v1/bundles --baseline-dir results/paper_v1/baseline_suite --cf-report results/paper_v1/cf_eval/counterfactual_directional_consistency.json --missingness-profile results/paper_v1/table1/missingness_profile/dataset_missingness_profile.json --evidence-audit results/paper_v1/audit/evidence_support_audit/evidence_support_audit.json --feedback-gap-report results/paper_v1/feedback_gaps/feedback_gap_report.json --requirement-candidates results/paper_v1/requirements/evidence_requirement_candidates.json --out results/paper_v1/paper_result_manifest.json
```

用途：

- 冻结论文输入输出
- 生成表格来源清单
- 支持复现实验

---

## 6. HMI 注入实验的证明逻辑

HMI 注入要证明的不是真实因果，而是机制敏感性。

证明链：

`same incident text seed -> injected HMI cue -> updated PM context -> updated vulnerability -> updated boundary -> updated action selection -> updated UCA context -> ranked pathway shift`

需要回答的四个问题：

1. 注入后，boundary 是否方向性变化？
2. 注入后，dominant UCA 是否翻转或增强？
3. 注入后，路径分数是否按预期增减？
4. 注入后，judge 理由是否与 STPA-HF 方向一致？

结论边界：

- 可以说 sensitivity
- 不可以说 real-world causal effect
- 可以说 mechanism shift
- 不可以说 HMI caused crash

---

## 7. 人工标注执行计划

### 7.1 标注目标

先让系统代替人工跑一轮，再把这轮结果作为准人工标注参考。

### 7.2 标注字段

每个 case 必须标：

1. `boundary_label`
2. `update_vulnerability`
3. `dominant_uca`
4. `active_uca_set`
5. `primary_pm_slots`
6. `supporting_evidence_ids`
7. `insufficient_information_flags`
8. `annotator_notes`

### 7.3 标注原则

1. 只用文本证据。
2. 不补缺失事实。
3. 不把 outcome 当因果。
4. 不把 HMI 缺失当 HMI 不存在。
5. 不把 `not_reported` 解释为反证。

### 7.4 标注产物

- `expert_preview_labels.jsonl`
- `expert_preview_annotation_report.json`
- `adjudicated_labels.jsonl`
- `annotation_agreement_report.json`

---

## 8. 推荐执行顺序

如果要按最稳妥顺序跑，建议：

1. 冻结输入 case 文件。
2. 跑 input audit。
3. 跑 missingness profile。
4. 导出 annotation packets。
5. 跑 expert preview labels。
6. 跑 full system。
7. 跑 baselines。
8. 跑 evidence audit。
9. 跑 feedback gaps。
10. 跑 requirement candidates。
11. 跑 counterfactual specs / cases / bundles / eval。
12. 跑 paper manifest。
13. 再做人工标注 adjudication。
14. 最后整理表格与图。

---

## 9. 结果目录冻结

`results/paper_v1/` 下建议固定如下结构：

```text
results/paper_v1/
  annotation_packets/
  audit/
  baseline_suite/
  bundles/
  cf_bundles/
  cf_eval/
  cf_specs.jsonl
  cf_cases.jsonl
  feedback_gaps/
  requirements/
  table1/
  paper_result_manifest.json
  expert_preview_eval/
```

---

## 10. 验收标准

本轮修改与执行完成后，至少要满足：

1. `schema_valid >= 95%`
2. `invalid evidence ID = 0`
3. `catalog consistency = 1.0`
4. `unsupported strong boundary warning = 0`
5. `outcome_only escalation warning = 0`
6. 至少 3 类 boundary 可稳定出现
7. 至少 3 类 update vulnerability 可稳定出现
8. HMI 注入在模板层面表现出方向性变化
9. 人工代理标注和系统输出在核心标签上可解释一致
10. `paper_result_manifest` 可冻结复现

---

## 11. 论文叙事对应关系

这份计划最终服务的论文叙事是：

> 在稀疏自动驾驶事故文本下，STPA-HF 约束的 LLM reasoning graph 可以生成可审计的解释路径，并把 HMI 缺失转化为可计算的证据边界与敏感性分析，而不是事故真因还原。

---

## 12. 当前版本评分目标

执行完成后，希望达到：

- 叙事：9/10
- 实验：8.5/10

若要再向上走，下一步就不是改主线，而是增加：

1. 更大的人类标注样本。
2. 更完整的 HMI paired sensitivity.
3. 更强的多源外部有效性。

