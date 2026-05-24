#!/usr/bin/env bash
# =============================================================================
# Paper-facing STPA-HF ESWA pipeline
#
# Default mode is audit-only: it freezes paper_v1 metadata and regenerates
# non-LLM outputs from the current stable inputs/results. Set RUN_LLM=1 to
# run full-system, baseline, and counterfactual LLM experiments into paper_v1.
# =============================================================================
set -euo pipefail
cd "$(dirname "$0")"

ENGINE="python stpa_hf_dan_eswa_engine_final.py"

ALL_CASES="${ALL_CASES:-data/cases/external_cases_v3.jsonl}"
PAPER_CASES="${PAPER_CASES:-data/cases/verify_5.jsonl}"
PAPER_ROOT="${PAPER_ROOT:-results/paper_v1}"
RUN_LLM="${RUN_LLM:-0}"

EXISTING_BUNDLES="${EXISTING_BUNDLES:-results/verify/bundles}"
EXISTING_BASELINE_SUITE="${EXISTING_BASELINE_SUITE:-results/verify/baseline_suite}"
EXISTING_CF_BUNDLES="${EXISTING_CF_BUNDLES:-results/verify/cf_bundles_v2}"
EXISTING_CF_SPECS="${EXISTING_CF_SPECS:-results/verify/cf_specs.jsonl}"

mkdir -p "$PAPER_ROOT"/{table1,annotation_packets,audit,feedback_gaps,requirements,cf_eval}

echo "Phase 1: freeze Table 1 missingness profile from $ALL_CASES"
$ENGINE missingness-profile \
  --cases "$ALL_CASES" \
  --out "$PAPER_ROOT/table1/missingness_profile"

echo "Phase 2: export paper annotation packets from $PAPER_CASES"
$ENGINE export-annotation-packets \
  --cases "$PAPER_CASES" \
  --out "$PAPER_ROOT/annotation_packets" \
  --csv "$PAPER_ROOT/annotation_packets/annotation_sheet.csv"

if [[ "$RUN_LLM" == "1" ]]; then
  echo "Phase 3: run LLM full system and baselines into paper_v1"
  $ENGINE run \
    --cases "$PAPER_CASES" \
    --out "$PAPER_ROOT/bundles"

  $ENGINE baseline-suite \
    --cases "$PAPER_CASES" \
    --out "$PAPER_ROOT/baseline_suite"

  $ENGINE generate-cf-specs \
    --cases "$PAPER_CASES" \
    --out "$PAPER_ROOT/cf_specs.jsonl"

  $ENGINE generate-counterfactual \
    --cases "$PAPER_CASES" \
    --specs "$PAPER_ROOT/cf_specs.jsonl" \
    --out "$PAPER_ROOT/cf_cases.jsonl"

  $ENGINE run \
    --cases "$PAPER_ROOT/cf_cases.jsonl" \
    --out "$PAPER_ROOT/cf_bundles"

  $ENGINE counterfactual-eval \
    --base-bundle-dir "$PAPER_ROOT/bundles" \
    --cf-bundle-dir "$PAPER_ROOT/cf_bundles" \
    --specs "$PAPER_ROOT/cf_specs.jsonl" \
    --out "$PAPER_ROOT/cf_eval"

  BUNDLES="$PAPER_ROOT/bundles"
  BASELINE_SUITE="$PAPER_ROOT/baseline_suite"
  CF_REPORT="$PAPER_ROOT/cf_eval/counterfactual_directional_consistency.json"
else
  echo "Phase 3: audit-only mode; reusing stable verify LLM outputs"
  BUNDLES="$EXISTING_BUNDLES"
  BASELINE_SUITE="$EXISTING_BASELINE_SUITE"
  CF_REPORT="$PAPER_ROOT/cf_eval/counterfactual_directional_consistency.json"
  $ENGINE counterfactual-eval \
    --base-bundle-dir "$EXISTING_BUNDLES" \
    --cf-bundle-dir "$EXISTING_CF_BUNDLES" \
    --specs "$EXISTING_CF_SPECS" \
    --out "$PAPER_ROOT/cf_eval"
fi

echo "Phase 4: evidence audit, feedback gaps, and requirement candidates"
$ENGINE evidence-audit \
  --bundle-dir "$BUNDLES" \
  --out "$PAPER_ROOT/audit/evidence_support_audit"

$ENGINE feedback-gap-report \
  --bundle-dir "$BUNDLES" \
  --out "$PAPER_ROOT/feedback_gaps"

$ENGINE requirement-candidates \
  --gap-report "$PAPER_ROOT/feedback_gaps/feedback_gap_report.json" \
  --out "$PAPER_ROOT/requirements"

echo "Phase 5: paper manifest"
$ENGINE paper-manifest \
  --out "$PAPER_ROOT/paper_result_manifest.json" \
  --cases "$PAPER_CASES" \
  --bundle-dir "$BUNDLES" \
  --baseline-dir "$BASELINE_SUITE" \
  --cf-report "$CF_REPORT" \
  --missingness-profile "$PAPER_ROOT/table1/missingness_profile/dataset_missingness_profile.json" \
  --evidence-audit "$PAPER_ROOT/audit/evidence_support_audit/evidence_support_audit.json" \
  --feedback-gap-report "$PAPER_ROOT/feedback_gaps/feedback_gap_report.json" \
  --requirement-candidates "$PAPER_ROOT/requirements/requirement_candidates.json"

echo "Paper pipeline complete: $PAPER_ROOT"
