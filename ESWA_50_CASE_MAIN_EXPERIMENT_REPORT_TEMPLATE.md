# ESWA 50-case Main Experiment Report Template

## 1. Alignment With Paper Guidance

This run follows `ESWA_CHINESE_NARRATIVE_AND_NEXT_PLAN.md`.

Public reports are treated as real high-risk functional scenario seeds, not complete causal ground truth. Base-case analysis preserves missing HMI/driver/internal ADS evidence. Counterfactual HMI cues are used only for feedback-boundary sensitivity testing.

## 2. Dataset

- Input case file:
- NHTSA SGO official crash/collision:
- CA DMV collision augmented:
- CA DMV official disengagement:
- Label leakage violations:
- Missingness mean/median/min/max:

## 3. Repair Checks

- Unsupported strong-boundary warnings:
- Outcome-only escalation warnings:
- Not-reported boundary support warnings:
- Warning case IDs:

## 4. Full System

- Cases:
- Schema valid:
- Boundary distribution:
- UCA distribution:
- Vulnerability distribution:

## 5. Baselines and Ablations

- Direct baseline:
- Generic CoT:
- Full-system rerun inside baseline suite:
- With vulnerability priority:
- No-update:

## 6. Evidence Audit

- Mean invalid evidence IDs:
- UCA catalog consistency:
- Claims without supporting evidence:
- Strong-boundary evidence strength:

## 7. Feedback Gaps and Evidence Requirements

- Total gaps:
- Gaps by category:
- Gaps by source regime:
- Evidence requirement candidates:
- Taxonomy summary files:

## 8. Counterfactual HMI Sensitivity

- CF specs:
- CF bundles valid:
- Directional consistency overall:
- Directional consistency by template:
- Directional consistency by source regime:
- Mismatch cases:

## 9. Expert-0 Preview Labels

These are not publication human-gold labels.

- Labels:
- Boundary distribution:
- Cases needing human adjudication:
- Preview evaluation:

## 10. Remaining Problems and Next Plan

- Problem 1:
- Problem 2:
- Problem 3:

