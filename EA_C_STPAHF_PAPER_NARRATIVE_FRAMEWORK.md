# EA-C-STPA-HF 论文叙事与技术框架总纲

日期：2026-05-03  
状态：新一轮论文叙事冻结草案  
方法名称：Evidence-Admissible Conditional STPA-HF，简称 EA-C-STPA-HF  
中文名称：证据可接受的条件化 STPA-HF 方法

## 1. 论文总定位

本文不主张从稀疏公开事故报告中还原真实事故因果、真实驾驶员心理状态或真实 HMI 因果作用。

本文主张：

> 提出一种面向自动驾驶稀疏公开报告与文本功能场景的 EA-C-STPA-HF 方法，使 LLM 能够在 STPA-HF 约束下进行证据可接受的人因安全分析：在真实公开报告中区分 reported outcome、admissible mechanism claim、blocked mechanism claim；在显式补充 HMI、驾驶员状态、ADS 转换条件后，执行条件化驾驶员过程模型分析，并生成可审计的 HMI/日志改进候选。

核心落点是：

> 从“LLM 替专家猜事故原因”转为“LLM 在改进版 STPA-HF 证据制度下辅助专家进行可审计的人因安全分析”。

## 2. 为什么需要改进 STPA-HF

传统 STPA-HF 强调人-自动化系统控制结构、反馈、驾驶员过程模型、unsafe control action 与控制缺陷。它通常需要较完整的信息：

- 系统设计与自动化模式；
- HMI 提示与显示策略；
- 驾驶员角色、注意状态与响应时间；
- ADS 内部状态与退化过程；
- 接管/干预时间线；
- 事故视频、日志或深度调查材料。

但是公开事故/接管报告经常只提供：

- ENV：天气、道路、光照、交通环境；
- ACTOR：相关道路参与者；
- CAR：车辆状态、是否 ADS/ADAS involved、碰撞/接管/脱离 outcome；
- 少量 narrative 或事件描述。

HMI、driver state、ADS internal confidence、handover timing 往往缺失。因此，直接套用完整 STPA-HF 会产生两个风险：

1. 将公开报告中没有的 HMI/driver/ADS 事实补出来。
2. 从 collision/disengagement outcome 过度推断 takeover failure、HMI failure 或 driver process-model failure。

本文的改进是将 STPA-HF 从完整事故建模方法扩展为适合稀疏公开报告的证据受限方法。

## 3. EA-C-STPA-HF 的核心定义

EA-C-STPA-HF 包含三个关键词。

### 3.1 Evidence-Admissible

任何机制 claim 都必须满足证据可接受性要求。

机制 claim 包括：

- takeover demand occurred；
- driver failed to take over；
- HMI ambiguity contributed；
- driver process model was outdated or mismatched；
- ADS capability boundary was not communicated；
- responsibility transferred from ADS to human；
- intervention was feasible but missed or delayed。

如果报告没有对应证据，系统必须输出 blocked claim，而不是推断真实发生。

### 3.2 Conditional

当 HMI、driver-state、ADS transition 证据缺失时，系统不能生成真实事故结论，但可以在研究者显式注入条件后执行条件化 STPA-HF 分析。

条件化输入示例：

- HMI clearly issued takeover request with 5-second time budget；
- HMI only gave ambiguous degradation cue；
- driver was distracted；
- ADS reported perception confidence drop；
- system required driver acknowledgement；
- no takeover request was displayed。

这些条件只支持 conditional analysis，不能被回写为真实事故事实。

### 3.3 STPA-HF

STPA-HF 在本文中不是装饰性术语，而是分析骨架：

- 定义人-自动化控制结构；
- 定义驾驶员监督/接管角色；
- 定义 process-model update 所需反馈；
- 定义 update vulnerability；
- 定义 commitment boundary；
- 定义 UCA catalog；
- 规定 claim 与 evidence 的约束关系。

## 4. 双模式技术框架

EA-C-STPA-HF 有两个模式。

### 4.1 Base-report mode：真实公开报告模式

输入：

- NHTSA SGO crash/collision CSV；
- CA DMV collision reports；
- CA DMV disengagement reports；
- 其他公开事故/接管文本报告。

允许证据：

- reported evidence；
- derived evidence；
- not_reported marker。

不允许：

- 将缺失 HMI 补成事实；
- 将 collision 直接推成 takeover failure；
- 将 disengagement 直接推成 driver failure；
- 将 counterfactual evidence 当成真实 evidence。

输出：

- reported outcome；
- evidence-admissible accident factor codes；
- commitment boundary；
- update vulnerability；
- UCA set；
- process-model observability report；
- blocked mechanism claims；
- claim admissibility report；
- evidence/logging requirement candidates。

Base-report mode 的结论是：

> 在公开报告所给证据下，可以安全主张什么，不能安全主张什么，以及还需要什么证据才能做更强 STPA-HF 机制分析。

### 4.2 Specified-scenario mode：显式条件场景模式

输入：

- 真实高风险场景种子；
- 研究者显式注入的 HMI cue；
- 显式接管时间预算；
- 显式驾驶员注意/压力/分心状态；
- 显式 ADS 退化、系统 issue、intervention 证据。

输出：

- conditional driver process-model update；
- conditional mismatch hypothesis；
- conditional UCA；
- conditional HMI improvement candidates；
- conditional logging requirements；
- sensitivity profile。

Specified-scenario mode 的结论是：

> 当关键人机反馈条件被明确给定时，LLM-STPA-HF 能否生成符合理论方向的条件化驾驶员模型与 HMI 改进分析。

## 5. STPA-HF 改进点

### 5.1 从 process-model inference 到 process-model observability

传统问题：

> 驾驶员是否知道自动驾驶系统的真实状态？

公开报告场景下不可直接回答。

本文改为：

> 报告是否提供证据，使分析者可以主张驾驶员有机会更新其过程模型？

输出不是驾驶员真实心理，而是过程模型可观测性。

### 5.2 从 binary claim 到 claim admissibility ladder

每个机制 claim 分为四级：

- `admissible`：有直接或足够明确证据支持；
- `weakly_supported`：有间接证据，但仍有关键缺口；
- `blocked`：缺少支持该 claim 的必要证据；
- `counterfactual_only`：只在显式注入条件下成立。

### 5.3 从 missing field 到 blocked STPA-HF mechanism

不只报告字段缺失，而是说明该缺失阻断什么 STPA-HF claim。

示例：

- 缺 `HMI.time_budget_indicator`：不能支持驾驶员具有明确 time-budget awareness。
- 缺 `CAR.reported_intervention`：不能支持发生了人类接管失败。
- 缺 `CAR.perception_confidence`：不能区分感知退化、规划退化或 HMI 反馈问题。
- 缺 `CABIN.distraction`：不能主张驾驶员分心导致 update failure。

### 5.4 从事故结果分类到 accident factor coding audit

本文不预测 crash，也不解释真实 crash cause。

本文审计：

> collision/disengagement outcome 是否被 LLM 或分析流程过度编码为 takeover/HMI/driver failure。

### 5.5 从 HMI design requirement 到双层候选

Base-report mode 输出：

- evidence/logging requirement candidates。

Specified-scenario mode 输出：

- conditional HMI improvement candidates。

前者是事故报告和日志应记录什么，后者才是在显式条件下提出的 HMI 改进候选。

## 6. Process-model observability dimensions

本文将驾驶员过程模型分析拆成 7 个可观测维度。

| 维度 | 核心问题 | 所需证据 | 缺失时阻断的 claim |
|---|---|---|---|
| mode awareness | 驾驶员是否有证据知道 ADS 当前模式？ | mode display、mode transition、automation status | mode confusion、responsibility transfer failure |
| capability boundary awareness | 驾驶员是否有证据知道 ADS 能力边界？ | capability warning、ODD boundary cue、degradation cue | HMI capability-boundary failure |
| hazard salience | 报告是否支持关键风险对象可被感知？ | actor position、visibility、trajectory、narrative | driver missed hazard |
| time-budget awareness | 是否有接管/干预时间预算证据？ | takeover request time、time budget display、handover timing | failed takeover、delayed response |
| responsibility allocation | 是否有责任从 ADS 到人类转移的证据？ | takeover demand、required ack、manual control transition | unsupported transfer |
| expected ADS action | 是否有证据支持驾驶员预测本车行为？ | planned trajectory、HMI trajectory display、vehicle maneuver cue | expectation mismatch |
| intervention feasibility | 是否有证据说明驾驶员能否完成干预？ | time-to-collision、driver readiness、control availability | feasible but missed intervention |

这些维度用于判断公开报告支持何种 STPA-HF 分析，而不是推断驾驶员真实心理。

## 7. 方法流程

### Step 1：Evidence extraction and provenance tagging

从输入报告中抽取：

- ENV；
- ACTOR；
- CAR；
- HMI；
- CABIN；
- ADS transition；
- outcome；
- narrative。

每个证据标注 provenance：

- `reported`；
- `derived`；
- `not_reported`；
- `counterfactual`。

### Step 2：Outcome-mechanism separation

先固定 reported outcome：

- collision；
- crash；
- disengagement；
- intervention；
- no crash；
- unknown。

然后显式禁止：

> outcome alone -> takeover failure。

### Step 3：Process-model observability analysis

对 7 个维度判断：

- required evidence；
- observed evidence IDs；
- evidence status；
- observability level；
- blocked claims。

### Step 4：Claim admissibility gate

对机制 claim 进行证据等级判断：

- admissible；
- weakly_supported；
- blocked；
- counterfactual_only。

### Step 5：STPA-HF coding

输出：

- boundary state；
- update vulnerability；
- active UCA set；
- dominant UCA；
- causal/mechanism trace；
- evidence citations。

### Step 6：Conditional scenario analysis

只在显式注入 HMI/driver/ADS 条件时执行：

- conditional driver process-model update；
- conditional UCA；
- conditional vulnerability；
- HMI improvement candidates；
- sensitivity direction check。

## 8. 研究问题

### RQ1：可审计生成能力

EA-C-STPA-HF 能否从稀疏自动驾驶公开报告中生成 schema-valid、evidence-grounded、catalog-consistent 的 accident factor coding bundle？

对应实验：

- schema valid rate；
- invalid evidence ID rate；
- UCA catalog consistency；
- claim admissibility consistency；
- process-model observability completeness；
- source-level missingness profile。

### RQ2：过度机制编码控制

相比 direct LLM 和 generic CoT，EA-C-STPA-HF 是否减少 outcome-to-mechanism overcoding，尤其是 collision/disengagement 到 takeover failure、HMI failure、driver failure 的过度升级？

对应实验：

- boundary distribution；
- unsupported strong-boundary warnings；
- outcome-only escalation warnings；
- direct/generic/full comparison；
- ablation comparison。

### RQ3：条件化驾驶员过程模型分析

当显式补充 HMI cue、接管时间、责任转移、驾驶员状态和 ADS 退化条件后，系统能否按 STPA-HF 理论方向生成条件化驾驶员过程模型分析和 HMI/日志改进候选？

对应实验：

- counterfactual HMI sensitivity；
- process-model observability lift；
- conditional UCA direction consistency；
- HMI/logging candidate validity；
- expert review。

## 9. 贡献

### Contribution 1：Evidence-Limited STPA-HF adaptation

提出 EA-C-STPA-HF，将 STPA-HF 从完整事故建模扩展到稀疏公开报告下的证据可接受分析。

验证：

- process-model observability report；
- blocked mechanism claim report；
- source-regime missingness profile。

### Contribution 2：STPA-HF-constrained LLM pipeline

提出分阶段 LLM pipeline，约束 LLM 不从 outcome 直接推断 driver/HMI/takeover failure。

验证：

- full system vs direct LLM；
- full system vs generic CoT；
- ablation；
- evidence audit。

### Contribution 3：Process-model observability and claim admissibility audit

将驾驶员过程模型从不可验证心理推断转为可审计证据可观测性分析。

验证：

- 7 维 observability coverage；
- blocked claims；
- minimal evidence to unblock；
- human expert annotation。

### Contribution 4：Conditional driver-model and HMI improvement analysis

在显式场景条件下，展示 LLM-STPA-HF 可执行更完整的驾驶员过程模型与 HMI 改进候选生成。

验证：

- counterfactual sensitivity；
- specified-scenario runs；
- expert review of conditional candidates。

## 10. 实验设计

### Experiment 1：Dataset and evidence-regime audit

目标：

- 说明不同公开报告制度对 STPA-HF 人因机制分析的支持程度。

数据：

- CA DMV collision reports；
- CA DMV disengagement reports；
- NHTSA SGO ADS-only crash/collision cases；
- 必要时将 L2 ADAS 与 ADS 分开报告。

输出：

- dataset statistics；
- missingness profile；
- process-model observability by source；
- source-regime evidence coverage。

### Experiment 2：Auditable bundle generation

目标：

- 验证系统能生成结构有效、证据引用合法、UCA catalog 一致的 bundle。

指标：

- schema valid rate；
- invalid evidence ID count；
- claims without support；
- catalog consistency；
- bundle completeness。

### Experiment 3：Baseline comparison

目标：

- 验证 EA-C-STPA-HF 减少 LLM 过度机制编码。

条件：

- direct LLM；
- generic CoT；
- full EA-C-STPA-HF；
- full without priority；
- no process-model observability gate；
- no update stage。

指标：

- boundary distribution；
- UCA distribution；
- outcome-only escalation warning；
- unsupported strong-boundary warning；
- schema valid rate。

### Experiment 4：Claim admissibility and blocked-claim audit

目标：

- 验证每个强 claim 是否被 evidence gate 约束。

输出：

- admissible claim counts；
- blocked claim counts；
- weakly supported claim counts；
- minimal evidence to unblock；
- top blocked STPA-HF mechanisms。

### Experiment 5：Conditional scenario and counterfactual sensitivity

目标：

- 验证显式补入人机反馈条件后，系统是否按 STPA-HF 方向变化。

模板：

- explicit takeover demand；
- ambiguous degradation without transition；
- ambiguous degradation with transition pressure；
- full support feedback；
- partial support feedback；
- driver distracted；
- clear time budget；
- absent time budget；
- ADS confidence degradation；
- intervention feasible but delayed。

指标：

- boundary direction consistency；
- process-model observability lift；
- UCA direction consistency；
- HMI/logging candidate consistency；
- mismatch analysis。

### Experiment 6：Human expert evaluation

目标：

- 验证系统输出是否符合专家在证据约束下的 STPA-HF 分析判断。

标注对象：

- boundary label；
- process-model observability level；
- admissible claims；
- blocked claims；
- active UCA set；
- dominant UCA；
- insufficient information flags；
- evidence IDs。

注意：

- human labels 不是事故真因；
- labels 是“给定公开证据下的 STPA-HF evidence-admissible judgment”。

## 11. 建议论文表格

Table 1：Dataset composition and missingness by source regime。  
Table 2：Process-model observability coverage by source regime。  
Table 3：Auditable generation quality。  
Table 4：Boundary and UCA comparison against baselines。  
Table 5：Ablation and robustness。  
Table 6：Claim admissibility and blocked mechanism audit。  
Table 7：Conditional scenario / counterfactual sensitivity。  
Table 8：Evidence/logging requirements and conditional HMI candidate taxonomy。  
Table 9：Human expert evaluation。

## 12. 当前已有结果如何进入论文

当前 50-case mixed-source 结果可作为方法验证基础：

- full system schema valid：50/50；
- invalid evidence ID mean：0；
- UCA catalog consistency：1.0；
- direct baseline：47/50 not_supported_transfer；
- full system：36 contingent_readiness、10 supported_monitoring、4 not_supported_transfer；
- unsupported strong-boundary warnings：0；
- counterfactual directional consistency：0.9476；
- feedback gaps / evidence requirements：570。

这些结果支持：

- LLM 直接推理存在 outcome-to-mechanism overcoding；
- STPA-HF 约束能收紧 claim boundary；
- evidence audit 可保持证据引用一致；
- counterfactual cue 会引起理论方向上的 boundary sensitivity。

这些结果尚不能单独支持：

- 真实事故因果重建；
- 真实驾驶员认知推断；
- 真实 HMI causal effect；
- 完整 STPA-HF 事故建模；
- 最终 HMI 设计有效性。

## 13. 论文最终结论

本文应支持：

> EA-C-STPA-HF 使 LLM 能够在稀疏自动驾驶公开报告中执行证据可接受的人因安全分析。系统不会从事故结果直接推断驾驶员或 HMI 失败，而是区分 reported outcome、admissible claims、blocked claims 与 conditional claims；当关键 HMI/driver/ADS 条件被显式给定时，系统进一步支持条件化驾驶员过程模型分析，并生成可审计的 HMI/日志改进候选。

本文不能支持：

- 还原真实事故原因；
- 证明真实 HMI 导致事故；
- 推断真实驾驶员心理；
- 验证最终 HMI 设计方案；
- 将 counterfactual 输出解释为真实事件。

## 14. 下一轮写作原则

1. 所有 Introduction claim 必须映射到方法模块与实验。
2. 不再把 missingness 当作消极结果，而是作为 STPA-HF 可观测性与 claim boundary 的核心问题。
3. 不再说 LLM 推理驾驶员心理，而说 LLM 在 STPA-HF 证据制度下分析过程模型可观测性。
4. 不再把 requirement candidates 写成 HMI design requirements，而写成 evidence/logging requirements。
5. HMI improvement candidates 只出现在 specified-scenario mode，必须带 conditional 标签。
6. 主投方向建议以 AAP 为优先，ESWA 为技术专家系统备选；若投 ESWA，必须强化 pipeline、schema、human-gold 与 ablation。
