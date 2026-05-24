# ESWA STPA-HF human annotation guide

## 1. Purpose

This guide defines the human annotation task for the ESWA paper. Annotators label STPA-HF safety-analysis judgments under evidence constraints.

Annotators do not label the true accident cause. Annotators do not infer true driver cognition. Annotators do not fill missing HMI evidence from the outcome.

The annotation target is:

> Given the reported/derived/not_reported evidence in the functional case, what safety-analysis claim is supportable under STPA-HF?

## 2. Inputs shown to annotators

Each annotation packet should include:

- case ID;
- source dataset and source regime;
- raw source summary or narrative;
- ENV / ACTOR / CAR / HMI / CABIN evidence slots;
- provenance for each slot: reported, derived, not_reported, counterfactual;
- missingness policy;
- no model output.

Do not show full-system, baseline, or counterfactual model predictions during gold labeling.

## 3. Main labels

### boundary_label

Choose one:

- `supported_monitoring`
- `contingent_readiness`
- `not_supported_transfer`
- `insufficient_information`

Decision rules:

- Use `supported_monitoring` only when ADS support/within-capability feedback is source-supported and no reported transition/intervention pressure exists.
- Use `contingent_readiness` when ADS operation is reported and the scenario creates preparation pressure, but there is no sufficient source evidence for a required takeover/unsupported transfer.
- Use `not_supported_transfer` when there is explicit source evidence of disengagement, takeover demand, driver/operator intervention, AV-system disengagement, support withdrawal, or transfer requirement.
- Use `insufficient_information` when even the functional scenario is too sparse to choose a boundary.

### update_vulnerability

Choose one:

- `missed_feedback`
- `ambiguous_feedback`
- `misinterpreted_feedback`
- `none`
- `insufficient_information`

Decision rules:

- `missed_feedback`: evidence suggests a relevant cue or condition may not have been detected/acted upon, but do not infer driver inattention without evidence.
- `ambiguous_feedback`: reported evidence suggests uncertainty, degraded support, unclear actor behavior, or unclear transition conditions.
- `misinterpreted_feedback`: reported evidence suggests the operator/system may have interpreted a boundary cue incorrectly.
- `none`: no source-supported update vulnerability is identifiable.
- `insufficient_information`: too little evidence to choose.

### dominant_uca

Choose a UCA consistent with the boundary:

Supported monitoring:

- `UCA-SM-1`: over-reliance while ADS support is degraded.
- `UCA-SM-2`: monitoring omission at boundary warning.

Contingent readiness:

- `UCA-CR-1`: late readiness formation.
- `UCA-CR-2`: premature readiness from misread boundary.
- `UCA-CR-3`: missed readiness under degraded support.

Not supported transfer:

- `UCA-NS-1`: takeover omission.
- `UCA-NS-2`: late takeover execution.
- `UCA-NS-3`: wrong-duration takeover correction.

Use `insufficient_information` if no UCA can be supported.

### active_uca_set

List all plausible UCA IDs supported by the same boundary. The dominant UCA must be in this set unless the label is `insufficient_information`.

## 4. Evidence labels

### supporting_evidence_ids

Annotators should cite the most important evidence IDs or field paths. If evidence IDs are unavailable in the packet, cite field paths, such as:

- `CAR.automation_context`
- `CAR.reported_intervention`
- `CAR.reported_system_issue`
- `HMI.mode_state_display`
- `ACTOR.primary_type`
- `ENV.road_geometry`

### insufficient_information_flags

Use flags when missing evidence blocks a stronger claim:

- `missing_hmi_mode_state`
- `missing_hmi_capability_boundary`
- `missing_hmi_time_budget`
- `missing_hmi_acknowledgement`
- `missing_driver_state`
- `missing_reported_intervention`
- `missing_reported_system_issue`
- `missing_ads_confidence`
- `missing_handover_time_budget`

### blocked_stronger_claims

Annotate which stronger claims are blocked by missing evidence:

- `blocked_not_supported_transfer`
- `blocked_supported_monitoring`
- `blocked_specific_driver_vulnerability`
- `blocked_specific_ads_failure_mode`

## 5. Source-regime rules

### NHTSA SGO crash/collision cases

These often report crash, ADS involvement, actor, road, lighting, and speed/deceleration. They often do not report HMI, driver state, intervention, or ADS internal state.

Default tendency:

- Do not label `not_supported_transfer` from crash alone.
- Use `contingent_readiness` when ADS context plus actor/road uncertainty creates preparation pressure.

### CA DMV collision augmented cases

These are third-party structured records derived from CA DMV collision PDFs. They increase scene diversity but are not official DMV CSV ground truth.

Default tendency:

- Treat as collision scenario seeds.
- Do not infer HMI or takeover failure unless explicitly reported.

### CA DMV disengagement official cases

These report disengagement initiation and disengagement facts. They often support stronger transfer/intervention boundary claims.

Default tendency:

- If `DISENGAGEMENT INITIATED BY` reports Test Driver, Remote Operator, AV System, retrieval, or passenger, `not_supported_transfer` is often supportable.
- Choose UCA based on whether the description supports omission, lateness, or wrong-duration correction. If not clear, prefer `UCA-NS-1` for a transfer-required condition with insufficient action detail.

## 6. Output schema

Each annotator should output JSONL rows:

```json
{
  "case_id": "...",
  "annotator_id": "A1",
  "label_scope": "human_gold_candidate",
  "boundary_label": "contingent_readiness",
  "update_vulnerability": "ambiguous_feedback",
  "dominant_uca": "UCA-CR-3",
  "active_uca_set": ["UCA-CR-3"],
  "supporting_evidence_ids": ["CAR.automation_context", "ACTOR.primary_type"],
  "insufficient_information_flags": ["missing_hmi_time_budget"],
  "blocked_stronger_claims": ["blocked_not_supported_transfer"],
  "rationale_short": "Crash/collision context creates readiness pressure, but no reported takeover demand or intervention evidence supports not_supported_transfer."
}
```

## 7. AI-pilot labels

AI-pilot labels may be used only to test the pipeline and annotation interface.

They must be marked:

```json
"label_scope": "ai_pilot_not_publication_gold"
```

They cannot be reported as human-gold results in the paper.

