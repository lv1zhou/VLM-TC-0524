# AAP 论文叙事与方法骨架 V2

日期：2026-05-11

## 1. 论文定位

本文面向 **Accident Analysis & Prevention (AAP)**，不是事故还原论文，也不是 HMI 因果验证论文。  
它是一篇 **技术型 expert-system 论文**，核心任务是在公开自动驾驶事故文本稀疏、HMI/driver-state/internal ADS 经常缺失的前提下，生成**可审计的 STPA-HF safety-case bundle**，并明确哪些更强的安全主张被证据边界阻断。

一句话定位：

> 本文提出一种缺失感知的 STPA-HF 约束 LLM 专家系统，将稀疏自动驾驶事故/接管文本转化为可审计、可排序、可反事实敏感分析的解释路径，并输出分析导出的 evidence/logging requirement candidates。

## 2. 必须坚持的论文立场

### 可以主张

- 系统能从稀疏事故文本生成 evidence-admissible 的安全分析路径。
- 系统能显式保留 HMI、driver-state、internal ADS 缺失，而不把缺失内容补成事实。
- 系统能减少 direct LLM 常见的 crash-to-takeover-failure 过度推断。
- 系统能输出 evidence gap 与 analysis-derived requirement candidates。
- 系统能对 HMI 注入做 sensitivity analysis。

### 不能主张

- 不能说我们重建了真实事故因果。
- 不能说我们证明了真实 HMI 导致或预防了事故。
- 不能说我们推断了真实驾驶员心理状态。
- 不能说 requirement candidates 是最终 HMI 设计方案。

## 3. 方法主线

方法主线不是 “四象限 -> UCA” 的硬编码链条，也不是 “碰撞 -> takeover failure” 的结果映射。  
方法主线应写成：

```text
事故文本证据
-> narrative propositions
-> PM context (CPS / CPB / OPS / OPB)
-> process-model update analysis
-> other factors analysis
-> control-action selection
-> UCA-in-context classification
-> ranked explanatory pathways
-> evidence audit / feedback gaps / requirement candidates
```

这里 STPA-HF 的作用是 **证据门控 + 过程模型约束 + 控制动作/上下文约束 + UCA 合法性约束**。  
它不是装饰性术语，也不是把事故文本拉直成单链条。  
系统是 **fail-closed** 的：如果证据不能支持一致的边界/动作/UCA 组合，程序不会自动修回一个“看起来合理”的答案。

## 4. 论文的核心问题

本文真正回答的是：

> 当公开事故报告只给出 ENV / ACTOR / CAR 等稀疏事实，而 HMI / driver-state / internal ADS transition 经常缺失时，如何在 STPA-HF 框架下，让 LLM 生成可审计、可排序、可反事实敏感分析的事故解释路径，而不把 collision 直接等同于 takeover failure？

这个问题比 “生成多少 case” 更像 AAP。

## 5. STPA-HF 在本文中的角色

STPA-HF 在本文里不是完整事故建模器，而是一个 **证据约束的解释框架**。  
它提供四层收束：

1. **PM context**：把文本中的事实组织成 CPS / CPB / OPS / OPB。
2. **Update process**：解释哪些反馈输入可能触发了过程模型更新，以及更新为什么被阻断、模糊或误读。
3. **Other factors**：把时间压力、驾驶员角色、手动接管可用性、交通压力等纳入动作选择条件。
4. **UCA-in-context**：只有在 action + context 被证据支持时，才允许 UCA 激活；否则允许 `no_activated_uca`。

因此，本文的 STPA-HF 贡献不是“更会猜”，而是“更会停”。

## 6. HMI 在本文中的位置

HMI 不是主结论，而是 **feedback-boundary sensitivity axis**。

它有三个作用：

1. 作为 base-case 中的证据槽位。
2. 作为 counterfactual injection 的敏感变量。
3. 作为 future reporting/logging 的 requirement target。

所以本文不说 “HMI 证明了什么”，而说：

> 如果 HMI feedback cues 改变，STPA-HF 的 boundary / update / action / UCA 路径会如何变化？

## 7. 论文输出是什么

每个 case 的输出不是单一标签，而是一个 bundle：

- evidence packet
- PM context
- update process
- other factors
- commitment boundary
- action selection
- UCA context
- reasoning graph
- ranked pathways
- evidence audit
- feedback gap report
- evidence/logging requirement candidates

这意味着本文的产出是：

> 一个可审计的 STPA-HF safety-case bundle，而不是事故真因判决书。

## 8. 三个研究问题

### RQ1
系统能否从稀疏 public report 中生成 schema-valid、evidence-grounded、catalog-consistent 的 STPA-HF safety-case bundle？

### RQ2
相比 direct LLM 和 generic CoT，STPA-HF 分阶段推理是否能减少 unsupported crash-to-takeover-failure escalation？

### RQ3
在不同 evidence regime 与 HMI counterfactual injection 下，boundary / vulnerability / UCA / pathway score 是否呈现 STPA-HF 一致的方向变化？

## 9. 最终贡献

### Contribution 1
提出一种 missingness-aware 的事故文本证据表示，严格区分 reported / derived / not_reported / counterfactual。

### Contribution 2
提出一个 STPA-HF 约束的 LLM reasoning graph，使 process-model、update process、other factors、action selection、UCA classification 形成可审计链条，并禁止语义修复式回填。

### Contribution 3
将 evidence gap 转化为 analysis-derived evidence/logging requirement candidates，而不是把缺失当成事实。

### Contribution 4
通过 HMI 注入实验验证解释路径的敏感性，但不声称真实因果，也不把 counterfactual 结果回填为 base-case 证据。

## 10. 当前代码和结果支撑什么

目前 30-case mixed run 已经说明：

- `schema_valid = 30/30`
- `invalid evidence ID = 0`
- `catalog consistency = 1.0`
- `unsupported strong boundary warning = 0`
- collision 与 disengagement 两种证据 regime 下，`uca_activation_status` 会自然分化
- feedback gaps 和 requirement candidates 可稳定产出

这足以支撑一篇 AAP 风格的技术论文，但还需要：

- human-gold 标注
- 更正式的 baseline table
- 统一的 paper-facing result freeze

## 11. 代码完成度提升到 9+ 的关键点

要把完成度推到 9+，下一步不是再加复杂模块，而是把以下三件事钉死：

1. **证据口径冻结**  
   所有 paper 表格只从 `results/paper_v1` 或冻结目录读取。

2. **更新 vulnerability 可证化**  
   `missed_feedback / ambiguous_feedback / misinterpreted_feedback` 不能空口出现，必须对应证据或缺失证据。
   同时禁止把某个默认 vulnerability 直接填入空白槽位。

3. **human-gold 标注接入**  
   至少 2 名标注者，输出 boundary / dominant UCA / update vulnerability / active UCA set / support evidence IDs。
   标注规则必须允许 `no_activated_uca`，而不是强制每个 case 都有 dominant UCA。

## 12. AAP 版一句话摘要

> We propose an evidence-admissible STPA-HF-guided reasoning graph that characterizes driver involvement and control-action pathways in sparse automated-driving incident texts, suppresses outcome-to-mechanism overreach, and uses HMI only as a sensitivity axis for explanation pathways.

## 13. 当前下一步

建议下一步按这个顺序做：

1. 冻结 paper-facing 结果目录。
2. 跑 human annotation packet。
3. 跑 full baseline suite。
4. 跑 HMI counterfactual suite。
5. 写 Introduction / Method / Results 三段主文。
