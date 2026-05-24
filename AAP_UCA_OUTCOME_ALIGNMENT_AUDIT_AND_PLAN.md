# AAP UCA-Outcome Alignment Audit and Code Revision Plan

Date: 2026-05-12

## 1. Paper-Level Decision

The paper's UCA logic is fixed as follows:

```text
accident outcome
-> compatibility constraint
not
-> direct UCA evidence
```

Collision, crash, disengagement, or takeover is the reported terminal event. It is not itself an unsafe control action. In the proposed AAP narrative, UCA is an evidence-admissible driver control-action hypothesis located between the STPA-HF driver process model and the reported outcome.

The correct reasoning chain is:

```text
source accident text
-> evidence objects with provenance
-> CPS / CPB / OPS / OPB driver process-model hypotheses
-> process-model formation/update analysis
-> other action-selection factors
-> driver control-action selection hypothesis
-> candidate UCA in context
-> outcome compatibility gate
-> ranked explanatory pathway
```

The system must not infer true accident cause, true driver cognition, or takeover failure from the outcome alone.

## 2. Current Code Audit

Main file audited:

```text
stpa_hf_dan_eswa_engine_final.py
```

Current schema after implementation:

```text
SCHEMA_VERSION = stpa_hf_reasoning_graph_v2.2
```

### 2.1 Already Aligned With the Narrative

The current code already implements several important safeguards.

1. Evidence provenance is explicit.

The engine distinguishes:

```text
reported
derived
not_reported
reported_narrative
assumed_for_counterfactual
```

2. The shared prompt contains the right red lines.

It tells the model:

```text
Do not infer HMI state, driver mental state, or internal ADS variables when they are not reported.
Do not infer takeover failure from crash/collision outcome alone.
Treat not_reported as absence of source evidence, not evidence of absence.
```

3. The process-model layer now has four explicit STPA-HF dimensions.

The code requires:

```text
CPS
CPB
OPS
OPB
```

and validates that every case has all four PM context nodes.

4. Update-process validation is strict.

The validator correctly prevents:

```text
not_reported -> observed_update_vulnerability
```

If an observed vulnerability is non-none, it must cite positive evidence, and the cited evidence cannot be `not_reported`.

5. The current pathway system already supports multi-pathway output.

Each case can output:

```text
admissible
weakly_supported
blocked
```

and LLM judge is not allowed to upgrade deterministic blocked pathways.

6. The reasoning graph already contains an outcome node.

This supports the paper's graph-based narrative, but the outcome node still needs a stricter role definition in the deterministic pathway gates.

### 2.2 Main Mismatches

#### Mismatch 1: UCA catalog is still boundary-scoped

Current behavior:

```text
UCA_CATALOG = {
  supported_monitoring: [...],
  contingent_readiness: [...],
  not_supported_transfer: [...]
}
```

and UCA validation restricts candidates to:

```text
UCA_CATALOG.get(committed_state, [])
```

This means the selected boundary controls which UCAs are allowed to appear.

Why this conflicts with the new narrative:

The boundary should be a claim-strength / commitment-boundary node. It should not pre-decide the UCA search space. UCA should be centered on driver control actions:

```text
monitor / prepare / takeover / brake / steer / safe stop / no action reported
```

Then each candidate UCA should be tested against:

```text
PM variables
update process
other factors
action evidence
unsafe context
outcome compatibility
```

Required change:

Flatten or re-index the UCA catalog into a driver-control-action catalog, then let boundary act as a contextual gate rather than a catalog filter.

#### Mismatch 2: Outcome compatibility is mostly judge-scored, not deterministically gated

Current behavior:

The LLM pathway judge scores `outcome_compatibility`, and the pathway object includes `reported_outcome`, but the deterministic gates are:

```text
G1 UCA context
G2 PM variable
G3 PM flaw
G4 update process
G5 action selection
G6 evidence admissibility
```

There is no deterministic outcome-compatibility gate.

Why this matters:

The paper's new claim depends on separating:

```text
outcome as compatibility constraint
```

from:

```text
outcome as UCA evidence
```

If outcome compatibility is only judge-scored, the code does not visibly enforce the central methodological claim.

Required change:

Add:

```text
G7_outcome_compatibility_gate
```

The gate must check:

```text
Does this UCA/action pathway plausibly terminate in the reported collision/disengagement/intervention outcome?
```

but it must also enforce:

```text
Outcome compatibility cannot upgrade blocked UCA evidence to admissible.
Outcome compatibility cannot activate a UCA.
```

#### Mismatch 3: The current UCA labels are still too boundary-language-heavy

Some UCA IDs encode boundary names:

```text
UCA-SM-*
UCA-CR-*
UCA-NS-*
```

This is understandable historically, but it weakens the paper's new driver-centered argument.

Required change:

Introduce publication-facing UCA IDs such as:

```text
UCA-H-1: monitoring not provided when required
UCA-H-2: takeover/intervention not provided when required
UCA-H-3: takeover/intervention provided too late
UCA-H-4: manual control input provided when not appropriate
UCA-H-5: manual control input applied with wrong duration or magnitude
UCA-H-6: safe-stop / fallback action not selected when required
```

Old IDs may be mapped internally during transition, but the paper-facing output should use driver-centered UCA IDs.

#### Mismatch 4: Boundary validation may over-force transfer states in intervention cases

Current behavior:

The validator requires `not_supported_transfer` to cite explicit transition/intervention/support-withdrawal evidence. That is good.

However, it also rejects `contingent_readiness` when explicit intervention evidence is cited. This can make some disengagement cases look like transfer-failure territory even when the text says the driver/operator safely intervened.

Required change:

Distinguish:

```text
reported intervention as outcome/transition evidence
```

from:

```text
reported intervention failure as unsafe action evidence
```

Safe intervention should support a safe or weak pathway, and should block failure pathways unless the text reports lateness, inability, collision after intervention, or wrong manual action.

#### Mismatch 5: UCA activation still depends too much on the selected boundary

Current behavior:

The UCA prompt receives:

```text
committed_fsm_state
uca_catalog: ordered_uca_catalog(committed_state, ...)
```

This makes the UCA stage downstream of boundary selection.

Required change:

The UCA stage should receive:

```text
full_driver_uca_catalog
committed_boundary
action_selection_nodes
reported_outcome
```

and should classify every relevant candidate as:

```text
activated
suppressed
blocked
```

The selected boundary can constrain claim strength, but cannot hide candidate UCAs from analysis.

#### Mismatch 6: HMI injection should rerun the whole chain with the new outcome gate

The current plan already says HMI injection should rerun:

```text
HMI -> PM -> update -> action -> UCA -> pathway
```

After adding outcome compatibility, injection must also report:

```text
how injected HMI changes outcome-compatible UCA pathways
```

not merely whether the boundary changes.

## 3. Revised Code Plan

### Phase A: UCA Catalog Refactor

1. Add a flat driver-centered UCA catalog:

```python
DRIVER_UCA_CATALOG = [
  UCA-H-1 ... UCA-H-6
]
```

Each entry must contain:

```text
uca_id
controller
control_action
stpa_uca_type
unsafe_context_template
minimum_required_evidence
outcome_compatibility_patterns
blocked_if_only_outcome
```

2. Add a backward-compatible mapping:

```python
LEGACY_UCA_ID_MAP = {
  "UCA-CR-1": "UCA-H-3",
  ...
}
```

3. Replace `ordered_uca_catalog(committed_state, ...)` in the main run path with:

```python
ordered_driver_uca_catalog(boundary, update_process, action_selection, reported_outcome)
```

This function may rank candidate order but must not remove candidates solely because of boundary.

### Phase B: UCA Context Prompt and Validator Refactor

1. Update `UCA_CONTEXT_CLASSIFICATION_PROMPT`.

The prompt must state:

```text
Classify candidate driver UCAs from the full driver-centered catalog.
The committed boundary is context, not the catalog filter.
The reported outcome is compatibility information, not activation evidence.
```

2. Update `validate_uca_context_classification`.

Remove:

```python
state_uca_ids = {u["uca_id"] for u in UCA_CATALOG.get(committed_state, [])}
```

Replace with:

```python
driver_uca_ids = {u["uca_id"] for u in DRIVER_UCA_CATALOG}
```

3. Add a validator rule:

```text
An activated UCA cannot cite only event_type / collision / disengagement outcome evidence.
```

4. Add a validator rule:

```text
If supporting evidence is only not_reported or outcome-only, classification must be blocked or suppressed.
```

### Phase C: Deterministic Outcome Gate

1. Add:

```python
def evaluate_outcome_compatibility_gate(pathway, reported_outcome, evidence_by_id): ...
```

2. Add `G7_outcome_compatibility_gate` to every pathway:

```text
pass: action/UCA/context is compatible with outcome and has independent action-context evidence
weak: compatible with outcome but missing action/update evidence
fail: contradicted by safe intervention, no conflict outcome, or outcome-only inference
```

3. Hard rule:

```text
G7 can lower or rank pathways, but cannot activate UCA and cannot upgrade blocked evidence.
```

### Phase D: Safe Intervention and Disengagement Semantics

1. Split reported intervention into three types:

```text
safe_intervention
late_or_failed_intervention
intervention_reported_but_quality_unknown
```

2. Safe intervention should block failure UCAs unless there is explicit late/wrong/failed evidence.

3. Disengagement alone should not equal driver failure.

4. Collision after disengagement may support compatibility with late/wrong/omitted intervention only if the text provides timing or action evidence beyond outcome.

### Phase E: Reasoning Graph Output Revision

Each pathway must show:

```text
evidence -> PM -> update -> other factors -> action selection -> UCA candidate -> outcome compatibility -> score/status
```

Add to each pathway:

```text
outcome_compatibility_block
outcome_used_as
outcome_cannot_support
activation_evidence_type
```

Allowed values:

```text
outcome_used_as = compatibility_constraint | contradiction | not_used
activation_evidence_type = action_context_evidence | weak_context_only | outcome_only_blocked
```

### Phase F: Audit Expansion

Extend `evidence-audit` to report:

```text
outcome_only_uca_activation_count
uca_catalog_boundary_filtering_count
safe_intervention_failure_pathway_block_count
mean_pathways_per_case
pathway_status_distribution
G7_outcome_gate_distribution
```

The target values for smoke tests:

```text
outcome_only_uca_activation_count = 0
not_reported_used_as_observed_update_fact_count = 0
invalid_evidence_id_count = 0
schema_valid_rate = 1.0
```

### Phase G: Smoke and Case Execution

After code changes:

1. Run 1-case smoke.

```powershell
python .\stpa_hf_dan_eswa_engine_final.py run `
  --cases .\data\cases\paper_30_mixed_nhtsa10_ca_collision10_ca_disengagement10.jsonl `
  --out .\results\aap_uca_outcome_smoke1 `
  --case-limit 1
```

2. Run audit.

```powershell
python .\stpa_hf_dan_eswa_engine_final.py evidence-audit `
  --bundle-dir .\results\aap_uca_outcome_smoke1 `
  --out .\results\aap_uca_outcome_smoke1_audit
```

3. Run 5-case smoke.

```powershell
python .\stpa_hf_dan_eswa_engine_final.py run `
  --cases .\data\cases\paper_30_mixed_nhtsa10_ca_collision10_ca_disengagement10.jsonl `
  --out .\results\aap_uca_outcome_smoke5 `
  --case-limit 5
```

4. If stable, run 30 cases.

```powershell
python .\stpa_hf_dan_eswa_engine_final.py run `
  --cases .\data\cases\paper_30_mixed_nhtsa10_ca_collision10_ca_disengagement10.jsonl `
  --out .\results\aap_uca_outcome_30
```

## 4. Expected Output Pattern After Revision

For a collision case, the desired result is not:

```text
collision -> driver failed takeover
```

The desired result is:

```text
reported_outcome: collision
UCA-H-2 takeover not provided when required: blocked or weakly_supported
UCA-H-3 takeover too late: blocked or weakly_supported
UCA-H-5 wrong manual input: blocked unless manual action evidence exists
no_activated_uca_pathway: weakly_supported when action evidence is missing
```

For a disengagement case, the desired result is not:

```text
disengagement -> unsafe driver action
```

The desired result is:

```text
reported_outcome: disengagement / intervention
safe intervention detected: failure pathways blocked
late/wrong/omitted intervention pathways only admissible if timing/action evidence exists
```

## 5. Paper Method Spine After Alignment

The method section should describe four modules:

1. Evidence-admissible accident text representation.

This module converts accident/disengagement text into source-cited evidence objects and explicitly tracks missing evidence.

2. STPA-HF driver process-model graph.

This module constructs CPS, CPB, OPS, and OPB hypotheses as process-model variables, not as ground-truth driver psychology.

3. Candidate-first UCA pathway generation.

This module treats UCA as driver control-action hypotheses and checks each hypothesis against process-model update, other action-selection factors, and source evidence.

4. Outcome-compatible pathway ranking.

This module uses collision/disengagement/takeover outcome only as a compatibility constraint for ranking and blocking pathways, never as direct UCA activation evidence.

## 6. Reviewer-Facing Claim Boundary

The paper can claim:

```text
The framework generates evidence-admissible, STPA-HF-structured, ranked driver-centered explanatory pathways from sparse AV accident/takeover reports.
```

The paper cannot claim:

```text
The framework reconstructs the true accident cause.
The framework infers the true driver mental state.
The framework proves HMI caused or prevented the accident.
The framework proves that a reported collision equals takeover failure.
```

## 7. Current Alignment Score

After the v2.2 revision:

```text
Narrative-code alignment: 8.8 / 10
```

Reason:

The v2.2 engine now uses a driver-centered UCA catalog, prevents legacy boundary-scoped UCA IDs from paper-facing outputs, adds a deterministic G7 outcome-compatibility gate, and separates terminal outcome evidence from driver action/state evidence for UCA activation.

Remaining target after full experimental validation:

```text
9.0 / 10
```

Remaining limitation even after revision:

Sparse accident text will still limit admissible claims. That limitation is acceptable only if the paper consistently positions the output as ranked safety-analysis pathways rather than accident reconstruction.
