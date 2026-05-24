# AAP 论文叙事 V1：基于驾驶员过程模型的 STPA-HF 桌面推演

日期：2026-05-15

## 1. 一句话定位

本文提出一种 **STPA-HF 约束的驾驶员过程模型桌面推演框架**，用于将人机共驾事故/接管文本转化为可审计的多路径推演包。系统以驾驶员/安全员为核心控制者，将事故文本证据映射为驾驶员过程模型四象限（CPS、CPB、OPS、OPB），分析这些心智/过程模型如何被反馈、车辆行为、道路环境和其他交通参与者信息形成或更新，并正向推导候选控制动作、UCA-in-context 链路、结果兼容性和改进需求。

本文的目标不是还原唯一事故真因，而是为安全分析员提供一种桌面推演工具：在公开事故/接管报告证据有限的条件下，系统化回答“驾驶员需要知道什么、报告支持其知道什么、哪些过程模型更新无法验证、哪些控制动作链路可能进入不安全控制动作、哪些数据/HMI/日志字段应在后续事件中补充”。

## 2. 核心问题定义

人机共驾事故复盘中的关键困难，不是简单判断事故是否发生，而是理解驾驶员在自动化系统控制下处于怎样的 **process-model problem**：

- 驾驶员是否能形成关于 ADS/车辆当前状态的过程模型（CPS）？
- 驾驶员是否能形成关于 ADS/车辆未来行为和能力边界的过程模型（CPB）？
- 驾驶员是否能形成关于道路、信号、可见性等外部当前状态的过程模型（OPS）？
- 驾驶员是否能形成关于其他交通参与者未来行为的过程模型（OPB）？
- 这些过程模型如何被 HMI、车辆行为、道路观察、他车运动、接管提示或干预记录更新？
- 这些过程模型与更新缺口如何影响候选驾驶员控制动作，并进一步形成 UCA-in-context 链路？

因此，本文将任务定义为：

> 给定一段人机共驾事故/接管文本，生成一个 evidence-bounded driver process-model tabletop replay package，包括证据边界、驾驶员过程模型、过程模型更新来源、候选控制动作、UCA 链路、结果兼容性、路径排序和改进需求。

## 3. 理论依据

### 3.1 驾驶员心智模型与接管研究

2018 年之后自动驾驶人因研究持续强调：驾驶员在自动化驾驶中可能脱离控制环，接管质量取决于情境意识恢复、时间预算、非驾驶任务、HMI 提示、信任与心理负荷等因素。相关研究通常通过驾驶模拟器、眼动、生理信号、反应时、接管质量等数据建模驾驶员状态或接管表现。

这些研究为本文提供理论基础：驾驶员是否能够安全接管，本质上取决于其是否拥有足够的、及时更新的过程模型。但这些研究通常依赖实验数据，而公开事故报告往往只有稀疏文本，缺少眼动、生理、HMI 和内部 ADS 日志。因此，本文不是预测真实驾驶员状态，而是把事故文本转化为可审计的 process-model replay：哪些心智/过程模型变量有证据，哪些只能作为弱假设，哪些因为证据缺失必须阻断强结论。

### 3.2 STPA-HF 与过程模型

STPA-HF 的优势在于，它不是只看组件故障，而是关注控制结构、反馈、控制动作和控制者过程模型之间的关系。本文将驾驶员过程模型细化为四类变量：

| 变量 | 本文解释 | 事故文本中的例子 |
|---|---|---|
| CPS | 驾驶员关于 ADS/车辆/控制权当前状态的过程模型 | ADS 是否 active，是否处于 autonomous mode，是否发生 disengagement，控制权是否转移 |
| CPB | 驾驶员关于 ADS/车辆未来行为和能力边界的过程模型 | ADS 是否会制动、避让、保持车道，是否仍处于 ODD 或能力边界内 |
| OPS | 驾驶员关于外部环境当前状态的过程模型 | 道路结构、交叉口、车道、天气、可见性、交通信号 |
| OPB | 驾驶员关于其他交通参与者未来行为的过程模型 | 后车是否会减速，旁车是否会切入，行人/骑行者是否会进入冲突路径 |

本文对 STPA-HF 的适配创新是：将这些过程模型变量从传统设计期 hazard analysis 中转化为事故复盘中的桌面推演节点，并严格区分 observed evidence、abductive hypothesis、blocked claim。

### 3.3 事故/接管报告的证据边界

公开 CA DMV collision/disengagement、NHTSA SGO 等报告适合支持事件事实提取和异常事件复盘，但通常不足以支持真实驾驶员心理或唯一事故因果判断。因此本文采用 evidence-bounded 原则：

- reported / derived evidence 可以支持事实节点。
- not_reported 只能支持 evidence gap，不能支持事实缺席。
- collision/disengagement outcome 只能作为 outcome compatibility constraint，不能激活 UCA。
- HMI/driver-state/internal ADS 缺失不是论文弱点，而是桌面推演必须显式输出的数据需求。

## 4. 方法框架

本文方法链路如下：

```text
事故/接管文本
-> provenance-aware evidence packet
-> CPS/CPB/OPS/OPB 驾驶员过程模型
-> process-model formation/update analysis
-> other factors affecting action selection
-> candidate driver control actions
-> forward-derived UCA-in-context hypotheses
-> outcome compatibility gate
-> LLM judge pathway ranking
-> tabletop replay package
-> data / HMI / logging improvement candidates
```

其中，LLM 的作用不是自由解释事故，而是在 STPA-HF schema、证据边界和 gate 约束下生成结构化节点。每个节点必须引用证据 ID 或声明证据缺口。

## 5. 三个 RQ

**RQ1：桌面推演生成能力。**  
系统能否从人机共驾事故/接管文本中生成 schema-valid、evidence-grounded、STPA-HF-compliant 的驾驶员过程模型桌面推演包？

**RQ2：方法约束价值。**  
相比 direct LLM 和 generic CoT，STPA-HF 分阶段过程模型推演是否能减少 outcome-only overreach，尤其是从 collision/disengagement 直接推出 takeover failure 或不安全驾驶员动作？

**RQ3：反馈与数据需求敏感性。**  
在同一事故场景下，注入不同 HMI/接管时间/能力边界/驾驶员状态记录后，过程模型更新、候选动作、UCA 链路排序和改进需求是否发生符合 STPA-HF 逻辑的变化？

## 6. 三个贡献

**Contribution 1：提出驾驶员过程模型桌面推演任务定义。**  
本文定义了面向人机共驾事故/接管文本的 driver process-model tabletop replay 任务，将事故复盘从单一原因判断转化为证据约束的过程模型、控制动作和 UCA 多路径推演问题。（Section 2）

**Contribution 2：提出 STPA-HF 约束的多节点推演框架。**  
本文将 STPA-HF 驾驶员过程模型四象限操作化为可计算节点，并构建 evidence -> PM variables -> update process -> other factors -> action selection -> UCA-in-context -> outcome compatibility 的推演链路。框架使用 schema validation、evidence ID 引用、case-specific UCA gate 和 LLM judge 排序，避免把事故结果直接当成 UCA 证据。（Section 3）

**Contribution 3：在真实事故/接管文本上评估桌面推演包的可审计性和改进价值。**  
本文基于 CA DMV collision/disengagement 等公开文本数据评估系统的 schema 有效性、证据一致性、overreach 抑制、多路径排序和 HMI/数据记录需求生成能力，并通过反馈注入实验分析过程模型更新和 UCA 链路的敏感性。（Sections 4-5）

## 7. 实验设计

### RQ1：生成质量

指标：

- schema valid rate
- invalid evidence ID count
- UCA catalog consistency
- tabletop replay package completeness
- 每个 case 的 PM 四象限覆盖率
- 每个 case 的 pathway 数量与状态分布

主要表格：

- Table 1：数据集统计与缺失分布
- Table 2：桌面推演包生成质量

### RQ2：方法约束价值

对比：

- direct LLM
- generic CoT
- no-update ablation
- full STPA-HF tabletop replay

指标：

- outcome-only UCA activation warning
- crash-to-transfer overreach warning
- not_reported-as-fact warning
- observed UCA without action evidence
- abductive pathway with complete PM/update/action chain

主要表格：

- Table 3：baseline 与 ablation 对比
- Table 4：evidence audit 与 overreach audit

### RQ3：反馈/数据需求敏感性

实验：

- base report
- HMI mode display injected
- takeover time budget injected
- capability boundary cue injected
- driver intervention/logging trace injected

观察：

- update_process 是否从 evidence_gap_only 变为 observed_update_claim
- candidate action 是否从 blocked/weak 变为 weak/admissible
- UCA pathway score 是否变化
- missing requirement candidates 是否减少
- blocked claims 是否解除

主要表格：

- Table 5：HMI/数据字段注入敏感性
- Table 6：改进需求 taxonomy

## 8. 当前代码对应关系

当前主引擎 `stpa_hf_dan_eswa_engine_final.py` 已收束到 `driver_pm_tabletop_replay_v2.4.3`。

主要输出：

- `e*_evidence_packet.json`：证据对象
- `e*_pm_context.json`：驾驶员过程模型四象限
- `e*_update_process.json`：过程模型形成/更新分析
- `e*_candidate_actions.json`：候选驾驶员控制动作
- `e*_forward_uca_hypotheses.json`：正向 UCA 假设
- `e*_ranked_pathways.json`：LLM judge 路径排序
- `e*_tabletop_replay_package.json`：论文主产物
- `bundle_summary.json`：case 级摘要

当前代码已经体现：

- UCA 必须绑定具体 action。
- 原始 LLM UCA 节点也要经过 v2.4.2/v2.4.3 gate。
- blocked action 不能支撑 abductive UCA。
- outcome 只做 compatibility gate。
- not_reported 不作为事实。
- missing fields 转化为 replay/data/logging requirement candidates。

## 9. 论文红线

本文不能声称：

- 还原真实事故因果。
- 推断真实驾驶员心理状态。
- 证明 HMI 真实导致或避免事故。
- 进行法律责任归因。
- 将 pathway_score 解释为真实因果概率。

本文可以声称：

- 生成证据约束的驾驶员过程模型桌面推演包。
- 显式区分 supported、weakly_supported、blocked 路径。
- 减少 LLM 从事故结果直接推出 takeover failure 的过度推断。
- 将证据缺口转化为后续事故复盘和 HMI/日志设计需求。
- 用反馈注入实验分析过程模型更新与 UCA 链路的敏感性。

## 10. 当前叙事评分

按照论文写作 skill 的六段式逻辑链：

- 背景和 running example：8.5/10。需要在正文中选一个 CA DMV case 作为贯穿例子。
- limitation 清晰度：9/10。现有文献缺少从稀疏事故文本到驾驶员过程模型桌面推演的证据约束链路。
- problem essence：9/10。核心约束明确：稀疏文本、不能推断真实心理、必须保留 STPA-HF 结构。
- challenge-module 对齐：9/10。三个挑战可分别对应 evidence boundary、PM/update/action/UCA chain、LLM judge/audit。
- contributions：9/10。三贡献聚焦，不冗余。
- 代码匹配度：8.8/10。新增 tabletop replay package 后已基本匹配；下一步应补 replay completeness audit 和统一旧 baseline 命名。

## 11. 2018 年之后相关研究趋势与本文位置

### 11.1 驾驶员心智模型与情境意识研究

近年自动驾驶人因研究的主线是：自动化等级提高后，驾驶员可能脱离控制环；当系统发出接管请求或场景超出能力边界时，驾驶员需要恢复情境意识并形成正确的系统/环境/他车过程模型。2024 年 Human Factors 的系统综述指出，接管中的驾驶员情境意识受驾驶员状态、接管事件、HVI 设计和测量方法影响；2024 年 AAP 研究进一步说明，加入情境意识变量能提升接管时间预测。2024 年 TRF 关于 takeover request 的系统综述也强调，不存在适用于所有场景的单一接管时间预算，多模态接管提示和额外信息提示对真实场景接管设计很重要。

本文与这些研究的关系是：这些研究多依赖模拟器、眼动、生理信号、问卷或可控实验数据；本文处理的是事故/接管报告文本。我们不预测真实驾驶员心理状态，而是把心智模型研究中的核心变量转化为事故复盘中的 process-model replay 节点：哪些 CPS/CPB/OPS/OPB 信息被报告支持，哪些反馈或输入可形成/更新这些模型，哪些缺失阻断强结论。

### 11.2 自动驾驶事故/接管文本分析研究

2019 年之后，CA DMV collision/disengagement 和 NHTSA SGO 等公开数据被大量用于 AV 事故描述统计、主题建模、场景类型提取、崩溃序列分析和 crash rate 对比。Scientific Data 2021 整理了 California public-road AV crash/disengagement 数据，AAP 2021 等研究分析了 vulnerable road users、rear-end crash 等风险模式，2020-2025 年也出现了基于 DMV 文本的 crash themes、pre-crash scenario mapping 和 reporting blind spots 研究。

本文与这些研究的关系是：既有研究主要回答“事故文本中出现了哪些场景、模式、车辆/道路/对象因素”；本文进一步回答“这些场景事实如何进入驾驶员过程模型、过程模型更新、候选控制动作和 UCA 链路”。因此本文不是替代事故描述统计，而是为事故文本分析增加一个驾驶员中心的 STPA-HF 推演层。

### 11.3 STPA/STAMP 与过程模型研究

STAMP/STPA 的核心思想是把安全视为控制问题，而不是单纯组件故障问题。近年 STPA 在复杂系统、自动化船舶、智能交通、网络物理系统中持续扩展。相关研究强调 controller 需要维护 process model，process model 由反馈更新，许多事故可追溯到过程模型错误、反馈不足或控制动作不适当。STPA-Cog 等工作进一步尝试把人类认知模型纳入系统理论安全分析。

本文与这些研究的关系是：我们不把 STPA-HF 直接套成静态 checklist，而是将其改造为事故文本下的桌面推演框架。四象限过程模型不是普通输入特征，而是从证据到控制动作和 UCA 的中间推演结构；结果只做 compatibility constraint，不反向激活 UCA。

### 11.4 事故桌面推演与数据需求趋势

交通事件管理和自动化系统事故响应中，tabletop exercise 常用于演练异常事件处置、数据保存、角色响应和复盘流程。CAV/ATMA 等项目也强调事故后数字证据保存、模拟事故事件中的数据恢复和复盘需求。这个趋势说明，事故分析不应只给出事后标签，还应输出可执行的复盘脚本、数据清单和改进项。

本文把这一趋势内化为 `tabletop_replay_package`：每个 case 不只输出 UCA 分类，还输出 replay questions、process-model nodes、ranked pathways、blocked claims 和 missing requirement candidates。它适合支持安全分析员进行桌面推演，而不是直接替代法律调查或责任认定。

## 12. 可引用文献方向

建议正文 Related Work 至少分为四组：

1. **Driver mental model / situation awareness / takeover**：用于证明驾驶员心智模型、情境意识、接管时间预算和 HMI 提示是人机共驾安全的核心变量。
2. **AV crash and disengagement text analysis**：用于说明公开事故/接管报告已被用于事故模式分析，但缺少驾驶员过程模型推演层。
3. **STPA/STAMP and process model safety analysis**：用于说明本文为何采用控制结构、反馈、过程模型和 UCA，而不是普通文本分类。
4. **Tabletop exercise / incident replay / data requirement**：用于说明输出 replay package、replay questions 和 data/logging requirements 的应用价值。

## 13. 修改后的代码叙事审视

当前代码已做以下收束：

- schema 改为 `driver_pm_tabletop_replay_v2.4.3`。
- shared prompt 改为 `STPA-HF-guided driver process-model tabletop replay pipeline`。
- `bundle_type` 改为 `driver_process_model_tabletop_replay_bundle`。
- 主产物标注为 `tabletop_replay_package`。
- 每个 case 新增 `e*_tabletop_replay_package.json`。
- requirement 文本去掉 remote assistance / remote operation 主线，聚焦 driver takeover、safety-operator intervention、manual-control trace。
- claim boundary 明确禁止 unique accident-cause reconstruction、true driver psychology inference、legal responsibility attribution、outcome-as-UCA evidence。

仍需下一轮改进：

- 新增 `tabletop-replay-audit` 命令，统计 replay package completeness。
- 把旧 `commitment_boundary` 文件在论文表述中统一解释为 `driver_replay_posture`。
- 将 baseline 输出从 dominant UCA 转为 replay overreach audit，更贴合新叙事。
- 为 HMI 注入实验生成 paired `tabletop_replay_package`，比较 replay package 中 update/action/UCA/pathway/requirement 的变化。
