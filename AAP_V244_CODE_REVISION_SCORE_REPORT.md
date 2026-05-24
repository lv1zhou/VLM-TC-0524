# AAP V2.4.4 Code Revision Score Report

Date: 2026-05-16

## 1. Revision Scope

This revision implements the metric/audit tightening requested after `AAP_V2_CURRENT_RESULTS_NARRATIVE_GAP_AND_NEXT_PLAN.md`.

Main code file:

- `stpa_hf_dan_eswa_engine_final.py`

Schema is now:

- `driver_pm_tabletop_replay_v2.4.4`

## 2. Implemented Changes

### 2.1 Evidence audit claim separation

The evidence audit now separates:

- `positive_claims_without_supporting_evidence_count`
- `negative_status_claims_without_supporting_evidence_count`
- `gap_claims_without_positive_support_count`
- `claim_support_type_distribution`
- `positive_unsupported_claim_warning_case_ids`

This fixes the previous issue where `observed_update_vulnerability = none` and `uca_activation_status = no_activated_uca` were mixed with unsupported positive claims.

### 2.2 no-evidence-gate diagnostic projection

The `no_evidence_gate` ablation now reports:

- `would_promote_blocked_pathway_count`
- `would_promote_outcome_only_pathway_count`
- `would_promote_no_action_evidence_pathway_count`
- `would_promote_not_reported_supported_pathway_count`
- `would_promote_any_risk_pathway_count`
- `promoted_pathway_examples`

This makes the ablation more useful for the paper claim:

> evidence gates are necessary because removing them would promote blocked or action-unsupported pathways.

### 2.3 Requirement candidate criticality

Requirement candidates now include:

- `requirement_criticality_class`
- `requirement_triggering_pathway_ids`
- `requirement_blocks_claims`
- `requirement_priority_reason`
- `requirement_specificity_level`

Criticality classes:

- `claim_blocking`
- `pathway_critical`
- `global_missing_logging_field`
- `lower_priority_completeness`

### 2.4 Richer-evidence structured metrics

The old text-length PM specificity metric is now explicitly marked as deprecated.

New structured metrics include:

- `reported_update_source_count`
- `direct_pm_node_support_count`
- `missing_pm_evidence_count`
- `blocked_pm_claim_count`
- `pathway_status_entropy`
- `top_pathway_margin`
- `pathway_status_upgrade_count`
- `structured_specificity_increased`

This fixes the prior invalid conclusion where richer evidence could appear less specific merely because the explanation text became shorter.

### 2.5 Strict Expert-0 and RIMS metrics

Expert-0 v2 now uses a strict preview mode:

- it scores pathway admissibility from packet evidence;
- it does not automatically copy the system top-ranked pathway;
- it can output no top pathway if no pathway reaches the preview admissibility threshold.

RIMS now includes:

- Top-1 match;
- Top-3 recall;
- Top-3 Jaccard;
- ranking correlation;
- pathway distribution distance;
- blocked-claim precision/recall;
- requirement relevance.

This still remains protocol-debug evidence, not human-gold validation.

## 3. Verification Runs

### 3.1 Syntax

Command:

```powershell
python -m py_compile .\STPAHF\stpa_hf_dan_eswa_engine_final.py
```

Result:

- passed.

### 3.2 Evidence audit on 10-case V2 results

Command:

```powershell
python .\stpa_hf_dan_eswa_engine_final.py evidence-audit --bundle-dir .\results\aap_v243_10case_full --out .\results\aap_v244_codecheck_10case_audit
```

Key result:

| Metric | Value |
|---|---:|
| num cases | 10 |
| invalid evidence ID mean | 0 |
| catalog consistency | 1.0 |
| mean claims without support | 1.8 |
| mean positive claims without support | 0 |
| mean negative status claims without support | 0.8 |
| mean gap claims without positive support | 1.0 |
| positive unsupported warning case IDs | 0 |
| outcome-only UCA activation | 0 |
| not_reported used as observed update fact | 0 |
| HMI absence inferred from nonreporting | 0 |

Interpretation:

The earlier unsupported-claim warning is now correctly decomposed. There are no unsupported positive claims in the 10-case V2 run; the remaining unsupported rows are negative status or evidence-gap statements.

### 3.3 no-evidence-gate ablation on 2-case codecheck

Command:

```powershell
python .\stpa_hf_dan_eswa_engine_final.py run-ablation-suite --cases .\data\cases\aap_v22_20case_runset.jsonl --out .\results\aap_v244_codecheck_ablation_2case --case-limit 2 --resume --temperature 0
```

Key result:

| Condition | Outcome-only overreach | Complete chain | Mean promoted blocked pathways | Mean promoted no-action-evidence pathways |
|---|---:|---:|---:|---:|
| direct LLM | 2/2 | 0.0 | 0 | 0 |
| generic CoT | 2/2 | 0.0 | 0 | 0 |
| structured prompt only | 2/2 | 0.0 | 0 | 0 |
| no-update | 0/2 | 0.0 | 0 | 0 |
| no-evidence-gate | 0/2 | 1.0 | 5.5 | 6 |
| full replay | 0/2 | 1.0 | 0 | 0 |

Interpretation:

This is now much stronger for the paper. The old no-evidence-gate row was too weak; the new row shows exactly what the gate prevents: promotion of blocked and action-unsupported pathways.

### 3.4 Requirement candidates on 10-case V2 results

Commands:

```powershell
python .\stpa_hf_dan_eswa_engine_final.py feedback-gap-report --bundle-dir .\results\aap_v243_10case_full --out .\results\aap_v244_codecheck_10case_feedback_gaps
python .\stpa_hf_dan_eswa_engine_final.py requirement-candidates --gap-report .\results\aap_v244_codecheck_10case_feedback_gaps\feedback_gap_report.json --out .\results\aap_v244_codecheck_10case_requirements
```

Key result:

| Metric | Value |
|---|---:|
| feedback gaps | 120 |
| requirement candidates | 120 |
| claim_blocking requirements | 60 |
| global_missing_logging_field requirements | 60 |
| field_specific requirements | 120 |

Interpretation:

Requirement candidates are no longer only a flat checklist. They now distinguish claim-blocking fields from general recurring logging gaps.

### 3.5 Richer-evidence comparison

Command:

```powershell
python .\stpa_hf_dan_eswa_engine_final.py richer-evidence-compare --sparse-bundle-dir .\results\aap_v243_10case_full --richer-bundle-dir .\results\aap_v243_1case_hmi_cf_full --pair-map .\results\aap_v2_codecheck_richer_pair_map.jsonl --out .\results\aap_v244_codecheck_richer_compare
```

Key result:

| Metric | Value |
|---|---:|
| blocked claim reduction rate | 1.0 |
| missing requirement reduction rate | 1.0 |
| update source completeness increase rate | 1.0 |
| deprecated PM text-specificity increase rate | 0.0 |
| structured specificity increase rate | 1.0 |

Interpretation:

The richer-evidence story is now defensible: it narrows replay uncertainty structurally, even though text length does not increase.

### 3.6 Strict Expert-0 / RIMS protocol check

Commands:

```powershell
python .\stpa_hf_dan_eswa_engine_final.py export-expert-replay-packets --bundle-dir .\results\aap_v243_10case_full --out .\results\aap_v244_codecheck_expert_packets
python .\stpa_hf_dan_eswa_engine_final.py expert-preview-labels --packet-dir .\results\aap_v244_codecheck_expert_packets --out-labels .\results\aap_v244_codecheck_expert0_labels.jsonl --out-report .\results\aap_v244_codecheck_expert0_report.json
python .\stpa_hf_dan_eswa_engine_final.py replay-alignment-eval --bundle-dir .\results\aap_v243_10case_full --labels .\results\aap_v244_codecheck_expert0_labels.jsonl --out .\results\aap_v244_codecheck_replay_alignment
```

Key result:

| Metric | Value |
|---|---:|
| num evaluated | 10 |
| mean RIMS total | 1.0 |
| top1 match rate | 0.9 |
| mean top3 recall | 1.0 |
| mean top3 Jaccard | 0.4667 |
| mean ranking correlation | 0.7514 |
| mean pathway distribution distance | 0.2333 |

Interpretation:

This is better than the previous self-confirming RIMS = 1.0 everywhere. The top-1 match is no longer perfect, and Top-3 Jaccard/ranking correlation expose ranking-level differences. It is still not publication gold because Expert-0 is not an independent human annotator.

## 4. Updated Score

| Dimension | Before | After | Reason |
|---|---:|---:|---|
| Narrative-code alignment | 8.2 | 8.8 | Metrics now directly test evidence-bounded replay, PM mediation, and richer-evidence sensitivity |
| Audit integrity | 7.6 | 8.8 | Positive unsupported claims are separated from negative/gap claims |
| Ablation usefulness | 7.4 | 8.7 | no-evidence-gate now exposes promoted-risk counts |
| Requirement candidate utility | 7.2 | 8.4 | Requirement outputs now include criticality and claim-blocking status |
| RIMS protocol readiness | 6.8 | 7.8 | Strict Expert-0 reduces self-confirming behavior, but human labels remain required |
| Richer-evidence metric validity | 6.8 | 8.5 | Text-length specificity is deprecated and replaced with structured metrics |
| Overall code readiness for AAP V2 pilot | 8.2 | 8.9 | Ready for mixed 20-case V2.4.4 pilot after one remaining check |

## 5. Remaining Issues

1. Existing `aap_v243_10case_full` bundles do not yet contain the new requirement criticality fields inside `e*_tabletop_replay_package.json`, because those packages were generated before the v2.4.4 code change. New runs will include them.
2. The current verification reused 10 collision cases and 2 ablation cases. It confirms metric behavior but does not replace the required 20-case mixed pilot.
3. RIMS preview remains protocol-debug only. It should not be reported as human expert agreement.
4. The no-evidence-gate diagnostic now works, but it must be tested on mixed collision/disengagement data.
5. Some old internal names such as `commitment_boundary` still exist for backward compatibility. Paper-facing outputs should use `driver_replay_posture`.

## 6. Recommendation

The code is now close enough to run the next real experiment:

```text
20-case mixed pilot = 10 CA DMV collision + 10 CA DMV disengagement
```

Required run set:

1. full replay;
2. evidence audit;
3. tabletop replay audit;
4. feedback-gap report;
5. requirement candidates;
6. ablation suite;
7. expert packet export;
8. strict Expert-0 preview labels;
9. replay alignment eval;
10. 3-5 richer-evidence/HMI injection pairs.

Expected next score after mixed pilot:

- code-output alignment: 9.0+
- experiment readiness: 8.5+
- publication evidence strength: 8.2-8.5 before human labels

