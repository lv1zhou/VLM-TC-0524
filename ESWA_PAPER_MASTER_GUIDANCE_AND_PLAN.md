# ESWA paper master guidance and experiment plan

## 0. Purpose of this document

This document replaces the earlier loose narrative notes as the working master guide for the paper. It absorbs the useful parts of `Supervisor-Skills` and aligns them with the actual codebase and data now available:

- NHTSA SGO official crash CSV.
- CA DMV collision augmented CSV derived from DMV collision PDFs.
- CA DMV official disengagement CSVs extracted from the annual disengagement-report archive.

The goal is to decide what this paper is really about, what claims it can make, what claims it must avoid, and what experiments should be run next.

This document is a paper-guidance artifact, not a runnable Codex skill. It is based on the `Supervisor-Skills` writing logic from the HKUSTDial GitHub repository, especially the instruction to make the paper type explicit, keep the motivation tight, map every contribution to an experiment/artifact, and avoid unsupported claims.

## 1. Current diagnosis

The previous narrative had a real risk of being misunderstood in three ways:

1. It could sound like accident reconstruction.
2. It could sound like the model is inferring true driver cognition or real HMI causal effects.
3. It could make `feedback gaps` and `requirement candidates` look like a weak side product instead of the paper's safety-analysis value.

There was also a fourth risk:

4. It did not clearly explain what STPA-HF contributes beyond ordinary LLM prompting.

The new data sources clarify the correct landing point:

> The paper is about evidence-constrained safety-case generation under different public-report evidence regimes.

The important contrast is no longer simply "reports are sparse." It is:

- Crash/collision reports provide event and scene facts but often omit transition/intervention evidence.
- Disengagement reports provide intervention and disengagement-cause evidence but still omit HMI display, time budget, driver cognitive state, and internal ADS confidence.
- A useful expert system should expose exactly what safety claims are supported, what stronger claims are blocked, and what additional evidence would be needed.

The simplest corrected story is:

> Public reports provide real high-risk scenario seeds, but not complete causal ground truth. The system uses STPA-HF to convert these sparse scenarios into auditable safety-analysis cases, rather than reconstructing the true accident or inventing missing HMI/driver evidence.

## 2. Paper type

Following the `Supervisor-Skills` principle, the paper type must be explicit.

This is not a pure dataset paper and not a pure benchmark paper.

It should be framed as:

> A technical expert-system paper with an evaluation-oriented multi-source evidence dataset.

The method is the contribution. The dataset is the stress test and evidence-regime comparison that makes the method necessary.

## 3. Final one-sentence claim

> We propose a missingness-aware STPA-HF LLM expert system that converts sparse automated-driving public reports into auditable safety-case bundles, prevents crash-to-takeover-failure over-escalation, and identifies which HMI, driver-state, intervention, and ADS evidence would be required to support stronger feedback-boundary claims.

This is the sentence every section should serve.

Chinese working version:

> 本研究提出一种缺失感知、STPA-HF 约束的 LLM 专家系统，将稀疏自动驾驶公开报告中的真实高风险场景转化为可审计 safety-case bundle，避免从 crash 直接过度推断 takeover failure，并指出要支持更强 feedback-boundary claim 还需要哪些 HMI、driver-state、intervention 和 ADS 证据。

## 4. What the system outputs

The output is not merely a label.

For each case, the system should output a safety-case bundle containing:

- Evidence packet with reported, derived, not_reported, and counterfactual evidence separated.
- Commitment-boundary state, such as supported_monitoring, contingent_readiness, or not_supported_transfer.
- Update vulnerability, such as missed, ambiguous, or misinterpreted feedback.
- Catalog-constrained UCA set and dominant UCA.
- Mechanism trace with evidence IDs.
- Evidence audit.
- Feedback gap report.
- Analysis-derived evidence/logging requirement candidates.

The output should be described as:

> an auditable STPA-HF safety-case bundle.

In Chinese:

> 一份结构化、证据受限、可审计的 STPA-HF 安全分析报告。

Do not describe it as:

- accident cause reconstruction;
- true driver mental-state inference;
- proof that real HMI caused the event;
- final HMI design requirements.

## 4.1 What STPA-HF contributes

STPA-HF is the reasoning backbone. It is not decorative terminology.

It forces the LLM to reason through:

- the human-automation control/monitoring relationship;
- the commitment boundary, such as supported monitoring, contingent readiness, or unsupported transfer;
- feedback-update vulnerabilities, such as missed, ambiguous, or misinterpreted feedback;
- catalog-constrained unsafe control actions;
- evidence support for each claim.

Without STPA-HF, a direct LLM baseline can easily reason:

> A crash occurred, therefore takeover failed.

With STPA-HF, the system must ask:

> Was there a reported takeover demand? Was HMI feedback reported? Was intervention reported? Was ADS degradation reported? What evidence supports the stronger boundary claim?

If these are missing, the stronger claim is blocked. This is the methodological core.

## 5. What HMI means in this paper

HMI is not treated as a proven real-world cause.

HMI is treated as a feedback-boundary evidence channel.

The question is not:

> Did HMI cause the crash?

The question is:

> Given the reported evidence, is there enough HMI/driver/ADS-transition evidence to support a stronger claim that a takeover demand, supported monitoring state, or unsupported transfer occurred?

Therefore HMI has three roles:

1. Evidence slot in the base safety case.
2. Counterfactual intervention variable for sensitivity testing.
3. Requirement target for future reporting/logging evidence.

This resolves the earlier confusion: HMI is not the final conclusion. HMI is one part of the feedback boundary that determines what can and cannot be claimed.

Important distinction:

- Base-case analysis does not fill in missing HMI as fact.
- Counterfactual analysis can inject hypothetical HMI cues to test sensitivity.

This means:

> We do not reconstruct true HMI. We preserve missing HMI in the base case and use injected HMI only as a controlled sensitivity experiment.

## 5.1 What public reports are used for

Public reports are used as:

> real-world high-risk functional scenario seeds.

They are not used as:

> complete causal ground truth.

This is why the system can use real reported crashes/collisions/disengagements without claiming to reconstruct the true accident cause.

## 6. What feedback gaps mean

Feedback gaps are missing evidence slots that block stronger safety claims.

They are not discovered design defects.

They are not proof of HMI failure.

They answer this question:

> Why can the system not responsibly make a stronger boundary/UCA claim?

For example:

- If `HMI.time_budget_indicator` is missing, the system cannot claim that the driver was given a clear takeover time budget.
- If `CAR.reported_intervention` is missing, the system cannot claim that a takeover did or did not occur.
- If `CAR.perception_confidence` is missing, the system cannot distinguish perception uncertainty from planner uncertainty or HMI feedback failure.

The contribution is not the raw number of gaps. The contribution is turning missingness into an auditable claim boundary.

## 7. What requirement candidates mean

The term `requirement_candidates` is too easy to misunderstand.

Use this phrase in the paper:

> analysis-derived evidence/logging requirement candidates

Definition:

> Evidence/logging requirement candidates are analyst-facing recommendations about what should be recorded, reported, or inspected in order to support stronger future STPA-HF safety claims.

They are not validated HMI design requirements.

They are not prescriptions that a UI must have a specific visual design.

They are not causal conclusions.

Examples:

- Missing `HMI.mode_state_display` -> future reports/logs should preserve whether the driver-visible automation mode/state was displayed.
- Missing `HMI.time_budget_indicator` -> future takeover/degradation reports should record whether a time budget was shown and what the available time was.
- Missing `CAR.reported_intervention` -> incident records should distinguish no intervention, test-driver takeover, remote-operator intervention, in-field retrieval, and AV-system fallback.
- Missing `CAR.perception_confidence` -> ADS logs should preserve evidence sufficient to distinguish perception degradation from planner degradation.

This is one of the paper's application contributions.

## 8. Data sources and evidence regimes

### Source A: NHTSA SGO official CSV

Role:

- Main official crash/collision CSV source.
- Good for high-risk crash/collision settings.
- Often sparse for HMI, driver-state, intervention, and ADS internal state.

Paper use:

- Shows crash-to-takeover-failure over-escalation risk.
- Supports missingness-aware safety-case generation.

### Source B: CA DMV collision augmented CSV

Role:

- Third-party augmented CSV derived from CA DMV collision PDFs.
- Useful for scene diversity: intersections, parked vehicles, pedestrians, bicyclists, two-wheelers.

Source boundary:

- Must be described as third-party derived/augmented, not official DMV CSV.

Paper use:

- Adds external scene diversity.
- Tests whether the method remains conservative beyond NHTSA SGO.

### Source C: CA DMV official disengagement CSV

Role:

- Official DMV disengagement reports extracted from annual report archive.
- Provides intervention and disengagement-cause evidence.

Paper use:

- Creates a second evidence regime.
- Tests whether the system changes claim boundaries when intervention/system-issue evidence is reported.
- Strengthens the feedback-boundary story more than collision data alone.

## 9. Revised research questions

Use three RQs.

### RQ1: Auditable generation under public-report missingness

Can the system generate schema-valid, evidence-grounded, catalog-consistent STPA-HF safety-case bundles from sparse public automated-driving reports?

Main outputs:

- schema valid rate;
- invalid evidence ID rate;
- UCA catalog consistency;
- claim-level evidence coverage;
- source-level missingness profile.

### RQ2: Reduction of unsupported boundary escalation

Compared with direct LLM and generic CoT baselines, does staged STPA-HF reasoning reduce unsupported crash-to-takeover-failure escalation and produce more stable boundary/UCA claims?

Main outputs:

- direct/generic/full boundary distributions;
- unsupported strong-boundary warnings;
- schema robustness;
- human-gold agreement once annotations exist.

### RQ3: Evidence-regime and HMI feedback-boundary sensitivity

How do boundary/UCA/vulnerability outputs change when reported evidence differs across crash, collision, and disengagement sources, and when HMI feedback cues are injected counterfactually?

Main outputs:

- NHTSA vs CA collision vs CA disengagement gap profiles;
- reduction of `reported_intervention` and `reported_system_issue` gaps in disengagement reports;
- counterfactual HMI directional consistency;
- evidence/logging requirement taxonomy.

## 10. Contributions

### Contribution 1: Missingness-aware functional case representation

The paper introduces a representation that separates reported, derived, not_reported, and counterfactual evidence. It forbids HMI, driver-state, and internal ADS imputation from crash outcomes.

Validated by:

- input audit;
- missingness profile;
- evidence provenance counts.

### Contribution 2: STPA-HF constrained LLM expert system

The paper introduces a staged reasoning pipeline that maps evidence into commitment boundary, update vulnerability, and catalog-constrained UCA activation.

Validated by:

- schema-valid bundle rate;
- UCA catalog consistency;
- baseline comparison;
- ablation.

### Contribution 3: Evidence audit and gap-to-requirement transformation

The paper turns missing feedback/intervention/internal ADS evidence into explicit blocked-claim explanations and evidence/logging requirement candidates.

Validated by:

- feedback gap report;
- requirement candidate taxonomy;
- source-regime comparison.

### Contribution 4: HMI feedback-boundary sensitivity test

The paper uses controlled counterfactual HMI cue injection to test whether boundary states shift in STPA-HF-consistent directions.

Validated by:

- counterfactual directional consistency by template.

## 11. What the current results already support

### 20-case NHTSA pilot

Supports:

- full system schema-valid generation: 20/20;
- direct LLM over-escalation: 20/20 direct baseline to not_supported_transfer;
- evidence audit cleanliness: invalid evidence IDs = 0, catalog consistency = 1.0;
- HMI counterfactual sensitivity: 80 pairs, directional consistency = 0.9875.

Limitations:

- single source regime;
- no human gold labels;
- no source diversity;
- no_update ablation had 18/20 schema valid.

### 30-case mixed source pilot

Current non-LLM audit:

- NHTSA official crash CSV: 10;
- CA DMV augmented collision CSV: 10;
- CA DMV official disengagement CSV: 10;
- label leakage violations: 0;
- missingness mean: 0.6967;
- feedback gaps: 340.

Important finding:

- `reported_intervention` and `reported_system_issue` are missing in 20/30 cases, not 30/30, because DMV disengagement reports provide these fields.

This supports the new evidence-regime narrative.

## 12. Current weaknesses to fix before ESWA submission

### Weakness 1: Requirement candidates may be misunderstood

Fix:

- Rename in paper and ideally code outputs to `evidence_requirement_candidates`.
- Add fields: `missing_evidence_slot`, `blocked_stronger_claim`, `candidate_evidence_requirement`, `supports`, `source_regime`.

### Weakness 2: Human-gold evaluation is missing

Fix:

- Create annotation protocol.
- Use at least two annotators.
- Label safety-analysis judgments under evidence constraints, not true accident cause.

### Weakness 3: no_update ablation has invalid outputs

Meaning:

- Without update stage, the model produced 2 invalid state/UCA combinations in the 20-case pilot.

Fix:

- Keep this as robustness evidence.
- Improve summarization and error reporting.
- Do not hide invalid outputs.

### Weakness 4: HMI counterfactuals might be overclaimed

Fix:

- State clearly that CF tests sensitivity to injected feedback cues.
- Do not claim real HMI causal effects.

### Weakness 5: Data source boundaries must be explicit

Fix:

- NHTSA SGO = official CSV.
- CA DMV disengagement = official CSV extracted from official archive.
- CA DMV collision CSV = third-party augmented dataset derived from official PDFs.

## 13. Revised method figure

The paper should have one main framework figure:

1. Public reports:
   - NHTSA crash CSV;
   - CA DMV collision derived CSV;
   - CA DMV disengagement official CSV.
2. Functional case builder:
   - ENV / ACTOR / CAR / HMI / CABIN;
   - reported / derived / not_reported provenance.
3. STPA-HF LLM expert system:
   - prior formation;
   - update;
   - commitment boundary;
   - mechanism trace;
   - UCA activation.
4. Auditable outputs:
   - bundle;
   - evidence audit;
   - feedback gaps;
   - evidence/logging requirement candidates.
5. Evaluations:
   - baseline;
   - ablation;
   - human gold;
   - counterfactual HMI sensitivity.

## 14. Main experiment plan for review

### Phase 1: Data freeze

Before the 50-case main run, use the current 30-case mixed pilot as the next gate:

```text
data/cases/paper_30_mixed_nhtsa10_ca_collision10_ca_disengagement10.jsonl
```

This pilot checks whether the prompts and audits work when crash/collision and disengagement evidence regimes are mixed.

Then create a paper main case file with 50 cases:

- 20 NHTSA SGO official crash/collision cases;
- 15 CA DMV augmented collision cases;
- 15 CA DMV official disengagement cases.

Selection principles:

- diversify source;
- diversify road type;
- diversify actor or trigger;
- include cases with and without reported intervention;
- include driver-present and driverless disengagement where possible.

Expected output:

```text
data/cases/paper_50_mixed_sources_v1.jsonl
results/paper_v1_50_mixed_sources/sample_summary.json
```

Decision rule:

- If the 30-case mixed LLM pilot has schema-valid rate below 95%, fix prompts/schema robustness before scaling to 50.
- If the 30-case pilot is stable, freeze the 50-case dataset and begin human annotation.

### Phase 2: Non-LLM dataset audit

Run:

- no-label audit;
- missingness profile;
- feedback gap report;
- evidence/logging requirement candidates;
- annotation packets.

Expected tables:

- dataset statistics;
- missingness by source regime;
- gap taxonomy by source regime.

### Phase 3: Full LLM experiment

Run:

- full system;
- direct baseline;
- generic CoT baseline;
- with vulnerability priority;
- no_update ablation.

Expected outputs:

- schema-valid rate;
- boundary distribution;
- UCA distribution;
- evidence audit;
- unsupported strong-boundary warnings.

### Phase 4: Counterfactual HMI sensitivity

Run HMI cue injections only for cases where HMI evidence is not_reported.

Templates:

- explicit takeover demand;
- ambiguous degradation;
- full support;
- partial support.

Expected output:

- directional consistency overall;
- directional consistency by source;
- directional consistency by template.

### Phase 5: Human-gold evaluation

Create annotation sheet for at least 40 cases, preferably all 50.

Annotators label:

- boundary label;
- dominant UCA;
- active UCA set;
- update vulnerability;
- insufficient information flags;
- blocked stronger claims;
- supporting evidence IDs.

Important:

- The label is the expert STPA-HF safety-analysis judgment given the evidence, not the true accident cause.

Expected output:

- raw annotator labels;
- agreement summary;
- adjudicated labels;
- full system vs baseline performance.

### Phase 6: Paper tables

Table 1: Multi-source dataset statistics and missingness.

Table 2: Main human-gold evaluation.

Table 3: Boundary escalation comparison against direct/generic CoT.

Table 4: Ablation and schema robustness.

Table 5: Evidence audit and catalog consistency.

Table 6: HMI counterfactual feedback-boundary sensitivity.

Table 7: Feedback gaps and evidence/logging requirement taxonomy.

## 15. Immediate code plan

### P0: Output terminology

- Add an alias command or output name: `evidence-requirement-candidates`.
- Keep old `requirement-candidates` command for backward compatibility.
- Add richer fields to candidates.

Rationale:

- The old name sounds like final design requirements.
- The intended meaning is evidence/logging requirements for stronger future safety claims.

### P1: Source-regime reporting

Update feedback-gap and missingness outputs to group by:

- `source_metadata.source_dataset`;
- `CAR.event_type`;
- `CAR.reported_intervention` reported vs missing;
- `CAR.reported_system_issue` reported vs missing.

### P2: 50-case sampler

Create deterministic sampler:

```text
paper_50_mixed_sources_v1.jsonl
```

Inputs:

- NHTSA cases;
- CA DMV collision augmented cases;
- CA DMV disengagement cases.

### P3: Full 30-case LLM pilot

Before spending on 50 cases, run full LLM experiment on the current 30-case mixed file:

```text
data/cases/paper_30_mixed_nhtsa10_ca_collision10_ca_disengagement10.jsonl
```

This checks whether disengagement cases break prompts or improve boundary diversity.

Minimum commands:

```powershell
$env:OPENAI_API_KEY="<YOUR_API_KEY>"
$env:OPENAI_MODEL="qwen-max-latest"
$env:OPENAI_BASE_URL="https://dashscope.aliyuncs.com/compatible-mode/v1"
python stpa_hf_dan_eswa_engine_final.py run --cases data/cases/paper_30_mixed_nhtsa10_ca_collision10_ca_disengagement10.jsonl --out results/paper_v1_30_mixed_sources/bundles
python stpa_hf_dan_eswa_engine_final.py baseline-suite --cases data/cases/paper_30_mixed_nhtsa10_ca_collision10_ca_disengagement10.jsonl --out results/paper_v1_30_mixed_sources/baseline_suite
python stpa_hf_dan_eswa_engine_final.py generate-cf-specs --cases data/cases/paper_30_mixed_nhtsa10_ca_collision10_ca_disengagement10.jsonl --out results/paper_v1_30_mixed_sources/cf_specs.jsonl
python stpa_hf_dan_eswa_engine_final.py generate-counterfactual --cases data/cases/paper_30_mixed_nhtsa10_ca_collision10_ca_disengagement10.jsonl --specs results/paper_v1_30_mixed_sources/cf_specs.jsonl --out results/paper_v1_30_mixed_sources/cf_cases.jsonl
python stpa_hf_dan_eswa_engine_final.py run --cases results/paper_v1_30_mixed_sources/cf_cases.jsonl --out results/paper_v1_30_mixed_sources/cf_bundles
python stpa_hf_dan_eswa_engine_final.py counterfactual-eval --base-bundle-dir results/paper_v1_30_mixed_sources/bundles --cf-bundle-dir results/paper_v1_30_mixed_sources/cf_bundles --specs results/paper_v1_30_mixed_sources/cf_specs.jsonl --out results/paper_v1_30_mixed_sources/cf_eval
python stpa_hf_dan_eswa_engine_final.py evidence-audit --bundle-dir results/paper_v1_30_mixed_sources/bundles --out results/paper_v1_30_mixed_sources/audit/evidence_support_audit
python stpa_hf_dan_eswa_engine_final.py feedback-gap-report --bundle-dir results/paper_v1_30_mixed_sources/bundles --out results/paper_v1_30_mixed_sources/feedback_gaps
python stpa_hf_dan_eswa_engine_final.py requirement-candidates --gap-report results/paper_v1_30_mixed_sources/feedback_gaps/feedback_gap_report.json --out results/paper_v1_30_mixed_sources/requirements
```

### P4: Annotation protocol

Write a formal annotation guide:

- definitions;
- decision rules;
- examples;
- insufficient information flags.

## 16. Acceptance criteria for the next milestone

The next milestone should be considered successful if:

- mixed-source 30-case full system has schema-valid rate >= 95%;
- evidence audit has invalid evidence ID mean = 0;
- UCA catalog consistency = 1.0;
- direct baseline still shows stronger boundary escalation relative to full system;
- disengagement cases show reduced `reported_intervention` and `reported_system_issue` gaps;
- CF directional consistency remains >= 90%;
- requirement candidates are clearly framed as evidence/logging requirements;
- annotation packet is ready for human labeling.

## 17. Final conclusion the paper should support

The paper should conclude:

> A missingness-aware STPA-HF constrained LLM expert system can transform sparse multi-source automated-driving public reports into auditable safety-case bundles, preserve epistemic boundaries around missing HMI/driver/internal ADS evidence, reduce unsupported crash-to-takeover-failure escalation, and identify concrete evidence/logging needs for stronger future feedback-boundary safety analysis.

Chinese version:

> 缺失感知、STPA-HF 约束的 LLM 专家系统能够把多源稀疏自动驾驶公开报告转化为可审计 safety-case bundle，在 HMI、driver-state、internal ADS 证据缺失时保留认知边界，减少从 crash 到 takeover failure 的无证据过度推断，并输出支持更强 feedback-boundary 安全分析所需的证据/日志需求。

The paper should not conclude:

- that it reconstructs true accident causes;
- that it proves HMI caused or prevented events;
- that it infers true driver cognition;
- that its requirement candidates are validated final HMI design requirements.
