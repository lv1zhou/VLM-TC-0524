# AAP V2 Experiment and Code Preparation Plan

Date: 2026-05-16

## 1. Current Paper Thesis

The paper is now framed as:

**Evidence-Bounded Driver Process-Model Replay for Automated-Driving Incident Analysis**

The method converts public automated-driving collision and disengagement reports into auditable **driver process-model tabletop replay packages**. The package is not a reconstruction of the true accident cause, not a verdict about the true driver state, not a proof of HMI causality, and not a legal responsibility analysis. It is a structured post-incident safety-review artifact.

Core chain:

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

## 2. Role of Richer-Evidence Case Study

The paper should not claim a separate video-understanding contribution.

The final case study should be called:

**Richer-evidence replay case study**  
or  
**Evidence-density stress test**

Its role is to test whether the same replay structure becomes more specific when additional evidence is available. The additional evidence may come from video-derived descriptions, official timelines, third-party reconstructions, attachments, HMI descriptions, intervention traces, or more complete narratives.

Expected comparison:

| Sparse text report | Richer-evidence version |
|---|---|
| more missing update sources | more reported update sources |
| more blocked claims | fewer blocked claims |
| more competing pathways | more stable pathway ranking |
| broader requirements | more targeted HMI/logging requirements |

The conclusion should be:

> Richer evidence narrows the replay boundary; it does not turn the method into a true-cause reconstruction tool.

## 3. AAP LLM/VLM Paper Benchmarking Logic

The experiment design should follow the evaluation grammar of recent AAP LLM/VLM papers:

1. **DDLM, AAP 2024**
   - Pattern: driver behavior + reasoning chain + VLLM.
   - Lesson for us: prove the intermediate reasoning chain is necessary.

2. **SeeUnsafe, AAP 2025**
   - Pattern: MLLM framework, structured outputs, visual grounding, ablation, information matching score.
   - Lesson for us: define a structured replay-quality score instead of only reporting schema validity.

3. **Crash reports to safer roads, AAP 2026**
   - Pattern: crash report + multimodal evidence + expert-annotated subset + ranking/distribution metrics.
   - Lesson for us: add an expert-annotated subset and evaluate ranked pathway alignment.

Our paper adapts these patterns to a different task:

> driver-process-model replay under sparse automated-driving incident evidence.

## 4. Final Research Questions

### RQ1: Replay Generation and Auditability

Can the framework generate schema-valid, evidence-grounded, and review-ready driver process-model tabletop replay packages from public automated-driving collision and disengagement reports?

### RQ2: Necessity of Driver Process-Model Mediation

Compared with direct LLM, generic CoT, structured-prompt-only, no-update, and no-evidence-gate variants, does the full replay framework reduce outcome-only overreach and improve complete PM-update-action-UCA chain formation?

### RQ3: Expert Alignment and Evidence-Density Sensitivity

Do ranked replay pathways, blocked claims, and minimum HMI/logging requirements align with expert review, and do they change in expected ways when HMI, logging, or richer evidence is added?

## 5. Main Experiments

### Block 1: Replay Package Generation Quality

Dataset:
- Pilot: 20 cases
  - 10 CA DMV collision
  - 10 CA DMV disengagement
- Main experiment: 40-50 cases
  - balanced collision/disengagement where possible
  - NHTSA SGO as supplementary/robustness only if the supervision regime is clear

Metrics:
- schema valid rate
- evidence ID validity
- quadrant coverage rate
- update-process presence rate
- candidate-action count
- UCA-pathway count
- ranked-pathway count
- blocked-claim count
- missing-requirement count
- replay-ready rate

Target paper table:
- Table 2: replay generation quality and auditability

### Block 2: Baseline and Ablation Comparison

Compared systems:
- direct LLM
- generic CoT
- structured prompt only
- no-update ablation
- no-evidence-gate ablation
- full replay

Metrics:
- outcome-only overreach count
- unsupported driver-state claim count
- unsupported takeover-failure claim count
- complete PM-update-action-UCA chain rate
- evidence-cited pathway rate
- blocked-claim transparency rate

Target paper table:
- Table 3: baseline and ablation comparison

### Block 3: Expert Alignment

Expert annotation target:
- evidence sufficiency
- supported CPS / CPB / OPS / OPB nodes
- reported or missing update sources
- admissible candidate actions
- admissible UCA pathways
- top-1 / top-3 pathway ranking
- blocked claims
- minimum HMI/logging evidence requirements

Metrics:
- Top-1 pathway match
- Top-3 pathway recall
- ranking correlation
- pathway-distribution distance
- blocked-claim correctness
- requirement relevance
- Replay Information Matching Score (RIMS)

RIMS dimensions:
- evidence fidelity
- process-model alignment
- update alignment
- action-UCA alignment
- blocked-claim correctness
- requirement relevance

Target paper table:
- Table 4: expert-alignment metrics

### Block 4: HMI/Logging Sensitivity

Conditions:
- sparse report baseline
- mode cue added
- takeover cue added
- time budget added
- driver intervention trace added
- richer logging condition

Metrics:
- update-status change
- candidate-action change
- pathway-rank change
- blocked-claim reduction
- missing-requirement reduction
- top-pathway convergence
- RIMS change

Target paper table:
- Table 5: HMI/logging sensitivity

### Block 5: Richer-Evidence Replay Case Study

Input versions:
- sparse-text version
- richer-evidence version

Comparison:
- process-model node specificity
- update source completeness
- candidate-action narrowing
- pathway ranking convergence
- blocked-claim reduction
- requirement specificity

Target paper figure:
- Figure 2: sparse vs richer-evidence replay package comparison

## 6. Code Modification Plan

### Phase 1: Naming and Output Freeze

Ensure all paper-facing output uses:
- `driver_pm_tabletop_replay_v2.4.3` or next frozen schema version
- `driver_process_model_tabletop_replay_bundle`
- `tabletop_replay_package`
- `driver replay posture`
- `post-incident safety review artifact`

Remove or hide paper-facing remnants:
- safety-case
- commitment boundary
- feedback-boundary
- video-supported experiment as a main task

### Phase 2: Baseline/Ablation Runner

Add or standardize conditions:
- direct LLM
- generic CoT
- structured prompt only
- no-update
- no-evidence-gate
- full replay

Each condition must produce comparable audit fields:
- outcome-only overreach
- unsupported driver-state claim
- unsupported takeover-failure claim
- complete chain
- evidence citation coverage
- blocked-claim transparency

### Phase 3: Expert Annotation Interface

Create an annotation packet format for each case:
- original report text
- evidence packet
- CPS / CPB / OPS / OPB candidates
- update source candidates
- candidate actions
- candidate UCA pathways
- system ranking
- blocked claims
- requirement candidates

Create expert label schema:
- supported quadrant nodes
- valid update claims
- admissible candidate actions
- admissible UCA pathways
- top-1 pathway
- top-3 pathways
- blocked claims
- required missing evidence

### Phase 4: RIMS Metric

Implement RIMS as a report-level and case-level metric.

Suggested scoring:
- each dimension scored 0-2
- total normalized to 0-1
- dimensions:
  - evidence fidelity
  - process-model alignment
  - update alignment
  - action-UCA alignment
  - blocked-claim correctness
  - requirement relevance

The metric should be computed against expert labels, not against model self-assessment.

### Phase 5: HMI/Logging Sensitivity Runner

Standardize counterfactual evidence templates:
- mode cue
- takeover cue
- time budget
- intervention trace
- richer logging

Output deltas:
- update-status change
- candidate-action change
- pathway-rank change
- blocked-claim reduction
- missing-requirement reduction
- top-pathway convergence
- RIMS change when labels exist

### Phase 6: Richer-Evidence Case Study Support

Add a case-pair runner:
- sparse input
- richer-evidence input

Output side-by-side comparison:
- evidence additions
- PM node changes
- update-source changes
- candidate-action changes
- pathway-ranking changes
- blocked-claim changes
- requirement changes

## 7. Execution Order

### M0: Sanity

Run 2 cases:
- 1 collision
- 1 disengagement

Purpose:
- verify schema
- verify no old terminology leaks
- verify audit fields exist

### M1: 20-Case Pilot

Run:
- 10 collision
- 10 disengagement
- full replay
- evidence audit
- tabletop replay audit
- feedback gap / requirement candidates

Gate:
- schema valid >= 95%
- evidence invalid ID mean = 0
- replay package generation rate >= 95%

### M2: Baseline/Ablation Pilot

Run all baseline and ablation conditions on the same 20 cases.

Gate:
- full replay has lower overreach than direct/generic CoT
- no-update weakens complete chain formation
- no-evidence-gate increases unsupported claims

### M3: Expert Preview Annotation

Use Codex as preview expert annotator first.

Output:
- expert labels for 20 cases
- Top-1 / Top-3 / RIMS pilot metrics

Gate:
- labels expose meaningful differences among systems
- RIMS is interpretable and not just another schema score

### M4: Sensitivity Pilot

Run HMI/logging sensitivity on 5-10 cases.

Gate:
- richer evidence changes replay package fields
- blocked claims and missing requirements respond sensibly

### M5: Richer-Evidence Case Study

Run one sparse/richer pair.

Gate:
- richer-evidence version narrows replay boundary without claiming true cause

### M6: Main Experiment Expansion

Expand to 40-50 cases only after M1-M5 pass.

## 8. Paper Table Mapping

| Table/Figure | Evidence Source | Main Claim |
|---|---|---|
| Table 1 | dataset profile | reports are sparse and evidence-limited |
| Table 2 | replay audit | package generation is stable and auditable |
| Table 3 | baselines/ablations | PM mediation prevents outcome-only overreach |
| Table 4 | expert labels/RIMS | ranked pathways align with expert review |
| Table 5 | HMI/logging sensitivity | replay package responds to evidence density |
| Table 6 | requirement taxonomy | outputs support reporting/logging improvement |
| Figure 1 | method diagram | pipeline is structured and STPA-HF constrained |
| Figure 2 | richer-evidence case | richer evidence narrows replay boundary |

## 9. Current Gap Score

Narrative fit:
- 9.2 / 10

Method prose:
- 8.2 / 10

Code-output alignment:
- 8.0 / 10

Experiment readiness:
- 7.2 / 10

Main bottlenecks:
- expert annotation protocol and labels are not yet implemented
- RIMS metric is not yet implemented
- baseline/ablation conditions need to be standardized
- richer-evidence pair runner is not yet implemented
- main experiment sample is not yet frozen

## 10. Immediate Next Action

Start with code changes for:

1. baseline/ablation runner standardization
2. expert annotation packet generation
3. expert label schema
4. RIMS computation
5. HMI/logging sensitivity deltas
6. richer-evidence pair comparison

Then run M0 and M1 before expanding.
