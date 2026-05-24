# AAP V245 Code Execution and Structure SK

Date: 2026-05-24

## 1. 文档目的

本文档用于说明当前 `STPAHF/stpa_hf_dan_eswa_engine_final.py` 的论文面向执行流程、核心代码结构、结果产物和审计含义。  
目标不是做事故真因还原，而是把稀疏事故文本转成 **driver-process-model tabletop replay package**，供后续论文写作、复现实验和人工复核直接使用。

核心边界：
- 不推断真实驾驶员心理。
- 不把 crash / disengagement 直接等同于 takeover failure。
- 不用 `not_reported` 充当正向证据。
- 不用 Python 规则硬编码代替 LLM 语义判断。

## 2. 当前方法主线

当前主线是：

1. 从事故文本读取 ENV / ACTOR / CAR / HMI / CABIN / driver profile 等字段。
2. 用 STPA-HF 驱动的过程模型，形成 CPS / CPB / OPS / OPB 的候选更新。
3. 生成候选行动、UCA 路径、blocked claims、replay questions。
4. 打包成 `tabletop_replay_package`。
5. 再做 evidence audit、feedback gap report、requirement candidates、semantic warning audit。

最终输出定位为：
- post-incident safety review artifact
- driver replay posture
- evidence-bounded safety review bundle
- analysis-derived evidence/logging requirement candidates

## 3. 代码结构解析

主文件：
- [`stpa_hf_dan_eswa_engine_final.py`](C:/Users/32401/PycharmProjects/PythonProject/STPAHF/stpa_hf_dan_eswa_engine_final.py)

### 3.1 输入与摄入层

职责：
- 读取 functional cases。
- 保留 source provenance。
- 不把缺失字段补成真值。
- 支持外部事故 CSV / JSONL 的标准化摄入。

相关内容通常包括：
- 外部 case 读取
- missingness policy
- source metadata
- role disambiguation 前的结构字段

### 3.2 角色消歧层

新增的核心模块：
- `ROLE_DISAMBIGUATION_PROMPT`
- `role_disambiguate_case`
- `role_disambiguate_cases_file`
- CLI: `role-disambiguate-cases`

作用：
- 修正 ego_vehicle / conflict_actor / scene_level 的叙事归属。
- 阻止把“本车 stopped / yielding”错写成对方 actor intent。
- 输出 `paper_10_mixed_ca_5collision_5disengagement_role_adjudicated.jsonl`

这一步是当前版本最重要的结构修补之一。

### 3.3 主 replay 层

核心函数：
- `run_case(...)`
- `run_full_system_batch(...)`
- `cmd_run(...)`

职责：
- 根据 case 构建 replay bundle。
- 生成 action / UCA / pathway / blocked claim / replay question。
- 输出 `tabletop_replay_package`。

主输出目录示例：
- `results/aap_v245_10case_role_adjudicated_full_final/`

### 3.4 Replay 审计层

核心函数：
- `audit_tabletop_replay_packages`
- CLI: `tabletop-replay-audit`

审计指标：
- replay package generation rate
- quadrant coverage rate
- update process present rate
- candidate action count
- UCA pathway count
- ranked pathway count
- replay question count
- missing requirement count
- blocked claim count
- review ready case rate

### 3.5 Evidence 审计层

核心函数：
- `run_evidence_support_audit`
- CLI: `evidence-audit`

作用：
- 检查 evidence ID 是否有效。
- 检查 catalog consistency。
- 检查是否发生 outcome-only UCA、心理过推断、HMI 缺失当作证据等问题。
- 给出 generic UCA expansion warning。

### 3.6 Feedback gap 层

核心函数：
- `run_feedback_gap_report`
- CLI: `feedback-gap-report`

作用：
- 找出每个 case 的 HMI / driver-state / internal ADS 缺口。
- 这些缺口是分析边界，不是真值缺失。

### 3.7 Requirement candidates 层

核心函数：
- `requirement_candidates`

作用：
- 将缺口转成 analysis-derived evidence/logging requirement candidates。
- 这些不是最终 HMI 设计要求，而是“为了更强的 post-incident review，应该记录什么”的候选项。

### 3.8 语义 warning 审计层

新增的核心模块：
- `SEMANTIC_WARNING_AUDIT_PROMPT`
- `run_semantic_warning_audit`
- CLI: `semantic-warning-audit`

作用：
- 不靠硬编码删除 warning。
- 先结构筛查，再由 LLM 语义判别：
  - `true_generic_expansion`
  - `properly_gated_blocked_hypothesis`
  - `under_supported_abductive_candidate`
  - `overreaching_positive_claim`
  - `needs_human_review`

## 4. 推荐执行顺序

标准执行顺序如下：

```powershell
cd C:\Users\32401\PycharmProjects\PythonProject\STPAHF

$env:OPENAI_API_KEY='...'
$env:OPENAI_BASE_URL='https://dashscope.aliyuncs.com/compatible-mode/v1'
$env:OPENAI_MODEL='qwen-max-latest'
$env:OPENAI_TIMEOUT_S='240'

python .\stpa_hf_dan_eswa_engine_final.py role-disambiguate-cases --cases .\data\cases\paper_10_mixed_ca_5collision_5disengagement.jsonl --out-cases .\data\cases\paper_10_mixed_ca_5collision_5disengagement_role_adjudicated.jsonl --out-report .\results\aap_v245_10case_role_disambiguation\role_disambiguation_report.json --temperature 0

python .\stpa_hf_dan_eswa_engine_final.py run --cases .\data\cases\paper_10_mixed_ca_5collision_5disengagement_role_adjudicated.jsonl --out .\results\aap_v245_10case_role_adjudicated_full_final --temperature 0 --resume

python .\stpa_hf_dan_eswa_engine_final.py tabletop-replay-audit --bundle-dir .\results\aap_v245_10case_role_adjudicated_full_final --out .\results\aap_v245_10case_replay_audit
python .\stpa_hf_dan_eswa_engine_final.py evidence-audit --bundle-dir .\results\aap_v245_10case_role_adjudicated_full_final --out .\results\aap_v245_10case_evidence_audit
python .\stpa_hf_dan_eswa_engine_final.py feedback-gap-report --bundle-dir .\results\aap_v245_10case_role_adjudicated_full_final --out .\results\aap_v245_10case_feedback_gaps
python .\stpa_hf_dan_eswa_engine_final.py requirement-candidates --gap-report .\results\aap_v245_10case_feedback_gaps\feedback_gap_report.json --out .\results\aap_v245_10case_requirements
python .\stpa_hf_dan_eswa_engine_final.py semantic-warning-audit --bundle-dir .\results\aap_v245_10case_role_adjudicated_full_final --evidence-audit .\results\aap_v245_10case_evidence_audit\evidence_support_audit.json --out .\results\aap_v245_10case_semantic_warning_audit --temperature 0
```

## 5. 当前 10-case 运行结果

输入：
- 5 collision
- 5 disengagement

当前结果：
- 10/10 schema valid
- replay package generation rate = 1.0
- quadrant coverage = 1.0
- update process present = 1.0
- review ready case rate = 1.0
- invalid evidence ID = 0
- catalog consistency rate = 1.0
- generic UCA expansion warning = 2
- feedback gaps = 110
- requirement candidates = 110

语义 warning 审计结果：
- 2 个结构性 warning candidate
- 2 个都被 LLM 判为 `properly_gated_blocked_hypothesis`

这表示当前系统已能把“可疑链条”保留下来，但不把它们误写成正向事故真因。

## 6. 结果产物说明

关键结果文件：
- `results/aap_v245_10case_role_disambiguation/role_disambiguation_report.json`
- `results/aap_v245_10case_role_adjudicated_full_final/`
- `results/aap_v245_10case_replay_audit/tabletop_replay_audit.json`
- `results/aap_v245_10case_evidence_audit/evidence_support_audit.json`
- `results/aap_v245_10case_feedback_gaps/feedback_gap_report.json`
- `results/aap_v245_10case_requirements/requirement_candidates.json`
- `results/aap_v245_10case_semantic_warning_audit/semantic_warning_audit.json`

论文写作时建议把它们分别映射到：
- main result
- evidence audit
- gap analysis
- requirement candidates
- semantic warning audit

## 7. 结构性判断

这套代码当前最适合支撑的论文表述是：

> AAP-style driver-process-model tabletop replay under sparse incident evidence.

不适合支撑的表述是：
- 真实事故还原
- 驾驶员心理真值恢复
- HMI 因果验证
- legal responsibility attribution

## 8. 下一步建议

下一步最值得做的三件事：

1. 扩展 case 数，形成更稳的 main experiment。
2. 把 `requirement candidates` 改写成论文里的 evidence/logging requirement taxonomy。
3. 用更细粒度的对比表说明：
   - direct LLM 如何过度推断
   - full replay 如何收紧 claim boundary
   - semantic warning audit 如何保留 blocked hypothesis 而不误删

