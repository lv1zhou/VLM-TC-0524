param(
  [string]$Cases = "data/cases/paper_50_mixed_sources_v1.jsonl",
  [string]$OutRoot = "results/paper_v1_50_mixed_sources",
  [switch]$SkipLlm
)

$ErrorActionPreference = "Stop"

function Invoke-Step {
  param(
    [string]$Name,
    [scriptblock]$Block
  )
  Write-Host ""
  Write-Host "==== $Name ===="
  & $Block
}

Invoke-Step "Input audit" {
  python stpa_hf_dan_eswa_engine_final.py audit-case-input --cases $Cases --out "$OutRoot/input_audit"
}

Invoke-Step "Missingness profile" {
  python stpa_hf_dan_eswa_engine_final.py missingness-profile --cases $Cases --out "$OutRoot/table1/missingness_profile"
}

Invoke-Step "Annotation packets" {
  python stpa_hf_dan_eswa_engine_final.py export-annotation-packets --cases $Cases --out "data/annotation_packets/paper_50_v1" --csv "data/annotation_packets/paper_50_v1/annotation_sheet.csv"
}

Invoke-Step "Expert-0 preview labels" {
  python stpa_hf_dan_eswa_engine_final.py expert-preview-labels --cases $Cases --out-labels "data/annotations/expert_preview_not_publication_gold_50.jsonl" --out-report "$OutRoot/expert_preview_eval/expert_preview_annotation_report.json"
}

if (-not $SkipLlm) {
  Invoke-Step "Full system" {
    python stpa_hf_dan_eswa_engine_final.py run --cases $Cases --out "$OutRoot/bundles"
  }

  Invoke-Step "Baseline suite" {
    python stpa_hf_dan_eswa_engine_final.py baseline-suite --cases $Cases --out "$OutRoot/baseline_suite"
  }

  Invoke-Step "Evidence audit" {
    python stpa_hf_dan_eswa_engine_final.py evidence-audit --bundle-dir "$OutRoot/bundles" --out "$OutRoot/audit/evidence_support_audit"
  }

  Invoke-Step "Feedback gaps" {
    python stpa_hf_dan_eswa_engine_final.py feedback-gap-report --bundle-dir "$OutRoot/bundles" --out "$OutRoot/feedback_gaps"
  }

  Invoke-Step "Evidence requirement candidates" {
    python stpa_hf_dan_eswa_engine_final.py evidence-requirement-candidates --gap-report "$OutRoot/feedback_gaps/feedback_gap_report.json" --out "$OutRoot/evidence_requirements"
  }

  Invoke-Step "Counterfactual specs" {
    python stpa_hf_dan_eswa_engine_final.py generate-cf-specs --cases $Cases --out "$OutRoot/cf_specs.jsonl"
  }

  Invoke-Step "Counterfactual cases" {
    python stpa_hf_dan_eswa_engine_final.py generate-counterfactual --cases $Cases --specs "$OutRoot/cf_specs.jsonl" --out "$OutRoot/cf_cases.jsonl"
  }

  Invoke-Step "Counterfactual full system" {
    python stpa_hf_dan_eswa_engine_final.py run --cases "$OutRoot/cf_cases.jsonl" --out "$OutRoot/cf_bundles"
  }

  Invoke-Step "Counterfactual eval" {
    python stpa_hf_dan_eswa_engine_final.py counterfactual-eval --base-bundle-dir "$OutRoot/bundles" --cf-bundle-dir "$OutRoot/cf_bundles" --specs "$OutRoot/cf_specs.jsonl" --out "$OutRoot/cf_eval"
  }

  Invoke-Step "Paper manifest" {
    python stpa_hf_dan_eswa_engine_final.py paper-manifest --cases $Cases --bundle-dir "$OutRoot/bundles" --baseline-dir "$OutRoot/baseline_suite" --cf-report "$OutRoot/cf_eval/counterfactual_directional_consistency.json" --missingness-profile "$OutRoot/table1/missingness_profile/dataset_missingness_profile.json" --evidence-audit "$OutRoot/audit/evidence_support_audit/evidence_support_audit.json" --feedback-gap-report "$OutRoot/feedback_gaps/feedback_gap_report.json" --requirement-candidates "$OutRoot/evidence_requirements/evidence_requirement_candidates.json" --out "$OutRoot/paper_result_manifest.json"
  }
}

Write-Host ""
Write-Host "Pipeline complete: $OutRoot"
