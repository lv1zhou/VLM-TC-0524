#!/usr/bin/env bash
# =============================================================================
# STPA-HF ESWA Pipeline — Reproducible Execution Script
# Generated: 2026-04-27
# Engine:    stpa_hf_dan_eswa_engine_final.py
# Ingestion: external_case_ingestion_final.py
# LLM:       Qwen-max-latest via DashScope (OpenAI-compatible)
# =============================================================================
set -euo pipefail
cd "$(dirname "$0")"

ENGINE="python stpa_hf_dan_eswa_engine_final.py"
INGEST="python external_case_ingestion_final.py"

# Number of external cases for full/baseline/CF runs (adjust as needed)
N_CASES=30

echo "============================================"
echo "Phase 0: Create directory structure"
echo "============================================"
mkdir -p data/raw data/records data/cases data/annotation_packets
mkdir -p results/demo results/external results/table1 results/audit results/cf_eval

echo "============================================"
echo "Phase 1: Internal Demo Smoke Test"
echo "============================================"

# 1a. Generate demo cases + labels
$ENGINE demo-cases --out data/cases
echo "[1a] Demo cases generated"

# 1b. Audit — verify no label leakage
$ENGINE audit-case-input --cases data/cases/demo_cases.jsonl
echo "[1b] Audit passed"

# 1c. Run full system on demo cases
$ENGINE run --cases data/cases/demo_cases.jsonl --out results/demo/bundles
echo "[1c] Demo full system run complete"

# 1d. Evaluate against demo labels
$ENGINE eval --bundle-dir results/demo/bundles \
             --labels data/cases/demo_labels.jsonl \
             --out results/demo/eval_report.json
echo "[1d] Demo evaluation complete"

# 1e. Evidence audit
$ENGINE evidence-audit --bundle-dir results/demo/bundles \
                       --out results/demo/evidence_audit.json
echo "[1e] Demo evidence audit complete"

echo "============================================"
echo "Phase 2: NHTSA Data Download & Case Building"
echo "============================================"

# 2a. Download NHTSA SGO CSV (ADS + ADAS)
$INGEST download-official --out-dir data/raw --nhtsa-sgo
echo "[2a] NHTSA SGO CSV downloaded"

# 2b. Build functional cases from ADS CSV
$INGEST build-external-cases \
    --nhtsa-sgo-ads data/raw/nhtsa_sgo/SGO-2021-01_Incident_Reports_ADS.csv \
    --out data/cases/external_cases_v3.jsonl
echo "[2b] External cases built"

# 2b2. LLM narrative enrichment — fill not_reported ENV/ACTOR/CAR fields from Narrative
echo "[2b2] Narrative enrichment skipped for paper-facing v3 cases"

# 2c. Audit — verify no label leakage in enriched cases
$ENGINE audit-case-input --cases data/cases/external_cases_v3.jsonl
echo "[2c] External case audit passed"

# 2d. Stratified sampling (by ENV.visibility)
python -c "
import json, random
from collections import defaultdict
random.seed(42)
cases = [json.loads(l) for l in open('data/cases/external_cases_v3.jsonl')]
buckets = defaultdict(list)
for c in cases:
    ev = c['latent_events'][0]
    vis = ev.get('ENV',{}).get('visibility',{})
    v = vis.get('value','unknown') if isinstance(vis,dict) else vis
    buckets[v].append(c)
total = len(cases)
sampled = []
for v, b in sorted(buckets.items(), key=lambda x:-len(x[1])):
    n = max(1, round($N_CASES * len(b) / total))
    sampled.extend(random.sample(b, min(n, len(b))))
random.shuffle(sampled)
sampled = sampled[:$N_CASES]
with open('data/cases/external_cases_sample.jsonl','w') as f:
    for c in sampled:
        f.write(json.dumps(c, ensure_ascii=False)+'\n')
print(f'Sampled {len(sampled)} cases')
"
echo "[2d] Stratified sample created"

echo "============================================"
echo "Phase 3: Missingness Profile + Annotation Packets"
echo "============================================"

# 3a. Missingness profile (Table 1 data) — on ALL enriched cases
$ENGINE missingness-profile \
    --cases data/cases/external_cases_v3.jsonl \
    --out results/table1/missingness_profile
echo "[3a] Missingness profile generated"

# 3b. Annotation packets — on sampled cases
$ENGINE export-annotation-packets \
    --cases data/cases/external_cases_sample.jsonl \
    --out data/annotation_packets
echo "[3b] Annotation packets exported"

echo "============================================"
echo "Phase 4: Full System Run on External Cases"
echo "============================================"

$ENGINE run \
    --cases data/cases/external_cases_sample.jsonl \
    --out results/external/bundles
echo "[4] Full system run complete"

# Evidence audit on external bundles
$ENGINE evidence-audit \
    --bundle-dir results/external/bundles \
    --out results/audit/external_evidence_audit.json
echo "[4-audit] External evidence audit complete"

echo "============================================"
echo "Phase 5: Baseline Suite (5 conditions)"
echo "============================================"
# Conditions: direct, generic_cot, full_system, with_vulnerability_priority, no_update
$ENGINE baseline-suite \
    --cases data/cases/external_cases_sample.jsonl \
    --out results/external/baseline_suite
echo "[5] Baseline suite complete"

echo "============================================"
echo "Phase 6: Counterfactual HMI Experiment"
echo "============================================"

# 6a. Generate CF specs from templates
$ENGINE generate-cf-specs \
    --cases data/cases/external_cases_sample.jsonl \
    --out results/cf_eval/cf_specs.jsonl
echo "[6a] CF specs generated"

# 6b. Generate counterfactual cases
$ENGINE generate-counterfactual \
    --cases data/cases/external_cases_sample.jsonl \
    --specs results/cf_eval/cf_specs.jsonl \
    --out data/cases/cf_cases.jsonl
echo "[6b] Counterfactual cases generated"

# 6c. Run full system on counterfactual cases
$ENGINE run \
    --cases data/cases/cf_cases.jsonl \
    --out results/cf_eval/cf_bundles
echo "[6c] CF full system run complete"

# 6d. Directional consistency evaluation
$ENGINE counterfactual-eval \
    --base-bundle-dir results/external/bundles \
    --cf-bundle-dir results/cf_eval/cf_bundles \
    --specs results/cf_eval/cf_specs.jsonl \
    --out results/cf_eval/cf_eval_report
echo "[6d] CF directional consistency evaluation complete"

echo "============================================"
echo "Pipeline Complete"
echo "============================================"
echo ""
echo "Key outputs:"
echo "  results/demo/eval_report.json          — Demo evaluation"
echo "  results/table1/missingness_profile/     — Table 1 data"
echo "  results/external/bundles/               — External case bundles"
echo "  results/external/baseline_suite/        — 5-condition baseline comparison"
echo "  results/cf_eval/cf_eval_report/         — Counterfactual consistency"
echo "  results/audit/                          — Evidence audit reports"
echo "  data/annotation_packets/                — Human annotation packets"
