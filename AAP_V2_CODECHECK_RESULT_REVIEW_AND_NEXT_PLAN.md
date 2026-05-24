# AAP V2 Codecheck Result Review and Next Plan

Date: 2026-05-16

## 1. What Was Tested

This review reads the outputs from the AAP V2 codecheck run:

- `results/aap_v2_codecheck_ablation_2case/`
- `results/aap_v2_codecheck_ablation_2case/full_replay_audit/`
- `results/aap_v2_codecheck_ablation_2case/evidence_audit/`
- `results/aap_v2_codecheck_ablation_2case/replay_alignment/`
- `results/aap_v2_codecheck_richer_compare/`

The run used 2 CA DMV collision cases. It is a codecheck and narrative-alignment test, not a publication-scale experiment.

## 2. Narrative Target

The current AAP thesis is:

> Evidence-Bounded Driver Process-Model Replay transforms sparse automated-driving collision/disengagement reports into auditable tabletop replay packages. It supports post-incident driver-centered safety review by separating evidence, missing evidence, process-model updates, candidate driver actions, UCA pathways, blocked claims, replay questions, and minimum reporting/logging requirements.

The paper must support three claims:

1. The system can generate auditable replay packages from sparse AV incident text.
2. STPA-HF driver process-model mediation is necessary to suppress outcome-only overreach.
3. HMI/logging/richer evidence changes the replay package by narrowing uncertainty, not by proving true accident cause.

## 3. Result Summary

### 3.1 Replay Package Generation

Full replay audit on 2 cases:

- replay package generation rate: `1.0`
- quadrant coverage rate: `1.0`
- update-process present rate: `1.0`
- review-ready case rate: `1.0`
- mean ranked pathways: `6`
- mean replay questions: `4`
- mean missing requirements: `12`
- mean blocked claims: `3.5`

Interpretation:

This supports RQ1 at codecheck scale. The replay package exists, is complete, and exposes the right review-facing artifacts.

Limitation:

Both cases are CA DMV collision cases. This does not yet test disengagement cases or a mixed evidence regime.

### 3.2 Baseline and Ablation Comparison

Six-condition ablation result:

| Condition | Outcome-only overreach | Complete chain | Blocked-claim transparency | Mean ranked pathways |
|---|---:|---:|---:|---:|
| direct LLM | 2/2 | 0.0 | 0.0 | 0 |
| generic CoT | 2/2 | 0.0 | 0.0 | 0 |
| structured prompt only | 2/2 | 0.0 | 0.0 | 0 |
| no-update | 0/2 | 0.0 | 1.0 | 1 |
| no-evidence-gate | 0/2 | 1.0 | 0.0 | 6 |
| full replay | 0/2 | 1.0 | 1.0 | 6 |

Interpretation:

This is the strongest result from the codecheck. It directly supports RQ2:

- Direct LLM, generic CoT, and structured-prompt-only all escalate to `not_supported_transfer` in both cases.
- Generic CoT and structured-prompt-only also activate `UCA-H-2` in both cases, despite no complete PM-update-action-UCA chain.
- Full replay keeps both cases at `contingent_readiness`, avoids unsupported takeover-failure claims, and produces complete chains.
- No-update preserves some artifact structure but collapses ranked pathways from 5-7 down to 1, showing that update analysis is doing real work.

Key paper claim supported:

> STPA-HF driver process-model mediation is not decorative; it prevents collapse from collision outcome to driver takeover failure and creates auditable intermediate chains.

Current weakness:

`no_evidence_gate` is only a diagnostic projection and currently does not expose enough additional unsupported-claim risk. It has complete chain rate `1.0`, mean ranked pathways `6`, but unsupported-claim metrics remain `0`. This makes it less useful as an ablation unless we sharpen its definition.

### 3.3 Evidence Audit

Evidence audit on full replay:

- invalid evidence ID mean: `0`
- UCA catalog consistency: `1.0`
- outcome-only UCA activation: `0`
- not-reported used as observed update fact: `0`
- hmi absence inferred from nonreporting: `0`
- psychological overclaim warning: `0`
- generic UCA expansion warning: `1`
- mean candidate pathways per case: `6`
- pathway status distribution: `10 blocked`, `2 weakly_supported`

Interpretation:

This supports the evidence-bounded claim boundary. The system does not use not-reported evidence as positive evidence, does not activate UCAs from outcome alone, and does not make true-psychology claims in these two cases.

Important nuance:

The system still cites many `not_reported` evidence IDs as gap evidence, which is correct. But the paper must explain this clearly:

> not_reported citations are evidence-gap citations, not factual support for a real-world absence.

Current weakness:

`claims_without_supporting_evidence_count` averages `1.5`. In the case reports, this is mostly tied to:

- `observed_update_vulnerability = none`
- `uca_activation_status = no_activated_uca`

These are negative or absence-of-activation claims. The audit should distinguish:

- unsupported positive claims
- negative/no-activation status claims
- evidence-gap-only claims

Otherwise reviewers may misread this as unsupported reasoning.

### 3.4 Expert-0 and RIMS

Replay alignment result using Expert-0 preview labels:

- RIMS total: `1.0`
- Top-1 pathway match: `1.0`
- Top-3 pathway recall: `1.0`
- blocked-claim recall: `1.0`
- requirement relevance: `1.0`

Interpretation:

The pipeline works technically: packets -> preview labels -> RIMS.

But this is not yet paper evidence. Expert-0 labels are generated from system outputs and therefore are self-consistency labels. They are useful for debugging the protocol, not for proving expert alignment.

Current weakness:

RIMS is currently too forgiving because Expert-0 copies system top pathways as the preview label. This makes RIMS artificially perfect.

Required correction:

RIMS must be computed against independent human labels, or against a stricter Expert-0 protocol that does not simply mirror the system ranking. Until then, RIMS can only be reported as a protocol check.

### 3.5 Richer-Evidence Pair Comparison

One sparse vs richer-evidence pair was tested using an HMI takeover-demand counterfactual:

- blocked claim reduction rate: `1.0`
- missing requirement reduction rate: `1.0`
- update source completeness increase rate: `1.0`
- PM specificity increase rate: `0.0`

Case-level details:

- blocked claims: `3 -> 2`
- missing requirements: `12 -> 8`
- update source count: `6 -> 10`
- pathway rank changed: `true`
- PM specificity score: `275 -> 237`
- candidate action count: `3 -> 3`

Interpretation:

This supports the evidence-density story in the most important ways:

- richer HMI evidence reduces blocked claims;
- richer HMI evidence reduces missing requirements;
- update sources become more complete;
- pathway ranking changes.

But the `PM specificity` metric is currently flawed. A richer evidence condition can reduce text length because uncertainty wording shrinks. That is not less specificity. Word-count specificity is not a valid measure.

Required correction:

Replace word-count specificity with structured specificity:

- number of reported update sources
- number of non-missing PM nodes
- number of PM nodes with direct/derived evidence
- number of blocked PM claims reduced
- number of pathways changing from blocked to weak/admissible
- top-pathway entropy or rank convergence

## 4. Match Against AAP V2 Narrative

### Claim 1: Auditable replay package generation

Status: **partially supported**

Why:
- replay package generation is complete in 2/2 cases;
- audit fields are present;
- evidence consistency is good.

Gap:
- only 2 collision cases;
- no disengagement cases in this run;
- no 20-case mixed pilot yet.

### Claim 2: PM mediation prevents overreach

Status: **strongly supported at codecheck scale**

Why:
- direct/generic/structured all overreach;
- full replay does not;
- no-update loses complete chain.

Gap:
- need 20-case pilot to confirm this is not a two-case artifact.

### Claim 3: Expert alignment

Status: **pipeline-ready but not substantively supported**

Why:
- packet export, Expert-0 labels, and RIMS run successfully.

Gap:
- Expert-0 labels mirror system outputs;
- no independent labels;
- no ranking correlation or distribution metrics yet.

### Claim 4: HMI/logging/richer-evidence sensitivity

Status: **directionally supported**

Why:
- richer evidence reduces blocked claims and missing requirements;
- update source completeness increases;
- pathway ranking changes.

Gap:
- only 1 pair;
- PM specificity metric is invalid;
- HMI templates still use legacy names and need AAP V2 naming.

## 5. Current Code Gaps

### Gap 1: no-evidence-gate ablation is weak

Problem:

The current no-evidence-gate condition is a diagnostic projection, but it does not yet show what unsupported claims would become visible if the gate were removed.

Fix:

Make no-evidence-gate output:

- `would_promote_blocked_pathway_count`
- `would_promote_outcome_only_pathway_count`
- `would_promote_no_action_evidence_pathway_count`
- `would_promote_not_reported_supported_pathway_count`
- `promoted_pathway_examples`

This will make the ablation useful without pretending the invalid output is a real replay package.

### Gap 2: RIMS is too self-confirming

Problem:

Expert-0 labels currently copy system ranking. This makes RIMS perfect by construction.

Fix:

Add strict Expert-0 mode:

- build labels from packet evidence and pathway content;
- do not copy system ranking automatically;
- require explicit admissibility reasons;
- penalize top pathways if their evidence is only missingness or weak compatibility.

Longer-term:

Human labels are still necessary for publication.

### Gap 3: RIMS lacks ranking/distribution metrics

Problem:

`ranking_correlation` and `pathway_distribution_distance` are null.

Fix:

Require expert labels to include either:

- ranked pathway list, or
- pathway scores / admissibility tiers.

Then compute:

- Spearman or Kendall correlation;
- Top-1 match;
- Top-3 recall;
- Jaccard overlap;
- simple distribution distance over admissibility tiers.

### Gap 4: PM specificity metric is invalid

Problem:

Word count decreases when uncertainty wording is reduced, so it can incorrectly say richer evidence is less specific.

Fix:

Replace with structured evidence-density metrics:

- `reported_update_source_count`
- `direct_pm_node_support_count`
- `missing_pm_evidence_count`
- `blocked_pm_claim_count`
- `pathway_status_entropy`
- `top_pathway_margin`

### Gap 5: missing requirements are still too checklist-like

Problem:

Both replay audits report exactly 12 missing requirements per sparse case. This supports missingness but may look mechanical.

Fix:

Classify requirements into:

- global missing logging fields;
- pathway-critical requirements;
- claim-blocking requirements;
- lower-priority completeness fields.

Add:

- `requirement_triggering_pathway_ids`
- `requirement_blocks_claims`
- `requirement_priority_reason`
- `requirement_specificity_level`

### Gap 6: evidence audit needs claim-type separation

Problem:

`claims_without_supporting_evidence_count` mixes positive claims and no-activation/negative claims.

Fix:

Split into:

- `positive_claims_without_supporting_evidence_count`
- `negative_status_claims_without_supporting_evidence_count`
- `gap_claims_without_positive_support_count`

Only the first should count as a major warning.

### Gap 7: current codecheck has no disengagement cases

Problem:

The AAP narrative is about collision and disengagement. This test only covers collision.

Fix:

Next run must use:

- 2-case sanity: 1 collision + 1 disengagement
- 20-case pilot: 10 collision + 10 disengagement

## 6. Revised Next Plan

### Phase A: Fix Metrics Before Scaling

Implement:

1. no-evidence-gate promoted-pathway diagnostics
2. strict Expert-0 v2 label mode
3. RIMS ranking/distribution metrics
4. structured specificity metrics for richer-evidence comparison
5. requirement criticality classification
6. evidence-audit claim-type separation

Acceptance:

- RIMS should no longer be automatically 1.0 on preview labels.
- richer-evidence specificity should reflect evidence structure, not text length.
- no-evidence-gate should expose promoted-risk counts.

### Phase B: Run M0 Mixed Sanity

Dataset:

- 1 CA DMV collision
- 1 CA DMV disengagement

Run:

- full replay
- tabletop replay audit
- evidence audit
- ablation suite
- expert replay packets
- strict Expert-0 labels
- RIMS

Gate:

- all commands complete;
- no old terminology leaks;
- full replay still avoids outcome-only overreach;
- disengagement case produces interpretable replay package.

### Phase C: Run 20-Case Pilot

Dataset:

- 10 collision
- 10 disengagement

Run:

- full replay
- evidence audit
- tabletop replay audit
- ablation suite
- expert replay packets
- strict Expert-0 labels
- RIMS preview
- HMI/logging sensitivity on 5 cases
- richer-evidence comparison on 1 pair if available

Gate:

- schema valid >= 95%
- evidence invalid ID mean = 0
- replay package generation rate >= 95%
- full replay overreach < direct/generic/structured
- no-update complete-chain rate clearly lower than full replay
- no-evidence-gate promoted-risk count > 0 in at least some cases
- RIMS preview interpretable and not uniformly perfect

### Phase D: Prepare Human Annotation

After M0/M1 pass:

- freeze expert replay annotation guide;
- select 20 cases for human annotation;
- annotate top pathways, blocked claims, and missing evidence;
- compute real RIMS and ranking metrics.

### Phase E: Main Experiment

Only after pilot:

- expand to 40-50 cases;
- include balanced collision/disengagement;
- use human labels for at least 20-case subset;
- report final tables.

## 7. Current Score After Codecheck

Narrative fit:
- `9.2 / 10`

Code-output alignment:
- before: `8.0 / 10`
- now: `8.5 / 10`

Experiment readiness:
- before: `7.2 / 10`
- now: `8.0 / 10`

Publication evidence strength:
- current codecheck only: `6.8 / 10`
- expected after 20-case mixed pilot with stricter metrics: `8.3 / 10`
- expected after human labels and 40-50 cases: `9.0+ / 10`

## 8. Immediate Recommendation

Do not scale to 20 cases yet.

First implement Phase A metric fixes. The current 2-case results are good enough to prove the pipeline works, but scaling before fixing RIMS, no-evidence-gate, and richer-evidence specificity would generate results that need to be rerun.
