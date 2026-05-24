#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CASE_FILE="${CASE_FILE:-$ROOT_DIR/data/cases/paper_10_mixed_ca_5collision_5disengagement.jsonl}"
ADJ_FILE="${ADJ_FILE:-$ROOT_DIR/data/cases/paper_10_mixed_ca_5collision_5disengagement_role_adjudicated.jsonl}"
OUT_ROOT="${OUT_ROOT:-$ROOT_DIR/results/aap_v245_release}"
MODEL="${OPENAI_MODEL:-qwen-max-latest}"
BASE_URL="${OPENAI_BASE_URL:-https://dashscope.aliyuncs.com/compatible-mode/v1}"
TIMEOUT="${OPENAI_TIMEOUT_S:-240}"

RUN_BASELINE_SUITE="${RUN_BASELINE_SUITE:-0}"
RUN_ABLATION_SUITE="${RUN_ABLATION_SUITE:-0}"
RUN_COUNTERFACTUAL="${RUN_COUNTERFACTUAL:-0}"
RUN_PM_MEDIATION="${RUN_PM_MEDIATION:-0}"

mkdir -p "$OUT_ROOT"

export OPENAI_API_KEY="${OPENAI_API_KEY:?OPENAI_API_KEY must be set}"
export OPENAI_BASE_URL="$BASE_URL"
export OPENAI_MODEL="$MODEL"
export OPENAI_TIMEOUT_S="$TIMEOUT"

cd "$ROOT_DIR"

echo "[1/7] role disambiguation"
python .\stpa_hf_dan_eswa_engine_final.py role-disambiguate-cases \
  --cases "$CASE_FILE" \
  --out-cases "$ADJ_FILE" \
  --out-report "$OUT_ROOT/role_disambiguation_report.json" \
  --temperature 0

echo "[2/7] full replay"
python .\stpa_hf_dan_eswa_engine_final.py run \
  --cases "$ADJ_FILE" \
  --out "$OUT_ROOT/full_replay" \
  --temperature 0 \
  --resume

echo "[3/7] tabletop replay audit"
python .\stpa_hf_dan_eswa_engine_final.py tabletop-replay-audit \
  --bundle-dir "$OUT_ROOT/full_replay" \
  --out "$OUT_ROOT/replay_audit"

echo "[4/7] evidence audit"
python .\stpa_hf_dan_eswa_engine_final.py evidence-audit \
  --bundle-dir "$OUT_ROOT/full_replay" \
  --out "$OUT_ROOT/evidence_audit"

echo "[5/7] feedback gaps and requirement candidates"
python .\stpa_hf_dan_eswa_engine_final.py feedback-gap-report \
  --bundle-dir "$OUT_ROOT/full_replay" \
  --out "$OUT_ROOT/feedback_gaps"
python .\stpa_hf_dan_eswa_engine_final.py requirement-candidates \
  --gap-report "$OUT_ROOT/feedback_gaps/feedback_gap_report.json" \
  --out "$OUT_ROOT/requirement_candidates"

echo "[6/7] semantic warning audit"
python .\stpa_hf_dan_eswa_engine_final.py semantic-warning-audit \
  --bundle-dir "$OUT_ROOT/full_replay" \
  --evidence-audit "$OUT_ROOT/evidence_audit/evidence_support_audit.json" \
  --out "$OUT_ROOT/semantic_warning_audit" \
  --temperature 0

if [[ "$RUN_BASELINE_SUITE" != "0" ]]; then
  echo "[optional] baseline suite"
  python .\stpa_hf_dan_eswa_engine_final.py baseline-suite \
    --cases "$ADJ_FILE" \
    --out "$OUT_ROOT/baseline_suite" \
    --temperature 0 \
    --resume
fi

if [[ "$RUN_ABLATION_SUITE" != "0" ]]; then
  echo "[optional] ablation suite"
  python .\stpa_hf_dan_eswa_engine_final.py run-ablation-suite \
    --cases "$ADJ_FILE" \
    --out "$OUT_ROOT/ablation_suite" \
    --full-bundle-dir "$OUT_ROOT/full_replay" \
    --temperature 0 \
    --resume
fi

if [[ "$RUN_COUNTERFACTUAL" != "0" ]]; then
  echo "[optional] counterfactual replay"
  python .\stpa_hf_dan_eswa_engine_final.py generate-cf-specs \
    --cases "$ADJ_FILE" \
    --out "$OUT_ROOT/counterfactual_specs.jsonl"
  python .\stpa_hf_dan_eswa_engine_final.py generate-counterfactual \
    --cases "$ADJ_FILE" \
    --specs "$OUT_ROOT/counterfactual_specs.jsonl" \
    --out "$OUT_ROOT/counterfactual_cases.jsonl"
  python .\stpa_hf_dan_eswa_engine_final.py run \
    --cases "$OUT_ROOT/counterfactual_cases.jsonl" \
    --out "$OUT_ROOT/counterfactual_full" \
    --temperature 0 \
    --resume
  python .\stpa_hf_dan_eswa_engine_final.py counterfactual-eval \
    --base-bundle-dir "$OUT_ROOT/full_replay" \
    --cf-bundle-dir "$OUT_ROOT/counterfactual_full" \
    --specs "$OUT_ROOT/counterfactual_specs.jsonl" \
    --out "$OUT_ROOT/counterfactual_eval"
fi

if [[ "$RUN_PM_MEDIATION" != "0" ]]; then
  echo "[optional] pm mediation comparison"
  python .\stpa_hf_dan_eswa_engine_final.py pm-mediation-comparison \
    --out "$OUT_ROOT/pm_mediation_comparison.json" \
    --full-bundle-dir "$OUT_ROOT/full_replay" \
    --baseline-suite-dir "$OUT_ROOT/baseline_suite"
fi

echo "done"

