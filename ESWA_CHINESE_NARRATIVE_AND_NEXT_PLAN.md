# ESWA 中文论文叙事与下一轮细颗粒度计划

版本：v1.0  
日期：2026-04-28  
定位：本文档用于统一论文叙事、实验解释、代码问题复盘和下一轮执行计划。它应当作为后续代码、实验、人工标注和论文写作的中文主纲领。

## 1. 当前论文的一句话落点

本文提出一种 **缺失感知、STPA-HF 约束的 LLM 专家系统**，将多源自动驾驶公开事件报告转化为 **可审计的 STPA-HF safety-case bundle**；系统不还原真实事故因果，不推断真实驾驶员心理，也不证明真实 HMI 因果效果，而是在证据缺失条件下明确哪些 feedback-boundary 安全主张可以成立、哪些更强主张被缺失证据阻断，并输出面向未来报告和日志改进的 evidence/logging requirement candidates。

更短的论文主张可以写成：

> Sparse public automated-driving reports are real high-risk scenario seeds, but not complete causal ground truth. A missingness-aware STPA-HF constrained LLM expert system can convert them into auditable safety-case bundles, reduce unsupported crash-to-takeover-failure escalation, and identify evidence/logging needs for stronger future feedback-boundary analysis.

中文表达：

> 自动驾驶公开报告可以作为真实高风险功能场景种子，但不能当作完整事故真因。本文的方法把这些稀疏报告转化为可审计的 STPA-HF 安全分析包，减少从 crash 到 takeover failure 的无证据过度推断，并指出未来要支持更强 feedback-boundary 安全主张所需的 HMI、驾驶员状态、介入和 ADS 内部证据。

## 2. 研究对象到底是什么

本文研究对象不是“事故复盘”，而是：

> 在公开报告证据稀疏、HMI/driver-state/internal ADS 信息经常缺失的前提下，如何生成证据受限、可审计、可反事实检验的 STPA-HF safety case。

因此，报告中的 crash、collision、disengagement 是真实高风险场景的入口，但不是完整因果链。我们把它们作为 functional scenario seed，进入 STPA-HF 安全分析，而不是让 LLM 从结局反推真实心理、真实 HMI、真实系统内部状态。

本文明确不做：

- 不还原真实事故原因。
- 不证明真实 HMI 导致或避免事故。
- 不推断真实驾驶员认知状态。
- 不把 requirement candidates 说成最终 HMI 设计要求。

本文明确要做：

- 从公开报告构建 provenance-aware functional case。
- 区分 reported、derived、not_reported、assumed_for_counterfactual。
- 用 STPA-HF 约束 LLM 的安全分析逻辑。
- 生成 boundary、update vulnerability、UCA、evidence trace、audit、feedback gaps。
- 将缺失证据转化为未来报告和日志应补充的 evidence/logging requirement candidates。

## 3. STPA-HF 在本文中到底起什么作用

STPA-HF 不是装饰性理论，而是本文的推理骨架。它至少承担五个作用。

第一，定义 human-automation feedback boundary。  
系统不直接问“事故是不是接管失败”，而是问：在现有证据下，人机之间的责任、监控、接管和支持边界能被支持到什么程度？

第二，定义 commitment boundary 标签。  
当前代码中的核心边界包括：

- `supported_monitoring`：有证据支持自动化仍在可监控支持状态。
- `contingent_readiness`：存在高风险或准备压力，但没有足够证据证明发生了明确转移或不支持的接管要求。
- `not_supported_transfer`：有明确证据支持 disengagement、takeover demand、driver/operator intervention、support withdrawal 或 transition requirement。

第三，定义 update vulnerability。  
STPA-HF 关注人在自动化反馈中的更新过程。当前系统使用：

- `missed_feedback`
- `ambiguous_feedback`
- `misinterpreted_feedback`

这些不是在判断真实驾驶员心理，而是在给定证据下标注可能的 feedback update vulnerability。

第四，约束 UCA。  
UCA 不由 LLM 自由编造，而来自 catalog。不同 boundary 对应不同 UCA 家族，避免直接从 crash 跳到 takeover omission。

第五，要求每个强主张绑定 evidence。  
如果 HMI、驾驶员状态、系统介入、ADS 内部置信度都缺失，系统必须保留认知边界，而不是补出一个看似完整的事故故事。

一句话说：

> STPA-HF 的作用是把 LLM 从“事故故事生成器”改造成“证据受限的安全分析专家系统执行器”。

## 4. HMI 在本文中到底是什么

HMI 不是本文要证明的真实事故原因。HMI 在本文中是 feedback-boundary evidence channel。

也就是说，HMI 字段的意义不是“我们要补出真实 HMI 是什么”，而是：

- 如果真实报告没有 HMI，则 base case 必须保留 `not_reported`。
- 如果要支持更强 boundary claim，比如明确 takeover demand 或 supported monitoring，就必须说明缺哪些 HMI/driver/ADS 证据。
- 如果在 counterfactual 实验中注入 HMI cue，只能说明系统对反馈边界证据敏感，不能说明真实 HMI 有因果效果。

因此 HMI 有三层作用：

- Base-case evidence slot：在真实报告证据中被检查，缺失则保留缺失。
- Counterfactual variable：在反事实中注入不同反馈线索，检查 STPA-HF 输出方向是否变化。
- Evidence/logging requirement target：提示未来报告或日志应记录哪些 HMI 证据，才能支持更强安全主张。

## 5. “缺失前提下我们在检查什么”

缺失前提下，我们不是在问“能不能猜出真相”，而是在检查系统是否具备安全分析中的证据纪律。

核心检查点如下：

| 实验/产物 | 缺失条件下检查什么 | 论文价值 |
| --- | --- | --- |
| Missingness profile | 公开报告到底缺什么，缺失比例是否可量化 | 证明问题真实存在，不是人为制造 |
| Feedback gap report | 哪些 HMI、驾驶员、介入、ADS 内部证据缺失阻断更强主张 | 把 missingness 变成可审计边界 |
| Full system run | 系统能否在缺失条件下生成 schema-valid、evidence-grounded、catalog-consistent bundle | 证明专家系统可运行且输出结构化 |
| Evidence audit | 是否存在 invalid evidence ID、无证据 claim、catalog 不一致 | 证明输出可审计，不只是文本 |
| Direct baseline | 直接 LLM 是否把 crash 过度推成 takeover failure | 证明为什么需要 STPA-HF 约束 |
| Generic CoT baseline | 通用 CoT 是否仍不够稳定 | 证明不是“让模型多想一步”就够 |
| No-update ablation | 去掉 PM/update 阶段后 boundary 是否更容易变强或不稳定 | 证明 staged update 有方法价值 |
| Requirement candidates | 缺失证据应如何转化成未来报告/日志需要 | 证明系统不止分类，还能服务安全审计 |

因此，缺失前提下的主要结论应是：

> 系统能在证据不足时保持边界克制，显式指出哪些证据缺口阻止 stronger feedback-boundary claim，并避免将 crash outcome 直接等同于 takeover failure。

## 6. “补齐之后说明什么”

这里的“补齐”必须分成两种，不能混在一起。

### 6.1 真实来源的证据补充

例如 CA DMV disengagement 官方记录中可能报告：

- disengagement initiated by test driver / AV system / remote operator；
- reported intervention；
- reported system issue；
- disengagement cause。

这类信息不是模型猜的，而是来源报告中存在的证据。它的作用是检查：

> 当真实来源提供更多 transition/intervention evidence 时，系统是否相应支持更强 boundary claim。

这可以支持 evidence-regime narrative：不同公开报告制度提供不同证据，因此支持不同强度的 safety claim。

### 6.2 反事实 HMI 注入

例如对同一个 ENV/ACTOR/CAR 高风险场景注入：

- explicit takeover demand；
- ambiguous degradation；
- full support；
- partial support。

这不是补出真实事实，而是 controlled sensitivity test。它的作用是检查：

> 在相同场景下，如果 feedback evidence 以不同形式出现，boundary、UCA、vulnerability 是否按 STPA-HF 理论方向变化。

所以 counterfactual 只能支持：

- 系统对 HMI feedback cues 敏感。
- 输出变化方向大体符合 STPA-HF。
- 可以形成 feedback-boundary sensitivity profile。

不能支持：

- 真实 HMI 导致事故。
- 某个真实 UI 设计有效或无效。
- 驾驶员当时真实看见或没看见某个提示。

## 7. 当前代码和结果与叙事的符合程度

总体判断：当前代码已经基本对齐上述叙事，可以作为 ESWA expert-system paper 的方法原型继续推进。

已经符合的部分：

- 输入侧已支持 provenance-aware functional case。
- `external_case_ingestion_final.py` 能摄入 NHTSA SGO、CA DMV collision augmented CSV、CA DMV disengagement CSV/dir。
- 主引擎已区分 reported、derived、not_reported、assumed_for_counterfactual。
- 主引擎已有 staged STPA-HF LLM 推理、baseline suite、ablation、CF specs、CF evaluation。
- 已有 `missingness-profile`、`feedback-gap-report`、`evidence-requirement-candidates`、`evidence-audit`、`paper-manifest`。
- `results/paper_v1_30_mixed_sources/` 已经比 `results/verify/` 更适合作为论文实验根目录。
- human annotation guide 已经建立，AI-pilot labels 明确不能作为 publication gold。

仍需改进的部分：

- Prompt 仍有一例 crash-only unsupported strong-boundary warning。
- `ambiguous_degradation` 反事实模板方向一致性不足。
- requirement candidates 数量过多，论文中必须做 taxonomy，不应逐条堆砌。
- full-system standalone 与 baseline-suite rerun 的 boundary 分布存在差异，说明 LLM 服务存在非严格确定性。
- 当前还没有真实 human-gold evaluation。
- UCA 和 vulnerability 标签相对细，人工标注时可能一致性低，应先稳住 boundary 和 insufficient-information flags。
- CA DMV collision augmented CSV 必须标注为 third-party derived，不可写成官方 DMV CSV。
- 旧中文总纲中存在编码乱码，新中文文件应作为后续中文叙事基准。

## 8. 最新 30-case mixed-source 结果怎么解释

输入：

- 10 个 NHTSA SGO official crash CSV case。
- 10 个 CA DMV collision augmented CSV case。
- 10 个 CA DMV official disengagement CSV case。

### 8.1 Missingness 和 gaps

30 个 case 的平均 missingness 为 `0.6967`。这说明即使加入 DMV 数据，HMI、driver-state、internal ADS evidence 仍然大量缺失。

Feedback gaps 共 `340`：

- HMI feedback gaps：`150`
- driver-state gaps：`60`
- internal ADS/transition gaps：`130`

按来源：

- NHTSA crash CSV：`120`
- CA DMV collision augmented：`120`
- CA DMV disengagement official：`100`

解释：

> DMV disengagement 记录减少了 `reported_intervention` 和 `reported_system_issue` 的缺口，但仍没有解决 HMI display、time budget、driver state、perception confidence、planner confidence 等关键证据缺失。

这正好支持本文的 evidence-regime 叙事：不同来源不是“谁更真实”，而是提供了不同强度、不同类型的安全分析证据。

### 8.2 Full system

Full system 结果：

- `30/30` schema valid。
- `contingent_readiness = 23`
- `not_supported_transfer = 7`

解释：

> 系统没有把全部 crash/collision/disengagement 都判为 takeover failure，而是在证据足够时支持更强 boundary，在证据不足时保留 contingent_readiness。

### 8.3 Baseline

Direct baseline：

- `30/30 not_supported_transfer`
- `30/30 UCA-NS-1`

解释：

> 直接 LLM 明显把事件结果过度升级为不支持接管或接管失败。这是本文方法必要性的核心证据。

Generic CoT：

- `25 NS + 4 CR + 1 SM`

解释：

> 通用 CoT 有少量缓解，但仍强烈偏向 NS，说明问题不只是“有没有推理链”，而是有没有 STPA-HF 和 evidence constraints。

No-update ablation：

- 本轮 `30/30` valid；
- `17 CR + 13 NS`。

解释：

> 去掉 update 阶段后，系统更容易向 NS 移动，说明 PM/update 阶段有助于保留更克制的证据边界。早先 20-case 中 no_update 只有 `18/20` valid，说明该消融条件也暴露了 robustness 风险；论文中应如实报告不同阶段的 schema robustness。

### 8.4 Evidence audit

结果：

- invalid evidence ID mean = `0`
- UCA catalog consistency = `1.0`
- claims without supporting evidence mean = `0`
- unsupported strong-boundary warning = `1`

解释：

> 总体审计质量良好，但仍存在一个高价值失败案例。这个案例应作为 prompt hardening 和 audit warning 的例证，而不是隐藏。

### 8.5 Counterfactual HMI

结果：

- CF pairs = `120`
- schema valid = `120/120`
- overall directional consistency = `0.9417`
- takeover demand = `1.0`
- full support = `1.0`
- partial support = `1.0`
- ambiguous degradation = `0.7667`

解释：

> 系统对明确 HMI cue 的方向变化稳定，但对 ambiguous degradation 的理论期待和模板表达仍不够清晰。下一轮必须重写该模板或调整评价规则。

## 9. 当前最重要的代码/实验问题清单

### 问题 1：仍有 crash-only over-escalation

表现：`external_nhtsa_sgo_882f14ad142c` 出现 unsupported strong-boundary warning。

意义：这是本文要解决的问题在系统内部残留的一例，不是小问题。它说明 prompt 或 post-hoc audit 还要更硬。

下一步：增加规则：

> 对 crash/collision case，不得仅凭 crash outcome、actor conflict、deceleration 或 severity 判定 `not_supported_transfer`；必须有 source-reported intervention、disengagement、takeover demand、support withdrawal 或 transition requirement。

### 问题 2：Ambiguous degradation CF 不稳定

表现：方向一致性 `0.7667`，低于其他模板。

可能原因：

- 模板太像弱 takeover demand。
- 评价规则要求“保持 CR”可能过严。
- 不同 source regime 下 ambiguous degradation 的理论方向不完全一致。

下一步：把模板拆成两类：

- ambiguous support degradation without transition demand：预期保持 CR 或维持原边界。
- ambiguous degradation with explicit transition pressure：允许向 NS 移动。

### 问题 3：没有 human-gold

表现：当前 AI-pilot labels 只能测试接口，不能作为论文主评价。

下一步：至少 2 名标注者，对 40-50 case 做 human-gold candidate labels，并计算 agreement。

优先标注：

- boundary label；
- insufficient-information flags；
- blocked stronger claims；
- supporting evidence；
- dominant UCA；
- update vulnerability。

### 问题 4：LLM 非严格确定性

表现：standalone full system 是 `23 CR + 7 NS`，baseline-suite 内 full-system rerun 是 `20 CR + 10 NS`。

下一步：

- 论文主结果必须引用 frozen output path 和 manifest hash。
- 增加 run_id、model、base_url、created_at、case_file_hash、bundle_dir_hash。
- 关键表格只从 frozen `results/paper_v1_*` 读取。

### 问题 5：Requirement candidates 需要压缩成 taxonomy

表现：30 case 输出 `340` 条 candidates，主文不能逐条展示。

下一步：论文中只报告：

- evidence type；
- source regime；
- blocked stronger claim；
- priority；
- count；
- representative examples。

### 问题 6：UCA/vulnerability 细粒度标签可能导致人工一致性低

表现：AI-pilot 方向显示 boundary 比 UCA/vulnerability 更稳。

下一步：

- 主指标优先报告 boundary、insufficient-information、blocked claims。
- UCA/vulnerability 作为 secondary analysis。
- 人工标注指南中增加 tie-break rules。

### 问题 7：CA DMV collision 数据源边界要写清楚

表现：当前 collision CSV 是第三方 augmented，不能写成官方 CSV。

下一步：

- 论文中写作：third-party augmented CSV derived from CA DMV AV collision PDFs。
- official source 只用于 NHTSA SGO 和 CA DMV disengagement。

### 问题 8：需要 paper pipeline 固化

表现：当前命令已经可跑，但还需要一个论文专用脚本把 case build、audit、LLM run、CF、manifest 串起来。

下一步：

- 新增 `run_paper_v1_pipeline.ps1` 或整理现有 `run_pipeline.sh`。
- Windows 环境优先用 PowerShell 脚本，避免路径和编码问题。

## 10. 下一轮细颗粒度计划

### P0：冻结叙事和术语

目标：所有代码产物、表格、论文段落使用同一套边界。

任务：

- 采用本文档作为中文主纲领。
- 英文主文使用 `ESWA_PAPER_MASTER_GUIDANCE_AND_PLAN.md` 的框架，但修复乱码中文。
- 统一术语：`evidence/logging requirement candidates`，不要只写 `requirements`。
- 所有图表避免写 “HMI causes crash” 或 “driver cognition inferred”。

验收：

- 论文 introduction、method、experiment 三部分都能对应同一个 one-sentence claim。

### P1：代码 prompt hardening 与审计增强

目标：降低 unsupported strong-boundary warning。

任务：

- 在 STPA-HF prompt 中加入 crash/collision boundary guardrail。
- 在 post-hoc audit 中将 strong boundary 证据分级：
  - explicit transition/intervention evidence；
  - indirect event pressure evidence；
  - outcome-only evidence。
- 如果 `not_supported_transfer` 只有 outcome-only evidence，则输出 warning。
- 将 warning 汇总到 paper summary JSON。

验收：

- 30-case rerun 中 unsupported strong-boundary warning 降到 `0` 或保留但被正确标记。
- 不因过度保守导致所有 disengagement case 都退回 CR。

### P2：重写 ambiguous degradation CF 模板

目标：让 CF 实验的理论期待更清楚。

任务：

- 拆分 ambiguous degradation：
  - `ambiguous_degradation_no_transition`
  - `ambiguous_degradation_with_transition_pressure`
- 更新 CF evaluation 的 expected direction。
- 按 source regime 汇报 CF consistency。

验收：

- ambiguous 类模板方向一致性达到 `>= 0.90`，或论文中能解释为什么它天然存在多方向性。

### P3：冻结 50-case 主实验数据

目标：从 pilot 进入主实验。

建议配比：

- NHTSA SGO official crash/collision：20
- CA DMV collision augmented：15
- CA DMV official disengagement：15

采样原则：

- 覆盖不同 actor：vehicle、pedestrian、cyclist、parked object、two-wheeler。
- 覆盖不同 road geometry：intersection、straight road、lane change、parking/curb。
- 覆盖不同 source regime。
- 保留 intervention/system issue 有无差异。

产物：

- `data/cases/paper_50_mixed_sources_v1.jsonl`
- `results/paper_v1_50_mixed_sources/sample_summary.json`
- `results/paper_v1_50_mixed_sources/input_audit/`

验收：

- case 数量 `>= 50`。
- source composition 固定。
- forbidden label leakage = `0`。

### P4：人工标注进入正式流程

目标：让 ESWA 主实验有 human-gold evaluation。

任务：

- 从 50 case 生成 annotation packets。
- 至少 2 名标注者独立标注。
- 标注不看模型输出。
- 先计算 boundary agreement，再看 UCA/vulnerability。
- 生成 adjudicated labels。

产物：

- `data/annotation_packets/paper_50_v1/`
- `data/annotations/human_raw_A1.jsonl`
- `data/annotations/human_raw_A2.jsonl`
- `data/annotations/human_adjudicated_v1.jsonl`
- `results/paper_v1_50_mixed_sources/human_agreement/`

验收：

- 至少 40 case 有双人标签，最好 50 case 全部完成。
- boundary label agreement 可报告。
- disputed cases 有 adjudication rationale。

### P5：50-case 完整实验重跑

目标：形成论文主结果目录。

建议目录：

```text
results/paper_v1_50_mixed_sources/
```

核心命令顺序：

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
- unsupported strong-boundary warning count 尽量为 `0`，若不为 0 必须逐例解释。
- direct baseline 相对 full system 明显过度 NS。
- CF overall directional consistency `>= 0.90`。
- evidence requirement candidates 能按 taxonomy 汇总。

### P6：论文表格和图

建议表格：

- Table 1：multi-source dataset statistics and missingness。
- Table 2：full system vs direct/generic CoT against human gold。
- Table 3：boundary escalation and ablation。
- Table 4：evidence audit and catalog consistency。
- Table 5：counterfactual HMI feedback-boundary sensitivity。
- Table 6：feedback gaps and evidence/logging requirement taxonomy。

建议主图：

1. Multi-source public reports。
2. Provenance-aware functional case builder。
3. STPA-HF constrained LLM reasoning。
4. Safety-case bundle output。
5. Evidence audit、feedback gaps、requirement candidates、CF sensitivity。

## 11. 下一轮论文写作的核心逻辑

Introduction 可以按六段写：

第一段：自动驾驶公开报告是安全分析的重要来源，但通常只完整给出 ENV/ACTOR/CAR 和事件结果。  
第二段：HMI、driver-state、takeover/intervention、internal ADS confidence 常缺失，导致 feedback-boundary 安全分析困难。  
第三段：直接 LLM 容易从 crash/collision outcome 过度推断 takeover failure。  
第四段：STPA-HF 提供 human-automation feedback、commitment boundary、update vulnerability 和 UCA 的专家分析框架。  
第五段：本文提出 missingness-aware STPA-HF constrained LLM expert system，生成可审计 safety-case bundle。  
第六段：贡献包括 functional case representation、STPA-HF LLM pipeline、evidence audit/gap-to-requirement、multi-source evidence-regime and CF sensitivity evaluation。

三条 RQ 固定为：

RQ1：系统能否在公开报告缺失条件下生成 schema-valid、evidence-grounded、catalog-consistent 的 STPA-HF safety-case bundle？  
RQ2：相比 direct LLM 和 generic CoT，STPA-HF 分阶段推理能否减少 unsupported crash-to-takeover-failure escalation？  
RQ3：不同 evidence regime 和反事实 HMI feedback cue 下，boundary、UCA、vulnerability 是否呈现符合 STPA-HF 的 sensitivity profile？

## 12. 最终结论应该支持什么

本文最终应支持：

> 缺失感知、STPA-HF 约束的 LLM 专家系统可以把稀疏、多源自动驾驶公开报告转化为可审计的 safety-case bundle；它能显式保留 HMI、driver-state、internal ADS 证据缺口，减少从 crash 到 takeover failure 的无证据过度升级，并把 blocked stronger claims 转化为未来安全报告和系统日志应补充的 evidence/logging requirement candidates。

本文最终不应支持：

- 本系统还原了真实事故因果。
- 本系统证明了某个真实 HMI 造成事故。
- 本系统推断了真实驾驶员心理。
- 本系统输出的是最终 HMI 设计方案。

## 13. 当前最应该做的下一步

如果只选三个最重要动作：

1. 先修 prompt 和 audit，解决 crash-only strong-boundary warning。
2. 重写 ambiguous degradation CF 模板，保证反事实实验的理论口径清楚。
3. 启动 50-case 数据冻结和双人 human-gold annotation。

这三个动作完成后，本文才会从“方法和 pilot 很有希望”进入“ESWA 主实验证据足够”的阶段。
