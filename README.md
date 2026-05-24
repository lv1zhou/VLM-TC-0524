# STPAHF Driver-Process-Model Replay

This repository contains an evidence-bounded, STPA-HF-grounded LLM pipeline for converting sparse automated-driving incident reports into auditable tabletop replay artifacts.

## What this code does

The main engine, `stpa_hf_dan_eswa_engine_final.py`, reads functional incident cases and produces:

- `tabletop_replay_package` bundles
- evidence audits
- feedback gap reports
- analysis-derived evidence/logging requirement candidates
- semantic warning audits
- baseline, ablation, and counterfactual comparisons

The system is designed for post-incident safety review, not for true accident reconstruction or true driver-psychology inference.

## Core idea

Public AV incident reports often contain scene facts but omit key HMI, driver-state, and internal ADS transition evidence.
The pipeline therefore treats missingness as an epistemic boundary and uses STPA-HF to generate bounded replay hypotheses instead of jumping directly from outcome to takeover failure.

## Main files

- [`stpa_hf_dan_eswa_engine_final.py`](./stpa_hf_dan_eswa_engine_final.py): main engine and CLI
- [`external_case_ingestion_final.py`](./external_case_ingestion_final.py): raw CSV ingestion and functional case construction
- [`run_pipeline.sh`](./run_pipeline.sh): older end-to-end pipeline
- [`run_paper_pipeline.sh`](./run_paper_pipeline.sh): paper-oriented pipeline
- [`AAP_V245_CODE_EXECUTION_AND_STRUCTURE_SK.md`](./AAP_V245_CODE_EXECUTION_AND_STRUCTURE_SK.md): execution and structure guide

## Input data

Typical inputs:

- `data/cases/*.jsonl`: functional cases
- `data/raw/nhtsa_sgo/*`: raw NHTSA source files
- third-party augmented CA DMV collision CSVs
- official CA DMV disengagement report data

Key case fields:

- `ENV`, `ACTOR`, `CAR`
- `HMI`
- `CABIN`
- `driver_profile`
- source metadata and provenance

## Main outputs

The main pipeline writes result bundles under `results/`.

Important report types:

- `driver_process_model_tabletop_replay_bundle`
- `tabletop_replay_audit.json`
- `evidence_support_audit.json`
- `feedback_gap_report.json`
- `requirement_candidates.json`
- `semantic_warning_audit.json`
- `counterfactual_directional_consistency.json`

## CLI workflow

The typical execution order is:

1. Role disambiguation
2. Main replay generation
3. Tabletop replay audit
4. Evidence audit
5. Feedback gap report
6. Requirement candidate extraction
7. Semantic warning audit
8. Optional baseline, ablation, and counterfactual runs

### Example commands

```powershell
cd C:\Users\32401\PycharmProjects\PythonProject\STPAHF

$env:OPENAI_API_KEY='YOUR_KEY'
$env:OPENAI_BASE_URL='https://dashscope.aliyuncs.com/compatible-mode/v1'
$env:OPENAI_MODEL='qwen-max-latest'
$env:OPENAI_TIMEOUT_S='240'

python .\stpa_hf_dan_eswa_engine_final.py role-disambiguate-cases --cases .\data\cases\paper_10_mixed_ca_5collision_5disengagement.jsonl --out-cases .\data\cases\paper_10_mixed_ca_5collision_5disengagement_role_adjudicated.jsonl --out-report .\results\aap_v245_10case_role_disambiguation\role_disambiguation_report.json --temperature 0

python .\stpa_hf_dan_eswa_engine_final.py run --cases .\data\cases\paper_10_mixed_ca_5collision_5disengagement_role_adjudicated.jsonl --out .\results\aap_v245_10case_role_adjudicated_full_final --temperature 0 --resume

python .\stpa_hf_dan_eswa_engine_final.py tabletop-replay-audit --bundle-dir .\results\aap_v245_10case_role_adjudicated_full_final --out .\results\aap_v245_10case_replay_audit
python .\stpa_hf_dan_eswa_engine_final.py evidence-audit --bundle-dir .\results\aap_v245_10case_role_adjudicated_full_final --out .\results\aap_v245_10case_evidence_audit
python .\stpa_hf_dan_eswa_engine_final.py feedback-gap-report --bundle-dir .\results\aap_v245_10case_role_adjudicated_full_final --out .\results\aap_v245_10case_feedback_gaps
python .\stpa_hf_dan_eswa_engine_final.py requirement-candidates --gap-report .\results\aap_v245_10case_feedback_gaps\feedback_gap_report.json --out .\results\aap_v245_10case_requirements
python .\stpa_hf_dan_eswa_engine_final.py semantic-warning-audit --bundle-dir .\results\aap_v245_10case_role_adjudicated_full_final --evidence-audit .\results\aap_v245_10case_evidence_audit\evidence_support_audit.json --out .\results\aap_v245_10case_semantic_warning_audit --temperature 0
```

## One-shot execution

Use the shell script below to run the full pipeline with one command:

```bash
bash ./run_aap_v245_all.sh
```

Optional expensive branches can be enabled with environment flags:

- `RUN_BASELINE_SUITE=1`
- `RUN_ABLATION_SUITE=1`
- `RUN_COUNTERFACTUAL=1`
- `RUN_PM_MEDIATION=1`

## Current pilot result

For the current 10-case pilot (5 collision + 5 disengagement), the pipeline produced:

- 10/10 schema-valid replay bundles
- 1.0 replay package generation rate
- 1.0 quadrant coverage
- 1.0 update-process presence
- 0 invalid evidence IDs
- 1.0 catalog consistency
- 110 feedback gaps
- 110 requirement candidates
- 2 semantic warning candidates, both adjudicated as properly gated blocked hypotheses

## Safety boundaries

This system does not claim:

- true driver psychology
- true accident cause
- HMI causal proof
- legal responsibility

It is a bounded post-incident review and sensitivity-analysis tool.

