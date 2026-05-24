# AAP STPA-HF 多路径论文叙事 V3

日期：2026-05-12

## 1. 一句话定位

本文提出一种 **STPA-HF 约束的证据可采纳多路径推理图**，用于从稀疏自动驾驶事故/接管文本中，以驾驶员为控制器，生成并排序多条安全分析解释路径。系统不还原真实事故因果，不推断真实驾驶员心理，而是判断哪些 driver-process-model / update-process / control-action / UCA-in-context 路径被文本证据支持、弱支持或阻断。

## 2. 方法论红线

本文不能主张：

- 还原真实事故原因。
- 证明真实 HMI 导致或避免事故。
- 推断真实驾驶员心理状态。
- 把 `not_reported` 当成事实。
- 从 crash/collision outcome 直接推出 takeover failure。

本文可以主张：

- 将事故文本证据映射为 STPA-HF 的 process-model variable space。
- 明确区分 reported / derived / not_reported / counterfactual evidence。
- 对候选 UCA 路径进行 STPA-HF gate-by-gate 合规检查。
- 输出 admissible / weakly_supported / blocked 的多路径解释。
- 说明哪些 HMI、driver-state、internal ADS 证据缺失阻断更强 claim。
- 用 HMI 注入做 feedback-update-action-UCA 路径敏感性分析。

## 3. STPA-HF 原方法对应关系

本文不把四象限当成普通输入特征。四象限是驾驶员过程模型变量空间：

| STPA-HF process-model variable | 本文含义 | 自动驾驶事故文本中的例子 |
|---|---|---|
| Controlled Process States (CPS) | 驾驶员关于被控过程当前状态的模型 | ADS 是否开启、控制权是否在 ADS、是否已经 disengage、是否有接管权限 |
| Controlled Process Behaviors (CPB) | 驾驶员关于被控过程后续行为/能力的模型 | ADS 是否会制动、避障、保持车道、继续支持、退出自动驾驶 |
| Other Process States (OPS) | 驾驶员关于环境/外部过程当前状态的模型 | 道路、车道、天气、工作区、交叉口、交通队列 |
| Other Process Behaviors (OPB) | 驾驶员关于其他交通参与者未来行为的模型 | 后车是否会停、旁车是否切入、行人/骑行者是否进入冲突路径 |

STPA-HF 的递进不是：

```text
四象限 -> vulnerability -> UCA
```

而是：

```text
candidate UCA / unsafe decision context
-> required process-model variables
-> process-model flaw hypothesis
-> process-model update analysis
-> other factors affecting action selection
-> control-action selection hypothesis
-> UCA-in-context admissibility
-> outcome compatibility
-> ranked explanatory pathway
```

## 4. Update process 的严格定义

Update process 不是“是否有 HMI 提示”。

在本文中，update process 分析的是：

- 驾驶员如何形成初始 process model。
- 哪些反馈或输入可能更新该 process model。
- 这些反馈是否可用、可观察、显著、及时、可解释、一致。
- 证据是否足以支持 observed update flaw。
- 如果证据不足，哪些 evidence gap 阻断该 claim。

每个 update node 必须区分两层：

```json
{
  "observed_update_vulnerability": {
    "label": "none | missed_feedback | ambiguous_feedback | misinterpreted_feedback",
    "supporting_evidence_ids": []
  },
  "evidence_gap_update_risk": {
    "labels": [
      "missing_hmi_feedback",
      "missing_time_budget",
      "missing_driver_state",
      "missing_internal_ads_state"
    ],
    "gap_evidence_ids": []
  },
  "update_evidence_status": "observed_update_claim | evidence_gap_only | not_admissible"
}
```

规则：

- `not_reported` 只能支持 `evidence_gap_update_risk`。
- `not_reported` 不能支持真实的 `observed_update_vulnerability`。
- 若没有 reported/derived/counterfactual 直接证据，observed label 必须为 `none`。
- HMI 缺失代表 update evidence gap，不代表驾驶员 missed HMI。

## 5. 多路径输出

每个 case 不应只输出一个 UCA 或一个象限。每个 case 应输出多条 candidate pathways：

```json
{
  "pathway_id": "P1",
  "pathway_status": "admissible | weakly_supported | blocked",
  "pathway_score": 0.0,
  "pm_variable_requirements": [],
  "update_process_contribution": {},
  "control_action_selection": {},
  "uca_reasoning_block": {},
  "stpa_hf_compliance_gates": {},
  "blocking_reasons": []
}
```

`pathway_score` 的含义是 evidence-conditioned explanatory plausibility，不是真实因果概率。

## 6. STPA-HF 合规门控

每条 pathway 必须通过七个 gate：

| Gate | 问题 | 不通过时的处理 |
|---|---|---|
| G1 UCA context gate | 是否有 driver control action + unsafe context | 不能成为 admissible UCA |
| G2 PM variable gate | 是否覆盖必要 CPS/CPB/OPS/OPB 变量 | 最多 weakly_supported |
| G3 PM flaw gate | 是否有 process-model flaw 或 evidence gap | 无则不能声称 update flaw |
| G4 update process gate | 是否能解释 formation/update 过程 | 缺失则 blocked 或 weak |
| G5 action selection gate | 是否有具体控制动作选择 | 缺失则 blocked |
| G6 evidence admissibility gate | 是否避免把 not_reported 当事实 | 失败则 blocked |
| G7 outcome compatibility gate | 候选 UCA/action pathway 是否与报告的 collision/disengagement/intervention outcome 相容，且没有把 outcome 当成 UCA 激活证据 | 只能降低、阻断或排序路径，不能激活 UCA，不能把 blocked 升级为 admissible |

G7 是本文新叙事的关键：事故结果是 terminal safety constraint violation / compatibility constraint，而不是驾驶员 UCA 的直接证据。因此：

- collision/crash/contact 不能单独激活 takeover failure。
- disengagement/intervention 不能单独激活 unsafe driver action。
- reported intervention 需要进一步区分为转移事实、驾驶员动作证据、动作质量证据。
- 若缺少驾驶员动作、动作质量或驾驶员状态证据，UCA pathway 最多 weakly_supported 或 blocked。

## 7. HMI 在本文中的作用

HMI 不是主结论，也不是唯一 update source。HMI 是 process-model update source / feedback channel / sensitivity variable。

HMI injection 实验要重新跑完整链路：

```text
HMI injection
-> PM variables
-> update process
-> other factors
-> action selection
-> UCA candidates
-> pathway ranking
```

要观察：

- blocked pathway 是否变成 weakly_supported 或 admissible。
- update_evidence_status 是否从 evidence_gap_only 变成 observed_update_claim。
- unsafe pathway score 是否下降或上升。
- boundary 是否按 STPA-HF 方向变化。

## 8. RQ

RQ1：系统能否从稀疏 AV accident/takeover 文本中生成 schema-valid、evidence-grounded、STPA-HF-compliant 的多路径 safety-analysis bundle？

RQ2：相比 direct LLM 和 generic CoT，STPA-HF 多路径门控是否减少 outcome-to-mechanism overreach，尤其是 crash-to-takeover-failure 和 unsupported UCA activation？

RQ3：在相同事故文本下，HMI feedback injection 是否会沿着 update-process / action-selection / UCA-in-context / pathway-score 链路产生符合 STPA-HF 的敏感性变化？

## 9. 论文贡献

Contribution 1：提出面向稀疏事故文本的 STPA-HF 证据表示，严格区分 reported / derived / not_reported / counterfactual。

Contribution 2：提出 UCA-candidate-first 的 STPA-HF 多路径推理图，将 PM variables、update process、other factors、control action、UCA-in-context 连接为可审计链条。

Contribution 3：提出路径合规门控与 LLM judge 排序，输出 admissible / weakly_supported / blocked，而不是单一事故真因。

Contribution 4：将 evidence gaps 转化为 future evidence/logging requirement candidates，并通过 HMI injection 分析反馈路径敏感性。

## 10. 当前代码修改目标

下一轮实验前必须满足：

- 每个 case 生成多条 pathway。
- 每条 pathway 包含 STPA-HF gates。
- `not_reported` 不再支持 observed vulnerability。
- `no_activated_uca` 仍保留，但必须伴随 blocked/weak UCA candidates。
- manifest 统计 mean candidate pathways per case 和 pathway status distribution。
- evidence audit 输出 not_reported-as-fact warning。
