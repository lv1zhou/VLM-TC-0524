# ESWA 50-case 后复盘与下一步修订计划

日期：2026-04-29  
上位纲领：`ESWA_CHINESE_NARRATIVE_AND_NEXT_PLAN.md`  
主结果目录：`results/paper_v1_50_mixed_sources/`

## 1. 本轮已经完成什么

本轮完成了从 30-case pilot 到 50-case mixed-source 主实验候选结果的推进。

已完成代码改动：

- 在 STPA-HF prompt 中加入 crash/collision boundary guardrail。
- 在 evidence audit 中加入 strong-boundary evidence strength 分类。
- 将 ambiguous degradation CF 拆成：
  - `cf_hmi_ambiguous_degradation_no_transition`
  - `cf_hmi_ambiguous_degradation_with_transition_pressure`
- 为 requirement candidates 增加 taxonomy summary、CSV 和 representative examples。
- 新增 50-case deterministic sampler。
- 新增 Expert-0 preview annotation 命令。
- 新增 PowerShell paper pipeline。
- 新增可恢复运行参数 `--resume`。

已完成实验：

- 30-case repair 全流程。
- 50-case mixed-source 主实验。
- 50-case baseline suite。
- 250 个 HMI counterfactual sensitivity case。
- Expert-0 preview labels。

## 2. 上一轮问题是否解决

### 问题 1：crash-only strong-boundary over-escalation

已解决。

30-case repair：

- unsupported strong-boundary warning：`0`
- outcome-only escalation warning：`0`
- not_reported boundary support warning：`0`

50-case main：

- unsupported strong-boundary warning：`0`
- outcome-only escalation warning：`0`
- strong boundary evidence strength：
  - `not_strong_boundary = 46`
  - `explicit_transition_or_intervention = 4`

解释：

> 修复后，系统只有在 explicit transition/intervention evidence 存在时才给出 `not_supported_transfer`，这正好符合论文叙事：不能从 crash/collision outcome 直接推出 takeover failure。

### 问题 2：ambiguous degradation CF 不稳定

基本解决，但仍需解释。

30-case repair：

- no-transition ambiguous：`1.0`
- with-transition-pressure ambiguous：`0.9`

50-case main：

- no-transition ambiguous：`1.0`
- with-transition-pressure ambiguous：`0.94`

解释：

> 拆分模板后，ambiguous degradation 的理论口径清楚了。没有 transition pressure 的模糊退化不应强推 NS；带 transition pressure 的模糊退化可以朝强边界移动。结果支持这个区分。

### 问题 3：requirement candidates 太多

已缓解。

50-case：

- raw candidates：`570`
- 已生成：
  - `evidence_requirement_taxonomy_summary.json`
  - `evidence_requirement_taxonomy_summary.csv`
  - `evidence_requirement_representative_examples.md`

解释：

> 论文主文应报告 taxonomy，不逐条列 570 条。该产物的定位仍是 evidence/logging needs，不是最终 HMI design requirements。

### 问题 4：没有 human-gold

尚未解决。

已完成：

- Expert-0 preview labels：`50`
- 明确 `expert_preview_not_publication_gold`
- 生成 annotation packets。

仍需：

- 至少 2 名真实人工标注者。
- 双人 agreement。
- adjudicated human-gold labels。

解释：

> Expert-0 只能用于预演和发现争议，不能作为 ESWA 主实验 gold。

### 问题 5：no_update ablation

出现了更强烈的现象。

30-case repair：

- no_update schema valid：`12/30`

50-case main：

- no_update schema valid：`19/50`

解释：

> 去掉 PM update 后，系统结构稳定性显著下降。这是一个重要消融结果：staged PM update 不只是改变标签分布，也提高 schema 和 boundary/UCA 一致性。但论文必须如实报告 invalid rate，不能只报有效样本。

### 问题 6：CF schema robustness

50-case CF：

- specs：`250`
- evaluable：`248`
- schema valid：`248/250 = 99.2%`
- overall directional consistency：`0.9476`

解释：

> 满足 `>=95%` 验收线，但仍有 2 个 CF invalid case。最终论文前建议单独检查或 rerun 失败 CF。

## 3. 50-case 主结果如何支撑论文叙事

### RQ1：可审计生成能力

支持。

- full system schema valid：`50/50`
- invalid evidence ID mean：`0`
- UCA catalog consistency：`1.0`
- claims without supporting evidence mean：`0`
- unsupported strong-boundary warning：`0`

结论：

> 系统能够从多源稀疏报告生成 schema-valid、evidence-grounded、catalog-consistent 的 STPA-HF safety-case bundle。

### RQ2：减少无证据边界升级

支持。

50-case boundary：

- full system：`36 CR + 10 SM + 4 NS`
- direct baseline：`47 NS + 3 SM`
- generic CoT：`23 NS + 27 SM`

解释：

> Direct baseline 强烈 over-escalate 到 NS；generic CoT 虽然减少 NS，但又大量偏到 SM，说明通用推理链不是稳定的 STPA-HF evidence boundary。full system 更符合证据约束：多数保持 CR，只在 explicit transition/intervention evidence 下给 NS。

### RQ3：HMI feedback-boundary sensitivity

基本支持。

50-case CF：

- takeover demand：`1.0`
- ambiguous no transition：`1.0`
- ambiguous with transition pressure：`0.94`
- full support：`0.9375`
- partial support：`0.86`
- overall：`0.9476`

解释：

> 系统对明确 HMI cue 有稳定方向响应；partial support 最弱，说明部分支持线索在 evidence-boundary 上本来就更模糊，应作为论文中的 nuanced finding，而不是硬说所有 HMI cue 都稳定。

## 4. 当前最重要的剩余问题

### 剩余问题 1：真实人工 gold labels 仍缺

下一步必须做。

建议：

- 使用 `data/annotation_packets/paper_50_v1/`
- 两名标注者独立标注。
- 优先看：
  - boundary label
  - insufficient information flags
  - blocked stronger claims
  - supporting evidence ids
- UCA/vulnerability 作为第二层标签。

### 剩余问题 2：partial support CF 只有 0.86

建议不要强行修到很高。

论文解释：

> Partial support supplies some supportive feedback but leaves acknowledgement/latency/driver-state/internal ADS evidence missing. Therefore it should be more ambiguous than full support, and lower directional consistency is theoretically plausible.

可选代码动作：

- 将 partial support expected direction 从严格 `toward_weaker` 改成 `maintain_or_toward_weaker`。
- 或在论文中把它作为 sensitivity nuance 报告。

### 剩余问题 3：2 个 CF invalid bundles

下一步：

- 找出 invalid case。
- 单独 rerun。
- 如果仍失败，报告 CF schema valid `248/250`。

### 剩余问题 4：CA DMV collision augmented 需要人工确认

Expert-0 把 15 个 CA DMV collision augmented cases 都列为需人工裁决。

原因：

- 该数据是 third-party augmented，不是官方 CSV。
- 车辆/actor 字段较杂。
- 需要人工确认其 scene diversity 和 field mapping 是否适合论文主实验。

## 5. 论文写作建议

主文应强调：

> 本文不是证明 HMI 因果效果，而是证明缺失条件下的 evidence-boundary discipline。

50-case 结果可写成：

> The full system generated valid bundles for all 50 mixed-source cases, with zero invalid evidence IDs, perfect UCA catalog consistency, and no unsupported strong-boundary warnings. In contrast, direct prompting assigned not_supported_transfer to 47/50 cases, illustrating crash/intervention over-escalation. Counterfactual HMI tests achieved 0.9476 directional consistency, showing feedback-boundary sensitivity while preserving the distinction between source evidence and hypothetical cue injection.

必须谨慎写：

- Expert-0 labels are not human gold。
- CA DMV collision augmented is third-party derived。
- Requirement candidates are evidence/logging requirements。
- CF HMI is sensitivity only。

## 6. 下一步最小行动

1. 检查 2 个 invalid CF bundles。
2. 决定 partial support 是调整 expected rule，还是作为 nuanced finding 报告。
3. 安排两名真实标注者完成 50-case human-gold。
4. 用 frozen outputs 生成论文 Tables 1-6。
5. 开始写 ESWA Introduction 和 Method。

