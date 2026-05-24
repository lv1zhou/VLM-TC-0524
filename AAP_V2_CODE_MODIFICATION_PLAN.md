# AAP V2 Code Modification Plan

Date: 2026-05-16

Target file:
- `stpa_hf_dan_eswa_engine_final.py`

Main narrative target:
- Evidence-Bounded Driver Process-Model Replay
- Output artifact: `driver_process_model_tabletop_replay_package`
- Evaluation target: AAP-style structured safety analysis, baseline/ablation comparison, expert alignment, HMI/logging sensitivity, and richer-evidence replay convergence

Hard constraints:
- No hardcoded case outcomes.
- No semantic fallback that silently converts failures into plausible outputs.
- No `not_reported` as positive evidence.
- No true driver psychology, true accident cause, HMI causality, or legal responsibility claims.
- No "video experiment" as a paper-facing main task. Use `richer-evidence replay case study` or `evidence-density stress test`.

## 1. Current Code Readiness

Already present:
- Full replay pipeline and `tabletop_replay_package` generation.
- `tabletop-replay-audit`.
- `baseline-suite` for direct and generic CoT.
- `pm-mediation-comparison` for direct/generic/no-update/full comparison.
- `counterfactual-eval` with replay-package change metrics.
- `feedback-gap-report` and `requirement-candidates`.
- `expert-preview-labels`, but currently too coarse for AAP V2 expert alignment.
- `paper-manifest`, `missingness-profile`, and sample builders.

Main gaps:
- No standardized 6-condition baseline/ablation runner.
- No `structured_prompt_only` condition.
- No explicit `no_evidence_gate` condition.
- Existing expert preview labels do not yet label ranked pathways, blocked claims, or RIMS dimensions.
- No RIMS metric.
- No richer-evidence sparse/richer case-pair comparison command.
- Requirement candidates still risk looking like mechanical missing-field checklists unless tied to pathway/replay impact.

## 2. Phase 1: Paper-Facing Naming and Output Hygiene

### Goal

Ensure every paper-facing output matches the AAP V2 narrative.

### Edits

Search and revise paper-facing strings in `stpa_hf_dan_eswa_engine_final.py`:
- Replace `ESWA-facing` with AAP-neutral wording.
- Hide or rename remaining `safety-case`, `commitment boundary`, and `feedback-boundary` terms in outputs.
- Keep internal variable names if changing them risks large refactors, but output JSON and reports must use:
  - `driver_pm_tabletop_replay_v2.4.3`
  - `driver_process_model_tabletop_replay_bundle`
  - `tabletop_replay_package`
  - `driver_replay_posture`
  - `post_incident_safety_review_artifact`
  - `richer_evidence_replay_case_study`

### Acceptance checks

Run:

```powershell
rg -n "ESWA|safety-case|commitment boundary|feedback-boundary|video-supported|video experiment" .\STPAHF\stpa_hf_dan_eswa_engine_final.py
```

Allowed only if:
- occurrence is in historical comments, not paper-facing output; or
- line explicitly says the method is not doing that task.

## 3. Phase 2: Standardized Six-Condition Baseline/Ablation Runner

### Goal

Support AAP RQ2 directly:

> Does driver process-model mediation reduce outcome-only overreach and improve complete PM-update-action-UCA chains?

### New command

Add:

```text
run-ablation-suite
```

Inputs:
- `--cases`
- `--full-bundle-dir` optional, reuse existing full replay
- `--out`
- `--case-limit`
- `--temperature`
- `--resume`

Conditions:
- `direct_llm`
- `generic_cot`
- `structured_prompt_only`
- `no_update`
- `no_evidence_gate`
- `full_replay`

### Implementation details

Reuse existing:
- `run_direct_case_baseline`
- `run_generic_cot_baseline`
- existing no-update pathway if available in `run(...)` options, otherwise add a controlled ablation flag
- `build_pm_mediation_comparison_report`

Add:
- `STRUCTURED_PROMPT_ONLY_PROMPT`
  - Same output schema as baselines.
  - Allows structured sections but no STPA-HF process-model gate.
  - Must not include CPS/CPB/OPS/OPB definitions as hard constraints.

- `NO_EVIDENCE_GATE_PROMPT` or controlled full-run variant
  - Keeps PM/update/action/UCA structure.
  - Disables blocked-claim enforcement.
  - Must output unsupported claims explicitly so audit can detect overreach.

### Standard per-condition audit fields

Every condition summary must include:
- `case_id`
- `condition`
- `schema_valid`
- `outcome_only_overreach`
- `unsupported_driver_state_claim`
- `unsupported_takeover_failure_claim`
- `complete_pm_update_action_uca_chain`
- `evidence_cited_pathway_rate`
- `blocked_claim_transparency`
- `ranked_pathway_count`
- `notes`

### Output files

```text
results/.../ablation_suite/
  condition_outputs/
  ablation_suite_summary.json
  pm_mediation_comparison_v2.json
  pm_mediation_comparison_v2.csv
```

### Acceptance checks

For a 2-case sanity run:
- all 6 conditions produce rows;
- direct/generic can be invalid only if schema enforcement catches it, not silently repaired;
- full replay has complete-chain fields;
- no-evidence-gate is auditable for unsupported claims.

## 4. Phase 3: Expert Annotation Packet V2

### Goal

Support AAP RQ3 with expert-alignment metrics.

### New or revised command

Add:

```text
export-expert-replay-packets
```

or revise `export-annotation-packets` with:

```text
--schema-version expert_replay_annotation_v2
```

### Packet contents

Each packet should include:
- `case_id`
- original case narrative and source metadata
- evidence packet
- extracted narrative propositions
- CPS / CPB / OPS / OPB nodes
- update-process nodes
- other factors
- candidate driver actions
- UCA pathway candidates
- system pathway ranking
- blocked claims
- replay questions
- missing requirement candidates
- instruction: labels are safety-review admissibility labels, not true-cause labels

### Expert label schema

Create JSON schema-like template:

```json
{
  "case_id": "...",
  "label_scope": "expert_replay_admissibility",
  "supported_quadrant_nodes": [],
  "valid_update_claims": [],
  "admissible_candidate_actions": [],
  "admissible_uca_pathways": [],
  "top1_pathway_id": "...",
  "top3_pathway_ids": [],
  "blocked_claims_correct": [],
  "blocked_claims_missing": [],
  "required_missing_evidence": [],
  "requirement_relevance": [],
  "notes": "..."
}
```

### Output files

```text
annotation_packets_v2/
  <case_id>.expert_replay_packet.json
  expert_replay_label_template.jsonl
  expert_replay_annotation_guide.md
```

### Acceptance checks

For 2 cases:
- packet can be read without opening raw bundle files;
- label template contains all fields required for RIMS;
- no field asks annotators to label the true accident cause.

## 5. Phase 4: Expert Preview Labels V2

### Goal

Use Codex/LLM as "Expert-0 preview" to debug the protocol before real human annotation.

### Revise command

Revise:

```text
expert-preview-labels
```

Add optional inputs:
- `--bundle-dir`
- `--packet-dir`
- `--out-labels`
- `--out-report`
- `--label-schema expert_replay_v2`

### Output labels

Generate preview labels for:
- supported quadrant nodes
- valid update claims
- admissible candidate actions
- admissible UCA pathways
- top1/top3 pathway ids
- blocked claims correctness
- missing evidence requirements

### Important boundary

Every output report must state:

```text
Expert-0 preview labels are protocol-debug labels, not publication human-gold labels.
```

### Acceptance checks

For 2 cases:
- labels reference actual pathway IDs from replay packages;
- labels do not invent unavailable evidence;
- labels can be consumed by RIMS evaluator.

## 6. Phase 5: RIMS Metric

### Goal

Implement a replay-quality metric analogous in spirit to AAP LLM/VLM information-matching metrics, but adapted to driver-process-model replay.

### New command

Add:

```text
replay-alignment-eval
```

Inputs:
- `--bundle-dir`
- `--labels`
- `--out`

### Metrics

Case-level:
- `top1_pathway_match`
- `top3_pathway_recall`
- `ranking_correlation`
- `pathway_distribution_distance`
- `blocked_claim_precision`
- `blocked_claim_recall`
- `requirement_relevance_rate`
- `rims_total`
- `rims_evidence_fidelity`
- `rims_pm_alignment`
- `rims_update_alignment`
- `rims_action_uca_alignment`
- `rims_blocked_claim_correctness`
- `rims_requirement_relevance`

RIMS scoring:
- each dimension 0, 1, or 2
- normalize total to 0-1
- must be computed from expert labels, not model self-rating

Summary-level:
- mean/std by source regime
- mean/std by collision vs disengagement
- failure cases list

### Output files

```text
replay_alignment_eval.json
replay_alignment_eval.csv
rims_dimension_summary.json
```

### Acceptance checks

For Expert-0 preview labels:
- evaluator runs end-to-end;
- top1/top3 can be computed even when pathway ids are missing, but missing ids must be reported as label errors, not silently ignored;
- RIMS is not computed if required label dimensions are absent.

## 7. Phase 6: HMI/Logging Sensitivity V2

### Goal

Make HMI/logging experiment report replay-package changes, not just boundary changes.

### Existing basis

Current code already has:
- `generate-cf-specs`
- `generate-counterfactual`
- `counterfactual-eval`
- replay-package change metrics

### Required revisions

Standardize templates:
- `mode_cue_added`
- `takeover_cue_added`
- `time_budget_added`
- `driver_intervention_trace_added`
- `richer_logging_added`

Ensure each template:
- uses `assumed_for_counterfactual`
- writes a `counterfactual_claim_boundary`
- avoids claiming the cue existed in the real event

Add metrics:
- `top_pathway_convergence`
- `rims_change` when labels are supplied
- `requirement_target_shift`
- `blocked_claim_category_reduction`

### Output files

```text
hmi_logging_sensitivity_summary.json
hmi_logging_sensitivity_by_template.csv
counterfactual_replay_package_change.json
```

### Acceptance checks

For 2 base cases:
- 5 templates generate 10 CF cases;
- CF eval reports package deltas;
- no output says injected evidence is real evidence.

## 8. Phase 7: Richer-Evidence Pair Comparison

### Goal

Support the final evidence-density stress test.

### New command

Add:

```text
richer-evidence-compare
```

Inputs:
- `--sparse-bundle-dir`
- `--richer-bundle-dir`
- `--pair-map`
- `--out`

`pair-map` format:

```jsonl
{"pair_id":"caseA","sparse_case_id":"...","richer_case_id":"...","evidence_addition_summary":"..."}
```

### Comparison dimensions

For each pair:
- evidence additions
- PM node specificity change
- update source completeness change
- candidate action narrowing
- pathway ranking convergence
- blocked claim reduction
- missing requirement reduction
- requirement specificity change

### Output files

```text
richer_evidence_pair_comparison.json
richer_evidence_pair_comparison.csv
richer_evidence_case_study.md
```

### Acceptance checks

For 1 pair:
- comparison runs without manual JSON editing;
- output says richer evidence narrows replay boundary, not proves true cause;
- case-study markdown is paper-readable.

## 9. Phase 8: Paper Pipeline Script

### Goal

Make the next experiment reproducible.

### New script

Create:

```text
run_aap_v2_pilot_pipeline.ps1
```

Stages:
1. py_compile
2. audit case input
3. missingness profile
4. full replay run
5. evidence audit
6. tabletop replay audit
7. feedback gap report
8. requirement candidates
9. ablation suite
10. expert replay packets
11. Expert-0 preview labels
12. replay alignment eval / RIMS
13. HMI/logging CF specs
14. CF case generation
15. CF full replay run
16. HMI/logging sensitivity eval
17. paper manifest

Default pilot:
- 20 cases
- 10 collision
- 10 disengagement

### Acceptance checks

The script should fail on missing required outputs. It should not silently skip failed phases.

## 10. Implementation Order

### Step 1

Paper-facing naming hygiene.

### Step 2

Add `run-ablation-suite`, `structured_prompt_only`, and `no_evidence_gate`.

### Step 3

Add expert replay packet V2 and label template.

### Step 4

Revise expert preview labels to V2.

### Step 5

Add `replay-alignment-eval` and RIMS.

### Step 6

Revise HMI/logging sensitivity outputs.

### Step 7

Add richer-evidence pair comparison.

### Step 8

Add AAP V2 pilot pipeline script.

### Step 9

Run M0:
- 1 collision
- 1 disengagement

### Step 10

Run M1/M2/M3 pilot:
- 20 cases
- full replay
- ablation suite
- Expert-0 labels
- RIMS

## 11. Final Readiness Gate Before Main Experiment

Proceed to 40-50 case main experiment only if:
- schema valid rate >= 95%
- evidence invalid ID mean = 0
- replay package generation rate >= 95%
- all 6 ablation conditions run for >= 95% cases
- Expert-0 labels can be consumed by RIMS without manual correction
- full replay has lower overreach than direct/generic CoT
- no-update and no-evidence-gate ablations show interpretable degradation
- HMI/logging sensitivity changes replay package fields without causal overclaim
- richer-evidence comparison produces a paper-readable case-study artifact
