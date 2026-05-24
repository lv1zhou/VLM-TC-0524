from __future__ import annotations
"""
stpa_hf_dan_eswa_clean.py

Clean AAP-facing backbone for an STPA-HF-grounded driver process-model tabletop replay system.

Design commitments
------------------
1. Keep the core reasoning chain stable:
   evidence objects -> PM synthesis -> update analysis -> action/UCA pathways -> tabletop replay package.
2. Do not use seed labels as publication-facing gold.
3. Do not infer missing HMI, driver state, or internal ADS variables from regulatory reports.
4. Distinguish reported / derived / not_reported / counterfactual evidence explicitly.
5. Use strict schema validation. JSON/API retries are allowed; semantic defaults and label repair are not.
6. Keep expert-system knowledge explicit: FSM states and UCA catalog are visible; vulnerability-conditioned UCA priority is disabled by default and can be enabled explicitly for ablation.

This file intentionally removes earlier non-core modules such as slot-richness scoring,
driver-risk scoring, OBL activation, LLM-judge ablation, and seed-label generation.
"""

import argparse
import csv
import hashlib
import json
import math
import os
import statistics
import time
from datetime import datetime, timezone
from collections import Counter, defaultdict
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import requests

try:
    from external_case_ingestion_final import ev, nr, unwrap_value, wrap_if_plain, load_external_cases
except ImportError:  # keep compatibility if final module is renamed to external_case_ingestion.py
    from external_case_ingestion import ev, nr, unwrap_value, wrap_if_plain, load_external_cases
SCHEMA_VERSION = "driver_pm_tabletop_replay_v2.4.4"

ALLOWED_BOUNDARIES = ["supported_monitoring", "contingent_readiness", "not_supported_transfer"]
ALLOWED_BASIS = ["supported", "contingent", "not_supported"]
ALLOWED_POSTURES = ["heightened_monitoring", "readiness_formed", "transfer_initiated"]
ALLOWED_ACTIONS = [
    "continue_monitoring",
    "prepare_takeover",
    "initiate_takeover",
    "initiate_intervention",
    "maintain_no_intervention",
    "modulate_braking",
    "modulate_steering",
    "safe_stop_or_minimal_risk_response",
]
ALLOWED_QUADRANTS = ["CPS", "CPB", "OPS", "OPB"]
ALLOWED_VULNERABILITIES = ["none", "missed_feedback", "ambiguous_feedback", "misinterpreted_feedback"]
ALLOWED_CLAIM_STATUS = ["observed", "observed_admissible", "abductive_candidate", "blocked"]
ALLOWED_ABDUCTIVE_STRENGTH = ["strong_abductive", "weak_abductive", "speculative_abductive", "blocked"]
ALLOWED_PM_FLAW_TYPES = ["incomplete_belief", "incorrect_belief", "outdated_belief", "unverified_belief", "none_supported"]
ALLOWED_OUTCOME_COMPATIBILITY = ["compatible", "weakly_compatible", "contradicted", "not_assessable"]
ALLOWED_PROVENANCE = ["reported", "derived", "not_reported", "reported_narrative", "assumed_for_counterfactual"]
ALLOWED_PATHWAY_STATUS = ["admissible", "weakly_supported", "blocked"]
ALLOWED_UPDATE_EVIDENCE_STATUS = ["observed_update_claim", "evidence_gap_only", "not_admissible"]
ALLOWED_UPDATE_GAP_RISKS = [
    "missing_hmi_feedback",
    "missing_time_budget",
    "missing_driver_state",
    "missing_internal_ads_state",
    "missing_actor_observability",
    "missing_action_feedback",
    "incomplete_feedback",
    "missing_environmental_feedback",
    "missing_ads_behavior",
    "missing_ads_behavioral_cues",
    "missing_ads_behavioral_metrics",
    "missing_ads_capability",
    "missing_ads_capability_feedback",
    "missing_ads_capability_indicators",
    "missing_ads_capability_metrics",
    "missing_capability_boundary",
    "missing_capability_boundary_hint",
    "missing_vehicle_behavior",
    "missing_environmental_context",
    "missing_environment_visibility",
    "missing_environmental_details",
]
ALLOWED_UPDATE_PROCESS_VALUES = ["reported", "partially_reported", "not_reported", "unclear", "not_admissible_from_report"]
ALLOWED_UPDATE_SALIENCE_VALUES = ["high", "medium", "low", "not_reported", "not_admissible_from_report"]
ALLOWED_UPDATE_INTERPRETATION_VALUES = ["clear", "partial", "ambiguous", "unclear", "partially_reported", "not_reported", "not_admissible_from_report"]
ALLOWED_GATE_STATUSES = ["pass", "weak", "fail"]
ALLOWED_GROUNDING_LEVELS = ["direct", "indirect", "absent"]
ALLOWED_UCA_ACTIVATION_STATUS = ["activated", "no_activated_uca"]
OUTCOME_ONLY_FIELD_PATHS = {"CAR.event_type", "CAR.reported_consequence"}
ACTION_EVIDENCE_ROLES = {"driver_action_or_transition_evidence", "driver_action_quality_evidence", "driver_state_evidence"}
ALLOWED_OTHER_FACTOR_TYPES = [
    "time_pressure",
    "workload",
    "driver_role",
    "test_protocol",
    "manual_fallback_availability",
    "traffic_pressure",
    "maneuver_constraint",
    "safe_stop_target",
    "control_authority_availability",
    "distraction",
    "impairment",
    "prediction_uncertainty",
    "actor_prediction_uncertainty",
    "system_recommendation_pressure",
    "other",
]
STPA_UCA_CATEGORY_MAP = {
    "provided_when_not_appropriate": "provided_when_not_appropriate",
    "not_provided_when_required": "not_provided_when_required",
    "too_late": "too_early_too_late_or_wrong_order",
    "wrong_duration": "wrong_duration_or_stopped_too_soon",
}
PM_QUADRANT_DEFINITIONS = {
    "CPS": {
        "name": "Controlled Process States",
        "definition": "Driver belief about current controlled-process state, mode, phase, or variable.",
        "strict_scope": "Current ADS mode, vehicle state, control authority, transfer state, intervention state, and driver control availability.",
    },
    "CPB": {
        "name": "Controlled Process Behaviors",
        "definition": "Driver belief about what the controlled process can do, will do, or how it behaves in a mode or phase.",
        "strict_scope": "Expected ADS/vehicle behavior, capability boundary, braking/steering/lane behavior, system issue, and future control behavior.",
    },
    "OPS": {
        "name": "Other Process States",
        "definition": "Driver belief about current states of other processes, the environment, or external controllers.",
        "strict_scope": "Current road, visibility, weather, lane, intersection, infrastructure, and traffic-control state.",
    },
    "OPB": {
        "name": "Other Process Behaviors",
        "definition": "Driver belief about what other processes or actors can do, will do, or how they may behave.",
        "strict_scope": "Other-actor motion, intent, cut-in, crossing, rear approach, observability, and prediction uncertainty.",
    },
}

UPDATE_SOURCE_GUIDE = {
    "CPS": {
        "target_belief": "driver belief about ADS/vehicle/control-authority current state",
        "formation_sources": ["HMI mode display", "takeover demand", "mode transition cue", "training/documentation", "vehicle behavior observation", "manual-intervention experience"],
        "later_update_sources": ["HMI mode/status cue", "takeover request", "mode transition feedback", "vehicle behavior observation", "reported intervention/disengagement"],
    },
    "CPB": {
        "target_belief": "driver belief about ADS/vehicle future behavior and capability",
        "formation_sources": ["capability boundary cue", "ADS behavior observation", "braking/steering response", "system warning", "historical experience", "manual/documentation"],
        "later_update_sources": ["capability boundary cue", "planner/braking/steering behavior", "system issue cue", "vehicle motion", "reported system issue"],
    },
    "OPS": {
        "target_belief": "driver belief about current external environment state",
        "formation_sources": ["visual observation", "road geometry", "weather/visibility", "map/perception display", "road markings", "traffic signal"],
        "later_update_sources": ["visual scene", "traffic signal change", "road geometry cue", "visibility/weather cue", "map/perception display"],
    },
    "OPB": {
        "target_belief": "driver belief about other traffic participants' future behavior",
        "formation_sources": ["actor trajectory", "speed change", "cut-in cue", "rear approach cue", "pedestrian behavior", "actor observability", "occlusion"],
        "later_update_sources": ["actor motion", "speed/deceleration change", "cut-in/crossing event", "rear approach", "observability cue", "occlusion cue"],
    },
}

CANONICAL_UPDATE_GAP_TAXONOMY = {
    "missing_hmi_or_mode_feedback": [
        "hmi", "mode", "display", "capability_boundary", "capability boundary", "feedback",
        "incomplete_feedback",
    ],
    "missing_time_budget_or_transition_cue": [
        "time_budget", "time budget", "transition", "takeover", "handover",
    ],
    "missing_ads_behavior_feedback": [
        "ads_behavior", "ads behavior", "vehicle_behavior", "vehicle behavior", "lane_keeping",
        "deceleration", "planner", "perception", "capability",
    ],
    "missing_actor_observability": [
        "actor", "traffic", "cut_in", "cut-in", "pedestrian", "secondary", "observability",
    ],
    "missing_environment_observability": [
        "environment", "visibility", "weather", "lane_topology", "markings", "construction",
        "infrastructure", "environmental_context",
    ],
    "missing_driver_response_evidence": [
        "driver", "cabin", "pressure", "distraction", "intervention", "response", "manual",
    ],
}

PSYCHOLOGICAL_OVERCLAIM_PATTERNS = [
    "driver was unaware",
    "driver may have been unaware",
    "driver failed to notice",
    "driver did not notice",
    "driver ignored",
    "driver misunderstood",
    "driver believed incorrectly",
]
BOUNDARY_FSM_DEFINITIONS = {
    "supported_monitoring": {
        "ordinal_level": 1,
        "definition": "ADS support is still treated as source-supported enough for driver monitoring rather than active takeover preparation.",
        "necessary_condition": "No explicit transition/intervention/support-withdrawal evidence; reported evidence does not require readiness formation.",
        "allowed_control_actions": ["continue_monitoring"],
        "coverage_role": "lowest control-responsibility state for ADS-supported operation.",
        "excludes": ["contingent_readiness when source evidence creates preparation pressure", "not_supported_transfer when explicit transfer/intervention evidence exists"],
    },
    "contingent_readiness": {
        "ordinal_level": 2,
        "definition": "ADS support is uncertain or degraded enough that the driver should form takeover readiness, but explicit transfer is not established.",
        "necessary_condition": "Source-visible capability, actor, environment, or system evidence creates readiness pressure without explicit takeover/transfer evidence.",
        "allowed_control_actions": ["prepare_takeover"],
        "coverage_role": "middle control-responsibility state for degraded/uncertain support.",
        "excludes": ["supported_monitoring when there is clear preparation pressure", "not_supported_transfer without explicit transfer/intervention/support-withdrawal evidence"],
    },
    "not_supported_transfer": {
        "ordinal_level": 3,
        "definition": "ADS support is no longer sufficient or a transfer/intervention is explicitly reported.",
        "necessary_condition": "Explicit disengagement, intervention, takeover demand, support withdrawal, or source-reported manual control transition.",
        "allowed_control_actions": ["initiate_takeover"],
        "coverage_role": "highest control-responsibility state for transfer or fallback.",
        "excludes": ["lower states when explicit transfer/intervention evidence is present"],
    },
}
UPDATE_VULNERABILITY_DEFINITIONS = {
    "missed_feedback": {
        "stpa_hf_origin": "process model update flaw where needed feedback is absent, unavailable, not registered, or not carried into the controller's update.",
        "definition": "The text supports pressure for a process-model update, while key feedback needed for that update is absent or not reported.",
        "distinguishes_from": "ambiguous_feedback has unclear/mixed feedback; misinterpreted_feedback has evidence of wrong interpretation or conflicting cues.",
    },
    "ambiguous_feedback": {
        "stpa_hf_origin": "process model update flaw where feedback is incomplete, underspecified, or insufficiently discriminating for the controller.",
        "definition": "The text supports uncertainty or degraded support, but the evidence does not clearly establish the required control-state or behavior update.",
        "distinguishes_from": "missed_feedback emphasizes absent feedback; misinterpreted_feedback emphasizes wrong reading of available feedback.",
    },
    "misinterpreted_feedback": {
        "stpa_hf_origin": "process model update flaw where available feedback is interpreted into the wrong process-model state or behavior expectation.",
        "definition": "The text supports a mismatch or conflict suggesting the controller could form an incorrect readiness/capability/actor-behavior hypothesis.",
        "distinguishes_from": "missed_feedback and ambiguous_feedback do not require a wrong interpretation pattern.",
    },
}
ALLOWED_DESIGN_TYPES = [
    "mode_clarity",
    "capability_communication",
    "takeover_timing_communication",
    "warning_salience",
    "workload_support",
    "conflict_resolution_support",
    "none",
]

FORBIDDEN_CASE_INPUT_KEYS = {
    "boundary_label", "gold_boundary_label", "expected_primary_axis",
    "dominant_uca", "gold_dominant_uca", "active_uca_set", "gold_active_uca_set",
    "update_vulnerability", "gold_update_vulnerability", "expected_update_vulnerability_family",
    "requirement_focus", "gold_requirement_focus", "label_scope",
}


# =============================================================================
# Exceptions and low-level IO
# =============================================================================


class SchemaValidationError(RuntimeError):
    """Raised when an LLM or data artifact violates the publication-facing schema."""


class DataCurationError(RuntimeError):
    """Raised when an external raw record cannot be safely mapped into a functional case."""


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: str | Path, obj: Any) -> None:
    p = Path(path)
    ensure_dir(p.parent)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def read_jsonl(path: str | Path) -> List[Dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(str(p))
    rows: List[Dict[str, Any]] = []
    for line_no, line in enumerate(p.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            raise DataCurationError(f"Invalid JSONL at {p}:{line_no}: {exc}") from exc
        if not isinstance(obj, dict):
            raise DataCurationError(f"JSONL row must be object at {p}:{line_no}")
        rows.append(obj)
    return rows


def write_jsonl(path: str | Path, rows: Iterable[Dict[str, Any]]) -> None:
    p = Path(path)
    ensure_dir(p.parent)
    with p.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def iter_jsonl(path: str | Path) -> Iterable[Dict[str, Any]]:
    p = Path(path)
    with p.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise DataCurationError(f"Invalid JSONL at {p}:{line_no}: {exc}") from exc
            if not isinstance(obj, dict):
                raise DataCurationError(f"JSONL row must be object at {p}:{line_no}")
            yield obj


def select_case_window(
    cases: Sequence[Dict[str, Any]],
    *,
    case_start: Optional[int] = None,
    case_limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Select a stable contiguous case window for batch execution."""
    start = max(0, int(case_start or 0))
    if case_limit is None:
        end = len(cases)
    else:
        end = start + max(0, int(case_limit))
    return list(cases)[start:end]


def stable_digest(obj: Any, n: int = 16) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:n]


def file_sha256(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def get_path(obj: Dict[str, Any], dotted: str, default: Any = None) -> Any:
    cur: Any = obj
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur


def set_path(obj: Dict[str, Any], dotted: str, value: Any) -> None:
    cur = obj
    parts = dotted.split(".")
    for part in parts[:-1]:
        if part not in cur or not isinstance(cur[part], dict):
            cur[part] = {}
        cur = cur[part]
    cur[parts[-1]] = value


def find_forbidden_input_keys(obj: Any, prefix: str = "") -> List[str]:
    """Find label-like keys that would leak gold or expected outputs into LLM input."""
    hits: List[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            path = f"{prefix}.{k}" if prefix else str(k)
            if k in FORBIDDEN_CASE_INPUT_KEYS:
                hits.append(path)
            hits.extend(find_forbidden_input_keys(v, path))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            hits.extend(find_forbidden_input_keys(v, f"{prefix}[{i}]"))
    return hits


def validate_case_no_label_leakage(case_spec: Dict[str, Any], allow_internal_demo_labels: bool = False) -> None:
    """Reject publication-facing cases that contain labels, expected axes, or gold fields.

    Internal demo labels must live in a separate labels file, not in the case payload.
    """
    hits = find_forbidden_input_keys(case_spec)
    if hits:
        raise DataCurationError(
            "Forbidden label-like keys in case input. Labels must stay in labels_master_adjudicated.jsonl, "
            f"not in LLM input. Offending paths: {hits[:20]}"
        )


def normalize_token(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def majority_vote(values: Sequence[str]) -> Tuple[Optional[str], float]:
    clean = [v for v in values if v]
    if not clean:
        return None, 0.0
    counts = Counter(clean)
    label, count = counts.most_common(1)[0]
    return label, count / len(clean)


def macro_f1(y_true: Sequence[str], y_pred: Sequence[str], labels: Optional[Sequence[str]] = None) -> float:
    if len(y_true) != len(y_pred):
        raise ValueError("y_true and y_pred length mismatch")
    if not y_true:
        return 0.0
    use_labels = list(labels or sorted(set(y_true) | set(y_pred)))
    f1s = []
    for label in use_labels:
        tp = sum(1 for t, p in zip(y_true, y_pred) if t == label and p == label)
        fp = sum(1 for t, p in zip(y_true, y_pred) if t != label and p == label)
        fn = sum(1 for t, p in zip(y_true, y_pred) if t == label and p != label)
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1s.append((2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0)
    return round(sum(f1s) / len(f1s), 4) if f1s else 0.0


def balanced_accuracy(y_true: Sequence[str], y_pred: Sequence[str], labels: Optional[Sequence[str]] = None) -> float:
    if not y_true:
        return 0.0
    use_labels = list(labels or sorted(set(y_true) | set(y_pred)))
    recalls = []
    for label in use_labels:
        denom = sum(1 for t in y_true if t == label)
        if denom == 0:
            continue
        recalls.append(sum(1 for t, p in zip(y_true, y_pred) if t == label and p == label) / denom)
    return round(sum(recalls) / len(recalls), 4) if recalls else 0.0


def confusion_matrix(y_true: Sequence[str], y_pred: Sequence[str]) -> Dict[str, Dict[str, int]]:
    matrix: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for t, p in zip(y_true, y_pred):
        matrix[str(t)][str(p)] += 1
    return {k: dict(v) for k, v in matrix.items()}


# =============================================================================
# Expert-system knowledge: FSM and UCA catalog
# =============================================================================

UCA_CATALOG: Dict[str, List[Dict[str, Any]]] = {
    "supported_monitoring": [
        {
            "uca_id": "UCA-SM-1",
            "canonical_uca_ref": "UCA_HF_2A",
            "control_action": "continue_monitoring",
            "uca_type": "provided_when_not_appropriate",
            "short_name": "over-reliance while ADS support is degraded",
            "description": "Driver continues monitoring/relying on ADS when capability evidence no longer supports safe reliance.",
            "proximal_update_vulnerability": "missed_feedback",
            "unsafe_context_template": "ADS support appears degraded or uncertain, but driver continues to rely on it as if support remained sufficient.",
            "hazard_link": "continued reliance prevents timely transition to readiness.",
        },
        {
            "uca_id": "UCA-SM-2",
            "canonical_uca_ref": "UCA_HF_3A",
            "control_action": "continue_monitoring",
            "uca_type": "not_provided_when_required",
            "short_name": "monitoring omission at boundary warning",
            "description": "Driver fails to actively monitor boundary-warning signals needed to prepare for takeover.",
            "proximal_update_vulnerability": "missed_feedback",
            "unsafe_context_template": "Boundary-warning evidence is source-visible, but required monitoring does not occur.",
            "hazard_link": "missing monitoring blocks readiness formation.",
        },
    ],
    "contingent_readiness": [
        {
            "uca_id": "UCA-CR-1",
            "canonical_uca_ref": "UCA_HF_3A",
            "control_action": "prepare_takeover",
            "uca_type": "too_late",
            "short_name": "late readiness formation",
            "description": "Driver forms readiness too late relative to takeover pressure.",
            "proximal_update_vulnerability": "missed_feedback",
            "unsafe_context_template": "Takeover pressure exists, but readiness is formed only after the critical window has narrowed.",
            "hazard_link": "late readiness increases exposure before control transfer.",
        },
        {
            "uca_id": "UCA-CR-2",
            "canonical_uca_ref": "UCA_HF_2A",
            "control_action": "prepare_takeover",
            "uca_type": "provided_when_not_appropriate",
            "short_name": "premature readiness from misread boundary",
            "description": "Driver prematurely forms takeover readiness by misreading subtle/ambiguous boundary evidence as exceeded.",
            "proximal_update_vulnerability": "misinterpreted_feedback",
            "unsafe_context_template": "Ambiguous boundary evidence is interpreted as requiring readiness before the source text justifies it.",
            "hazard_link": "premature readiness may misallocate attention or control effort.",
        },
        {
            "uca_id": "UCA-CR-3",
            "canonical_uca_ref": "UCA_HF_3B",
            "control_action": "prepare_takeover",
            "uca_type": "not_provided_when_required",
            "short_name": "missed readiness under degraded support",
            "description": "Driver fails to form takeover readiness although posterior PM indicates degraded or conditionally supportable ADS reliance.",
            "proximal_update_vulnerability": "ambiguous_feedback",
            "unsafe_context_template": "Degraded support is present in the source text, but readiness is not formed in time.",
            "hazard_link": "absent readiness under degradation leaves no fallback buffer.",
        },
    ],
    "not_supported_transfer": [
        {
            "uca_id": "UCA-NS-1",
            "canonical_uca_ref": "UCA_HF_3B",
            "control_action": "initiate_takeover",
            "uca_type": "not_provided_when_required",
            "short_name": "takeover omission",
            "description": "Driver does not initiate takeover when ADS support has been withdrawn or takeover is required.",
            "proximal_update_vulnerability": "ambiguous_feedback",
            "unsafe_context_template": "Source text supports transfer need, but takeover is not initiated.",
            "hazard_link": "omission under required transfer can lead to loss of control.",
        },
        {
            "uca_id": "UCA-NS-2",
            "canonical_uca_ref": "UCA_HF_4A",
            "control_action": "initiate_takeover",
            "uca_type": "too_late",
            "short_name": "late takeover execution",
            "description": "Driver initiates takeover too late for safe authority transition.",
            "proximal_update_vulnerability": "missed_feedback",
            "unsafe_context_template": "Takeover is required, but execution occurs outside the safe transfer window.",
            "hazard_link": "late authority transition increases conflict with vehicle dynamics.",
        },
        {
            "uca_id": "UCA-NS-3",
            "canonical_uca_ref": "UCA_HF_4B",
            "control_action": "initiate_takeover",
            "uca_type": "wrong_duration",
            "short_name": "wrong-duration takeover correction",
            "description": "Driver takeover input is discontinuous, over-corrective, under-controlled, or applied for the wrong duration.",
            "proximal_update_vulnerability": "misinterpreted_feedback",
            "unsafe_context_template": "Manual takeover occurs, but control application is unstable, discontinuous, or duration-mismatched.",
            "hazard_link": "wrong-duration control can amplify instability or conflict with the hazard.",
        },
    ],
}

DRIVER_UCA_CATALOG: List[Dict[str, Any]] = [
    {
        "uca_id": "UCA-H-1",
        "legacy_uca_ids": ["UCA-SM-2"],
        "canonical_uca_ref": "UCA_HF_3A",
        "controller": "driver_or_safety_operator",
        "control_action": "monitor_ads_and_roadway",
        "uca_type": "not_provided_when_required",
        "short_name": "monitoring not provided when required",
        "description": "Driver or safety operator does not maintain the monitoring needed to detect a boundary-relevant change.",
        "unsafe_context_template": "The report supports a need for active supervision, but monitoring/attention evidence is absent, late, or contradicted.",
        "hazard_link": "Insufficient monitoring can prevent timely process-model update and fallback preparation.",
        "minimum_required_evidence": [
            "reported driver/operator attention, monitoring, gaze, distraction, or supervision evidence",
            "source-visible ADS or traffic context requiring supervision",
        ],
        "outcome_compatibility_patterns": ["collision", "crash", "contact", "disengagement", "intervention"],
        "blocked_if_only_outcome": True,
    },
    {
        "uca_id": "UCA-H-2",
        "legacy_uca_ids": ["UCA-NS-1", "UCA-CR-3"],
        "canonical_uca_ref": "UCA_HF_3B",
        "controller": "driver_or_safety_operator",
        "control_action": "initiate_takeover_or_intervention",
        "uca_type": "not_provided_when_required",
        "short_name": "takeover or intervention not provided when required",
        "description": "Driver or safety operator does not initiate takeover/intervention when the source text supports a required transfer or fallback.",
        "unsafe_context_template": "A transfer or fallback is source-supported, but the report supports omitted intervention or no action.",
        "hazard_link": "Omitted takeover or fallback can leave the ADS/vehicle in an unsafe state.",
        "minimum_required_evidence": [
            "reported takeover demand, support withdrawal, disengagement condition, or required fallback",
            "reported omitted intervention, no response, or no action beyond the outcome itself",
        ],
        "outcome_compatibility_patterns": ["collision", "crash", "contact", "near miss"],
        "blocked_if_only_outcome": True,
    },
    {
        "uca_id": "UCA-H-3",
        "legacy_uca_ids": ["UCA-NS-2", "UCA-CR-1"],
        "canonical_uca_ref": "UCA_HF_4A",
        "controller": "driver_or_safety_operator",
        "control_action": "initiate_takeover_or_intervention",
        "uca_type": "too_late",
        "short_name": "takeover or intervention provided too late",
        "description": "Driver or safety operator initiates intervention too late relative to the hazardous control-transfer window.",
        "unsafe_context_template": "The report supports intervention timing pressure and a late or insufficiently timed response.",
        "hazard_link": "Late intervention can be compatible with collision or unresolved disengagement outcomes.",
        "minimum_required_evidence": [
            "reported timing cue, intervention time, after-impact response, delayed response, or insufficient time budget",
            "reported transfer/fallback pressure",
        ],
        "outcome_compatibility_patterns": ["collision", "crash", "contact", "disengagement"],
        "blocked_if_only_outcome": True,
    },
    {
        "uca_id": "UCA-H-4",
        "legacy_uca_ids": ["UCA-CR-2"],
        "canonical_uca_ref": "UCA_HF_2A",
        "controller": "driver_or_safety_operator",
        "control_action": "prepare_or_initiate_manual_control",
        "uca_type": "provided_when_not_appropriate",
        "short_name": "manual control or readiness provided when not appropriate",
        "description": "Driver or safety operator selects manual readiness/control in a context where the report supports that the action was premature, conflicting, or not required.",
        "unsafe_context_template": "The report supports premature or inappropriate manual readiness/control relative to the available boundary evidence.",
        "hazard_link": "Premature or inappropriate control can create conflict with ADS behavior or surrounding traffic.",
        "minimum_required_evidence": [
            "reported manual control/readiness action",
            "source evidence that the action was inappropriate, premature, or conflicting",
        ],
        "outcome_compatibility_patterns": ["collision", "crash", "contact", "disengagement", "intervention"],
        "blocked_if_only_outcome": True,
    },
    {
        "uca_id": "UCA-H-5",
        "legacy_uca_ids": ["UCA-NS-3"],
        "canonical_uca_ref": "UCA_HF_4B",
        "controller": "driver_or_safety_operator",
        "control_action": "apply_manual_control_input",
        "uca_type": "wrong_duration",
        "short_name": "manual control input has wrong duration or magnitude",
        "description": "Driver or safety operator applies steering, braking, acceleration, or fallback control with unstable, insufficient, excessive, or mistimed magnitude/duration.",
        "unsafe_context_template": "The report supports a manual control input and a wrong-duration, over-corrective, or insufficient application.",
        "hazard_link": "Wrong-duration or wrong-magnitude control can amplify instability or fail to avoid conflict.",
        "minimum_required_evidence": [
            "reported manual steering, braking, acceleration, or fallback input",
            "reported excessive, insufficient, discontinuous, or mistimed control quality",
        ],
        "outcome_compatibility_patterns": ["collision", "crash", "contact", "near miss"],
        "blocked_if_only_outcome": True,
    },
    {
        "uca_id": "UCA-H-6",
        "legacy_uca_ids": ["UCA-SM-1"],
        "canonical_uca_ref": "UCA_HF_3B",
        "controller": "driver_or_safety_operator",
        "control_action": "select_safe_stop_or_fallback",
        "uca_type": "not_provided_when_required",
        "short_name": "safe-stop or fallback action not selected when required",
        "description": "Driver or safety operator does not select an available safe-stop/fallback action when the source text supports that fallback was required.",
        "unsafe_context_template": "The report supports fallback availability and need, but not selection or execution.",
        "hazard_link": "Failure to select fallback can prolong exposure to the unsafe control state.",
        "minimum_required_evidence": [
            "reported fallback/safe-stop availability or requirement",
            "reported missing, delayed, or failed fallback selection",
        ],
        "outcome_compatibility_patterns": ["collision", "crash", "contact", "disengagement"],
        "blocked_if_only_outcome": True,
    },
]

LEGACY_UCA_ID_MAP: Dict[str, str] = {
    legacy_id: entry["uca_id"]
    for entry in DRIVER_UCA_CATALOG
    for legacy_id in entry.get("legacy_uca_ids", [])
}

DRIVER_UCA_BY_ID = {u["uca_id"]: u for u in DRIVER_UCA_CATALOG}
DRIVER_UCA_ID_SET = set(DRIVER_UCA_BY_ID)
LEGACY_UCA_ID_SET = {u["uca_id"] for items in UCA_CATALOG.values() for u in items}
UCA_ID_SET = DRIVER_UCA_ID_SET
SAFE_INTERVENTION_BLOCKED_DRIVER_UCAS = {"UCA-H-1", "UCA-H-2", "UCA-H-3", "UCA-H-5", "UCA-H-6"}

FSM_TRANSITIONS: Dict[str, Dict[str, Any]] = {
    "supported_monitoring": {
        "guard": "basis_state=ADS_SUPPORTED AND readiness_state=NOT_REQUIRED",
        "allowed_next": ["contingent_readiness"],
        "trigger_evidence": ["capability_boundary_hint in [uncertain_capability, subtle_boundary]", "time_budget_indicator=takeover_soon", "mode_state_display in [conflicting, engaged_but_uncertain]"],
    },
    "contingent_readiness": {
        "guard": "basis_state=ADS_CONDITIONAL AND readiness_state=ACTIVE",
        "allowed_next": ["supported_monitoring", "not_supported_transfer"],
        "trigger_evidence": ["capability_boundary_hint=boundary_exceeded", "time_budget_indicator=takeover_now", "mode_state_display=takeover_requested"],
    },
    "not_supported_transfer": {
        "guard": "basis_state=ADS_WITHDRAWN AND authority_transfer_state=INITIATED",
        "allowed_next": [],
        "trigger_evidence": ["require_ack=yes", "time_budget_indicator=takeover_now"],
    },
}

UPDATE_VULN_UCA_PRIORITY: Dict[Tuple[str, str], List[str]] = {
    ("supported_monitoring", "missed_feedback"): ["UCA-SM-1", "UCA-SM-2"],
    ("supported_monitoring", "ambiguous_feedback"): ["UCA-SM-1", "UCA-SM-2"],
    ("supported_monitoring", "misinterpreted_feedback"): ["UCA-SM-1", "UCA-SM-2"],
    ("contingent_readiness", "missed_feedback"): ["UCA-CR-1", "UCA-CR-3", "UCA-CR-2"],
    ("contingent_readiness", "ambiguous_feedback"): ["UCA-CR-3", "UCA-CR-1", "UCA-CR-2"],
    ("contingent_readiness", "misinterpreted_feedback"): ["UCA-CR-2", "UCA-CR-1", "UCA-CR-3"],
    ("not_supported_transfer", "missed_feedback"): ["UCA-NS-2", "UCA-NS-1", "UCA-NS-3"],
    ("not_supported_transfer", "ambiguous_feedback"): ["UCA-NS-1", "UCA-NS-2", "UCA-NS-3"],
    ("not_supported_transfer", "misinterpreted_feedback"): ["UCA-NS-3", "UCA-NS-1", "UCA-NS-2"],
}


# =============================================================================
# Provenance-aware functional scenario representation
# =============================================================================



# =============================================================================
# Evidence mapping: functional case -> STPA-HF evidence objects
# =============================================================================
FIELD_MAP: Dict[str, Dict[str, Any]] = {
    "HMI.mode_state_display": {"slot_id": "CPS_1", "quadrants": ["CPS"], "channel": "hmi_mode_channel"},
    "HMI.time_budget_indicator": {"slot_id": "CPS_1", "quadrants": ["CPS"], "channel": "hmi_timing_channel"},
    "HMI.require_ack": {"slot_id": "CPS_1", "quadrants": ["CPS"], "channel": "hmi_timing_channel"},
    "HMI.capability_boundary_hint": {"slot_id": "CPB_1", "quadrants": ["CPB"], "channel": "hmi_capability_channel"},
    "HMI.trajectory_display_latency": {"slot_id": "CPB_1", "quadrants": ["CPB"], "channel": "hmi_capability_channel"},
    "CAR.ads_mode": {"slot_id": "CPS_1", "quadrants": ["CPS"], "channel": "observable_vehicle_mode"},
    "CAR.reported_intervention": {"slot_id": "CPS_1", "quadrants": ["CPS"], "channel": "reported_control_transition"},
    "CAR.reported_system_issue": {"slot_id": "CPB_1", "quadrants": ["CPB"], "channel": "reported_system_issue"},
    "CAR.perception_confidence": {"slot_id": "CPB_1", "quadrants": ["CPB"], "channel": "reported_ads_capability"},
    "CAR.planner_confidence": {"slot_id": "CPB_1", "quadrants": ["CPB"], "channel": "reported_ads_capability"},
    "CAR.lane_keeping_behavior": {"slot_id": "CPS_1", "quadrants": ["CPS", "CPB"], "channel": "observable_vehicle_behavior"},
    "CAR.deceleration_behavior": {"slot_id": "CPS_1", "quadrants": ["CPS", "CPB"], "channel": "observable_vehicle_behavior"},
    "CAR.automation_context": {"slot_id": "CPS_1", "quadrants": ["CPS"], "channel": "observable_vehicle_mode"},
    "CAR.event_type": {"slot_id": "OPB_1", "quadrants": ["OPB"], "channel": "traffic_interaction_channel"},
    "CAR.time_budget_to_handover": {"slot_id": "CPS_1", "quadrants": ["CPS"], "channel": "hmi_timing_channel"},
    "ENV.visibility": {"slot_id": "OPS_1", "quadrants": ["OPS"], "channel": "environment_visibility"},
    "ENV.weather": {"slot_id": "OPS_1", "quadrants": ["OPS"], "channel": "weather_channel"},
    "ENV.road_geometry": {"slot_id": "OPS_1", "quadrants": ["OPS"], "channel": "geometry_channel"},
    "ENV.lane_topology": {"slot_id": "OPS_1", "quadrants": ["OPS"], "channel": "geometry_channel"},
    "ENV.markings_quality": {"slot_id": "OPS_1", "quadrants": ["OPS"], "channel": "infrastructure_channel"},
    "ENV.construction_state": {"slot_id": "OPS_1", "quadrants": ["OPS"], "channel": "infrastructure_channel"},
    "ENV.cut_in_event": {"slot_id": "OPB_1", "quadrants": ["OPB"], "channel": "traffic_interaction_channel"},
    "ENV.intersection_type": {"slot_id": "OPS_1", "quadrants": ["OPS"], "channel": "geometry_channel"},
    "ENV.pedestrian_crossing_event": {"slot_id": "OPB_1", "quadrants": ["OPB"], "channel": "vru_interaction_channel"},
    "ACTOR.primary_type": {"slot_id": "OPB_1", "quadrants": ["OPB"], "channel": "actor_type_channel"},
    "ACTOR.primary_intent": {"slot_id": "OPB_1", "quadrants": ["OPB"], "channel": "actor_intent_channel"},
    "ACTOR.primary_observability": {"slot_id": "OPB_1", "quadrants": ["OPB"], "channel": "actor_observability_channel"},
    "ACTOR.secondary_pressure": {"slot_id": "OPB_1", "quadrants": ["OPB"], "channel": "traffic_pressure_channel"},
    "ACTOR.prediction_uncertainty": {"slot_id": "OPB_1", "quadrants": ["OPB"], "channel": "actor_prediction_channel"},
    "CABIN.pressure": {"slot_id": "CPS_1", "quadrants": ["CPS"], "channel": "driver_context_reported"},
    "CABIN.distraction": {"slot_id": "CPS_1", "quadrants": ["CPS"], "channel": "driver_context_reported"},
}

NARRATIVE_PROPOSITION_PROMPT = """\
You extract free-text evidence propositions from automated-driving incident narratives.

Do not classify into fixed option values. Extract only facts stated by the source text.
Do not infer driver psychology, HMI behavior, ADS internal state, or timing unless explicitly stated.
Each proposition must preserve a source_span from the narrative.

Map each proposition to STPA-HF process-model relevance only when justified:
- CPS: driver process-model hypothesis about current ADS/vehicle/control-transfer state.
- CPB: driver process-model hypothesis about future ADS/vehicle behavior or capability.
- OPS: driver process-model hypothesis about current environment/other-process state.
- OPB: driver process-model hypothesis about future behavior of other actors/processes.

Return exactly:
{
  "extracted_propositions": [
    {
      "proposition_id": "N1",
      "source_span": "...",
      "proposition": "...",
      "event_phase": "...",
      "who_or_what": "...",
      "action_or_state": "...",
      "stpa_hf_relevance": {
        "quadrants": ["CPS"],
        "rationale": "..."
      },
      "evidence_role": "supports | weakly_supports | blocks | context",
      "uncertainty": "low | medium | high"
    }
  ],
  "non_inferable_items": ["..."]
}
"""

ROLE_DISAMBIGUATION_PROMPT = """\
You are an evidence-bounded automated-driving incident role-disambiguation judge.

Your task is to reconcile a raw incident narrative with structured ENV / ACTOR / CAR fields.

Identify which entity each reported state or behavior belongs to:
- ego automated vehicle
- conflict actor
- pedestrian/cyclist/other road user
- environment or scene-level state
- unknown / not inferable

You must not infer HMI state, driver mental state, legal responsibility, or true accident cause.
You must not infer internal ADS confidence, driver distraction, cabin pressure, or time budget unless the source text explicitly states it.

Only use explicit source spans from the raw narrative or structured fields. If the narrative does not support a field correction, mark it as not_inferable.

Return JSON only:
{
  "case_id": "...",
  "role_disambiguation_result": {
    "ego_vehicle": {"reported_states": [{"state_or_behavior": "...", "source_span": "...", "certainty": "high|medium|low"}]},
    "conflict_actor": {"reported_states": [{"state_or_behavior": "...", "source_span": "...", "certainty": "high|medium|low"}]},
    "scene_level_states": [{"state_or_behavior": "...", "source_span": "...", "certainty": "high|medium|low"}]
  },
  "field_adjudications": [
    {
      "field_path": "ACTOR.primary_intent",
      "current_value": "...",
      "adjudication": "supported|misassigned|unsupported|not_inferable",
      "corrected_owner": "ego_vehicle|conflict_actor|scene_level|unknown",
      "corrected_value": "... or null",
      "source_span": "... or null",
      "reasoning": "..."
    }
  ],
  "proposed_field_updates": [
    {
      "field_path": "ACTOR.primary_intent",
      "new_value": "...",
      "provenance": "reported_narrative",
      "source_span": "...",
      "certainty": "high|medium|low",
      "update_allowed": true
    }
  ],
  "blocked_inferences": [{"claim": "...", "reason": "not supported by source narrative"}]
}
"""

SEMANTIC_WARNING_AUDIT_PROMPT = """\
You are an STPA-HF semantic audit judge for driver process-model tabletop replay.

You will receive one structurally flagged UCA pathway.

Classify whether the warning represents:
1. true_generic_expansion: template-like candidate generation without case-specific evidence or gate rationale,
2. properly_gated_blocked_hypothesis: a case-specific hypothesis that is explicitly blocked by the evidence gate,
3. under_supported_abductive_candidate: a plausible candidate with weak but non-empty case-specific chain support,
4. overreaching_positive_claim: the output promotes a positive UCA/action claim without enough evidence,
5. needs_human_review: source evidence is conflicting or too ambiguous.

Use only the supplied evidence items, PM nodes, update nodes, action node, UCA pathway, gate result, blocked reasons, and source narrative.
Do not infer true driver psychology, true accident causality, HMI presence, or legal responsibility.
Do not treat collision or disengagement outcome as UCA activation evidence.

Return JSON only:
{
  "case_id": "...",
  "pathway_id": "...",
  "uca_id": "...",
  "linked_action_id": "...",
  "semantic_warning_class": "true_generic_expansion|properly_gated_blocked_hypothesis|under_supported_abductive_candidate|overreaching_positive_claim|needs_human_review",
  "is_true_warning": true,
  "severity": "none|low|medium|high",
  "semantic_verdict": "...",
  "evidence_assessment": {
    "has_case_specific_evidence": true,
    "has_pm_update_action_chain": true,
    "uses_outcome_as_activation_evidence": false,
    "uses_not_reported_as_positive_fact": false,
    "has_valid_blocking_reason": true
  },
  "supporting_evidence_ids": ["..."],
  "missing_evidence_ids": ["..."],
  "source_spans": ["..."],
  "recommended_treatment": "keep_as_ranked_pathway|keep_as_blocked_claim_only|remove_from_candidate_space|send_to_human_review",
  "reasoning": "..."
}
"""

NARRATIVE_QUADRANT_TO_SLOT = {"CPS": "CPS_1", "CPB": "CPB_1", "OPS": "OPS_1", "OPB": "OPB_1"}


def build_evidence_items(event: Dict[str, Any], event_index: int = 0) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for dotted, meta in FIELD_MAP.items():
        group, field_name = dotted.split(".", 1)
        raw = get_path(event, dotted, None)
        wrapped = wrap_if_plain(raw)
        evidence_id = f"E{event_index + 1:02d}-{group}-{field_name}"
        item = {
            "evidence_id": evidence_id,
            "event_index": event_index,
            "source_group": group,
            "field": field_name,
            "field_path": dotted,
            "value": wrapped.get("value"),
            "provenance": wrapped.get("provenance", "reported"),
            "visibility": wrapped.get("visibility", "source_reported"),
            "certainty": wrapped.get("certainty", "high"),
            "source_text": wrapped.get("source_text", ""),
            "derivation_basis": wrapped.get("derivation_basis", ""),
            "is_driver_visible": wrapped.get("is_driver_visible", "unknown"),
            "use_as_negative_evidence": bool(wrapped.get("use_as_negative_evidence", False)),
            "timestamp_ms": wrapped.get("timestamp_ms"),
            "persistence_ms": wrapped.get("persistence_ms"),
            "slot_id": meta["slot_id"],
            "quadrant_targets": meta["quadrants"],
            "channel": meta["channel"],
        }
        if item["provenance"] not in ALLOWED_PROVENANCE:
            raise DataCurationError(f"Invalid provenance for {evidence_id}: {item['provenance']}")
        items.append(item)
    for prop in event.get("narrative_propositions", []) or []:
        quadrants = prop.get("stpa_hf_relevance", {}).get("quadrants") or []
        quadrants = [q for q in quadrants if q in ALLOWED_QUADRANTS]
        if not quadrants:
            continue
        primary_q = quadrants[0]
        pid = str(prop.get("proposition_id") or f"N{len(items)+1}")
        evidence_id = f"E{event_index + 1:02d}-NARR-{pid}"
        item = {
            "evidence_id": evidence_id,
            "event_index": event_index,
            "source_group": "NARRATIVE",
            "field": pid,
            "field_path": f"NARRATIVE.{pid}",
            "value": prop.get("proposition"),
            "provenance": "reported_narrative",
            "visibility": "source_reported",
            "certainty": prop.get("uncertainty", "medium"),
            "source_text": prop.get("source_span", ""),
            "derivation_basis": prop.get("stpa_hf_relevance", {}).get("rationale", ""),
            "is_driver_visible": "unknown",
            "use_as_negative_evidence": False,
            "timestamp_ms": None,
            "persistence_ms": None,
            "slot_id": NARRATIVE_QUADRANT_TO_SLOT[primary_q],
            "quadrant_targets": quadrants,
            "channel": "free_text_narrative_proposition",
            "event_phase": prop.get("event_phase", "unknown"),
            "who_or_what": prop.get("who_or_what", ""),
            "action_or_state": prop.get("action_or_state", ""),
            "evidence_role": prop.get("evidence_role", "supports"),
        }
        items.append(item)
    return items


def map_evidence_items_to_slots(evidence_items: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    slots = {
        "CPS_1": {"slot_id": "CPS_1", "quadrant": "CPS", "evidence_items": [], "evidence_summaries": []},
        "CPB_1": {"slot_id": "CPB_1", "quadrant": "CPB", "evidence_items": [], "evidence_summaries": []},
        "OPS_1": {"slot_id": "OPS_1", "quadrant": "OPS", "evidence_items": [], "evidence_summaries": []},
        "OPB_1": {"slot_id": "OPB_1", "quadrant": "OPB", "evidence_items": [], "evidence_summaries": []},
    }
    for item in evidence_items:
        target_slots = [item.get("slot_id")]
        if item.get("source_group") == "NARRATIVE":
            target_slots = [NARRATIVE_QUADRANT_TO_SLOT[q] for q in item.get("quadrant_targets", []) if q in NARRATIVE_QUADRANT_TO_SLOT]
        for slot_id in target_slots:
            if slot_id not in slots:
                continue
            summary = f"{item['evidence_id']}: {item['field_path']}={item['value']} [provenance={item['provenance']}, visibility={item['visibility']}, certainty={item['certainty']}]"
            slots[slot_id]["evidence_items"].append(item)
            slots[slot_id]["evidence_summaries"].append(summary)
    return slots


def build_visible_evidence_packet_from_items(evidence_items: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_group: Dict[str, List[str]] = defaultdict(list)
    for item in evidence_items:
        if item["provenance"] == "not_reported":
            continue
        by_group[item["source_group"]].append(f"{item['field']}={item['value']} ({item['provenance']})")
    return {
        "env_summary": "; ".join(by_group.get("ENV", [])) or "No source-reported ENV evidence.",
        "actor_summary": "; ".join(by_group.get("ACTOR", [])) or "No source-reported ACTOR evidence.",
        "car_summary": "; ".join(by_group.get("CAR", [])) or "No source-reported CAR/ADS evidence.",
        "hmi_summary": "; ".join(by_group.get("HMI", [])) or "No source-reported HMI evidence; do not infer HMI state.",
        "cabin_summary": "; ".join(by_group.get("CABIN", [])) or "No source-reported cabin/driver-state evidence; do not infer driver state.",
    }


def build_source_evidence_audit(evidence_items: List[Dict[str, Any]]) -> Dict[str, Any]:
    counts = Counter(item["provenance"] for item in evidence_items)
    hmi_reported = any(i["source_group"] == "HMI" and i["provenance"] == "reported" for i in evidence_items)
    cabin_reported = any(i["source_group"] == "CABIN" and i["provenance"] == "reported" for i in evidence_items)
    car_reported = any(i["source_group"] == "CAR" and i["provenance"] == "reported" for i in evidence_items)
    return {
        "reported_field_count": counts.get("reported", 0),
        "derived_field_count": counts.get("derived", 0),
        "not_reported_field_count": counts.get("not_reported", 0),
        "counterfactual_assumption_count": counts.get("assumed_for_counterfactual", 0),
        "hmi_reported": hmi_reported,
        "driver_state_reported": cabin_reported,
        "car_ads_fields_reported": car_reported,
        "not_reported_is_not_absence": True,
    }


def build_evidence_packet(event: Dict[str, Any], driver_profile: Dict[str, Any], event_index: int = 0) -> Dict[str, Any]:
    evidence_items = build_evidence_items(event, event_index=event_index)
    slot_pack = map_evidence_items_to_slots(evidence_items)
    visible_packet = build_visible_evidence_packet_from_items(evidence_items)
    audit = build_source_evidence_audit(evidence_items)
    return {
        "schema_version": SCHEMA_VERSION,
        "event_index": event_index,
        "evidence_items": evidence_items,
        "driver_visible_slot_evidence_pack": slot_pack,
        "visible_evidence_packet": visible_packet,
        "source_evidence_audit": audit,
        "event_factor_envelope": {
            "driver_profile": driver_profile,
            "missingness_policy": {
                "not_reported_is_not_absence": True,
                "forbid_hmi_imputation": True,
                "forbid_driver_state_imputation": True,
                "forbid_internal_ads_imputation": True,
            },
        },
    }


class LLMClient:
    def __init__(self, api_key: str, model: str, base_url: str, timeout_s: int = 180):
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is required")
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s

    @classmethod
    def from_env(cls) -> "LLMClient":
        return cls(
            api_key=os.environ.get("OPENAI_API_KEY", "").strip(),
            model=os.environ.get("OPENAI_MODEL", "qwen-max-latest"),
            base_url=os.environ.get("OPENAI_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
            timeout_s=int(os.environ.get("OPENAI_TIMEOUT_S", "180")),
        )

    def chat_text(self, messages: List[Dict[str, str]], temperature: float = 0.0) -> str:
        url = f"{self.base_url}/chat/completions"
        payload = {"model": self.model, "messages": messages, "temperature": temperature}
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        last_err = None
        for attempt in range(5):
            try:
                resp = requests.post(url, headers=headers, json=payload, timeout=(10, self.timeout_s))
                if resp.status_code in {429, 500, 502, 503, 504}:
                    last_err = f"HTTP {resp.status_code}"
                    time.sleep(min(2 ** attempt, 12))
                    continue
                if resp.status_code >= 400:
                    raise RuntimeError(f"LLM API error {resp.status_code}: {resp.text[:500]}")
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                if isinstance(content, list):
                    return "\n".join(str(x.get("text", x)) if isinstance(x, dict) else str(x) for x in content).strip()
                return str(content).strip()
            except requests.RequestException as exc:
                last_err = repr(exc)
                time.sleep(min(2 ** attempt, 12))
        raise RuntimeError(f"LLM request failed: {last_err}")

    def chat_json_strict(self, messages: List[Dict[str, str]], required_keys: List[str], validator=None, temperature: float = 0.0, retries: int = 2) -> Dict[str, Any]:
        """JSON/API repair is allowed; semantic defaults are not."""
        errors: List[str] = []
        cur_messages = list(messages)
        for _ in range(retries + 1):
            text = self.chat_text(cur_messages, temperature=temperature)
            try:
                obj = extract_json_object(text)
                missing = [k for k in required_keys if k not in obj]
                if missing:
                    raise SchemaValidationError(f"Missing required keys: {missing}")
                if validator:
                    validator(obj)
                return obj
            except Exception as exc:
                errors.append(str(exc))
                cur_messages = cur_messages + [{"role": "user", "content": f"Invalid JSON/schema. Re-output valid JSON only. Error: {exc}"}]
        raise SchemaValidationError("LLM JSON/schema failed after retries: " + " | ".join(errors[-3:]))


def extract_json_object(text: str) -> Dict[str, Any]:
    text = text.strip()
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass
    start = text.find("{")
    if start < 0:
        raise ValueError("No JSON object found")
    depth, in_str, esc = 0, False, False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                obj = json.loads(text[start : i + 1])
                if not isinstance(obj, dict):
                    raise ValueError("Top-level JSON is not an object")
                return obj
    raise ValueError("Unbalanced JSON")


def make_messages(system_prompt: str, payload: Dict[str, Any]) -> List[Dict[str, str]]:
    return [{"role": "system", "content": system_prompt}, {"role": "user", "content": json.dumps(payload, ensure_ascii=False, indent=2)}]


SHARED_SYSTEM_PROMPT = """\
You are participating in an STPA-HF-guided driver process-model tabletop replay pipeline for human-automation co-driving incidents.

Core commitments:
- Use only source-visible and driver-visible evidence provided in evidence_items.
- Treat not_reported as absence of source evidence, not evidence of absence.
- Do not infer HMI state, driver mental state, or internal ADS variables when they are not reported.
- Do not infer takeover failure from crash/collision outcome alone.
- For crash/collision cases, not_supported_transfer requires explicit source-reported transition/intervention evidence such as disengagement, takeover demand, driver/operator intervention, support withdrawal, or transition requirement.
- Maintain stage separation: PM context synthesis, process-model update, other-factor extraction, driver replay posture selection, action selection, UCA context classification, and pathway ranking remain separate.
- UCA classification uses the full driver-centered catalog; the driver replay posture is context, not a catalog filter.
- Reported collision/disengagement/intervention outcome is a compatibility constraint, not UCA activation evidence.
- The output is a tabletop replay package for safety analysis and improvement planning, not a unique accident-cause reconstruction.
- Return only valid JSON. No markdown.
"""

ROUND1_PROMPT = SHARED_SYSTEM_PROMPT + """\

Round 1: bounded prior formation only.
Return exactly this JSON structure (no markdown, no extra keys):
{
  "prior_formation_mode": "bounded_prior",
  "pm_prior": [
    {"slot_id": "CPS_1", "quadrant": "CPS", "prior_belief": "...", "prior_strength": "moderate", "formation_basis": "..."},
    {"slot_id": "CPB_1", "quadrant": "CPB", "prior_belief": "...", "prior_strength": "moderate", "formation_basis": "..."},
    {"slot_id": "OPS_1", "quadrant": "OPS", "prior_belief": "...", "prior_strength": "moderate", "formation_basis": "..."},
    {"slot_id": "OPB_1", "quadrant": "OPB", "prior_belief": "...", "prior_strength": "moderate", "formation_basis": "..."}
  ],
  "prior_formation_summary": "..."
}
pm_prior must contain exactly 4 entries, one per quadrant (CPS, CPB, OPS, OPB). prior_formation_mode must always be "bounded_prior".
Do not use current-event evidence to select boundary or UCA.
"""

ROUND2A_PROMPT = SHARED_SYSTEM_PROMPT + """\

Round 2A: posterior PM update only.
Update each prior slot using only driver_visible_slot_evidence_pack and evidence_items.
Each quadrant update must be an evidence-grounded driver process-model hypothesis, not a claim about true driver psychology.
If the accident text does not report evidence for a quadrant, mark the hypothesis weak/blocked/unchanged; do not infer from the crash outcome.
Return exactly: slot_updates, integrated_update_summary.

Each slot_updates item must include:
- slot_id
- quadrant
- posterior_update_paragraph
- supporting_evidence_ids: list of evidence_id values used for the update
- pm_hypothesis_status: supported | weakly_supported | blocked | unchanged
- evidence_grounding_level: direct | indirect | absent
- unsupported_inference_warning: boolean
- slot_belief_state with exactly:
  belief_polarity: supportive | neutral | contradictory
  belief_confidence: high | medium | low | uncertain
  update_direction: strengthened | unchanged | weakened | reversed
  retained_support_ratio: float 0.0-1.0
  tension_type: none | capability_tension | mode_tension | actor_tension | env_tension
  tension_severity: none | mild | moderate | severe
- slot_update_vulnerability:
  vulnerability_type: none | missed_feedback | ambiguous_feedback | misinterpreted_feedback
  supporting_evidence_ids: list of evidence_id values
  rationale: string

Do not name driver replay postures, select actions, assign UCA, or infer missing HMI/driver/internal ADS details.
"""

ROUND2B_PROMPT = SHARED_SYSTEM_PROMPT + """\

Round 2B: driver replay posture selection only.
Select the minimal sufficient FSM state from posterior PM content.
Return exactly:
- ads_reliance_basis: supported | contingent | not_supported
- committed_posture: heightened_monitoring | readiness_formed | transfer_initiated
- selected_action_code: continue_monitoring | prepare_takeover | initiate_takeover
- commitment_block: object with basis_explanation, minimal_sufficiency_basis, boundary_rationale, supporting_evidence_ids.

Boundary discipline:
- supported_monitoring: ADS basis visibly/source-supported; external uncertainty alone does not justify readiness.
- contingent_readiness: ADS conditionally supportable and visible/source evidence creates preparation pressure.
- not_supported_transfer: explicit transition demand, source-reported intervention, or visible withdrawal of ADS support.
- crash, collision, stopped vehicle, rear-end contact, or deceleration alone never justify not_supported_transfer.
- In crash/collision cases, never choose not_supported_transfer from crash outcome, collision severity, actor conflict, or deceleration alone.
- To choose not_supported_transfer, cite evidence_ids for explicit transition/intervention/support-withdrawal evidence. If those fields are not_reported, choose the weaker evidence-bounded boundary.
Explain why weaker and stronger neighboring boundaries are excluded.
Do not output mechanism, UCA, or design recommendations.
"""

ROUND2C_PROMPT = SHARED_SYSTEM_PROMPT + """\

Round 2C: mechanism translation only.
Return exactly: mechanism_paragraph, supporting_evidence_ids.
Trace evidence -> slot belief changes -> committed FSM state.
Do not revise the boundary or assign UCA.
"""

LEGACY_ROUND3_UCA_PROMPT = SHARED_SYSTEM_PROMPT + """\

Legacy Round 3 UCA activation prompt retained only for old-result inspection.
Given committed_fsm_state, PM update pattern, update_vulnerability_causal_map, and the full driver-centered uca_catalog,
activate/suppress only UCAs from the provided catalog. The FSM state is context, not a catalog filter.
Return exactly:
- committed_fsm_state
- activated_ucas: list of objects with uca_id, is_active=true, activation_reason, causal_factor_trace, supporting_evidence_ids
- suppressed_ucas: list of objects with uca_id, is_active=false, suppression_reason, supporting_evidence_ids
- dominant_uca: uca_id
- dominant_uca_rationale
- pm_mismatch_pattern
Do not invent UCAs outside the catalog. Do not revise the committed boundary.
"""

LEGACY_PATHWAY_JUDGE_PROMPT = SHARED_SYSTEM_PROMPT + """\

You are an STPA-HF pathway judge.
Score candidate pathways for an automated-driving incident using only supplied evidence and STPA-HF structure.

Important boundary:
- Scores are evidence-conditioned explanatory plausibility, not true causal probabilities.
- Do not reward a pathway that infers true driver mental state without evidence.
- A crash/collision outcome alone cannot support takeover failure.
- A UCA must be a driver control action in an unsafe context, consistent with STPA categories.
- A pathway should be "admissible" only if its STPA-HF compliance gates support PM variables, update process, action selection, UCA context, and evidence admissibility without using not_reported evidence as fact.
- Use "weakly_supported" for plausible but incomplete pathways.
- Use "blocked" for pathways where takeover demand, action evidence, timing, driver response, update process, or UCA context is missing.

Return exactly:
{
  "judged_pathways": [
    {
      "pathway_id": "...",
      "rubric_scores": {
        "evidence_text_grounding": 0.0,
        "quadrant_mapping_validity": 0.0,
        "vulnerability_definition_fit": 0.0,
        "boundary_fsm_validity": 0.0,
        "uca_stpa_validity": 0.0,
        "outcome_compatibility": 0.0,
        "missingness_penalty": 0.0,
        "overclaim_penalty": 0.0,
        "safe_intervention_consistency": 0.0
      },
      "node_level_scores": {
        "evidence_to_quadrant": 0.0,
        "quadrant_to_vulnerability": 0.0,
        "vulnerability_to_boundary": 0.0,
        "boundary_to_uca": 0.0,
        "uca_to_outcome": 0.0
      },
      "pathway_score": 0.0,
      "pathway_status": "admissible | weakly_supported | blocked",
      "judge_rationale": "..."
    }
  ],
  "ranking_summary": "..."
}
All numeric rubric and node-level values must be between 0 and 1. Penalty fields are penalty magnitudes, not negative numbers.
"""

DIRECT_BASELINE_PROMPT = SHARED_SYSTEM_PROMPT + """\

Baseline: direct boundary and dominant UCA inference from functional evidence only.
Return exactly this JSON (no markdown):
{
  "commitment_state_fsm": "<one of: supported_monitoring | contingent_readiness | not_supported_transfer>",
  "uca_activation_status": "activated | no_activated_uca",
  "dominant_uca": "<uca_id from the supplied driver-centered uca_catalog, e.g. UCA-H-1, UCA-H-2>",
  "rationale": "..."
}
Use only the supplied driver-centered UCA catalog and evidence_items. If no source-supported UCA is activated, set uca_activation_status to "no_activated_uca" and dominant_uca to null. If a UCA is activated, dominant_uca must be a valid uca_id from the catalog; the chosen commitment_state_fsm is context and must not filter the catalog.
"""

GENERIC_COT_BASELINE_PROMPT = SHARED_SYSTEM_PROMPT + """\

Baseline: generic step-by-step reasoning without STPA-HF round separation.
Think step by step, then return exactly this JSON (no markdown):
{
  "commitment_state_fsm": "<one of: supported_monitoring | contingent_readiness | not_supported_transfer>",
  "uca_activation_status": "activated | no_activated_uca",
  "dominant_uca": "<uca_id from the supplied driver-centered uca_catalog, e.g. UCA-H-1, UCA-H-2>",
  "rationale": "..."
}
Use only the supplied driver-centered UCA catalog and evidence_items. If no source-supported UCA is activated, set uca_activation_status to "no_activated_uca" and dominant_uca to null. If a UCA is activated, dominant_uca must be a valid uca_id from the catalog; the chosen commitment_state_fsm is context and must not filter the catalog.
"""

STRUCTURED_PROMPT_ONLY_BASELINE_PROMPT = SHARED_SYSTEM_PROMPT + """\

Baseline: structured incident-review prompt without STPA-HF driver process-model gates.
Use the supplied evidence_items to make a structured safety-review judgment, but do not use CPS/CPB/OPS/OPB terminology, process-model update gates, or blocked-claim gates.
Return exactly this JSON (no markdown):
{
  "commitment_state_fsm": "<one of: supported_monitoring | contingent_readiness | not_supported_transfer>",
  "uca_activation_status": "activated | no_activated_uca",
  "dominant_uca": "<uca_id from the supplied driver-centered uca_catalog, e.g. UCA-H-1, UCA-H-2>",
  "rationale": "..."
}
Use only the supplied driver-centered UCA catalog and evidence_items. If no source-supported UCA is activated, set uca_activation_status to "no_activated_uca" and dominant_uca to null. If a UCA is activated, dominant_uca must be a valid uca_id from the catalog; the chosen commitment_state_fsm is context and must not filter the catalog.
"""

PM_CONTEXT_SYNTHESIS_PROMPT = SHARED_SYSTEM_PROMPT + """\

Round 1: STPA-HF process-model variable synthesis only.
Use evidence_items plus narrative propositions to produce exactly four driver process-model variable nodes:
CPS, CPB, OPS, OPB.

STPA-HF discipline:
- These nodes are not ordinary scene summaries. They represent what a driver/safety operator would need to believe about controlled-process state, controlled-process behavior, other-process state, and other-process behavior to choose a control action.
- Separate reported_context from driver_belief_requirement. A source fact does not prove the driver's actual belief.
- Generate process-model flaw hypotheses only as observed, abductive_candidate, or blocked. Collision/disengagement outcome alone cannot prove a PM flaw.
- not_reported evidence is missing evidence, not evidence of absence.
- Do not write "driver was unaware", "driver failed to notice", "driver misunderstood", or equivalent true-psychology claims. Write "driver-visible evidence is not verifiable from the report" instead.
- Do not write "collision suggests ADS behavioral anomaly". Collision is a terminal outcome and cannot support a CPB flaw by itself.
- Do not choose a boundary, action, UCA, or accident cause.

Return exactly:
{
  "pm_context_nodes": [
    {
      "node_id": "PM-CPS-1",
      "dimension": "CPS",
      "dimension_definition": "Controlled Process States",
      "reported_context": "...",
      "driver_belief_requirement": "...",
      "observed_belief_evidence_ids": [],
      "missing_belief_evidence_ids": [],
      "belief_uncertainty": "low | medium | high",
      "pm_flaw_hypotheses": [
        {
          "flaw_id": "PMF-CPS-1",
          "flaw_type": "incomplete_belief | incorrect_belief | outdated_belief | unverified_belief | none_supported",
          "claim_status": "observed | abductive_candidate | blocked",
          "supporting_evidence_ids": [],
          "missing_evidence_ids": [],
          "blocked_claims": [],
          "rationale": "..."
        }
      ],
      "context_hypothesis": "...",
      "internal_reasoning_text": "...",
      "display_summary": "...",
      "supporting_evidence_ids": [],
      "contradicting_evidence_ids": [],
      "missing_evidence_ids": [],
      "claim_strength": "supported | weakly_supported | blocked"
    }
  ],
  "integrated_pm_context_text": "..."
}
Return one node for each dimension: CPS, CPB, OPS, OPB.
"""

PROCESS_MODEL_UPDATE_PROMPT = SHARED_SYSTEM_PROMPT + """\

Round 2A: STPA-HF process-model update analysis only.
Given PM variable nodes and evidence_items, analyze how each process-model belief could be initially formed or later updated.
Do not select a boundary, do not select a control action, do not classify UCA.

STPA-HF discipline:
- Process-model update is not equal to HMI. Consider feedback, non-feedback inputs, observation, training/documentation, vehicle behavior, external visual scene, actor behavior, direct control/action feedback, and reported intervention/disengagement.
- Target the four PM variables separately:
  * UPD-CPS: how the driver's belief about ADS/vehicle/control-authority current state is formed/updated.
  * UPD-CPB: how the driver's belief about ADS/vehicle future behavior and capability is formed/updated.
  * UPD-OPS: how the driver's belief about current external environment state is formed/updated.
  * UPD-OPB: how the driver's belief about other traffic participants' future behavior is formed/updated.
- observed_update_issue requires direct source evidence. Missing HMI/time budget/driver state can only support abductive_update_hypotheses or blocked_update_claims.
- Do not claim true driver cognition.
- In most sparse accident reports, observed_update_issue.label and observed_update_vulnerability.label should be "none". Use a non-none observed label ONLY when the report directly states that a warning/feedback was missed, ignored, delayed, misunderstood, conflicting, or unavailable to the driver/operator.
- Missing evidence IDs must never support observed_update_issue or observed_update_vulnerability. Put missingness-based concerns only in abductive_update_hypotheses, evidence_gap_update_risk, or blocked_update_claims.

Return exactly:
{
  "update_process_nodes": [
    {
      "node_id": "UPD-CPS-1",
      "target_pm_dimensions": ["CPS"],
      "target_quadrant": "CPS",
      "target_belief": "...",
      "formation_question": "...",
      "later_update_question": "...",
      "formation_sources": [],
      "later_update_sources": [],
      "observed_sources_in_report": [],
      "missing_sources": [],
      "observability_assessment": "reported | partially_reported | not_reported",
      "interpretability_assessment": "reported | partially_reported | not_reported",
      "timing_assessment": "reported | partially_reported | not_reported",
      "observed_update_issue": {
        "label": "none",
        "supporting_evidence_ids": [],
        "rationale": "..."
      },
      "abductive_update_hypotheses": [
        {
          "hypothesis_id": "UPDH-CPS-1",
          "label": "missed_feedback | ambiguous_feedback | misinterpreted_feedback",
          "supporting_evidence_ids": [],
          "missing_evidence_ids": [],
          "rationale": "..."
        }
      ],
      "blocked_update_claims": [],
      "triggering_evidence_ids": [],
      "feedback_or_input_text": "...",
      "update_need": "...",
      "update_path": {
        "initial_formation_sources": [],
        "later_update_sources": [],
        "availability": "reported | not_reported | unclear | not_admissible_from_report",
        "observability": "reported | not_reported | unclear | not_admissible_from_report",
        "salience": "high | medium | low | not_reported | not_admissible_from_report",
        "timing": "reported | not_reported | unclear | not_admissible_from_report",
        "interpretability": "clear | partial | ambiguous | not_reported | not_admissible_from_report",
        "consistency": "consistent | conflicting | not_reported | unclear | not_admissible_from_report"
      },
      "observed_update_vulnerability": {
        "label": "none",
        "supporting_evidence_ids": [],
        "rationale": "..."
      },
      "evidence_gap_update_risk": {
        "labels": ["missing_hmi_feedback | missing_time_budget | missing_driver_state | missing_internal_ads_state | missing_actor_observability | missing_action_feedback"],
        "gap_evidence_ids": [],
        "rationale": "..."
      },
      "update_evidence_status": "observed_update_claim | evidence_gap_only | not_admissible",
      "pm_flaw_hypothesis": "incomplete | incorrect | delayed | unknown | no_flaw_supported",
      "internal_reasoning_text": "...",
      "display_summary": "...",
      "claim_strength": "supported | weakly_supported | blocked",
      "claim_status": "observed | abductive_candidate | blocked",
      "missingness_notes": []
    }
  ],
  "integrated_update_text": "..."
}
Return at least one update node for each target_quadrant: CPS, CPB, OPS, OPB.
"""

OTHER_FACTORS_PROMPT = SHARED_SYSTEM_PROMPT + """\

Round 2B: other factors analysis only.
Extract non-PM conditions that may affect control-action selection, such as time pressure, workload, driver role, protocol, traffic pressure, maneuver constraint, or fallback availability.
Do not infer absent factors from the outcome.
Do not choose a boundary, do not choose a control action, do not classify UCA.
Use factor_type only from:
time_pressure, workload, driver_role, test_protocol, manual_fallback_availability, traffic_pressure, maneuver_constraint, safe_stop_target, control_authority_availability, distraction, impairment, prediction_uncertainty, actor_prediction_uncertainty, system_recommendation_pressure, other.
Return exactly:
{
  "other_factor_nodes": [
    {
      "node_id": "OF-1",
      "factor_type": "time_pressure",
      "description": "...",
      "supporting_evidence_ids": [],
      "effect_on_action_selection": "...",
      "internal_reasoning_text": "...",
      "display_summary": "...",
      "claim_strength": "supported | weakly_supported | blocked"
    }
  ],
  "missing_other_factors": [
    {
      "factor_type": "driver_distraction",
      "missing_reason": "not reported in source text"
    }
  ],
  "integrated_other_factors_text": "..."
}
"""

COMMITMENT_BOUNDARY_PROMPT = SHARED_SYSTEM_PROMPT + """\

Round 2C: driver replay posture selection only.
Select the minimal sufficient FSM state from the PM context and update analysis.
Do not classify UCA and do not infer control action beyond the selected boundary posture.
The basis/posture/action tuple must be one of:
- supported, heightened_monitoring, continue_monitoring
- contingent, readiness_formed, prepare_takeover
- not_supported, transfer_initiated, initiate_takeover
Return exactly:
{
  "ads_reliance_basis": "supported | contingent | not_supported",
  "committed_posture": "heightened_monitoring | readiness_formed | transfer_initiated",
  "selected_action_code": "continue_monitoring | prepare_takeover | initiate_takeover",
  "commitment_block": {
    "basis_explanation": "...",
    "minimal_sufficiency_basis": "...",
    "boundary_rationale": "...",
    "supporting_evidence_ids": []
  },
  "boundary_internal_text": "..."
}
"""

CONTROL_ACTION_SELECTION_PROMPT = SHARED_SYSTEM_PROMPT + """\

Round 2D: multi-candidate control-action selection only.
Given PM variables, PM flaw hypotheses, update hypotheses, other factors, and the committed boundary, identify multiple plausible driver/safety-operator control-action hypotheses.
Do not classify UCA yet. Do not infer an action from collision/disengagement outcome alone.
Use candidate_action only from:
continue_monitoring, prepare_takeover, initiate_takeover, initiate_intervention, maintain_no_intervention, modulate_braking, modulate_steering, safe_stop_or_minimal_risk_response.
Output 2-4 action candidates whenever evidence allows. At minimum, include:
- one action consistent with the committed boundary posture;
- one alternative/omitted action that could become a UCA hypothesis if the PM/update/action chain supports it.
Mark weak actions as abductive_candidate or blocked rather than omitting them.
Observed action rule:
- action_role=observed and claim_status=observed require direct driver/operator action evidence such as reported intervention, manual control, braking, steering, takeover, or explicit driver response.
- Do not mark continue_monitoring as observed merely because no intervention is reported. That must be abductive_candidate or blocked.
Return exactly:
{
  "action_selection_nodes": [
    {
      "node_id": "ACT-1",
      "candidate_action": "continue_monitoring | prepare_takeover | initiate_takeover | initiate_intervention | maintain_no_intervention | modulate_braking | modulate_steering | safe_stop_or_minimal_risk_response",
      "action_role": "observed | expected | omitted | alternative | blocked",
      "selection_context": "...",
      "pm_context_inputs": ["PM-CPS-1"],
      "update_process_inputs": ["UPD-1"],
      "other_factor_inputs": ["OF-1"],
      "supporting_evidence_ids": [],
      "missing_evidence_ids": [],
      "why_this_action_is_relevant": "...",
      "why_this_action_is_not_observed": "...",
      "internal_reasoning_text": "...",
      "display_summary": "...",
      "claim_strength": "supported | weakly_supported | blocked",
      "claim_status": "observed | abductive_candidate | blocked"
    }
  ],
  "integrated_action_selection_text": "..."
}
Return at least two candidate actions unless only one source-supported action is admissible.
"""

UCA_CONTEXT_CLASSIFICATION_PROMPT = SHARED_SYSTEM_PROMPT + """\

Round 3: forward-derived UCA hypothesis generation.
Given PM variables, PM flaw hypotheses, update hypotheses, other factors, and candidate action nodes, generate UCA hypotheses only from the provided full driver-centered catalog.

STPA-HF discipline:
- UCA is generated forward from PM/update/action/unsafe context. It is not inferred from the accident outcome.
- Reported outcome is only a compatibility constraint handled later; do not use it as supporting evidence.
- Classify each UCA hypothesis as observed_admissible, abductive_candidate, or blocked.
- observed_admissible requires direct source-visible driver/control-action/action-quality evidence.
- abductive_candidate is allowed when the PM/update/action chain is coherent and evidence-linked, but direct driver action evidence is missing.
- blocked is required when the chain is unsupported, contradicted, or outcome-only.
- Prefer producing a compact UCA hypothesis space rather than a single UCA. When the action nodes support them, include 2-3 UCA nodes covering monitoring, intervention/takeover timing, and manual control quality. Use blocked for unsupported branches.
- Add abductive_strength to every UCA node: strong_abductive, weak_abductive, speculative_abductive, or blocked.
- UCA-H-3 late intervention requires timing pressure, time-budget/transition cue, intervention timing, or a missing timing source. Do not generate it from generic uncertainty alone.
- UCA-H-5 manual control quality requires manual/brake/steer/control-quality evidence or an explicit manual-control evidence gap.
- UCA-H-6 safe-stop/fallback requires fallback/safe-stop context.

Return exactly:
{
  "committed_fsm_state": "supported_monitoring | contingent_readiness | not_supported_transfer",
  "uca_activation_status": "activated | no_activated_uca",
  "uca_context_nodes": [
    {
      "node_id": "UCACTX-1",
      "uca_id": "UCA-...",
      "controller": "driver | test_driver | safety_operator",
      "control_action": "...",
      "stpa_uca_type": "not_provided_when_required | provided_when_not_appropriate | too_early_too_late_or_wrong_order | wrong_duration_or_stopped_too_soon",
      "unsafe_context_text": "...",
      "hazard_link": "...",
      "action_selection_node_ids": ["ACT-1"],
      "forward_derivation": {
        "pm_flaw_inputs": [],
        "update_flaw_inputs": [],
        "action_selection_inputs": ["ACT-1"],
        "other_factor_inputs": []
      },
      "supporting_evidence_ids": [],
      "missing_evidence_ids": [],
      "required_context": [],
      "blocking_reasons": [],
      "blocked_claims": [],
      "why_not_directly_observed": "...",
      "why_not_outcome_derived": "The reported outcome is used only as compatibility constraint.",
      "internal_reasoning_text": "...",
      "display_summary": "...",
      "classification": "activated | suppressed | blocked",
      "claim_strength": "supported | weakly_supported | blocked",
      "claim_status": "observed_admissible | abductive_candidate | blocked",
      "abductive_strength": "strong_abductive | weak_abductive | speculative_abductive | blocked"
    }
  ],
  "observed_uca_set": ["UCA-..."],
  "abductive_uca_candidates": ["UCA-..."],
  "blocked_uca_set": ["UCA-..."],
  "activated_uca_set": ["UCA-..."],
  "blocked_or_suppressed_uca_set": ["UCA-..."],
  "dominant_uca": "UCA-... | null",
  "dominant_uca_rationale": "... | empty string when no UCA is activated",
  "integrated_uca_text": "..."
}

Hard boundary:
- uca_context_nodes must never be empty.
- Never use collision, crash severity, or disengagement outcome as supporting_evidence_ids for UCA.
- observed_uca_set contains only observed_admissible nodes.
- abductive_uca_candidates contains abductive_candidate nodes; these are paper-facing UCA hypotheses, not factual UCA activation.
- activated_uca_set is retained for compatibility and must equal observed_uca_set.
- If there is no observed_admissible UCA, set uca_activation_status to no_activated_uca, dominant_uca to null, and activated_uca_set to [].
"""

PATHWAY_JUDGE_PROMPT = SHARED_SYSTEM_PROMPT + """\

You are an STPA-HF pathway judge.
Score candidate pathways for an automated-driving incident using only supplied evidence and STPA-HF structure.

Important boundary:
- Scores are evidence-conditioned explanatory plausibility, not true causal probabilities.
- Do not reward a pathway that infers true driver mental state without evidence.
- A crash/collision outcome alone cannot support takeover failure.
- A UCA must be a driver control action in an unsafe context, consistent with STPA categories.

Return exactly:
{
  "judged_pathways": [
    {
      "pathway_id": "...",
      "rubric_scores": {
        "evidence_grounding": 0.0,
        "pm_context_validity": 0.0,
        "update_process_validity": 0.0,
        "other_factors_validity": 0.0,
        "action_selection_validity": 0.0,
        "uca_context_validity": 0.0,
        "outcome_compatibility": 0.0,
        "missingness_penalty": 0.0,
        "overclaim_penalty": 0.0,
        "safe_intervention_consistency": 0.0
      },
      "node_level_scores": {
        "evidence_to_pm_context": 0.0,
        "pm_context_to_update_process": 0.0,
        "update_process_to_action_selection": 0.0,
        "other_factors_to_action_selection": 0.0,
        "action_selection_to_uca_context": 0.0,
        "uca_context_to_outcome": 0.0
      },
      "pathway_score": 0.0,
      "pathway_status": "admissible | weakly_supported | blocked",
      "judge_rationale": "..."
    }
  ],
  "ranking_summary": "..."
}
All numeric rubric and node-level values must be between 0 and 1. Penalty fields are penalty magnitudes, not negative numbers.
"""


def infer_boundary_from_commitment(commitment: Dict[str, Any]) -> str:
    basis = normalize_token(commitment.get("ads_reliance_basis"))
    posture = normalize_token(commitment.get("committed_posture"))
    mapping = {
        ("supported", "heightened_monitoring"): "supported_monitoring",
        ("contingent", "readiness_formed"): "contingent_readiness",
        ("not_supported", "transfer_initiated"): "not_supported_transfer",
    }
    if (basis, posture) not in mapping:
        raise SchemaValidationError(f"Cannot infer boundary from basis/posture: {(basis, posture)}")
    return mapping[(basis, posture)]


def validate_evidence_ids(ids: Sequence[str], evidence_items: Sequence[Dict[str, Any]], field_name: str) -> None:
    known = {item["evidence_id"] for item in evidence_items}
    invalid = [x for x in ids if x not in known]
    if invalid:
        raise SchemaValidationError(f"Invalid evidence ids in {field_name}: {invalid}")


def validate_round1(obj: Dict[str, Any]) -> None:
    if obj.get("prior_formation_mode") != "bounded_prior":
        raise SchemaValidationError("Round1 prior_formation_mode must be bounded_prior")
    priors = obj.get("pm_prior")
    if not isinstance(priors, list) or len(priors) != 4:
        raise SchemaValidationError("Round1 pm_prior must be list of four slots")
    quadrants = {p.get("quadrant") for p in priors}
    if set(ALLOWED_QUADRANTS) - quadrants:
        raise SchemaValidationError(f"Round1 missing quadrants: {set(ALLOWED_QUADRANTS)-quadrants}")


def validate_pm_context_synthesis(evidence_items: Sequence[Dict[str, Any]]):
    def _validator(obj: Dict[str, Any]) -> None:
        nodes = obj.get("pm_context_nodes")
        if not isinstance(nodes, list) or len(nodes) != 4:
            raise SchemaValidationError("pm_context_nodes must be list of four")
        seen = set()
        for node in nodes:
            dim = node.get("dimension")
            if dim not in ALLOWED_QUADRANTS:
                raise SchemaValidationError(f"Invalid PM dimension: {dim}")
            seen.add(dim)
            if not isinstance(node.get("context_hypothesis"), str) or not node["context_hypothesis"].strip():
                raise SchemaValidationError(f"PM node {dim} missing context_hypothesis")
            for text_key in ["reported_context", "driver_belief_requirement"]:
                if not isinstance(node.get(text_key), str) or not node[text_key].strip():
                    raise SchemaValidationError(f"PM node {dim} missing {text_key}")
            if node.get("belief_uncertainty") not in ["low", "medium", "high"]:
                raise SchemaValidationError(f"PM node {dim} invalid belief_uncertainty")
            flaws = node.get("pm_flaw_hypotheses")
            if not isinstance(flaws, list) or not flaws:
                raise SchemaValidationError(f"PM node {dim} must include pm_flaw_hypotheses")
            for flaw in flaws:
                if flaw.get("flaw_type") not in ALLOWED_PM_FLAW_TYPES:
                    raise SchemaValidationError(f"PM node {dim} invalid flaw_type: {flaw.get('flaw_type')}")
                if flaw.get("claim_status") not in ["observed", "abductive_candidate", "blocked"]:
                    raise SchemaValidationError(f"PM node {dim} invalid pm flaw claim_status: {flaw.get('claim_status')}")
                if not isinstance(flaw.get("rationale"), str) or not flaw["rationale"].strip():
                    raise SchemaValidationError(f"PM node {dim} flaw missing rationale")
                for fkey in ["supporting_evidence_ids", "missing_evidence_ids"]:
                    fids = flaw.get(fkey)
                    if not isinstance(fids, list):
                        raise SchemaValidationError(f"PM flaw {dim}.{fkey} must be list")
                    validate_evidence_ids(fids, evidence_items, f"PM flaw {dim}.{fkey}")
                if not isinstance(flaw.get("blocked_claims", []), list):
                    raise SchemaValidationError(f"PM flaw {dim}.blocked_claims must be list")
                if flaw.get("claim_status") == "observed" and not flaw.get("supporting_evidence_ids"):
                    raise SchemaValidationError(f"Observed PM flaw in {dim} requires supporting_evidence_ids")
            if not isinstance(node.get("internal_reasoning_text"), str) or not node["internal_reasoning_text"].strip():
                raise SchemaValidationError(f"PM node {dim} missing internal_reasoning_text")
            if node.get("claim_strength") not in ["supported", "weakly_supported", "blocked"]:
                raise SchemaValidationError(f"PM node {dim} invalid claim_strength")
            for key in ["supporting_evidence_ids", "contradicting_evidence_ids", "missing_evidence_ids", "observed_belief_evidence_ids", "missing_belief_evidence_ids"]:
                ids = node.get(key)
                if not isinstance(ids, list):
                    raise SchemaValidationError(f"PM node {dim} {key} must be list")
                validate_evidence_ids(ids, evidence_items, f"PM {dim}.{key}")
        if set(ALLOWED_QUADRANTS) - seen:
            raise SchemaValidationError(f"PM context missing dimensions: {set(ALLOWED_QUADRANTS)-seen}")
        if not isinstance(obj.get("integrated_pm_context_text"), str) or not obj["integrated_pm_context_text"].strip():
            raise SchemaValidationError("integrated_pm_context_text must be non-empty string")
    return _validator


def validate_process_model_update(evidence_items: Sequence[Dict[str, Any]]):
    def _validator(obj: Dict[str, Any]) -> None:
        nodes = obj.get("update_process_nodes")
        if not isinstance(nodes, list) or not nodes:
            raise SchemaValidationError("update_process_nodes must be non-empty list")
        evidence_by_id = {item["evidence_id"]: item for item in evidence_items}
        seen_quadrants = set()
        for node in nodes:
            target_q = node.get("target_quadrant")
            if target_q not in ALLOWED_QUADRANTS:
                raise SchemaValidationError(f"Invalid update target_quadrant: {target_q}")
            seen_quadrants.add(target_q)
            if target_q not in (node.get("target_pm_dimensions") or []):
                raise SchemaValidationError("update target_quadrant must appear in target_pm_dimensions")
            for text_key in ["target_belief", "formation_question", "later_update_question", "feedback_or_input_text", "update_need"]:
                if not isinstance(node.get(text_key), str) or not node[text_key].strip():
                    raise SchemaValidationError(f"update node {node.get('node_id')} missing {text_key}")
            for list_key in ["formation_sources", "later_update_sources", "observed_sources_in_report", "missing_sources", "blocked_update_claims"]:
                if not isinstance(node.get(list_key), list):
                    raise SchemaValidationError(f"update node {node.get('node_id')} {list_key} must be list")
            for assessment_key in ["observability_assessment", "interpretability_assessment", "timing_assessment"]:
                if node.get(assessment_key) not in ["reported", "partially_reported", "not_reported"]:
                    raise SchemaValidationError(f"Invalid {assessment_key}: {node.get(assessment_key)}")
            if node.get("claim_status") not in ["observed", "abductive_candidate", "blocked"]:
                raise SchemaValidationError(f"Invalid update claim_status: {node.get('claim_status')}")
            if not isinstance(node.get("internal_reasoning_text"), str) or not node["internal_reasoning_text"].strip():
                raise SchemaValidationError("update node missing internal_reasoning_text")
            update_path = node.get("update_path")
            if not isinstance(update_path, dict):
                raise SchemaValidationError("update_path must be object")
            for list_key in ["initial_formation_sources", "later_update_sources"]:
                if list_key in update_path and not isinstance(update_path.get(list_key), list):
                    raise SchemaValidationError(f"update_path.{list_key} must be list")
            if update_path.get("availability") not in ALLOWED_UPDATE_PROCESS_VALUES:
                raise SchemaValidationError("Invalid update_path.availability")
            if update_path.get("observability") not in ALLOWED_UPDATE_PROCESS_VALUES:
                raise SchemaValidationError("Invalid update_path.observability")
            if update_path.get("salience") not in ALLOWED_UPDATE_SALIENCE_VALUES:
                raise SchemaValidationError("Invalid update_path.salience")
            if update_path.get("timing") not in ALLOWED_UPDATE_PROCESS_VALUES:
                raise SchemaValidationError("Invalid update_path.timing")
            if update_path.get("interpretability") not in ALLOWED_UPDATE_INTERPRETATION_VALUES:
                raise SchemaValidationError("Invalid update_path.interpretability")
            if update_path.get("consistency") not in ["consistent", "conflicting", "not_reported", "unclear", "not_admissible_from_report"]:
                raise SchemaValidationError("Invalid update_path.consistency")
            ids = node.get("triggering_evidence_ids", [])
            if not isinstance(ids, list):
                raise SchemaValidationError("triggering_evidence_ids must be list")
            validate_evidence_ids(ids, evidence_items, "update_process.triggering_evidence_ids")
            observed_issue = node.get("observed_update_issue")
            if not isinstance(observed_issue, dict):
                raise SchemaValidationError("observed_update_issue must be object")
            observed_issue_label = observed_issue.get("label")
            if observed_issue_label not in ALLOWED_VULNERABILITIES:
                raise SchemaValidationError(f"Invalid observed_update_issue.label: {observed_issue_label}")
            observed_issue_ids = observed_issue.get("supporting_evidence_ids", [])
            if not isinstance(observed_issue_ids, list):
                raise SchemaValidationError("observed_update_issue.supporting_evidence_ids must be list")
            validate_evidence_ids(observed_issue_ids, evidence_items, "observed_update_issue.supporting_evidence_ids")
            if observed_issue_label != "none" and not observed_issue_ids:
                raise SchemaValidationError("non-none observed_update_issue requires supporting_evidence_ids")
            if any(evidence_by_id.get(eid, {}).get("provenance") == "not_reported" for eid in observed_issue_ids):
                raise SchemaValidationError("not_reported evidence cannot support observed_update_issue")
            abductive = node.get("abductive_update_hypotheses")
            if not isinstance(abductive, list):
                raise SchemaValidationError("abductive_update_hypotheses must be list")
            allowed_abductive_update_labels = set(ALLOWED_VULNERABILITIES) | {"missing_feedback"} | set(ALLOWED_UPDATE_GAP_RISKS)
            allowed_abductive_update_labels.discard("none")
            for hyp in abductive:
                if hyp.get("label") not in allowed_abductive_update_labels:
                    raise SchemaValidationError(f"Invalid abductive update label: {hyp.get('label')}")
                for hkey in ["supporting_evidence_ids", "missing_evidence_ids"]:
                    hids = hyp.get(hkey, [])
                    if not isinstance(hids, list):
                        raise SchemaValidationError(f"abductive_update_hypotheses.{hkey} must be list")
                    validate_evidence_ids(hids, evidence_items, f"abductive_update_hypotheses.{hkey}")
                if not isinstance(hyp.get("rationale"), str) or not hyp["rationale"].strip():
                    raise SchemaValidationError("abductive_update_hypothesis missing rationale")
            observed = node.get("observed_update_vulnerability")
            if not isinstance(observed, dict):
                raise SchemaValidationError("observed_update_vulnerability must be object")
            observed_label = observed.get("label")
            if observed_label not in ALLOWED_VULNERABILITIES:
                raise SchemaValidationError(f"Invalid observed_update_vulnerability.label: {observed_label}")
            observed_ids = observed.get("supporting_evidence_ids", [])
            if not isinstance(observed_ids, list):
                raise SchemaValidationError("observed_update_vulnerability.supporting_evidence_ids must be list")
            validate_evidence_ids(observed_ids, evidence_items, "observed_update_vulnerability.supporting_evidence_ids")
            if observed_label != "none":
                if not observed_ids:
                    raise SchemaValidationError("non-none observed_update_vulnerability must cite supporting_evidence_ids")
                not_reported_ids = [eid for eid in observed_ids if evidence_by_id.get(eid, {}).get("provenance") == "not_reported"]
                if not_reported_ids:
                    raise SchemaValidationError(
                        "not_reported evidence cannot support observed_update_vulnerability; "
                        f"move these IDs to evidence_gap_update_risk: {not_reported_ids}"
                    )
            gap_risk = node.get("evidence_gap_update_risk")
            if not isinstance(gap_risk, dict):
                raise SchemaValidationError("evidence_gap_update_risk must be object")
            gap_labels = gap_risk.get("labels", [])
            if not isinstance(gap_labels, list):
                raise SchemaValidationError("evidence_gap_update_risk.labels must be list")
            if not all(isinstance(x, str) and x.strip() for x in gap_labels):
                raise SchemaValidationError("evidence_gap_update_risk.labels must be non-empty strings")
            gap_ids = gap_risk.get("gap_evidence_ids", [])
            if not isinstance(gap_ids, list):
                raise SchemaValidationError("evidence_gap_update_risk.gap_evidence_ids must be list")
            validate_evidence_ids(gap_ids, evidence_items, "evidence_gap_update_risk.gap_evidence_ids")
            status = node.get("update_evidence_status")
            if status not in ALLOWED_UPDATE_EVIDENCE_STATUS:
                raise SchemaValidationError(f"Invalid update_evidence_status: {status}")
            if status == "observed_update_claim" and observed_label == "none":
                abductive_present = bool(node.get("abductive_update_hypotheses"))
                if abductive_present and not observed_ids:
                    node["update_evidence_status"] = "evidence_gap_only"
                    status = "evidence_gap_only"
                else:
                    raise SchemaValidationError("observed_update_claim requires non-none observed_update_vulnerability.label")
            if status != "observed_update_claim" and observed_label != "none":
                raise SchemaValidationError("non-none observed_update_vulnerability requires update_evidence_status=observed_update_claim")
            if node.get("pm_flaw_hypothesis") not in ["incomplete", "incorrect", "delayed", "unverified", "unknown", "no_flaw_supported"]:
                raise SchemaValidationError(f"Invalid pm_flaw_hypothesis: {node.get('pm_flaw_hypothesis')}")
            if node.get("claim_strength") not in ["supported", "weakly_supported", "blocked"]:
                raise SchemaValidationError(f"Invalid update claim_strength: {node.get('claim_strength')}")
        missing_quads = set(ALLOWED_QUADRANTS) - seen_quadrants
        if missing_quads:
            raise SchemaValidationError(f"update_process_nodes missing target_quadrants: {missing_quads}")
    return _validator


def validate_other_factors(evidence_items: Sequence[Dict[str, Any]]):
    def _validator(obj: Dict[str, Any]) -> None:
        nodes = obj.get("other_factor_nodes")
        if not isinstance(nodes, list):
            raise SchemaValidationError("other_factor_nodes must be list")
        for node in nodes:
            if node.get("factor_type") not in ALLOWED_OTHER_FACTOR_TYPES:
                raise SchemaValidationError(f"Invalid factor_type: {node.get('factor_type')}")
            ids = node.get("supporting_evidence_ids", [])
            if not isinstance(ids, list):
                raise SchemaValidationError("other factor supporting_evidence_ids must be list")
            validate_evidence_ids(ids, evidence_items, f"other_factor.{node.get('node_id')}.supporting_evidence_ids")
            if node.get("claim_strength") not in ["supported", "weakly_supported", "blocked"]:
                raise SchemaValidationError(f"Invalid other factor claim_strength: {node.get('claim_strength')}")
            if not isinstance(node.get("internal_reasoning_text"), str) or not node["internal_reasoning_text"].strip():
                raise SchemaValidationError("other factor missing internal_reasoning_text")
        if not isinstance(obj.get("integrated_other_factors_text"), str):
            raise SchemaValidationError("integrated_other_factors_text must be string")
        if not isinstance(obj.get("missing_other_factors", []), list):
            raise SchemaValidationError("missing_other_factors must be list")
    return _validator


def validate_commitment_boundary(obj: Dict[str, Any], evidence_items: Sequence[Dict[str, Any]]) -> None:
    if obj.get("ads_reliance_basis") not in ALLOWED_BASIS:
        raise SchemaValidationError(f"Invalid ads_reliance_basis: {obj.get('ads_reliance_basis')}")
    if obj.get("committed_posture") not in ALLOWED_POSTURES:
        raise SchemaValidationError(f"Invalid committed_posture: {obj.get('committed_posture')}")
    if obj.get("selected_action_code") not in ALLOWED_ACTIONS:
        raise SchemaValidationError(f"Invalid selected_action_code: {obj.get('selected_action_code')}")
    expected_tuple = {
        "supported": ("heightened_monitoring", "continue_monitoring"),
        "contingent": ("readiness_formed", "prepare_takeover"),
        "not_supported": ("transfer_initiated", "initiate_takeover"),
    }.get(obj.get("ads_reliance_basis"))
    actual_tuple = (obj.get("committed_posture"), obj.get("selected_action_code"))
    if expected_tuple != actual_tuple:
        raise SchemaValidationError(
            "commitment tuple must be internally consistent with ads_reliance_basis; "
            f"expected {expected_tuple}, got {actual_tuple}"
        )
    cb = obj.get("commitment_block")
    if not isinstance(cb, dict):
        raise SchemaValidationError("commitment_block must be object")
    ids = cb.get("supporting_evidence_ids", [])
    if not isinstance(ids, list):
        raise SchemaValidationError("commitment_block.supporting_evidence_ids must be list")
    validate_evidence_ids(ids, evidence_items, "commitment_block.supporting_evidence_ids")
    evidence_by_id = {item["evidence_id"]: item for item in evidence_items}
    evidence_by_field = {item["field_path"]: item for item in evidence_items}
    boundary = infer_boundary_from_commitment(obj)
    strength = classify_boundary_evidence_strength(boundary, evidence_by_field, ids, evidence_by_id)
    if boundary == "not_supported_transfer":
        if strength["strong_boundary_evidence_strength"] not in {
            "explicit_transition_or_intervention",
            "explicit_hmi_takeover_or_support_withdrawal",
            "reported_system_issue_or_disengagement_cause",
        }:
            raise SchemaValidationError(
                "not_supported_transfer requires explicit transition/intervention or support-withdrawal evidence; "
                f"got {strength['strong_boundary_evidence_strength']}"
            )
    elif boundary == "contingent_readiness":
        if strength["strong_boundary_evidence_strength"] in {
            "explicit_transition_or_intervention",
            "explicit_hmi_takeover_or_support_withdrawal",
            "reported_system_issue_or_disengagement_cause",
        }:
            raise SchemaValidationError(
                "contingent_readiness cannot use explicit transfer/intervention evidence; "
                f"got {strength['strong_boundary_evidence_strength']}"
            )
    if not isinstance(obj.get("boundary_internal_text"), str) or not obj["boundary_internal_text"].strip():
        raise SchemaValidationError("boundary_internal_text must be non-empty string")


def validate_action_selection(evidence_items: Sequence[Dict[str, Any]]):
    def _validator(obj: Dict[str, Any]) -> None:
        nodes = obj.get("action_selection_nodes")
        if not isinstance(nodes, list) or not nodes:
            raise SchemaValidationError("action_selection_nodes must be non-empty list")
        for node in nodes:
            if node.get("candidate_action") not in ALLOWED_ACTIONS:
                raise SchemaValidationError(f"Invalid candidate_action: {node.get('candidate_action')}")
            if node.get("action_role") not in ["observed", "expected", "omitted", "alternative", "blocked"]:
                raise SchemaValidationError(f"Invalid action_role: {node.get('action_role')}")
            ids = node.get("supporting_evidence_ids", [])
            if not isinstance(ids, list):
                raise SchemaValidationError("action_selection supporting_evidence_ids must be list")
            validate_evidence_ids(ids, evidence_items, f"action_selection.{node.get('node_id')}.supporting_evidence_ids")
            missing_ids = node.get("missing_evidence_ids", [])
            if not isinstance(missing_ids, list):
                raise SchemaValidationError("action_selection missing_evidence_ids must be list")
            validate_evidence_ids(missing_ids, evidence_items, f"action_selection.{node.get('node_id')}.missing_evidence_ids")
            for key in ["pm_context_inputs", "update_process_inputs", "other_factor_inputs"]:
                if not isinstance(node.get(key, []), list):
                    raise SchemaValidationError(f"{key} must be list")
            if node.get("claim_strength") not in ["supported", "weakly_supported", "blocked"]:
                raise SchemaValidationError(f"Invalid action_selection claim_strength: {node.get('claim_strength')}")
            if node.get("claim_status") not in ["observed", "abductive_candidate", "blocked"]:
                raise SchemaValidationError(f"Invalid action_selection claim_status: {node.get('claim_status')}")
            for text_key in ["why_this_action_is_relevant", "why_this_action_is_not_observed"]:
                if not isinstance(node.get(text_key), str):
                    raise SchemaValidationError(f"action_selection node missing {text_key}")
            if node.get("claim_status") == "observed" and not ids:
                raise SchemaValidationError("observed action selection requires supporting_evidence_ids")
            if node.get("claim_status") == "observed" and evidence_ids_lack_action_evidence(ids, evidence_items):
                raise SchemaValidationError("observed action selection requires direct driver/operator action evidence")
            if node.get("candidate_action") == "continue_monitoring" and node.get("action_role") == "observed":
                if evidence_ids_lack_action_evidence(ids, evidence_items):
                    raise SchemaValidationError("continue_monitoring cannot be observed from absence of intervention evidence")
            if not isinstance(node.get("internal_reasoning_text"), str) or not node["internal_reasoning_text"].strip():
                raise SchemaValidationError("action_selection node missing internal_reasoning_text")
        if not isinstance(obj.get("integrated_action_selection_text"), str):
            raise SchemaValidationError("integrated_action_selection_text must be string")
    return _validator


def classify_evidence_role_for_uca(item: Optional[Dict[str, Any]]) -> str:
    """Classify evidence role for UCA activation without repairing semantics."""
    if not item or item.get("provenance") == "not_reported":
        return "missingness_gap"
    field_path = str(item.get("field_path", ""))
    text = " ".join(str(item.get(k, "")) for k in ["value", "source_text", "derivation_basis", "summary"]).lower()
    if field_path in OUTCOME_ONLY_FIELD_PATHS:
        return "terminal_outcome"
    if field_path == "CAR.reported_intervention":
        if any(k in text for k in ["late", "delayed", "failed", "unable", "after impact", "abrupt", "hard brak", "steer", "overcorrect", "manual input"]):
            return "driver_action_quality_evidence"
        return "driver_action_or_transition_evidence"
    if field_path in {"CABIN.pressure", "CABIN.distraction"}:
        return "driver_state_evidence"
    if field_path in {"CAR.time_budget_to_handover"}:
        return "transition_timing_context"
    if field_path in {"CAR.reported_system_issue", "CAR.perception_confidence", "CAR.planner_confidence"}:
        return "system_issue_context"
    if field_path.startswith("HMI."):
        return "feedback_update_evidence"
    if field_path.startswith("NARRATIVE.") and any(k in text for k in ["driver", "operator", "manual", "takeover", "took over", "interven", "brak", "steer"]):
        return "driver_action_or_transition_evidence"
    if field_path.startswith("NARRATIVE.") and any(k in text for k in ["collision", "crash", "contact", "disengagement"]):
        return "terminal_or_transition_narrative"
    return "context_evidence"


def evidence_role_counts(ids: Sequence[str], evidence_items: Sequence[Dict[str, Any]]) -> Dict[str, int]:
    evidence_by_id = {item["evidence_id"]: item for item in evidence_items}
    return dict(Counter(classify_evidence_role_for_uca(evidence_by_id.get(eid)) for eid in ids))


def evidence_ids_are_outcome_only(ids: Sequence[str], evidence_items: Sequence[Dict[str, Any]]) -> bool:
    if not ids:
        return False
    evidence_by_id = {item["evidence_id"]: item for item in evidence_items}
    positive = [
        evidence_by_id.get(eid)
        for eid in ids
        if evidence_by_id.get(eid, {}).get("provenance") != "not_reported"
    ]
    if not positive:
        return False
    return all(classify_evidence_role_for_uca(item) == "terminal_outcome" for item in positive)


def evidence_ids_lack_action_evidence(ids: Sequence[str], evidence_items: Sequence[Dict[str, Any]]) -> bool:
    evidence_by_id = {item["evidence_id"]: item for item in evidence_items}
    positive = [
        evidence_by_id.get(eid)
        for eid in ids
        if evidence_by_id.get(eid, {}).get("provenance") != "not_reported"
    ]
    if not positive:
        return True
    roles = {classify_evidence_role_for_uca(item) for item in positive}
    return not bool(roles & ACTION_EVIDENCE_ROLES)


def evidence_ids_have_action_evidence(ids: Sequence[str], evidence_items: Sequence[Dict[str, Any]]) -> bool:
    return not evidence_ids_lack_action_evidence(ids, evidence_items)


def validate_uca_context_classification(evidence_items: Sequence[Dict[str, Any]], committed_state: str):
    driver_uca_ids = set(DRIVER_UCA_BY_ID)
    def _validator(obj: Dict[str, Any]) -> None:
        if obj.get("committed_fsm_state") != committed_state:
            raise SchemaValidationError("UCA context committed_fsm_state mismatch")
        status = obj.get("uca_activation_status")
        if status not in ALLOWED_UCA_ACTIVATION_STATUS:
            raise SchemaValidationError(f"Invalid uca_activation_status: {status}")
        nodes = obj.get("uca_context_nodes")
        if not isinstance(nodes, list) or not nodes:
            raise SchemaValidationError("uca_context_nodes must be non-empty list")
        present_node_ids = set()
        activated_ids = set()
        blocked_or_suppressed_ids = set()
        observed_ids = set()
        abductive_ids = set()
        blocked_ids = set()
        for node in nodes:
            if node.get("uca_id") not in driver_uca_ids:
                raise SchemaValidationError(f"Unknown driver-centered uca_id {node.get('uca_id')}")
            if node.get("node_id") in present_node_ids:
                raise SchemaValidationError(f"Duplicate UCA context node_id {node.get('node_id')}")
            if node.get("stpa_uca_type") not in STPA_UCA_CATEGORY_MAP.values() and node.get("stpa_uca_type") not in STPA_UCA_CATEGORY_MAP.keys():
                raise SchemaValidationError(f"Invalid stpa_uca_type: {node.get('stpa_uca_type')}")
            if node.get("classification") == "abductive_candidate":
                node["classification"] = "suppressed"
            if node.get("classification") not in ["activated", "suppressed", "blocked"]:
                raise SchemaValidationError(f"Invalid UCA classification: {node.get('classification')}")
            claim_status = node.get("claim_status")
            if claim_status is None:
                if node.get("classification") == "activated":
                    claim_status = "observed_admissible"
                elif node.get("classification") in {"blocked", "suppressed"}:
                    claim_status = "blocked"
                node["claim_status"] = claim_status
            if claim_status not in ["observed_admissible", "abductive_candidate", "blocked"]:
                raise SchemaValidationError(f"Invalid UCA claim_status: {claim_status}")
            if node.get("abductive_strength") is None:
                node["abductive_strength"] = "blocked" if claim_status == "blocked" else "weak_abductive"
            if node.get("abductive_strength") not in ALLOWED_ABDUCTIVE_STRENGTH:
                raise SchemaValidationError(f"Invalid UCA abductive_strength: {node.get('abductive_strength')}")
            if claim_status == "observed_admissible" and node.get("classification") != "activated":
                raise SchemaValidationError("observed_admissible UCA must use classification=activated")
            if claim_status == "abductive_candidate" and node.get("classification") == "activated":
                raise SchemaValidationError("abductive_candidate UCA must not be classified as activated")
            if claim_status == "blocked" and node.get("classification") not in {"blocked", "suppressed"}:
                raise SchemaValidationError("blocked UCA claim_status must be blocked or suppressed")
            fd = node.get("forward_derivation")
            if not isinstance(fd, dict):
                raise SchemaValidationError("UCA forward_derivation must be object")
            for key in ["pm_flaw_inputs", "update_flaw_inputs", "action_selection_inputs", "other_factor_inputs"]:
                if not isinstance(fd.get(key), list):
                    raise SchemaValidationError(f"UCA forward_derivation.{key} must be list")
            ids = node.get("supporting_evidence_ids", [])
            if not isinstance(ids, list):
                raise SchemaValidationError("UCA context supporting_evidence_ids must be list")
            validate_evidence_ids(ids, evidence_items, f"UCA context {node.get('node_id')}.supporting_evidence_ids")
            missing_ids = node.get("missing_evidence_ids", [])
            if not isinstance(missing_ids, list):
                raise SchemaValidationError("UCA context missing_evidence_ids must be list")
            validate_evidence_ids(missing_ids, evidence_items, f"UCA context {node.get('node_id')}.missing_evidence_ids")
            if claim_status == "observed_admissible" and not ids:
                raise SchemaValidationError(f"Activated UCA {node.get('uca_id')} must cite supporting_evidence_ids")
            if claim_status == "observed_admissible" and evidence_ids_are_outcome_only(ids, evidence_items):
                raise SchemaValidationError(
                    f"Activated UCA {node.get('uca_id')} cites only terminal outcome evidence; "
                    "outcome may constrain compatibility but cannot activate UCA"
                )
            if claim_status == "observed_admissible" and evidence_ids_lack_action_evidence(ids, evidence_items):
                raise SchemaValidationError(
                    f"Activated UCA {node.get('uca_id')} lacks driver action, action-quality, or driver-state evidence; "
                    "transition/system/outcome context alone cannot activate UCA"
                )
            if not isinstance(node.get("required_context", []), list):
                raise SchemaValidationError("UCA context required_context must be list")
            if not isinstance(node.get("blocking_reasons", []), list):
                raise SchemaValidationError("UCA context blocking_reasons must be list")
            if node.get("claim_status") == "blocked" and not node.get("blocking_reasons"):
                raise SchemaValidationError("blocked UCA candidates must list blocking_reasons")
            if not isinstance(node.get("blocked_claims", []), list):
                raise SchemaValidationError("UCA blocked_claims must be list")
            if not isinstance(node.get("why_not_outcome_derived"), str) or not node["why_not_outcome_derived"].strip():
                raise SchemaValidationError("UCA node missing why_not_outcome_derived")
            if not isinstance(node.get("internal_reasoning_text"), str) or not node["internal_reasoning_text"].strip():
                raise SchemaValidationError("UCA context node missing internal_reasoning_text")
            present_node_ids.add(node.get("node_id"))
            if node.get("classification") == "activated":
                activated_ids.add(node.get("uca_id"))
            else:
                blocked_or_suppressed_ids.add(node.get("uca_id"))
            if claim_status == "observed_admissible":
                observed_ids.add(node.get("uca_id"))
            elif claim_status == "abductive_candidate":
                abductive_ids.add(node.get("uca_id"))
            else:
                blocked_ids.add(node.get("uca_id"))
        for key in ["observed_uca_set", "abductive_uca_candidates", "blocked_uca_set"]:
            if not isinstance(obj.get(key), list):
                raise SchemaValidationError(f"{key} must be list")
        if set(obj.get("observed_uca_set") or []) != observed_ids:
            raise SchemaValidationError("observed_uca_set must match observed_admissible nodes")
        if set(obj.get("abductive_uca_candidates") or []) != abductive_ids:
            raise SchemaValidationError("abductive_uca_candidates must match abductive_candidate nodes")
        case_level_blocked_ids = blocked_ids - abductive_ids - observed_ids
        if set(obj.get("blocked_uca_set") or []) != case_level_blocked_ids:
            raise SchemaValidationError("blocked_uca_set must match case-level blocked nodes after excluding UCA IDs with admissible/abductive pathways")
        activated_set = obj.get("activated_uca_set")
        if not isinstance(activated_set, list):
            raise SchemaValidationError("activated_uca_set must be list")
        if set(activated_set) != observed_ids or activated_ids != observed_ids:
            raise SchemaValidationError("activated_uca_set must equal observed_uca_set/observed_admissible nodes")
        blocked_or_suppressed = obj.get("blocked_or_suppressed_uca_set")
        if not isinstance(blocked_or_suppressed, list):
            raise SchemaValidationError("blocked_or_suppressed_uca_set must be list")
        if set(blocked_or_suppressed) != blocked_or_suppressed_ids:
            obj["blocked_or_suppressed_uca_set"] = sorted(blocked_or_suppressed_ids)
        dominant = obj.get("dominant_uca")
        if status == "activated":
            if not activated_ids:
                raise SchemaValidationError("uca_activation_status activated requires at least one activated UCA")
            if dominant not in activated_ids:
                raise SchemaValidationError("dominant_uca must be one of the activated UCA ids")
            dominant_node = next((n for n in nodes if n.get("uca_id") == dominant and n.get("classification") == "activated"), None)
            if not dominant_node or not dominant_node.get("supporting_evidence_ids"):
                raise SchemaValidationError("dominant_uca must cite supporting_evidence_ids")
            if not isinstance(obj.get("dominant_uca_rationale"), str) or not obj["dominant_uca_rationale"].strip():
                raise SchemaValidationError("dominant_uca_rationale must be non-empty string when a UCA is activated")
        else:
            if activated_ids or activated_set:
                raise SchemaValidationError("no_activated_uca cannot include activated UCA nodes")
            if dominant is not None:
                raise SchemaValidationError("dominant_uca must be null when no UCA is activated")
            if not isinstance(obj.get("dominant_uca_rationale"), str):
                raise SchemaValidationError("dominant_uca_rationale must be string")
        if not isinstance(obj.get("integrated_uca_text"), str):
            raise SchemaValidationError("integrated_uca_text must be string")
    return _validator


def validate_round2a_with_evidence(evidence_items: Sequence[Dict[str, Any]]):
    def _validator(obj: Dict[str, Any]) -> None:
        updates = obj.get("slot_updates")
        if not isinstance(updates, list) or len(updates) != 4:
            raise SchemaValidationError("Round2A slot_updates must be list of four")
        seen = set()
        for item in updates:
            slot_id = item.get("slot_id")
            quadrant = item.get("quadrant")
            if quadrant not in ALLOWED_QUADRANTS:
                raise SchemaValidationError(f"Invalid quadrant in Round2A: {quadrant}")
            seen.add(quadrant)
            status = item.get("pm_hypothesis_status", "weakly_supported")
            if status not in ["supported", "weakly_supported", "blocked", "unchanged"]:
                raise SchemaValidationError(f"Invalid pm_hypothesis_status: {status}")
            grounding = item.get("evidence_grounding_level", "indirect")
            if grounding not in ALLOWED_GROUNDING_LEVELS:
                raise SchemaValidationError(f"Invalid evidence_grounding_level: {grounding}")
            if not isinstance(item.get("unsupported_inference_warning", False), bool):
                raise SchemaValidationError("unsupported_inference_warning must be boolean")
            ids = item.get("supporting_evidence_ids")
            if not isinstance(ids, list):
                raise SchemaValidationError("Round2A supporting_evidence_ids must be list")
            validate_evidence_ids(ids, evidence_items, f"Round2A {slot_id}.supporting_evidence_ids")
            bs = item.get("slot_belief_state")
            if not isinstance(bs, dict):
                raise SchemaValidationError("Round2A slot_belief_state must be object")
            enum_checks = {
                "belief_polarity": ["supportive", "neutral", "contradictory"],
                "belief_confidence": ["high", "medium", "low", "uncertain"],
                "update_direction": ["strengthened", "unchanged", "weakened", "reversed"],
                "tension_type": ["none", "capability_tension", "mode_tension", "actor_tension", "env_tension"],
                "tension_severity": ["none", "mild", "moderate", "severe"],
            }
            for k, allowed in enum_checks.items():
                if bs.get(k) not in allowed:
                    raise SchemaValidationError(f"Invalid slot_belief_state.{k}: {bs.get(k)}")
            ratio = bs.get("retained_support_ratio")
            if not isinstance(ratio, (int, float)) or not (0.0 <= float(ratio) <= 1.0):
                raise SchemaValidationError("retained_support_ratio must be float 0-1")
            vuln = item.get("slot_update_vulnerability")
            if not isinstance(vuln, dict):
                raise SchemaValidationError("slot_update_vulnerability missing/object required")
            vt = vuln.get("vulnerability_type")
            if vt not in ALLOWED_VULNERABILITIES:
                raise SchemaValidationError(f"Invalid vulnerability_type: {vt}")
            v_ids = vuln.get("supporting_evidence_ids")
            if not isinstance(v_ids, list):
                raise SchemaValidationError("slot_update_vulnerability.supporting_evidence_ids must be list")
            validate_evidence_ids(v_ids, evidence_items, f"Round2A {slot_id}.slot_update_vulnerability.supporting_evidence_ids")
        if set(ALLOWED_QUADRANTS) - seen:
            raise SchemaValidationError(f"Round2A missing quadrants: {set(ALLOWED_QUADRANTS)-seen}")
    return _validator


def validate_round2b_with_evidence(evidence_items: Sequence[Dict[str, Any]]):
    def _validator(obj: Dict[str, Any]) -> None:
        if obj.get("ads_reliance_basis") not in ALLOWED_BASIS:
            raise SchemaValidationError(f"Invalid ads_reliance_basis: {obj.get('ads_reliance_basis')}")
        if obj.get("committed_posture") not in ALLOWED_POSTURES:
            raise SchemaValidationError(f"Invalid committed_posture: {obj.get('committed_posture')}")
        if obj.get("selected_action_code") not in ALLOWED_ACTIONS:
            raise SchemaValidationError(f"Invalid selected_action_code: {obj.get('selected_action_code')}")
        cb = obj.get("commitment_block")
        if not isinstance(cb, dict):
            raise SchemaValidationError("commitment_block must be object")
        ids = cb.get("supporting_evidence_ids", [])
        if not isinstance(ids, list):
            raise SchemaValidationError("commitment_block.supporting_evidence_ids must be list")
        validate_evidence_ids(ids, evidence_items, "Round2B commitment_block.supporting_evidence_ids")
        infer_boundary_from_commitment(obj)
    return _validator


def validate_round2c_with_evidence(evidence_items: Sequence[Dict[str, Any]]):
    def _validator(obj: Dict[str, Any]) -> None:
        if not isinstance(obj.get("mechanism_paragraph"), str) or not obj["mechanism_paragraph"].strip():
            raise SchemaValidationError("mechanism_paragraph must be non-empty string")
        ids = obj.get("supporting_evidence_ids")
        if not isinstance(ids, list):
            raise SchemaValidationError("Round2C supporting_evidence_ids must be list")
        validate_evidence_ids(ids, evidence_items, "Round2C supporting_evidence_ids")
    return _validator


def validate_round3_with_evidence(evidence_items: Sequence[Dict[str, Any]], committed_state: str):
    state_uca_ids = set(DRIVER_UCA_BY_ID)
    def _validator(obj: Dict[str, Any]) -> None:
        if obj.get("committed_fsm_state") != committed_state:
            raise SchemaValidationError("Round3 committed_fsm_state mismatch")
        status = obj.get("uca_activation_status")
        if status not in ALLOWED_UCA_ACTIVATION_STATUS:
            raise SchemaValidationError(f"Invalid Round3 uca_activation_status: {status}")
        for key in ["activated_ucas", "suppressed_ucas"]:
            if not isinstance(obj.get(key), list):
                raise SchemaValidationError(f"Round3 {key} must be list")
            for u in obj[key]:
                uca_id = u.get("uca_id")
                if uca_id not in state_uca_ids:
                    raise SchemaValidationError(f"UCA {uca_id} not in driver-centered catalog")
                ids = u.get("supporting_evidence_ids", [])
                if not isinstance(ids, list):
                    raise SchemaValidationError(f"Round3 {uca_id}.supporting_evidence_ids must be list")
                validate_evidence_ids(ids, evidence_items, f"Round3 {uca_id}.supporting_evidence_ids")
        active_ids = {u.get("uca_id") for u in obj.get("activated_ucas", [])}
        dominant = obj.get("dominant_uca")
        if status == "activated":
            if not active_ids:
                raise SchemaValidationError("Round3 activated status requires activated_ucas")
            if dominant not in state_uca_ids:
                raise SchemaValidationError(f"dominant_uca {dominant} not in driver-centered catalog")
            if dominant not in active_ids:
                raise SchemaValidationError("dominant_uca must be in activated_ucas")
        else:
            if active_ids:
                raise SchemaValidationError("Round3 no_activated_uca cannot include activated_ucas")
            if dominant is not None:
                raise SchemaValidationError("Round3 dominant_uca must be null when no UCA is activated")
    return _validator


def aggregate_update_vulnerability_from_nodes(update_process: Dict[str, Any]) -> Dict[str, Any]:
    votes: List[str] = []
    node_details = []
    severity = {"none": 0, "missed_feedback": 1, "ambiguous_feedback": 2, "misinterpreted_feedback": 3}
    for node in update_process.get("update_process_nodes", []) or []:
        observed = node.get("observed_update_vulnerability") or {}
        vt = observed.get("label", node.get("update_vulnerability_type", "none"))
        if vt not in ALLOWED_VULNERABILITIES:
            raise SchemaValidationError(f"Invalid update vulnerability in update_process: {vt}")
        votes.append(vt)
        node_details.append({
            "node_id": node.get("node_id"),
            "target_pm_dimensions": node.get("target_pm_dimensions", []),
            "vulnerability_type": vt,
            "observed_supporting_evidence_ids": observed.get("supporting_evidence_ids", []),
            "evidence_gap_update_risk": node.get("evidence_gap_update_risk", {}),
            "update_evidence_status": node.get("update_evidence_status"),
            "triggering_evidence_ids": node.get("triggering_evidence_ids", []),
            "internal_reasoning_text": node.get("internal_reasoning_text", ""),
        })
    non_none = [v for v in votes if v != "none"]
    if not non_none:
        dominant = "none"
    else:
        counts = Counter(non_none)
        max_count = max(counts.values())
        tied = [k for k, c in counts.items() if c == max_count]
        dominant = sorted(tied, key=lambda x: severity[x], reverse=True)[0]
    return {
        "dominant_vulnerability": dominant,
        "dominant_observed_update_vulnerability": dominant,
        "node_vulnerability_votes": node_details,
        "vote_counts": dict(Counter(votes)),
    }


def aggregate_update_vulnerability(round2a: Dict[str, Any]) -> Dict[str, Any]:
    votes: List[str] = []
    slot_details = []
    severity = {"none": 0, "missed_feedback": 1, "ambiguous_feedback": 2, "misinterpreted_feedback": 3}
    for item in round2a.get("slot_updates", []):
        vuln = item.get("slot_update_vulnerability", {})
        vt = vuln.get("vulnerability_type")
        if vt not in ALLOWED_VULNERABILITIES:
            raise SchemaValidationError(f"Invalid vulnerability in Round2A aggregation: {vt}")
        votes.append(vt)
        slot_details.append({
            "slot_id": item.get("slot_id"),
            "quadrant": item.get("quadrant"),
            "vulnerability_type": vt,
            "supporting_evidence_ids": vuln.get("supporting_evidence_ids", []),
            "rationale": vuln.get("rationale", ""),
        })
    non_none = [v for v in votes if v != "none"]
    if not non_none:
        dominant = "none"
    else:
        counts = Counter(non_none)
        candidates = counts.most_common()
        max_count = candidates[0][1]
        tied = [k for k, c in candidates if c == max_count]
        dominant = sorted(tied, key=lambda x: severity[x], reverse=True)[0]
    return {
        "dominant_vulnerability": dominant,
        "slot_vulnerability_votes": slot_details,
        "vote_counts": dict(Counter(votes)),
    }


def ordered_uca_catalog(committed_state: str, dominant_vulnerability: str, use_vulnerability_priority: bool = False) -> List[Dict[str, Any]]:
    """Compatibility wrapper. Publication runs use the driver-centered catalog."""
    return ordered_driver_uca_catalog(committed_state, dominant_vulnerability, use_vulnerability_priority)


def ordered_driver_uca_catalog(
    committed_state: str,
    dominant_vulnerability: str,
    use_vulnerability_priority: bool = False,
) -> List[Dict[str, Any]]:
    """Return the full driver-centered UCA catalog without boundary filtering.

    The committed boundary may affect display order for ablations, but no UCA is
    removed solely because the current boundary is weaker or stronger.
    """
    catalog = [dict(u) for u in DRIVER_UCA_CATALOG]
    if not use_vulnerability_priority:
        return catalog
    legacy_order = UPDATE_VULN_UCA_PRIORITY.get((committed_state, dominant_vulnerability), [])
    driver_order: List[str] = []
    for legacy_id in legacy_order:
        mapped = LEGACY_UCA_ID_MAP.get(legacy_id)
        if mapped and mapped not in driver_order:
            driver_order.append(mapped)
    rank = {uca_id: i for i, uca_id in enumerate(driver_order)}
    return sorted(catalog, key=lambda u: rank.get(u["uca_id"], 999))


def _build_passthrough_pm_context(evidence_items: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    nodes = []
    for dim in ALLOWED_QUADRANTS:
        node_id = f"PM-{dim}-noop"
        supporting = [e["evidence_id"] for e in evidence_items if dim in e.get("quadrant_targets", []) and e.get("provenance") != "not_reported"]
        nodes.append({
            "node_id": node_id,
            "dimension": dim,
            "dimension_definition": PM_QUADRANT_DEFINITIONS.get(dim, {}).get("definition", dim),
            "reported_context": f"Ablation retained source-visible {dim} context.",
            "driver_belief_requirement": f"Ablation did not synthesize a {dim} driver-belief requirement.",
            "observed_belief_evidence_ids": supporting,
            "missing_belief_evidence_ids": [],
            "belief_uncertainty": "high" if not supporting else "medium",
            "pm_flaw_hypotheses": [
                {
                    "flaw_id": f"PMF-{dim}-noop",
                    "flaw_type": "none_supported",
                    "claim_status": "blocked",
                    "supporting_evidence_ids": [],
                    "missing_evidence_ids": [],
                    "blocked_claims": ["Ablation mode does not assert PM flaws."],
                    "rationale": "Process-model flaw synthesis skipped by ablation.",
                }
            ],
            "context_hypothesis": f"Ablation: retained source-visible {dim} context without synthesis update.",
            "internal_reasoning_text": f"Ablation retained the prior for {dim} context.",
            "display_summary": f"{dim} prior retained",
            "supporting_evidence_ids": supporting,
            "contradicting_evidence_ids": [],
            "missing_evidence_ids": [],
            "claim_strength": "blocked" if not supporting else "weakly_supported",
        })
    return {"pm_context_nodes": nodes, "integrated_pm_context_text": "Ablation retained all PM dimensions as priors."}


def _build_passthrough_update_analysis(pm_context: Dict[str, Any], evidence_items: Sequence[Dict[str, Any]] = ()) -> Dict[str, Any]:
    """Construct a no-op update-analysis result for ablation without collapsing the pipeline."""
    nodes = []
    for node in pm_context.get("pm_context_nodes", []) or []:
        dim = node.get("dimension")
        supporting = [eid for eid in node.get("supporting_evidence_ids", []) if eid in {e["evidence_id"] for e in evidence_items}]
        nodes.append({
            "node_id": f"UPD-{dim}-noop",
            "target_pm_dimensions": [dim],
            "target_quadrant": dim,
            "target_belief": UPDATE_SOURCE_GUIDE.get(dim, {}).get("target_belief", dim),
            "formation_question": "Ablation: formation source analysis skipped.",
            "later_update_question": "Ablation: later update source analysis skipped.",
            "formation_sources": UPDATE_SOURCE_GUIDE.get(dim, {}).get("formation_sources", []),
            "later_update_sources": UPDATE_SOURCE_GUIDE.get(dim, {}).get("later_update_sources", []),
            "observed_sources_in_report": [],
            "missing_sources": [],
            "observability_assessment": "not_reported",
            "interpretability_assessment": "not_reported",
            "timing_assessment": "not_reported",
            "observed_update_issue": {
                "label": "none",
                "supporting_evidence_ids": [],
                "rationale": "Ablation skipped update-process issue analysis.",
            },
            "abductive_update_hypotheses": [],
            "blocked_update_claims": ["Ablation mode does not assert update-process hypotheses."],
            "triggering_evidence_ids": supporting,
            "feedback_or_input_text": "Ablation: process-model update analysis skipped; no posterior update is asserted.",
            "update_need": "No update performed in ablation mode.",
            "update_path": {
                "initial_formation_sources": ["not_reported"],
                "later_update_sources": ["not_reported"],
                "availability": "not_reported",
                "observability": "not_reported",
                "salience": "not_reported",
                "timing": "not_reported",
                "interpretability": "not_reported",
                "consistency": "not_reported",
            },
            "observed_update_vulnerability": {
                "label": "none",
                "supporting_evidence_ids": [],
                "rationale": "Ablation skipped update-process analysis.",
            },
            "evidence_gap_update_risk": {
                "labels": [],
                "gap_evidence_ids": [],
                "rationale": "Ablation skipped update-process analysis.",
            },
            "update_evidence_status": "not_admissible",
            "pm_flaw_hypothesis": "unknown",
            "internal_reasoning_text": f"Ablation retained the PM context for {dim} without posterior update.",
            "display_summary": f"{dim}: update skipped",
            "claim_strength": "blocked" if supporting else "weakly_supported",
            "claim_status": "blocked",
            "missingness_notes": ["process-model update skipped by ablation"],
        })
    return {
        "update_process_nodes": nodes,
    "integrated_update_text": "Ablation: process-model update analysis skipped; PM context retained as a prior-only structure.",
    }


def _build_empty_other_factors(evidence_items: Sequence[Dict[str, Any]] = ()) -> Dict[str, Any]:
    return {
        "other_factor_nodes": [],
        "missing_other_factors": [],
        "integrated_other_factors_text": "No source-supported other factors extracted.",
    }


def _build_passthrough_boundary(update_process: Dict[str, Any], evidence_items: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    ids = []
    for node in update_process.get("update_process_nodes", []) or []:
        ids.extend(node.get("triggering_evidence_ids", []) or [])
    ids = [eid for eid in dict.fromkeys(ids) if eid in {e["evidence_id"] for e in evidence_items}]
    return {
        "ads_reliance_basis": "contingent" if ids else "supported",
        "committed_posture": "readiness_formed" if ids else "heightened_monitoring",
        "selected_action_code": "prepare_takeover" if ids else "continue_monitoring",
        "commitment_block": {
            "basis_explanation": "Ablation boundary selected from retained prior context without posterior boundary update.",
            "minimal_sufficiency_basis": "No posterior update performed.",
            "boundary_rationale": "Ablation boundary placeholder.",
            "supporting_evidence_ids": ids,
        },
        "boundary_internal_text": "Ablation boundary derived from retained prior structure.",
    }


def _build_passthrough_action_selection(boundary: Dict[str, Any], evidence_items: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    act = boundary.get("selected_action_code", "continue_monitoring")
    return {
        "action_selection_nodes": [
            {
                "node_id": "ACT-noop",
                "candidate_action": act,
                "action_role": "expected",
                "selection_context": "Ablation retained action selection from boundary posture.",
                "pm_context_inputs": [],
                "update_process_inputs": [],
                "other_factor_inputs": [],
                "supporting_evidence_ids": [],
                "missing_evidence_ids": [],
                "why_this_action_is_relevant": "Ablation retained the boundary action.",
                "why_this_action_is_not_observed": "Ablation does not assert observed action selection.",
                "internal_reasoning_text": "Ablation action-selection placeholder.",
                "display_summary": "action selection skipped",
                "claim_strength": "blocked",
                "claim_status": "blocked",
            }
        ],
        "integrated_action_selection_text": "Ablation action selection placeholder.",
    }


def _build_passthrough_uca_context(committed_state: str, boundary: Dict[str, Any], evidence_items: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    uca_id = DRIVER_UCA_CATALOG[0]["uca_id"]
    return {
        "committed_fsm_state": committed_state,
        "uca_activation_status": "no_activated_uca",
        "observed_uca_set": [],
        "abductive_uca_candidates": [],
        "blocked_uca_set": [uca_id],
        "uca_context_nodes": [
            {
                "node_id": "UCACTX-noop",
                "uca_id": uca_id,
                "controller": "driver",
                "control_action": boundary.get("selected_action_code", "continue_monitoring"),
                "stpa_uca_type": "not_provided_when_required",
                "unsafe_context_text": "Ablation placeholder context.",
                "hazard_link": "Ablation placeholder hazard link.",
                "action_selection_node_ids": ["ACT-noop"],
                "forward_derivation": {
                    "pm_flaw_inputs": [],
                    "update_flaw_inputs": [],
                    "action_selection_inputs": ["ACT-noop"],
                    "other_factor_inputs": [],
                },
                "supporting_evidence_ids": [],
                "missing_evidence_ids": [],
                "required_context": DRIVER_UCA_CATALOG[0]["minimum_required_evidence"],
                "blocking_reasons": ["ablation_no_uca_classification"],
                "blocked_claims": ["Ablation mode does not assert observed or abductive UCA hypotheses."],
                "why_not_directly_observed": "Ablation mode does not perform UCA evidence classification.",
                "why_not_outcome_derived": "The reported outcome is not used to derive UCA.",
                "internal_reasoning_text": "Ablation UCA placeholder.",
                "display_summary": "uca classification skipped",
                "classification": "blocked",
                "claim_strength": "blocked",
                "claim_status": "blocked",
            }
        ],
        "activated_uca_set": [],
        "blocked_or_suppressed_uca_set": [uca_id],
        "dominant_uca": None,
        "dominant_uca_rationale": "",
        "integrated_uca_text": "Ablation UCA placeholder.",
    }


def build_reasoning_graph_export(
    evidence_items: Sequence[Dict[str, Any]],
    pm_context: Dict[str, Any],
    update_process: Dict[str, Any],
    other_factors: Dict[str, Any],
    boundary: Dict[str, Any],
    action_selection: Dict[str, Any],
    uca_context: Dict[str, Any],
    reported_outcome: Dict[str, Any],
) -> Dict[str, Any]:
    evidence_by_id = _evidence_by_id(evidence_items)
    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []

    for node in pm_context.get("pm_context_nodes", []) or []:
        nodes.append({
            "node_id": node.get("node_id"),
            "node_type": "pm_context",
            "dimension": node.get("dimension"),
            "reported_context": node.get("reported_context"),
            "driver_belief_requirement": node.get("driver_belief_requirement"),
            "pm_flaw_hypotheses": node.get("pm_flaw_hypotheses", []),
            "internal_reasoning_text": node.get("internal_reasoning_text"),
            "display_summary": node.get("display_summary"),
            "supporting_evidence_ids": node.get("supporting_evidence_ids", []),
            "claim_strength": node.get("claim_strength"),
        })

    for node in update_process.get("update_process_nodes", []) or []:
        nodes.append({
            "node_id": node.get("node_id"),
            "node_type": "update_process",
            "target_pm_dimensions": node.get("target_pm_dimensions", []),
            "target_quadrant": node.get("target_quadrant"),
            "target_belief": node.get("target_belief"),
            "abductive_update_hypotheses": node.get("abductive_update_hypotheses", []),
            "blocked_update_claims": node.get("blocked_update_claims", []),
            "internal_reasoning_text": node.get("internal_reasoning_text"),
            "display_summary": node.get("display_summary"),
            "supporting_evidence_ids": node.get("triggering_evidence_ids", []),
            "claim_strength": node.get("claim_strength"),
        })

    for node in other_factors.get("other_factor_nodes", []) or []:
        nodes.append({
            "node_id": node.get("node_id"),
            "node_type": "other_factor",
            "factor_type": node.get("factor_type"),
            "internal_reasoning_text": node.get("internal_reasoning_text"),
            "display_summary": node.get("display_summary"),
            "supporting_evidence_ids": node.get("supporting_evidence_ids", []),
            "claim_strength": node.get("claim_strength"),
        })

    boundary_node_id = "BOUNDARY-1"
    nodes.append({
        "node_id": boundary_node_id,
        "node_type": "boundary",
        "boundary_state": boundary.get("committed_posture"),
        "internal_reasoning_text": boundary.get("boundary_internal_text"),
        "display_summary": boundary.get("commitment_block", {}).get("boundary_rationale"),
        "supporting_evidence_ids": boundary.get("commitment_block", {}).get("supporting_evidence_ids", []),
        "claim_strength": "supported",
    })

    for node in action_selection.get("action_selection_nodes", []) or []:
        nodes.append({
            "node_id": node.get("node_id"),
            "node_type": "action_selection",
            "candidate_action": node.get("candidate_action"),
            "claim_status": node.get("claim_status"),
            "why_this_action_is_relevant": node.get("why_this_action_is_relevant"),
            "why_this_action_is_not_observed": node.get("why_this_action_is_not_observed"),
            "internal_reasoning_text": node.get("internal_reasoning_text"),
            "display_summary": node.get("display_summary"),
            "supporting_evidence_ids": node.get("supporting_evidence_ids", []),
            "claim_strength": node.get("claim_strength"),
        })

    for node in uca_context.get("uca_context_nodes", []) or []:
        nodes.append({
            "node_id": node.get("node_id"),
            "node_type": "uca_context",
            "uca_id": node.get("uca_id"),
            "claim_status": node.get("claim_status"),
            "forward_derivation": node.get("forward_derivation", {}),
            "why_not_directly_observed": node.get("why_not_directly_observed"),
            "why_not_outcome_derived": node.get("why_not_outcome_derived"),
            "internal_reasoning_text": node.get("internal_reasoning_text"),
            "display_summary": node.get("display_summary"),
            "supporting_evidence_ids": node.get("supporting_evidence_ids", []),
            "classification": node.get("classification"),
            "claim_strength": node.get("claim_strength"),
        })

    outcome_node_id = "OUTCOME-1"
    nodes.append({
        "node_id": outcome_node_id,
        "node_type": "reported_outcome",
        "outcome": reported_outcome,
        "internal_reasoning_text": "Reported outcome retained as source-visible endpoint.",
        "display_summary": json.dumps(reported_outcome, ensure_ascii=False),
        "supporting_evidence_ids": [],
        "claim_strength": "supported",
    })

    for node in update_process.get("update_process_nodes", []) or []:
        for dim in node.get("target_pm_dimensions", []) or []:
            src = next((n for n in pm_context.get("pm_context_nodes", []) or [] if n.get("dimension") == dim), None)
            if src:
                edges.append({
                    "edge_id": f"EDGE-{src.get('node_id')}-{node.get('node_id')}",
                    "from_node_id": src.get("node_id"),
                    "to_node_id": node.get("node_id"),
                    "relation_type": "pm_context_conditions_update_process",
                    "supporting_evidence_ids": list(dict.fromkeys((src.get("supporting_evidence_ids") or []) + (node.get("triggering_evidence_ids") or []))),
                    "internal_reasoning_text": f"{dim} context conditions {node.get('node_id')}.",
                    "display_summary": f"{dim} -> update",
                    "claim_strength": node.get("claim_strength", "weakly_supported"),
                    "missingness_notes": node.get("missingness_notes", []),
                })

    for node in other_factors.get("other_factor_nodes", []) or []:
        for act in action_selection.get("action_selection_nodes", []) or []:
            if node.get("node_id") in (act.get("other_factor_inputs") or []):
                edges.append({
                    "edge_id": f"EDGE-{node.get('node_id')}-{act.get('node_id')}",
                    "from_node_id": node.get("node_id"),
                    "to_node_id": act.get("node_id"),
                    "relation_type": "other_factor_conditions_action_selection",
                    "supporting_evidence_ids": list(dict.fromkeys((node.get("supporting_evidence_ids") or []) + (act.get("supporting_evidence_ids") or []))),
                    "internal_reasoning_text": f"{node.get('factor_type')} conditions {act.get('node_id')}.",
                    "display_summary": f"{node.get('factor_type')} -> action",
                    "claim_strength": act.get("claim_strength", "weakly_supported"),
                    "missingness_notes": [],
                })

    for upd in update_process.get("update_process_nodes", []) or []:
        for act in action_selection.get("action_selection_nodes", []) or []:
            if upd.get("node_id") in (act.get("update_process_inputs") or []):
                edges.append({
                    "edge_id": f"EDGE-{upd.get('node_id')}-{act.get('node_id')}",
                    "from_node_id": upd.get("node_id"),
                    "to_node_id": act.get("node_id"),
                    "relation_type": "update_process_conditions_action_selection",
                    "supporting_evidence_ids": list(dict.fromkeys((upd.get("triggering_evidence_ids") or []) + (act.get("supporting_evidence_ids") or []))),
                    "internal_reasoning_text": f"{upd.get('node_id')} conditions {act.get('node_id')}.",
                    "display_summary": "update -> action",
                    "claim_strength": act.get("claim_strength", "weakly_supported"),
                    "missingness_notes": upd.get("missingness_notes", []),
                })

    for act in action_selection.get("action_selection_nodes", []) or []:
        edges.append({
            "edge_id": f"EDGE-{boundary_node_id}-{act.get('node_id')}",
            "from_node_id": boundary_node_id,
            "to_node_id": act.get("node_id"),
            "relation_type": "boundary_conditions_action_selection",
            "supporting_evidence_ids": boundary.get("commitment_block", {}).get("supporting_evidence_ids", []) + (act.get("supporting_evidence_ids") or []),
            "internal_reasoning_text": f"Boundary posture conditions {act.get('node_id')}.",
            "display_summary": "boundary -> action",
            "claim_strength": boundary.get("claim_strength", "supported"),
            "missingness_notes": [],
        })

    for act in action_selection.get("action_selection_nodes", []) or []:
        for uca in uca_context.get("uca_context_nodes", []) or []:
            if act.get("node_id") in (uca.get("action_selection_node_ids") or []):
                relation = "action_selection_instantiates_uca_context"
                if uca.get("classification") == "blocked":
                    relation = "action_selection_blocks_uca_context"
                elif uca.get("classification") == "suppressed":
                    relation = "action_selection_suppresses_uca_context"
                edges.append({
                    "edge_id": f"EDGE-{act.get('node_id')}-{uca.get('node_id')}",
                    "from_node_id": act.get("node_id"),
                    "to_node_id": uca.get("node_id"),
                    "relation_type": relation,
                    "supporting_evidence_ids": list(dict.fromkeys((act.get("supporting_evidence_ids") or []) + (uca.get("supporting_evidence_ids") or []))),
                    "internal_reasoning_text": f"{act.get('node_id')} conditions {uca.get('node_id')} with classification {uca.get('classification')}.",
                    "display_summary": f"action -> {uca.get('classification', 'uca')}",
                    "claim_strength": uca.get("claim_strength", "weakly_supported"),
                    "missingness_notes": [],
                })

    for uca in uca_context.get("uca_context_nodes", []) or []:
        relation_type = "uca_context_links_to_outcome"
        if uca.get("classification") == "blocked":
            relation_type = "blocked_uca_pathway"
        elif uca.get("classification") == "suppressed":
            relation_type = "suppressed_uca_pathway"
        edges.append({
            "edge_id": f"EDGE-{uca.get('node_id')}-{outcome_node_id}",
            "from_node_id": uca.get("node_id"),
            "to_node_id": outcome_node_id,
            "relation_type": relation_type,
            "supporting_evidence_ids": uca.get("supporting_evidence_ids", []),
            "internal_reasoning_text": f"{uca.get('uca_id')} links to the reported outcome as a candidate {uca.get('classification')} explanation path.",
            "display_summary": f"{uca.get('classification')} -> outcome",
            "claim_strength": uca.get("claim_strength", "weakly_supported"),
            "missingness_notes": [],
        })

    return {
        "nodes": nodes,
        "edges": edges,
        "uca_activation_status": uca_context.get("uca_activation_status"),
        "observed_uca_set": uca_context.get("observed_uca_set", []),
        "abductive_uca_candidates": uca_context.get("abductive_uca_candidates", []),
        "blocked_uca_set": uca_context.get("blocked_uca_set", []),
        "activated_uca_set": uca_context.get("activated_uca_set", []),
        "blocked_or_suppressed_uca_set": uca_context.get("blocked_or_suppressed_uca_set", []),
        "evidence_audit": {
            "invalid_evidence_ids": 0,
            "node_count": len(nodes),
            "edge_count": len(edges),
            "evidence_catalog_size": len(evidence_by_id),
        },
    }



def build_tabletop_replay_package(
    *,
    case_id: str,
    event_index: int,
    evidence_items: Sequence[Dict[str, Any]],
    pm_context: Dict[str, Any],
    update_process: Dict[str, Any],
    other_factors: Dict[str, Any],
    boundary: Dict[str, Any],
    committed_state: str,
    action_selection: Dict[str, Any],
    uca_context: Dict[str, Any],
    pathway_judgment: Dict[str, Any],
    reported_outcome: Dict[str, Any],
) -> Dict[str, Any]:
    provenance_counts = Counter(item.get("provenance", "missing") for item in evidence_items)
    missing_requirement_candidates = []
    ranked_pathways = pathway_judgment.get("ranked_pathways", []) or []
    for item in evidence_items:
        field_path = item.get("field_path")
        if item.get("provenance") != "not_reported" or field_path not in FIELD_REQUIREMENT_TEXT:
            continue
        target_type, target_slot = FIELD_REQUIREMENT_TARGETS.get(field_path, ("incident replay evidence", field_path))
        support_scope = FIELD_SUPPORT_SCOPE.get(field_path, [])
        triggering_pathway_ids = requirement_triggering_pathways(field_path, item.get("evidence_id"), ranked_pathways)
        blocked_claims = requirement_blocked_claims_for_field(field_path, committed_state)
        criticality = classify_requirement_criticality(field_path, blocked_claims, support_scope, triggering_pathway_ids)
        missing_requirement_candidates.append({
            "field_path": field_path,
            "evidence_id": item.get("evidence_id"),
            "target_type": target_type,
            "target_slot": target_slot,
            "support_scope": support_scope,
            "candidate_requirement": FIELD_REQUIREMENT_TEXT[field_path],
            "tabletop_replay_role": "This missing field limits driver process-model replay, action-selection analysis, or UCA-pathway ranking.",
            "requirement_criticality_class": criticality,
            "requirement_triggering_pathway_ids": triggering_pathway_ids,
            "requirement_blocks_claims": blocked_claims,
            "requirement_priority_reason": requirement_priority_reason(field_path, criticality, blocked_claims, support_scope),
            "requirement_specificity_level": requirement_specificity_level(field_path, triggering_pathway_ids),
            "claim_boundary": "A missing field is a replay limitation and data/logging need, not evidence that the field was absent in the real event.",
        })
    replay_questions = [
        {
            "question_id": "RQ-REPLAY-PM",
            "question": "Which CPS/CPB/OPS/OPB process-model variables are supported, weakly supported, or blocked by the incident text?",
            "answered_by": ["pm_context_nodes", "evidence_items"],
        },
        {
            "question_id": "RQ-REPLAY-UPDATE",
            "question": "Which feedback or input sources could form or update the driver's process model, and which missing sources prevent a stronger claim?",
            "answered_by": ["update_process_nodes", "missing_requirement_candidates"],
        },
        {
            "question_id": "RQ-REPLAY-ACTION-UCA",
            "question": "Which candidate driver control actions lead to observed, abductive, or blocked UCA-in-context pathways?",
            "answered_by": ["action_selection_nodes", "uca_pathway_summary", "ranked_pathways"],
        },
        {
            "question_id": "RQ-REPLAY-IMPROVE",
            "question": "Which HMI, driver-state, vehicle-behavior, or incident-log fields should be recorded or improved for future replay and safety analysis?",
            "answered_by": ["missing_requirement_candidates"],
        },
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "package_type": "driver_process_model_tabletop_replay_package",
        "case_id": case_id,
        "event_index": event_index,
        "replay_focus": "driver_process_model_and_control_action_replay",
        "reported_outcome": reported_outcome,
        "claim_boundary": {
            "allowed": "Evidence-bounded tabletop replay of driver process-model variables, update sources, candidate control actions, UCA pathways, and improvement needs.",
            "disallowed": [
                "unique accident-cause reconstruction",
                "true driver psychology inference",
                "legal responsibility attribution",
                "using collision/disengagement outcome as UCA activation evidence",
            ],
        },
        "evidence_profile": {
            "total_evidence_items": len(evidence_items),
            "provenance_counts": dict(provenance_counts),
            "reported_or_derived_count": sum(1 for item in evidence_items if item.get("provenance") != "not_reported"),
            "not_reported_count": provenance_counts.get("not_reported", 0),
        },
        "driver_process_model": {
            "quadrant_definitions": PM_QUADRANT_DEFINITIONS,
            "pm_context_nodes": pm_context.get("pm_context_nodes", []),
            "integrated_pm_context_text": pm_context.get("integrated_pm_context_text"),
        },
        "process_model_update": {
            "update_source_guide": UPDATE_SOURCE_GUIDE,
            "update_process_nodes": update_process.get("update_process_nodes", []),
            "integrated_update_text": update_process.get("integrated_update_text"),
        },
        "other_factors": other_factors,
        "driver_replay_posture": {
            "fsm_state": committed_state,
            "driver_replay_posture_block": boundary,
        },
        "candidate_driver_actions": action_selection.get("action_selection_nodes", []),
        "uca_pathway_summary": uca_context.get("uca_pathway_summary", []),
        "no_admissible_uca_summary": uca_context.get("no_admissible_uca_summary", {}),
        "ranked_pathways": ranked_pathways,
        "ranking_summary": pathway_judgment.get("ranking_summary"),
        "replay_questions": replay_questions,
        "missing_requirement_candidates": missing_requirement_candidates,
        "replay_package_completeness": {
            "quadrant_coverage_complete": len({n.get("dimension") for n in pm_context.get("pm_context_nodes", []) or [] if n.get("dimension") in ALLOWED_QUADRANTS}) == len(ALLOWED_QUADRANTS),
            "update_process_present": bool(update_process.get("update_process_nodes")),
            "candidate_actions_present": bool(action_selection.get("action_selection_nodes")),
            "uca_pathways_present": bool(uca_context.get("uca_pathway_summary")),
            "ranked_pathways_present": bool(pathway_judgment.get("ranked_pathways")),
            "replay_questions_present": bool(replay_questions),
        },
    }


# =============================================================================
# Generation chain
# =============================================================================


def run_case(client: LLMClient, case_spec: Dict[str, Any], out_dir: str | Path, use_vulnerability_priority: bool = False, skip_pm_update: bool = False, temperature: float = 0.0) -> Dict[str, Any]:
    validate_case_no_label_leakage(case_spec)
    case_id = case_spec.get("case_id") or stable_digest(case_spec)
    out = Path(out_dir) / case_id
    ensure_dir(out)
    event_records = []
    schema_errors = []
    prior: Optional[Dict[str, Any]] = None

    for idx, event in enumerate(case_spec.get("latent_events", [])):
        evidence_packet = build_evidence_packet(event, case_spec.get("driver_profile", {}), event_index=idx)
        evidence_items = evidence_packet["evidence_items"]
        write_json(out / f"e{idx+1}_evidence_packet.json", evidence_packet)
        try:
            pm_context_payload = {
                "case_id": case_id,
                "event_index": idx,
                "evidence_policy": evidence_packet["event_factor_envelope"]["missingness_policy"],
                "evidence_items": evidence_items,
                "narrative_propositions": event.get("narrative_propositions", []) or [],
            }
            if skip_pm_update:
                pm_context = _build_passthrough_pm_context(evidence_items)
                write_json(out / f"e{idx+1}_pm_context.json", {**pm_context, "_ablation": "skip_pm_update"})
                update_process = _build_passthrough_update_analysis(pm_context, evidence_items)
                vuln_map = {"dominant_vulnerability": "none", "node_vulnerability_votes": [], "vote_counts": {"none": 4}}
                write_json(out / f"e{idx+1}_update_process.json", {**update_process, "_ablation": "skip_pm_update"})
                write_json(out / f"e{idx+1}_round2a_update.json", {**update_process, "_ablation": "skip_pm_update"})
                write_json(out / f"e{idx+1}_update_vulnerability.json", vuln_map)
            else:
                pm_context = client.chat_json_strict(
                    make_messages(PM_CONTEXT_SYNTHESIS_PROMPT, pm_context_payload),
                    ["pm_context_nodes", "integrated_pm_context_text"],
                    validator=validate_pm_context_synthesis(evidence_items),
                    temperature=temperature,
                )
                write_json(out / f"e{idx+1}_pm_context.json", pm_context)
                write_json(out / f"e{idx+1}_pm_variables.json", pm_context)
                write_json(out / f"e{idx+1}_pm_flaws.json", {
                    "pm_flaw_hypotheses": [
                        {**flaw, "source_node_id": node.get("node_id"), "dimension": node.get("dimension")}
                        for node in pm_context.get("pm_context_nodes", []) or []
                        for flaw in node.get("pm_flaw_hypotheses", []) or []
                    ]
                })
                update_payload = {"case_id": case_id, "event_index": idx, "pm_context": pm_context, **evidence_packet}
                update_process = client.chat_json_strict(
                    make_messages(PROCESS_MODEL_UPDATE_PROMPT, update_payload),
                    ["update_process_nodes", "integrated_update_text"],
                    validator=validate_process_model_update(evidence_items),
                    temperature=temperature,
                )
                update_process = attach_canonical_gap_taxonomy(update_process)
                write_json(out / f"e{idx+1}_update_process.json", update_process)
                write_json(out / f"e{idx+1}_round2a_update.json", update_process)
                vuln_map = aggregate_update_vulnerability_from_nodes(update_process)
                write_json(out / f"e{idx+1}_update_vulnerability.json", vuln_map)

            other_factors_payload = {"case_id": case_id, "event_index": idx, "pm_context": pm_context, "update_process": update_process, **evidence_packet}
            other_factors = _build_empty_other_factors(evidence_items) if skip_pm_update else client.chat_json_strict(
                make_messages(OTHER_FACTORS_PROMPT, other_factors_payload),
                ["other_factor_nodes", "missing_other_factors", "integrated_other_factors_text"],
                validator=validate_other_factors(evidence_items),
                temperature=temperature,
            )
            write_json(out / f"e{idx+1}_other_factors.json", other_factors)

            r2b_payload = {"case_id": case_id, "event_index": idx, "pm_context": pm_context, "update_process": update_process, "other_factors": other_factors, **evidence_packet}
            boundary = _build_passthrough_boundary(update_process, evidence_items) if skip_pm_update else client.chat_json_strict(
                make_messages(COMMITMENT_BOUNDARY_PROMPT, r2b_payload),
                ["ads_reliance_basis", "committed_posture", "selected_action_code", "commitment_block", "boundary_internal_text"],
                validator=lambda obj: validate_commitment_boundary(obj, evidence_items),
                temperature=temperature,
            )
            committed_state = infer_boundary_from_commitment(boundary) if not skip_pm_update else infer_boundary_from_commitment(boundary)
            write_json(out / f"e{idx+1}_commitment_boundary.json", boundary)
            write_json(out / f"e{idx+1}_round2b_commitment.json", boundary)

            action_payload = {"case_id": case_id, "event_index": idx, "pm_context": pm_context, "update_process": update_process, "other_factors": other_factors, "boundary": boundary, **evidence_packet}
            action_selection = _build_passthrough_action_selection(boundary, evidence_items) if skip_pm_update else client.chat_json_strict(
                make_messages(CONTROL_ACTION_SELECTION_PROMPT, action_payload),
                ["action_selection_nodes", "integrated_action_selection_text"],
                validator=validate_action_selection(evidence_items),
                temperature=temperature,
            )
            write_json(out / f"e{idx+1}_action_selection.json", action_selection)
            write_json(out / f"e{idx+1}_candidate_actions.json", action_selection)

            uca_payload = {
                "case_id": case_id,
                "event_index": idx,
                "committed_fsm_state": committed_state,
                "pm_context": pm_context,
                "update_process": update_process,
                "other_factors": other_factors,
                "boundary": boundary,
                "action_selection": action_selection,
                "reported_outcome": _reported_outcome_from_event(event),
                "uca_catalog": ordered_driver_uca_catalog(committed_state, vuln_map["dominant_vulnerability"], use_vulnerability_priority=use_vulnerability_priority),
                **evidence_packet,
            }
            uca_context = _build_passthrough_uca_context(committed_state, boundary, evidence_items) if skip_pm_update else client.chat_json_strict(
                make_messages(UCA_CONTEXT_CLASSIFICATION_PROMPT, uca_payload),
                ["committed_fsm_state", "uca_activation_status", "uca_context_nodes", "observed_uca_set", "abductive_uca_candidates", "blocked_uca_set", "activated_uca_set", "blocked_or_suppressed_uca_set", "dominant_uca", "dominant_uca_rationale", "integrated_uca_text"],
                validator=validate_uca_context_classification(evidence_items, committed_state),
                temperature=temperature,
            )
            if not skip_pm_update:
                uca_context = expand_forward_uca_candidates_v241(
                    uca_context=uca_context,
                    pm_context=pm_context,
                    update_process=update_process,
                    other_factors=other_factors,
                    action_selection=action_selection,
                    evidence_items=evidence_items,
                    committed_state=committed_state,
                )
                validate_uca_context_classification(evidence_items, committed_state)(uca_context)
            write_json(out / f"e{idx+1}_uca_context.json", uca_context)
            write_json(out / f"e{idx+1}_forward_uca_hypotheses.json", uca_context)
            write_json(out / f"e{idx+1}_evidence_features_v242.json", uca_context.get("evidence_features_v242", {}))
            write_json(out / f"e{idx+1}_uca_pathway_summary.json", {
                "case_id": case_id,
                "event_index": idx,
                "uca_pathway_summary": uca_context.get("uca_pathway_summary", []),
            })
            write_json(out / f"e{idx+1}_no_admissible_uca_summary.json", uca_context.get("no_admissible_uca_summary", {}))

            reported_outcome = _reported_outcome_from_event(event)
            reasoning_graph = build_reasoning_graph_export(evidence_items, pm_context, update_process, other_factors, boundary, action_selection, uca_context, reported_outcome)
            write_json(out / f"e{idx+1}_reasoning_graph.json", reasoning_graph)

            mechanism_support_ids = sorted({
                eid
                for node in reasoning_graph.get("nodes", [])
                for eid in (node.get("supporting_evidence_ids") or [])
            })
            mechanism_paragraph = reasoning_graph.get("nodes", [])[-1].get("display_summary") if reasoning_graph.get("nodes") else None
            write_json(
                out / f"e{idx+1}_round2c_mechanism.json",
                {
                    "mechanism_paragraph": mechanism_paragraph,
                    "supporting_evidence_ids": mechanism_support_ids,
                },
            )

            candidate_pathways = build_candidate_pathways(case_id, idx, evidence_items, pm_context, update_process, other_factors, boundary, action_selection, uca_context, committed_state, event)
            pathway_judgment = judge_and_rank_pathways(client, case_id, idx, evidence_items, candidate_pathways, temperature=temperature)
            write_json(out / f"e{idx+1}_ranked_pathways.json", pathway_judgment)
            tabletop_replay_package = build_tabletop_replay_package(
                case_id=case_id,
                event_index=idx,
                evidence_items=evidence_items,
                pm_context=pm_context,
                update_process=update_process,
                other_factors=other_factors,
                boundary=boundary,
                committed_state=committed_state,
                action_selection=action_selection,
                uca_context=uca_context,
                pathway_judgment=pathway_judgment,
                reported_outcome=reported_outcome,
            )
            write_json(out / f"e{idx+1}_tabletop_replay_package.json", tabletop_replay_package)
            write_json(out / f"e{idx+1}_outcome_compatibility.json", {
                "case_id": case_id,
                "event_index": idx,
                "reported_outcome": reported_outcome,
                "outcome_compatibility_by_pathway": [
                    {
                        "pathway_id": p.get("pathway_id"),
                        "uca_id": p.get("uca_id"),
                        "claim_status": p.get("claim_status"),
                        "outcome_compatibility": p.get("outcome_compatibility"),
                    }
                    for p in pathway_judgment.get("ranked_pathways", [])
                ],
            })

            event_record = {
                "event_index": idx,
                "evidence_packet_path": f"e{idx+1}_evidence_packet.json",
                "commitment_state_fsm": committed_state,
                "driver_replay_posture_fsm": committed_state,
                "dominant_update_vulnerability": vuln_map["dominant_vulnerability"],
                "uca_activation_status": uca_context.get("uca_activation_status"),
                "dominant_uca": uca_context.get("dominant_uca"),
                "observed_uca_set": uca_context.get("observed_uca_set", []),
                "abductive_uca_candidates": uca_context.get("abductive_uca_candidates", []),
                "blocked_uca_set": uca_context.get("blocked_uca_set", []),
                "uca_pathway_summary": uca_context.get("uca_pathway_summary", []),
                "no_admissible_uca_summary": uca_context.get("no_admissible_uca_summary", {}),
                "active_uca_set": uca_context.get("activated_uca_set") or [u.get("uca_id") for u in uca_context.get("uca_context_nodes", []) if u.get("claim_status") == "observed_admissible"],
                "blocked_or_suppressed_uca_set": uca_context.get("blocked_or_suppressed_uca_set") or [u.get("uca_id") for u in uca_context.get("uca_context_nodes", []) if u.get("claim_status") == "blocked"],
                "mechanism_paragraph": reasoning_graph.get("nodes", [])[-1].get("display_summary") if reasoning_graph.get("nodes") else None,
                "ranked_pathways_path": f"e{idx+1}_ranked_pathways.json",
                "tabletop_replay_package_path": f"e{idx+1}_tabletop_replay_package.json",
                "replay_question_count": len(tabletop_replay_package.get("replay_questions", [])),
                "missing_requirement_count": len(tabletop_replay_package.get("missing_requirement_candidates", [])),
                "blocked_claim_count": sum(
                    len(node.get("blocked_claims") or [])
                    for node in (pm_context.get("pm_context_nodes", []) or [])
                ) + sum(
                    len(node.get("blocked_update_claims") or [])
                    for node in (update_process.get("update_process_nodes", []) or [])
                ) + sum(
                    len(node.get("blocked_claims") or [])
                    for node in (uca_context.get("uca_context_nodes", []) or [])
                ),
                "replay_ready": bool(
                    tabletop_replay_package.get("replay_package_completeness", {}).get("quadrant_coverage_complete")
                    and tabletop_replay_package.get("replay_package_completeness", {}).get("update_process_present")
                    and tabletop_replay_package.get("replay_package_completeness", {}).get("candidate_actions_present")
                    and tabletop_replay_package.get("replay_package_completeness", {}).get("ranked_pathways_present")
                ),
                "top_pathway": (pathway_judgment.get("ranked_pathways") or [None])[0],
                "pathway_status_counts": dict(Counter(p.get("pathway_status") for p in pathway_judgment.get("ranked_pathways", []))),
                "num_candidate_pathways": len(pathway_judgment.get("candidate_pathways", [])),
                "source_evidence_audit": evidence_packet["source_evidence_audit"],
                "schema_status": "valid",
            }
            write_json(out / f"e{idx+1}_round3_uca.json", uca_context)
            prior = {"pm_prior": pm_context.get("pm_context_nodes"), "prior_formation_summary": pm_context.get("integrated_pm_context_text")}
        except SchemaValidationError as exc:
            schema_errors.append({"event_index": idx, "error": str(exc)})
            event_record = {"event_index": idx, "schema_status": "invalid", "schema_error": str(exc), "source_evidence_audit": evidence_packet["source_evidence_audit"]}
        event_records.append(event_record)

    valid_events = [e for e in event_records if e.get("schema_status") == "valid"]
    final_event = valid_events[-1] if valid_events else None
    bundle = {
        "schema_version": SCHEMA_VERSION,
        "case_id": case_id,
        "case_source": case_spec.get("case_source", "unknown"),
        "source_regime": get_case_source_regime_from_case(case_spec),
        "analysis_mode": "base_report",
        "source_metadata": case_spec.get("source_metadata", {}),
        "bundle_type": "driver_process_model_tabletop_replay_bundle",
        "paper_facing_output": "tabletop_replay_package",
        "pipeline": "accident_text_evidence->STPA_HF_driver_PM_variables->process_model_update_analysis->other_factors->candidate_driver_actions->forward_derived_UCA_hypotheses->outcome_compatibility_gate->LLM_judged_ranked_pathways->tabletop_replay_package",
        "pipeline_components": [
            "provenance_aware_evidence_objects",
            "stpa_hf_pm_variable_synthesis",
            "process_model_flaw_hypothesis_generation",
            "process_model_update_source_analysis",
            "other_factors_analysis",
            "evidence_constrained_driver_replay_posture_reasoning",
            "multi_candidate_control_action_selection",
            "forward_derived_driver_uca_hypothesis_generation",
            "reported_outcome_compatibility_gate",
            "reasoning_graph_export",
            "llm_judged_ranked_stpa_hf_explanatory_pathways",
            "driver_process_model_tabletop_replay_package",
        ],
        "claim_boundary": {
            "allowed": "Evidence-grounded STPA-HF tabletop replay of driver process-model, update-process, action-selection, and forward-derived UCA pathway hypotheses with ranked explanatory plausibility.",
            "disallowed": [
                "claiming true driver mental state",
                "claiming unique accident cause",
                "assigning legal responsibility",
                "treating pathway_score as causal probability",
                "inferring takeover failure from crash/collision outcome alone",
                "deriving UCA from reported outcome instead of PM/update/action chain"
            ],
        },
        "pm_quadrant_definitions": PM_QUADRANT_DEFINITIONS,
        "update_source_guide": UPDATE_SOURCE_GUIDE,
        "pm_context": pm_context if valid_events else None,
        "event_records": event_records,
        "schema_errors": schema_errors,
        "schema_valid": len(schema_errors) == 0,
        "final_case_summary": {
            "final_commitment_state_fsm": final_event.get("commitment_state_fsm") if final_event else None,
            "final_driver_replay_posture_fsm": final_event.get("driver_replay_posture_fsm") if final_event else None,
            "final_dominant_update_vulnerability": final_event.get("dominant_update_vulnerability") if final_event else None,
            "final_uca_activation_status": final_event.get("uca_activation_status") if final_event else None,
            "final_dominant_uca": final_event.get("dominant_uca") if final_event else None,
            "final_observed_uca_set": final_event.get("observed_uca_set") if final_event else [],
            "final_abductive_uca_candidates": final_event.get("abductive_uca_candidates") if final_event else [],
            "final_blocked_uca_set": final_event.get("blocked_uca_set") if final_event else [],
            "final_uca_pathway_summary": final_event.get("uca_pathway_summary") if final_event else [],
            "final_no_admissible_uca_summary": final_event.get("no_admissible_uca_summary") if final_event else {},
            "final_abductive_uca_pathway_count": sum(1 for p in (final_event.get("uca_pathway_summary") if final_event else []) if p.get("claim_status") == "abductive_candidate"),
            "final_blocked_uca_pathway_count": sum(1 for p in (final_event.get("uca_pathway_summary") if final_event else []) if p.get("claim_status") == "blocked"),
            "final_case_level_abductive_uca_set": sorted({p.get("uca_id") for p in (final_event.get("uca_pathway_summary") if final_event else []) if p.get("claim_status") == "abductive_candidate" and p.get("uca_id")}),
            "final_case_level_blocked_uca_set": sorted({
                p.get("uca_id")
                for p in (final_event.get("uca_pathway_summary") if final_event else [])
                if p.get("claim_status") == "blocked"
                and p.get("uca_id")
                and p.get("uca_id") not in {q.get("uca_id") for q in (final_event.get("uca_pathway_summary") if final_event else []) if q.get("claim_status") == "abductive_candidate"}
            }),
            "final_active_uca_set": final_event.get("active_uca_set") if final_event else [],
            "final_blocked_or_suppressed_uca_set": final_event.get("blocked_or_suppressed_uca_set") if final_event else [],
            "final_mechanism_summary": final_event.get("mechanism_paragraph") if final_event else None,
            "final_top_pathway": final_event.get("top_pathway") if final_event else None,
            "final_tabletop_replay_package_path": final_event.get("tabletop_replay_package_path") if final_event else None,
            "final_replay_question_count": final_event.get("replay_question_count") if final_event else 0,
            "final_missing_requirement_count": final_event.get("missing_requirement_count") if final_event else 0,
            "final_blocked_claim_count": final_event.get("blocked_claim_count") if final_event else 0,
            "final_replay_ready": final_event.get("replay_ready") if final_event else False,
            "final_pathway_status_counts": final_event.get("pathway_status_counts") if final_event else {},
            "final_num_candidate_pathways": final_event.get("num_candidate_pathways") if final_event else 0,
            "final_source_regime": get_case_source_regime_from_case(case_spec),
        },
    }
    write_json(out / "bundle_summary.json", bundle)
    return bundle


def build_causal_chain_export(round3: Dict[str, Any], committed_state: str) -> Dict[str, Any]:
    catalog_by_id = DRIVER_UCA_BY_ID
    rows = []
    for u in round3.get("activated_ucas", []):
        uca_id = u.get("uca_id")
        meta = catalog_by_id.get(uca_id, {})
        rows.append({
            "uca_id": uca_id,
            "canonical_uca_ref": meta.get("canonical_uca_ref"),
            "control_action": meta.get("control_action"),
            "uca_type": meta.get("uca_type"),
            "causal_factor_chain": meta.get("causal_factor_chain"),
            "activation_reason": u.get("activation_reason"),
            "supporting_evidence_ids": u.get("supporting_evidence_ids", []),
        })
    return {
        "committed_fsm_state": committed_state,
        "uca_activation_status": round3.get("uca_activation_status"),
        "activated_causal_chains": rows,
        "dominant_uca": round3.get("dominant_uca"),
    }


def _evidence_by_id(evidence_items: Sequence[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {str(e.get("evidence_id")): e for e in evidence_items if e.get("evidence_id")}


def _reported_outcome_from_event(event: Dict[str, Any]) -> Dict[str, Any]:
    car = event.get("CAR", {}) if isinstance(event, dict) else {}
    evt = unwrap_value(car.get("event_type", {}))
    intervention = unwrap_value(car.get("reported_intervention", {}))
    system_issue = unwrap_value(car.get("reported_system_issue", {}))
    return {
        "event_type": evt or "unknown",
        "reported_intervention": intervention or "not_reported",
        "reported_system_issue": system_issue or "not_reported",
    }


def detect_safe_intervention_signal(evidence_items: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    safe_terms = ["safe stop", "safely took control", "safely take control", "navigated to the next safe stop", "re-engaged autonomy", "reengaged autonomy", "manual to clear the error", "navigated around"]
    late_terms = ["late", "delayed", "too late", "collision after", "unable to", "failed to"]
    matches = []
    late_matches = []
    for item in evidence_items:
        if item.get("provenance") == "not_reported":
            continue
        text = " ".join(str(item.get(k, "")) for k in ["value", "source_text", "derivation_basis"]).lower()
        if any(t in text for t in safe_terms):
            matches.append(item.get("evidence_id"))
        if any(t in text for t in late_terms):
            late_matches.append(item.get("evidence_id"))
    return {
        "safe_intervention_detected": bool(matches),
        "safe_intervention_evidence_ids": sorted(set(matches)),
        "late_or_failed_intervention_evidence_ids": sorted(set(late_matches)),
        "guard_applies": bool(matches) and not bool(late_matches),
    }


def evaluate_outcome_compatibility_gate(
    *,
    uca_obj: Dict[str, Any],
    uca_meta: Dict[str, Any],
    is_active: bool,
    evidence_ids: Sequence[str],
    evidence_by_id: Dict[str, Dict[str, Any]],
    outcome: Dict[str, Any],
    safe_guard: Dict[str, Any],
) -> Dict[str, Any]:
    """Evaluate reported outcome as a compatibility constraint, not UCA evidence."""
    event_text = " ".join(str(outcome.get(k, "")) for k in ["event_type", "reported_intervention", "reported_system_issue"]).lower()
    patterns = [str(x).lower() for x in uca_meta.get("outcome_compatibility_patterns", [])]
    compatible = bool(event_text.strip()) and any(p and p in event_text for p in patterns)
    positive_ids = [eid for eid in evidence_ids if evidence_by_id.get(eid, {}).get("provenance") != "not_reported"]
    roles = [classify_evidence_role_for_uca(evidence_by_id.get(eid)) for eid in positive_ids]
    role_counts = dict(Counter(roles))
    outcome_only = bool(positive_ids) and all(role == "terminal_outcome" for role in roles)
    has_action_evidence = bool(set(roles) & ACTION_EVIDENCE_ROLES)
    contradiction = bool(safe_guard.get("guard_applies") and is_active)
    if contradiction or (is_active and (outcome_only or not has_action_evidence)):
        status = "fail"
    elif compatible:
        status = "weak" if outcome_only or not is_active else "pass"
    else:
        status = "weak"
    return {
        "status": status,
        "question": "Is the candidate UCA/action pathway compatible with the reported terminal outcome without using that outcome as activation evidence?",
        "reported_outcome": outcome,
        "compatible_with_reported_outcome": compatible,
        "outcome_used_as": "compatibility_constraint" if compatible else "not_used",
        "outcome_cannot_support": "UCA activation, driver mental state, takeover failure, or true accident cause",
        "activation_evidence_type": "outcome_only_blocked" if outcome_only else "action_context_evidence" if has_action_evidence else "context_only_blocked" if positive_ids else "weak_context_only",
        "evidence_role_counts": role_counts,
        "outcome_only_positive_evidence": outcome_only,
        "action_evidence_present": has_action_evidence,
        "safe_intervention_contradiction": contradiction,
        "supporting_evidence_ids": [],
    }


def build_outcome_compatibility_v23(
    uca_node: Dict[str, Any],
    evidence_items: Sequence[Dict[str, Any]],
    outcome: Dict[str, Any],
) -> Dict[str, Any]:
    """Use reported outcome only as a compatibility constraint for a forward UCA hypothesis."""
    meta = DRIVER_UCA_BY_ID.get(uca_node.get("uca_id"), {})
    event_text = " ".join(str(outcome.get(k, "")) for k in ["event_type", "reported_intervention", "reported_system_issue"]).lower()
    patterns = [str(x).lower() for x in meta.get("outcome_compatibility_patterns", [])]
    compatible = bool(event_text.strip()) and any(p and p in event_text for p in patterns)
    safe_guard = detect_safe_intervention_signal(evidence_items)
    contradicted = bool(safe_guard.get("guard_applies") and uca_node.get("uca_id") in SAFE_INTERVENTION_BLOCKED_DRIVER_UCAS)
    if contradicted:
        label = "contradicted"
    elif compatible and uca_node.get("claim_status") == "observed_admissible":
        label = "compatible"
    elif compatible:
        label = "weakly_compatible"
    else:
        label = "not_assessable"
    return {
        "reported_outcome": outcome,
        "compatible_with_uca": label,
        "outcome_used_as": "compatibility_constraint",
        "outcome_not_used_for": [
            "UCA activation",
            "driver mental state inference",
            "true accident cause",
        ],
        "safe_intervention_guard": safe_guard,
        "rationale": (
            "The reported endpoint is compared against the UCA catalog's outcome-compatibility patterns. "
            "It does not provide positive evidence for the UCA hypothesis."
        ),
    }


def _collect_pm_flaw_ids(pm_context: Dict[str, Any]) -> List[str]:
    ids: List[str] = []
    for node in pm_context.get("pm_context_nodes", []) or []:
        for flaw in node.get("pm_flaw_hypotheses", []) or []:
            if flaw.get("flaw_type") != "none_supported":
                ids.append(flaw.get("flaw_id") or f"PMF-{node.get('dimension')}")
    return [x for x in dict.fromkeys(ids) if x]


def _collect_update_hypothesis_ids(update_process: Dict[str, Any]) -> List[str]:
    ids: List[str] = []
    for node in update_process.get("update_process_nodes", []) or []:
        for hyp in node.get("abductive_update_hypotheses", []) or []:
            ids.append(hyp.get("hypothesis_id") or node.get("node_id"))
        observed = node.get("observed_update_issue") or {}
        if observed.get("label") not in (None, "none"):
            ids.append(node.get("node_id"))
    return [x for x in dict.fromkeys(ids) if x]


def _collect_gap_ids_from_pm_update(pm_context: Dict[str, Any], update_process: Dict[str, Any]) -> List[str]:
    ids: List[str] = []
    for node in pm_context.get("pm_context_nodes", []) or []:
        ids.extend(node.get("missing_evidence_ids", []) or [])
        for flaw in node.get("pm_flaw_hypotheses", []) or []:
            ids.extend(flaw.get("missing_evidence_ids", []) or [])
    for node in update_process.get("update_process_nodes", []) or []:
        ids.extend((node.get("evidence_gap_update_risk") or {}).get("gap_evidence_ids", []) or [])
        for hyp in node.get("abductive_update_hypotheses", []) or []:
            ids.extend(hyp.get("missing_evidence_ids", []) or [])
    return [x for x in dict.fromkeys(ids) if x]


def canonicalize_update_gap_labels(raw_labels: Sequence[str]) -> List[str]:
    labels = []
    raw_texts = [str(x).lower() for x in raw_labels if str(x).strip()]
    for canonical, needles in CANONICAL_UPDATE_GAP_TAXONOMY.items():
        if any(any(n in raw for n in needles) for raw in raw_texts):
            labels.append(canonical)
    return labels or ["missing_unspecified_safety_analysis_evidence"]


def attach_canonical_gap_taxonomy(update_process: Dict[str, Any]) -> Dict[str, Any]:
    update_process = dict(update_process)
    nodes = []
    for node in update_process.get("update_process_nodes", []) or []:
        node = dict(node)
        gap = dict(node.get("evidence_gap_update_risk") or {})
        raw = list(gap.get("labels") or [])
        gap["raw_gap_labels"] = raw
        gap["canonical_gap_labels"] = canonicalize_update_gap_labels(raw)
        node["evidence_gap_update_risk"] = gap
        nodes.append(node)
    update_process["update_process_nodes"] = nodes
    return update_process


def _canonical_gaps(update_process: Dict[str, Any]) -> set[str]:
    out: set[str] = set()
    for node in update_process.get("update_process_nodes", []) or []:
        out.update((node.get("evidence_gap_update_risk") or {}).get("canonical_gap_labels") or [])
    return out


def _action_by_id(action_selection: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {n.get("node_id"): n for n in action_selection.get("action_selection_nodes", []) or [] if n.get("node_id")}


def _uca_gate_v241(uca_id: str, action: Dict[str, Any], update_process: Dict[str, Any], evidence_items: Sequence[Dict[str, Any]]) -> Tuple[str, List[str], str]:
    """Return abductive_strength, blocking_reasons, and rationale for a UCA/action pair."""
    gaps = _canonical_gaps(update_process)
    action_name = action.get("candidate_action")
    supporting = action.get("supporting_evidence_ids") or []
    missing = action.get("missing_evidence_ids") or []
    has_action_evidence = evidence_ids_have_action_evidence(supporting, evidence_items)
    blocks: List[str] = []
    if uca_id == "UCA-H-1":
        if not (gaps & {"missing_hmi_or_mode_feedback", "missing_actor_observability", "missing_environment_observability", "missing_ads_behavior_feedback"}):
            blocks.append("no_case_specific_monitoring_or_observability_gap")
        strength = "weak_abductive" if not blocks else "blocked"
    elif uca_id == "UCA-H-2":
        if not (
            action_name in {"prepare_takeover", "initiate_takeover", "initiate_intervention", "maintain_no_intervention"}
            and (gaps & {"missing_time_budget_or_transition_cue", "missing_driver_response_evidence", "missing_hmi_or_mode_feedback"})
        ):
            blocks.append("no_case_specific_transfer_or_fallback_pressure")
        strength = "weak_abductive" if not blocks else "blocked"
    elif uca_id == "UCA-H-3":
        if not (gaps & {"missing_time_budget_or_transition_cue", "missing_driver_response_evidence"}):
            blocks.append("no_case_specific_timing_pressure_or_timing_gap")
        strength = "speculative_abductive" if not blocks else "blocked"
    elif uca_id == "UCA-H-5":
        if not (has_action_evidence or any("manual" in str(x).lower() or "steer" in str(x).lower() or "brak" in str(x).lower() for x in supporting + missing)):
            blocks.append("no_manual_control_or_control_quality_context")
        strength = "speculative_abductive" if not blocks else "blocked"
    elif uca_id == "UCA-H-6":
        if not any("fallback" in str(x).lower() or "safe" in str(x).lower() for x in supporting + missing):
            blocks.append("no_safe_stop_or_fallback_context")
        strength = "speculative_abductive" if not blocks else "blocked"
    else:
        blocks.append("unknown_uca_gate")
        strength = "blocked"
    if has_action_evidence and strength != "blocked":
        strength = "strong_abductive"
    rationale = f"v2.4.1 gate for {uca_id} with action {action_name}; canonical gaps={sorted(gaps)}."
    return strength, blocks, rationale


def _evidence_text_for_features(evidence_items: Sequence[Dict[str, Any]]) -> str:
    return " ".join(
        " ".join(str(item.get(k, "")) for k in ["field_path", "value", "source_text", "derivation_basis", "summary"])
        for item in evidence_items
        if item.get("provenance") != "not_reported"
    ).lower()


def _field_is_missing(evidence_items: Sequence[Dict[str, Any]], field_path: str) -> bool:
    return any(item.get("field_path") == field_path and item.get("provenance") == "not_reported" for item in evidence_items)


def _field_is_reported(evidence_items: Sequence[Dict[str, Any]], field_path: str) -> bool:
    return any(item.get("field_path") == field_path and item.get("provenance") != "not_reported" for item in evidence_items)


def extract_case_evidence_features_v242(
    evidence_items: Sequence[Dict[str, Any]],
    pm_context: Dict[str, Any],
    update_process: Dict[str, Any],
    action_selection: Dict[str, Any],
    committed_state: Optional[str] = None,
) -> Dict[str, Any]:
    text = _evidence_text_for_features(evidence_items)
    gaps = _canonical_gaps(update_process)
    features = {
        "ads_active": _field_is_reported(evidence_items, "CAR.automation_context") or "ads" in text or "autonomous" in text,
        "complex_road": _field_is_reported(evidence_items, "ENV.road_geometry") or _field_is_reported(evidence_items, "ENV.intersection_type") or any(k in text for k in ["intersection", "cross", "lane", "turn"]),
        "actor_prediction_uncertainty": _field_is_reported(evidence_items, "ACTOR.prediction_uncertainty") or "uncertain" in text,
        "hmi_mode_missing": _field_is_missing(evidence_items, "HMI.mode_state_display"),
        "time_budget_missing": _field_is_missing(evidence_items, "HMI.time_budget_indicator") or _field_is_missing(evidence_items, "CAR.time_budget_to_handover"),
        "driver_state_missing": _field_is_missing(evidence_items, "CABIN.pressure") or _field_is_missing(evidence_items, "CABIN.distraction"),
        "actor_observability_missing": _field_is_missing(evidence_items, "ACTOR.primary_observability") or "missing_actor_observability" in gaps,
        "reported_intervention": _field_is_reported(evidence_items, "CAR.reported_intervention") or "interven" in text or "test driver" in text,
        "reported_disengagement": "disengagement" in text or "disengaged" in text,
        "reported_system_issue": _field_is_reported(evidence_items, "CAR.reported_system_issue") or any(k in text for k in ["system issue", "planner", "perception"]),
        "manual_control_evidence": any(k in text for k in ["manual", "brak", "steer", "took control", "takeover"]),
        "timing_context": bool(gaps & {"missing_time_budget_or_transition_cue", "missing_driver_response_evidence"}) or any(k in text for k in ["late", "delayed", "time", "takeover", "handover"]),
        "fallback_context": any(k in text for k in ["fallback", "safe stop", "minimal risk", "disengagement", "system issue"]),
        "outcome_only_collision": _field_is_reported(evidence_items, "CAR.event_type") and not (_field_is_reported(evidence_items, "CAR.reported_intervention") or _field_is_reported(evidence_items, "CAR.reported_system_issue")),
        "canonical_update_gaps": sorted(gaps),
        "committed_state": committed_state,
    }
    features["supervision_demand_score"] = sum(bool(features[k]) for k in ["ads_active", "complex_road", "actor_prediction_uncertainty"])
    features["monitoring_gap_score"] = sum(bool(features[k]) for k in ["driver_state_missing", "hmi_mode_missing", "time_budget_missing", "actor_observability_missing"])
    features["transfer_pressure_score"] = sum(bool(x) for x in [
        committed_state == "not_supported_transfer",
        features["reported_intervention"],
        features["reported_disengagement"],
        features["reported_system_issue"],
        features["hmi_mode_missing"] or features["time_budget_missing"],
        features["actor_prediction_uncertainty"] or features["complex_road"],
    ])
    return features


def _uca_gate_v242(
    uca_id: str,
    action: Dict[str, Any],
    features: Dict[str, Any],
    evidence_items: Sequence[Dict[str, Any]],
) -> Tuple[str, List[str], Dict[str, Any]]:
    action_name = action.get("candidate_action")
    supporting = action.get("supporting_evidence_ids") or []
    missing = action.get("missing_evidence_ids") or []
    has_action_evidence = evidence_ids_have_action_evidence(supporting, evidence_items)
    passed: List[str] = []
    failed: List[str] = []

    def req(name: str, ok: bool) -> None:
        (passed if ok else failed).append(name)

    if uca_id == "UCA-H-1":
        req("action_is_monitoring_or_readiness", action_name in {"continue_monitoring", "prepare_takeover"})
        req("supervision_demand_score_at_least_2", int(features.get("supervision_demand_score", 0)) >= 2)
        req("monitoring_gap_score_at_least_1", int(features.get("monitoring_gap_score", 0)) >= 1)
    elif uca_id == "UCA-H-2":
        req("action_is_transfer_relevant", action_name in {"prepare_takeover", "initiate_takeover", "initiate_intervention", "maintain_no_intervention"})
        req("transfer_pressure_score_at_least_2", int(features.get("transfer_pressure_score", 0)) >= 2)
        req("not_only_collision_outcome", not bool(features.get("outcome_only_collision")) or int(features.get("transfer_pressure_score", 0)) >= 3)
    elif uca_id == "UCA-H-3":
        req("action_is_takeover_or_intervention", action_name in {"initiate_takeover", "initiate_intervention"})
        req("timing_context_present", bool(features.get("timing_context")))
        req("action_timing_gap_present", bool(features.get("time_budget_missing") or not features.get("reported_intervention")))
    elif uca_id == "UCA-H-5":
        req("action_is_manual_control_quality", action_name in {"modulate_braking", "modulate_steering"})
        req("manual_control_evidence_or_gap", bool(features.get("manual_control_evidence") or any("manual" in str(x).lower() or "steer" in str(x).lower() or "brak" in str(x).lower() for x in supporting + missing)))
    elif uca_id == "UCA-H-6":
        req("action_is_safe_stop", action_name == "safe_stop_or_minimal_risk_response")
        req("fallback_context_present", bool(features.get("fallback_context")))
    else:
        failed.append("unknown_uca")

    if failed:
        strength = "blocked"
    elif has_action_evidence:
        strength = "strong_abductive"
    elif uca_id in {"UCA-H-3", "UCA-H-5", "UCA-H-6"}:
        strength = "speculative_abductive"
    else:
        strength = "weak_abductive"
    gate_result = {
        "passed": not failed,
        "passed_conditions": passed,
        "failed_conditions": failed,
        "case_evidence_features": features,
    }
    return strength, failed, gate_result


def expand_forward_uca_candidates_v242(
    *,
    uca_context: Dict[str, Any],
    pm_context: Dict[str, Any],
    update_process: Dict[str, Any],
    other_factors: Dict[str, Any],
    action_selection: Dict[str, Any],
    evidence_items: Sequence[Dict[str, Any]],
    committed_state: Optional[str] = None,
) -> Dict[str, Any]:
    """Expand the abductive UCA candidate space without creating observed claims.

    This is a candidate-space expander, not a semantic repair step: generated
    nodes are only abductive_candidate or blocked and still cite the PM/update/
    action chain plus missing evidence rather than terminal outcomes.
    """
    raw_nodes = list(uca_context.get("uca_context_nodes", []) or [])
    dropped_nodes = [
        {
            "node_id": n.get("node_id"),
            "uca_id": n.get("uca_id"),
            "reason": "dropped_no_linked_action_control_action_required_by_stpa_hf",
        }
        for n in raw_nodes
        if n.get("uca_id") and not (n.get("action_selection_node_ids") or n.get("linked_action_id"))
    ]
    nodes = [
        n for n in raw_nodes
        if not (n.get("uca_id") and not (n.get("action_selection_node_ids") or n.get("linked_action_id")))
    ]
    pm_flaws = _collect_pm_flaw_ids(pm_context)
    update_hyps = _collect_update_hypothesis_ids(update_process)
    gap_ids = _collect_gap_ids_from_pm_update(pm_context, update_process)
    other_ids = [n.get("node_id") for n in other_factors.get("other_factor_nodes", []) or [] if n.get("node_id")]
    action_nodes = action_selection.get("action_selection_nodes", []) or []
    actions_by_id = {n.get("node_id"): n for n in action_nodes if n.get("node_id")}
    evidence_features = extract_case_evidence_features_v242(
        evidence_items=evidence_items,
        pm_context=pm_context,
        update_process=update_process,
        action_selection=action_selection,
        committed_state=committed_state,
    )
    normalized_nodes: List[Dict[str, Any]] = []
    for raw_node in nodes:
        node = dict(raw_node)
        action_id = node.get("linked_action_id") or ((node.get("action_selection_node_ids") or [None])[0])
        action_obj = actions_by_id.get(action_id)
        if action_id:
            node["linked_action_id"] = action_id
        if action_obj:
            node["linked_action"] = action_obj.get("candidate_action")
            node["action_selection_node_ids"] = [action_id]
            strength, gate_blocks, gate_result = _uca_gate_v242(str(node.get("uca_id")), action_obj, evidence_features, evidence_items)
            node["gate_result"] = gate_result
            action_is_blocked = action_obj.get("claim_status") == "blocked" or action_obj.get("action_role") == "blocked"
            if action_is_blocked:
                node["claim_status"] = "blocked"
                node["classification"] = "blocked"
                node["abductive_strength"] = "blocked"
                node["blocking_reasons"] = list(dict.fromkeys((node.get("blocking_reasons") or []) + ["linked_action_blocked"] + gate_blocks))
            elif node.get("claim_status") == "abductive_candidate":
                if strength == "blocked":
                    node["claim_status"] = "blocked"
                    node["classification"] = "blocked"
                    node["abductive_strength"] = "blocked"
                    node["blocking_reasons"] = list(dict.fromkeys((node.get("blocking_reasons") or []) + gate_blocks))
                else:
                    node["abductive_strength"] = strength
            elif node.get("claim_status") == "blocked":
                node["abductive_strength"] = "blocked"
                node["blocking_reasons"] = list(dict.fromkeys((node.get("blocking_reasons") or []) + (gate_blocks or ["blocked_by_original_uca_context"])))
        else:
            node["claim_status"] = "blocked"
            node["classification"] = "blocked"
            node["abductive_strength"] = "blocked"
            node["gate_result"] = {
                "passed": False,
                "passed_conditions": [],
                "failed_conditions": ["linked_action_not_found"],
                "case_evidence_features": evidence_features,
            }
            node["blocking_reasons"] = list(dict.fromkeys((node.get("blocking_reasons") or []) + ["linked_action_not_found"]))
        if not node.get("generated_by"):
            node["generated_by"] = "llm_uca_context_normalized_by_v242_gate"
        normalized_nodes.append(node)
    nodes = normalized_nodes
    existing_pairs = {(n.get("uca_id"), tuple(n.get("action_selection_node_ids") or [])) for n in nodes}
    action_to_uca = {
        "continue_monitoring": ["UCA-H-1"],
        "prepare_takeover": ["UCA-H-1", "UCA-H-2"],
        "initiate_takeover": ["UCA-H-2", "UCA-H-3"],
        "initiate_intervention": ["UCA-H-2", "UCA-H-3"],
        "maintain_no_intervention": ["UCA-H-2"],
        "modulate_braking": ["UCA-H-5"],
        "modulate_steering": ["UCA-H-5"],
        "safe_stop_or_minimal_risk_response": ["UCA-H-6"],
    }
    for act in action_nodes:
        action_id = act.get("node_id")
        action = act.get("candidate_action")
        if not action_id or action not in action_to_uca:
            continue
        chain_complete = bool(pm_flaws and update_hyps and action_id)
        for uca_id in action_to_uca[action]:
            pair = (uca_id, (action_id,))
            if pair in existing_pairs:
                continue
            meta = DRIVER_UCA_BY_ID.get(uca_id, {})
            strength, gate_blocks, gate_result = _uca_gate_v242(uca_id, act, evidence_features, evidence_items)
            status = "abductive_candidate" if chain_complete and act.get("claim_status") != "blocked" and strength != "blocked" else "blocked"
            classification = "suppressed" if status == "abductive_candidate" else "blocked"
            node = {
                "node_id": f"UCACTX-V242-{uca_id}-{action_id}",
                "uca_id": uca_id,
                "controller": meta.get("controller", "driver_or_safety_operator"),
                "control_action": meta.get("control_action", action),
                "linked_action_id": action_id,
                "linked_action": action,
                "stpa_uca_type": STPA_UCA_CATEGORY_MAP.get(str(meta.get("uca_type")), str(meta.get("uca_type"))),
                "unsafe_context_text": meta.get("unsafe_context_template", ""),
                "hazard_link": meta.get("hazard_link", ""),
                "action_selection_node_ids": [action_id],
                "forward_derivation": {
                    "pm_flaw_inputs": pm_flaws,
                    "update_flaw_inputs": update_hyps,
                    "action_selection_inputs": [action_id],
                    "other_factor_inputs": other_ids,
                },
                "supporting_evidence_ids": [],
                "missing_evidence_ids": gap_ids[:20],
                "required_context": meta.get("minimum_required_evidence", []),
                "blocking_reasons": gate_blocks if status == "abductive_candidate" else (gate_blocks or ["incomplete_pm_update_action_chain"]),
                "blocked_claims": [
                    "Cannot assert this UCA as observed without direct driver/operator action or action-quality evidence."
                ],
                "why_not_directly_observed": "The report does not provide direct source-visible evidence that this driver/safety-operator control action was unsafe.",
                "why_not_outcome_derived": "The reported outcome is used only as a compatibility constraint and is not used to derive this UCA.",
                "internal_reasoning_text": (
                    f"v2.4.2 candidate-space expansion links action {action_id} ({action}) to {uca_id} through "
                    f"PM flaw and update-process hypotheses. Gate result: passed={gate_result.get('passed')}, "
                    f"passed_conditions={gate_result.get('passed_conditions')}, failed_conditions={gate_result.get('failed_conditions')}. The claim remains abductive or "
                    "blocked because direct driver action evidence is missing."
                ),
                "display_summary": f"Forward-derived {status} UCA candidate {uca_id} from action {action}.",
                "classification": classification,
                "claim_strength": "weakly_supported" if status == "abductive_candidate" else "blocked",
                "claim_status": status,
                "abductive_strength": strength,
                "gate_result": gate_result,
                "generated_by": "expand_forward_uca_candidates_v242",
            }
            nodes.append(node)
            existing_pairs.add(pair)
    observed = sorted({n.get("uca_id") for n in nodes if n.get("claim_status") == "observed_admissible" and n.get("uca_id")})
    abductive_nodes = [n for n in nodes if n.get("claim_status") == "abductive_candidate" and n.get("uca_id")]
    blocked_nodes = [n for n in nodes if n.get("claim_status") == "blocked" and n.get("uca_id")]
    abductive = sorted({n.get("uca_id") for n in abductive_nodes})
    blocked = sorted({n.get("uca_id") for n in blocked_nodes if n.get("uca_id") not in set(abductive)})
    pathway_summary = [
        {
            "uca_id": n.get("uca_id"),
            "linked_action_id": n.get("linked_action_id") or ((n.get("action_selection_node_ids") or [None])[0]),
            "linked_action": n.get("linked_action"),
            "claim_status": n.get("claim_status"),
            "abductive_strength": n.get("abductive_strength"),
            "gate_result": n.get("gate_result"),
            "blocking_reasons": n.get("blocking_reasons") or [],
        }
        for n in nodes
        if n.get("uca_id") and n.get("claim_status") in {"observed_admissible", "abductive_candidate", "blocked"}
    ]
    uca_context = dict(uca_context)
    uca_context["uca_context_nodes"] = nodes
    uca_context["dropped_uca_nodes_v242"] = dropped_nodes
    uca_context["evidence_features_v242"] = evidence_features
    uca_context["uca_pathway_summary"] = pathway_summary
    uca_context["no_admissible_uca_summary"] = {
        "has_admissible_or_abductive_uca": bool(observed or abductive),
        "reason": "" if (observed or abductive) else "No UCA/action pathway passed the v2.4.2 case-specific STPA-HF gate.",
        "blocked_pathway_count": len(blocked_nodes),
        "blocked_pathways": [p for p in pathway_summary if p.get("claim_status") == "blocked"],
    }
    uca_context["observed_uca_set"] = observed
    uca_context["abductive_uca_candidates"] = abductive
    uca_context["blocked_uca_set"] = blocked
    uca_context["activated_uca_set"] = observed
    uca_context["blocked_or_suppressed_uca_set"] = sorted({n.get("uca_id") for n in nodes if n.get("classification") in {"blocked", "suppressed"} and n.get("uca_id")})
    uca_context["uca_activation_status"] = "activated" if observed else "no_activated_uca"
    if not observed:
        uca_context["dominant_uca"] = None
        uca_context["dominant_uca_rationale"] = ""
    uca_context["integrated_uca_text"] = (
        str(uca_context.get("integrated_uca_text", "")).strip()
        + f" v2.4.2 expansion: observed={len(observed)}, abductive_pathways={len(abductive_nodes)}, blocked_pathways={len(blocked_nodes)}."
    ).strip()
    return uca_context


def expand_forward_uca_candidates_v241(**kwargs: Any) -> Dict[str, Any]:
    """Compatibility wrapper for older callers; implements v2.4.2 gating."""
    return expand_forward_uca_candidates_v242(**kwargs)


def _slot_by_quadrant(round2a: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for slot in round2a.get("slot_updates", []) or []:
        q = slot.get("quadrant")
        if q:
            out[q] = slot
    return out


def _evidence_summary_for_ids(evidence_by_id: Dict[str, Dict[str, Any]], ids: Sequence[str]) -> List[Dict[str, Any]]:
    rows = []
    for eid in ids:
        e = evidence_by_id.get(str(eid))
        if not e:
            continue
        rows.append({
            "evidence_id": e.get("evidence_id"),
            "field_path": e.get("field_path"),
            "value": e.get("value"),
            "provenance": e.get("provenance"),
            "visibility": e.get("visibility"),
            "summary": e.get("summary"),
        })
    return rows


def build_candidate_pathways(
    case_id: str,
    event_index: int,
    evidence_items: Sequence[Dict[str, Any]],
    pm_context: Dict[str, Any],
    update_process: Dict[str, Any],
    other_factors: Dict[str, Any],
    boundary: Dict[str, Any],
    action_selection: Dict[str, Any],
    uca_context: Dict[str, Any],
    committed_state: str,
    event: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Build STPA-HF explanatory pathway candidates before LLM judge ranking."""
    evidence_by_id = _evidence_by_id(evidence_items)
    pm_nodes = {n.get("dimension"): n for n in pm_context.get("pm_context_nodes", []) or []}
    pm_nodes_by_id = {n.get("node_id"): n for n in pm_context.get("pm_context_nodes", []) or []}
    upd_nodes = {n.get("node_id"): n for n in update_process.get("update_process_nodes", []) or []}
    other_nodes = {n.get("node_id"): n for n in other_factors.get("other_factor_nodes", []) or []}
    action_nodes = {n.get("node_id"): n for n in action_selection.get("action_selection_nodes", []) or []}
    uca_nodes = uca_context.get("uca_context_nodes", []) or []
    catalog_by_id = DRIVER_UCA_BY_ID
    outcome = _reported_outcome_from_event(event)
    observed = [u for u in uca_nodes if u.get("claim_status") == "observed_admissible"]
    abductive = [u for u in uca_nodes if u.get("claim_status") == "abductive_candidate"]
    blocked = [u for u in uca_nodes if u.get("claim_status") == "blocked"]
    candidates: List[Dict[str, Any]] = []

    def _pathway_gate_status(
        uca_obj: Dict[str, Any],
        is_active: bool,
        pm_used: List[Dict[str, Any]],
        upd_used: List[Dict[str, Any]],
        action_nodes_used: List[Dict[str, Any]],
        evidence_ids: List[str],
    ) -> Tuple[Dict[str, Dict[str, Any]], List[str], str]:
        blocking: List[str] = []
        gates: Dict[str, Dict[str, Any]] = {}
        has_positive_evidence = any(evidence_by_id.get(eid, {}).get("provenance") != "not_reported" for eid in evidence_ids)
        action_ids = [n.get("node_id") for n in action_nodes_used if n]
        uca_ids = uca_obj.get("supporting_evidence_ids") or []

        gates["G1_uca_context_gate"] = {
            "status": "pass" if is_active and uca_ids else "weak" if uca_obj.get("unsafe_context_text") else "fail",
            "question": "Does the candidate UCA specify a driver control action in an unsafe context?",
            "supporting_evidence_ids": uca_ids,
        }
        gates["G2_pm_variable_gate"] = {
            "status": "pass" if len(pm_used) >= 3 else "weak" if pm_used else "fail",
            "question": "Are required CPS/CPB/OPS/OPB process-model variables present for this pathway?",
            "pm_node_ids": [n.get("node_id") for n in pm_used],
        }
        observed_claims = [
            n for n in upd_used
            if (n.get("observed_update_vulnerability") or {}).get("label") not in (None, "none")
            and n.get("update_evidence_status") == "observed_update_claim"
        ]
        gap_claims = [n for n in upd_used if n.get("update_evidence_status") == "evidence_gap_only"]
        gates["G3_pm_flaw_gate"] = {
            "status": "pass" if observed_claims else "weak" if gap_claims or upd_used else "fail",
            "question": "Is a process-model flaw observed, weakly suggested, or only represented as an evidence gap?",
            "update_node_ids": [n.get("node_id") for n in upd_used],
        }
        gates["G4_update_process_gate"] = {
            "status": "pass" if observed_claims else "weak" if gap_claims else "fail",
            "question": "Can the report explain process-model formation/update without treating missing feedback as fact?",
            "update_evidence_statuses": [n.get("update_evidence_status") for n in upd_used],
        }
        gates["G5_action_selection_gate"] = {
            "status": "pass" if action_nodes_used and any(n.get("claim_strength") == "supported" for n in action_nodes_used) else "weak" if action_nodes_used else "fail",
            "question": "Is the candidate driver control action specific enough for STPA-HF UCA classification?",
            "action_node_ids": action_ids,
        }
        safe_guard = detect_safe_intervention_signal(evidence_items)
        meta = catalog_by_id.get(uca_obj.get("uca_id"), {})
        outcome_gate = evaluate_outcome_compatibility_gate(
            uca_obj=uca_obj,
            uca_meta=meta,
            is_active=is_active,
            evidence_ids=evidence_ids,
            evidence_by_id=evidence_by_id,
            outcome=outcome,
            safe_guard=safe_guard,
        )
        gates["G7_outcome_compatibility_gate"] = outcome_gate
        not_reported_fact_risk = bool(is_active and not has_positive_evidence)
        gates["G6_evidence_admissibility_gate"] = {
            "status": "fail" if not_reported_fact_risk else "pass" if has_positive_evidence else "weak",
            "question": "Does the pathway avoid using not_reported evidence as a positive fact?",
            "positive_evidence_present": has_positive_evidence,
        }
        if not action_nodes_used:
            blocking.append("missing_control_action_evidence")
        if not uca_ids and is_active:
            blocking.append("missing_uca_context_evidence")
        if gates["G4_update_process_gate"]["status"] == "fail":
            blocking.append("missing_update_process_evidence")
        if gates["G6_evidence_admissibility_gate"]["status"] == "fail":
            blocking.append("not_reported_used_as_positive_fact")
        if gates["G7_outcome_compatibility_gate"]["status"] == "fail":
            if outcome_gate.get("outcome_only_positive_evidence"):
                blocking.append("outcome_only_not_sufficient")
            if not outcome_gate.get("action_evidence_present"):
                blocking.append("missing_driver_action_or_state_evidence")
            if outcome_gate.get("safe_intervention_contradiction"):
                blocking.append("safe_intervention_contradicts_failure_pathway")
        blocking.extend(uca_obj.get("blocking_reasons") or [])
        if uca_obj.get("claim_status") == "blocked" and not blocking:
            blocking.append("uca_candidate_blocked_or_suppressed_by_llm_context")
        if any(g["status"] == "fail" for g in gates.values()) or uca_obj.get("claim_status") == "blocked":
            status = "blocked"
        elif uca_obj.get("claim_status") == "observed_admissible" and all(g["status"] == "pass" for g in gates.values()):
            status = "admissible"
        else:
            status = "weakly_supported"
        return gates, list(dict.fromkeys(blocking)), status

    def add_pathway(uca_obj: Optional[Dict[str, Any]], is_active: bool, rank_seed: int, pathway_type_override: Optional[str] = None) -> None:
        uca_obj = uca_obj or {}
        uca_id = uca_obj.get("uca_id")
        meta = catalog_by_id.get(uca_id, {})
        action_ids = uca_obj.get("action_selection_node_ids") or []
        action_nodes_used = [action_nodes.get(aid) for aid in action_ids if aid in action_nodes]
        primary_action_id = uca_obj.get("linked_action_id") or (action_ids[0] if action_ids else None)
        primary_action = uca_obj.get("linked_action")
        if not primary_action and primary_action_id in action_nodes:
            primary_action = action_nodes[primary_action_id].get("candidate_action")
        pm_ids = []
        upd_ids = []
        other_ids = []
        for act in action_nodes_used:
            pm_ids.extend(act.get("pm_context_inputs", []) or [])
            upd_ids.extend(act.get("update_process_inputs", []) or [])
            other_ids.extend(act.get("other_factor_inputs", []) or [])
        resolved_pm_nodes = []
        for ref in dict.fromkeys(pm_ids):
            if ref in pm_nodes_by_id:
                resolved_pm_nodes.append(pm_nodes_by_id[ref])
            elif ref in pm_nodes:
                resolved_pm_nodes.append(pm_nodes[ref])
        pm_used = resolved_pm_nodes or [pm_nodes.get(dim) for dim in ALLOWED_QUADRANTS if dim in pm_nodes]
        upd_used = [upd_nodes.get(uid) for uid in dict.fromkeys(upd_ids) if uid in upd_nodes]
        other_used = [other_nodes.get(oid) for oid in dict.fromkeys(other_ids) if oid in other_nodes]
        evidence_ids = list(dict.fromkeys(
            [eid for node in pm_used for eid in (node.get("supporting_evidence_ids") or [])]
            + [eid for node in upd_used for eid in (node.get("triggering_evidence_ids") or [])]
            + [eid for node in other_used for eid in (node.get("supporting_evidence_ids") or [])]
            + (boundary.get("commitment_block", {}).get("supporting_evidence_ids") or [])
            + [eid for node in action_nodes_used for eid in (node.get("supporting_evidence_ids") or [])]
            + (uca_obj.get("supporting_evidence_ids") or [])
        ))
        uca_type = meta.get("uca_type")
        is_no_activation = pathway_type_override == "no_activated_uca_pathway"
        gates, blocking_reasons, pathway_status = _pathway_gate_status(uca_obj, is_active, pm_used, upd_used, action_nodes_used, evidence_ids)
        safe_guard = detect_safe_intervention_signal(evidence_items)
        guarded_failure = bool(safe_guard["guard_applies"] and uca_id in SAFE_INTERVENTION_BLOCKED_DRIVER_UCAS)
        final_status = pathway_status
        claim_status = uca_obj.get("claim_status") or ("observed_admissible" if is_active else "blocked")
        abductive_strength = uca_obj.get("abductive_strength") or ("blocked" if claim_status == "blocked" else "weak_abductive")
        if pathway_type_override:
            pathway_type = pathway_type_override
        elif claim_status == "observed_admissible":
            pathway_type = "observed_uca_pathway"
        elif claim_status == "abductive_candidate":
            pathway_type = "abductive_uca_pathway"
        else:
            pathway_type = "blocked_pathway"
        if guarded_failure:
            final_status = "blocked"
            pathway_type = "blocked_by_safe_intervention_guard"
            blocking_reasons.append("safe_intervention_guard_blocks_failure_pathway")
        outcome_compatibility = build_outcome_compatibility_v23(uca_obj, evidence_items, outcome) if not is_no_activation else {
            "reported_outcome": outcome,
            "compatible_with_uca": "not_assessable",
            "outcome_used_as": "compatibility_constraint",
            "outcome_not_used_for": ["UCA activation", "driver mental state inference", "true accident cause"],
            "rationale": "No UCA hypothesis was selected for this no-activation pathway.",
        }
        pathway_id_parts = ["P", str(uca_id or "NO-UCA")]
        if primary_action_id:
            pathway_id_parts.append(str(primary_action_id))
        pathway_id_parts.append(str(rank_seed))
        pathway_id_parts.append("v242")
        candidates.append({
            "pathway_id": "-".join(pathway_id_parts),
            "case_id": case_id,
            "event_index": event_index,
            "pathway_status_initial": final_status,
            "pathway_status": final_status,
            "pathway_type": pathway_type,
            "claim_status": claim_status,
            "abductive_strength": abductive_strength,
            "linked_action_id": primary_action_id,
            "linked_action": primary_action,
            "uca_gate_result": uca_obj.get("gate_result"),
            "safe_intervention_guard": safe_guard,
            "reported_outcome": outcome,
            "outcome_compatibility": outcome_compatibility,
            "stpa_hf_compliance_gates": gates,
            "blocking_reasons": list(dict.fromkeys(blocking_reasons)),
            "pm_variable_requirements": [
                {
                    "dimension": dim,
                    "definition": PM_QUADRANT_DEFINITIONS.get(dim, {}).get("definition"),
                    "node_id": pm_nodes.get(dim, {}).get("node_id"),
                    "required_for_pathway": True,
                    "claim_strength": pm_nodes.get(dim, {}).get("claim_strength"),
                    "supporting_evidence_ids": pm_nodes.get(dim, {}).get("supporting_evidence_ids", []),
                    "missing_evidence_ids": pm_nodes.get(dim, {}).get("missing_evidence_ids", []),
                }
                for dim in ALLOWED_QUADRANTS
            ],
            "pm_context_contribution": {
                dim: {
                    "node_id": pm_nodes.get(dim, {}).get("node_id"),
                    "internal_reasoning_text": pm_nodes.get(dim, {}).get("internal_reasoning_text"),
                    "supporting_evidence_ids": pm_nodes.get(dim, {}).get("supporting_evidence_ids", []),
                    "claim_strength": pm_nodes.get(dim, {}).get("claim_strength"),
                }
                for dim in ALLOWED_QUADRANTS
            },
            "update_process_contribution": {
                "node_ids": [node.get("node_id") for node in upd_used],
                "target_quadrants": [node.get("target_quadrant") for node in upd_used],
                "abductive_update_hypotheses": [
                    hyp for node in upd_used for hyp in (node.get("abductive_update_hypotheses") or [])
                ],
                "blocked_update_claims": [
                    claim for node in upd_used for claim in (node.get("blocked_update_claims") or [])
                ],
                "dominant_observed_vulnerability": (upd_obj.get("observed_update_vulnerability") or {}).get("label", "none") if (upd_obj := (upd_used[0] if upd_used else {})) else "none",
                "update_evidence_statuses": [node.get("update_evidence_status") for node in upd_used],
                "evidence_gap_update_risks": [node.get("evidence_gap_update_risk", {}) for node in upd_used],
                "internal_reasoning_text": " ".join(node.get("internal_reasoning_text", "") for node in upd_used),
                "supporting_evidence_ids": [
                    eid for node in upd_used
                    for eid in ((node.get("observed_update_vulnerability") or {}).get("supporting_evidence_ids") or [])
                ],
                "gap_evidence_ids": [
                    eid for node in upd_used
                    for eid in ((node.get("evidence_gap_update_risk") or {}).get("gap_evidence_ids") or [])
                ],
            },
            "other_factors_contribution": {
                "node_ids": [node.get("node_id") for node in other_used],
                "internal_reasoning_text": " ".join(node.get("internal_reasoning_text", "") for node in other_used),
                "supporting_evidence_ids": [eid for node in other_used for eid in (node.get("supporting_evidence_ids") or [])],
            },
            "commitment_boundary": committed_state,
            "boundary_reasoning_block": {
                "selected_boundary": committed_state,
                "fsm_node_definition": BOUNDARY_FSM_DEFINITIONS.get(committed_state, {}),
                "supporting_evidence_ids": boundary.get("commitment_block", {}).get("supporting_evidence_ids") or [],
                "basis_explanation": boundary.get("commitment_block", {}).get("basis_explanation"),
                "minimal_sufficiency_basis": boundary.get("commitment_block", {}).get("minimal_sufficiency_basis"),
            },
            "boundary_rationale": boundary.get("commitment_block", {}).get("boundary_rationale"),
            "driver_control_action": meta.get("control_action") if not is_no_activation else None,
            "uca_id": uca_id,
            "uca_short_name": meta.get("short_name") if not is_no_activation else None,
            "uca_description": meta.get("description") if not is_no_activation else None,
            "uca_type": uca_type,
            "stpa_uca_category": STPA_UCA_CATEGORY_MAP.get(str(uca_type), str(uca_type)) if not is_no_activation else None,
            "uca_activation_state": "activated" if is_active else "no_activated_uca" if is_no_activation else "suppressed",
            "uca_reason": uca_obj.get("internal_reasoning_text") or (uca_obj.get("activation_reason") if is_active else uca_obj.get("suppression_reason")),
            "uca_reasoning_block": {
                "driver_control_action": meta.get("control_action") if not is_no_activation else None,
                "stpa_uca_category": STPA_UCA_CATEGORY_MAP.get(str(uca_type), str(uca_type)) if not is_no_activation else None,
                "unsafe_context": committed_state,
                "unsafe_context_text": uca_obj.get("unsafe_context_text"),
                "forward_derivation": uca_obj.get("forward_derivation", {}),
                "linked_action_id": primary_action_id,
                "linked_action": primary_action,
                "gate_result": uca_obj.get("gate_result"),
                "claim_status": claim_status,
                "abductive_strength": abductive_strength,
                "required_context": uca_obj.get("required_context", []),
                "blocking_reasons": blocking_reasons,
                "blocked_claims": uca_obj.get("blocked_claims", []),
                "why_not_directly_observed": uca_obj.get("why_not_directly_observed"),
                "why_not_outcome_derived": uca_obj.get("why_not_outcome_derived"),
                "why_action_required_or_inappropriate": meta.get("description") if not is_no_activation else "No source-supported UCA activation under the current evidence boundary.",
                "guarded_by_safe_intervention": guarded_failure,
            },
            "outcome_compatibility_block": gates.get("G7_outcome_compatibility_gate"),
            "outcome_used_as": (gates.get("G7_outcome_compatibility_gate") or {}).get("outcome_used_as"),
            "outcome_cannot_support": (gates.get("G7_outcome_compatibility_gate") or {}).get("outcome_cannot_support"),
            "activation_evidence_type": (gates.get("G7_outcome_compatibility_gate") or {}).get("activation_evidence_type"),
            "mechanism_summary": uca_context.get("integrated_uca_text"),
            "graph_node_ids": [n.get("node_id") for n in pm_used] + [n.get("node_id") for n in upd_used] + [n.get("node_id") for n in other_used] + [n.get("node_id") for n in action_nodes_used] + ([uca_obj.get("node_id")] if uca_obj.get("node_id") else []),
            "node_chain": [
                {"node_type": "evidence", "ids": evidence_ids},
                {"node_type": "pm_context", "value": [n.get("node_id") for n in pm_used]},
                {"node_type": "update_process", "value": [n.get("node_id") for n in upd_used]},
                {"node_type": "other_factors", "value": [n.get("node_id") for n in other_used]},
                {"node_type": "boundary", "value": committed_state},
                {"node_type": "action_selection", "value": [n.get("node_id") for n in action_nodes_used]},
                {"node_type": "uca_context", "value": uca_id},
                {"node_type": "uca", "value": uca_id if not is_no_activation else None},
                {"node_type": "uca_activation_status", "value": "no_activated_uca" if is_no_activation else ("activated" if is_active else "suppressed")},
                {"node_type": "outcome", "value": outcome},
            ],
            "cited_evidence_ids": evidence_ids,
            "positive_evidence_ids": [eid for eid in evidence_ids if evidence_by_id.get(eid, {}).get("provenance") != "not_reported"],
            "missingness_evidence_ids": [eid for eid in evidence_ids if evidence_by_id.get(eid, {}).get("provenance") == "not_reported"],
            "cited_evidence": _evidence_summary_for_ids(evidence_by_id, evidence_ids),
        })

    idx = 1
    for obj in observed:
        add_pathway(obj, True, idx)
        idx += 1
    for obj in abductive:
        if idx > 8:
            break
        add_pathway(obj, False, idx)
        idx += 1
    for obj in blocked:
        if idx > 10:
            break
        add_pathway(obj, False, idx)
        idx += 1
    return candidates


def validate_pathway_judgment(candidate_ids: Sequence[str]):
    allowed_ids = set(candidate_ids)

    def _validator(obj: Dict[str, Any]) -> None:
        rows = obj.get("judged_pathways")
        if not isinstance(rows, list):
            raise SchemaValidationError("judged_pathways must be a list")
        seen = set()
        for row in rows:
            pid = row.get("pathway_id")
            if pid not in allowed_ids:
                raise SchemaValidationError(f"Unknown pathway_id in judge output: {pid}")
            seen.add(pid)
            status = row.get("pathway_status")
            if status not in ALLOWED_PATHWAY_STATUS:
                raise SchemaValidationError(f"Invalid pathway_status: {status}")
            score = row.get("pathway_score")
            if not isinstance(score, (int, float)) or not 0 <= float(score) <= 1:
                raise SchemaValidationError(f"Invalid pathway_score: {score}")
            rubric = row.get("rubric_scores")
            if not isinstance(rubric, dict):
                raise SchemaValidationError("rubric_scores must be object")
            required = ["evidence_grounding", "pm_context_validity", "update_process_validity", "other_factors_validity", "action_selection_validity", "uca_context_validity", "outcome_compatibility", "missingness_penalty", "overclaim_penalty", "safe_intervention_consistency"]
            for key in required:
                val = rubric.get(key)
                if not isinstance(val, (int, float)) or not 0 <= float(val) <= 1:
                    raise SchemaValidationError(f"Invalid rubric score {key}: {val}")
            node_scores = row.get("node_level_scores", {})
            if not isinstance(node_scores, dict):
                raise SchemaValidationError("node_level_scores must be object")
            for key in ["evidence_to_pm_context", "pm_context_to_update_process", "update_process_to_action_selection", "other_factors_to_action_selection", "action_selection_to_uca_context", "uca_context_to_outcome"]:
                val = node_scores.get(key)
                if not isinstance(val, (int, float)) or not 0 <= float(val) <= 1:
                    raise SchemaValidationError(f"Invalid node-level score {key}: {val}")
        if seen != allowed_ids:
            raise SchemaValidationError(f"Judge did not score all pathways: missing {allowed_ids - seen}")
    return _validator


def judge_and_rank_pathways(
    client: LLMClient,
    case_id: str,
    event_index: int,
    evidence_items: Sequence[Dict[str, Any]],
    candidate_pathways: List[Dict[str, Any]],
    temperature: float = 0.0,
) -> Dict[str, Any]:
    if not candidate_pathways:
        return {"candidate_pathways": [], "ranked_pathways": [], "ranking_summary": "No candidate pathways generated."}
    payload = {
        "case_id": case_id,
        "event_index": event_index,
        "scoring_formula": {
            "interpretation": "pathway_score is evidence-conditioned explanatory plausibility, not true causal probability",
            "recommended_weights": {
                "evidence_grounding": 0.25,
                "pm_context_validity": 0.15,
                "update_process_validity": 0.15,
                "other_factors_validity": 0.10,
                "action_selection_validity": 0.15,
                "uca_context_validity": 0.15,
                "outcome_compatibility": 0.10,
                "missingness_penalty": -0.10,
                "overclaim_penalty": -0.20,
            },
        },
        "evidence_items": evidence_items,
        "candidate_pathways": candidate_pathways,
    }
    candidate_ids = [p["pathway_id"] for p in candidate_pathways]
    judged = client.chat_json_strict(
        make_messages(PATHWAY_JUDGE_PROMPT, payload),
        ["judged_pathways", "ranking_summary"],
        validator=validate_pathway_judgment(candidate_ids),
        temperature=temperature,
    )
    judged_by_id = {j["pathway_id"]: j for j in judged.get("judged_pathways", [])}
    ranked = []
    for p in candidate_pathways:
        j = judged_by_id[p["pathway_id"]]
        merged = {**p, **j}
        initial_status = p.get("pathway_status_initial") or p.get("pathway_status")
        judge_status = j.get("pathway_status")
        if initial_status == "blocked" and judge_status != "blocked":
            merged["pathway_status"] = "blocked"
            merged["judge_rationale"] = (
                str(j.get("judge_rationale", "")).strip()
                + " Pathway status retained as blocked by deterministic STPA-HF compliance gates."
            ).strip()
        elif initial_status == "weakly_supported" and judge_status == "admissible":
            merged["pathway_status"] = "weakly_supported"
            merged["judge_rationale"] = (
                str(j.get("judge_rationale", "")).strip()
                + " Pathway status capped at weakly_supported by deterministic STPA-HF compliance gates."
            ).strip()
        claim_status = merged.get("claim_status")
        abductive_strength = merged.get("abductive_strength")
        score_cap = 1.0
        if claim_status == "abductive_candidate":
            score_cap = {
                "strong_abductive": 0.70,
                "weak_abductive": 0.55,
                "speculative_abductive": 0.40,
            }.get(abductive_strength, 0.55)
        elif claim_status == "blocked" or merged.get("pathway_status") == "blocked":
            score_cap = 0.35
        try:
            raw_score = float(merged.get("pathway_score", 0))
            if raw_score > score_cap:
                merged["pathway_score_uncapped"] = raw_score
                merged["pathway_score"] = score_cap
                merged["judge_rationale"] = (
                    str(merged.get("judge_rationale", "")).strip()
                    + f" Score capped at {score_cap} by v2.4 claim-status policy."
                ).strip()
        except Exception:
            pass
        merged["not_causal_probability_notice"] = True
        merged["outcome_used_as"] = "compatibility_constraint"
        merged["forward_chain_complete"] = bool(
            (merged.get("uca_reasoning_block") or {}).get("forward_derivation", {}).get("pm_flaw_inputs")
            and (merged.get("uca_reasoning_block") or {}).get("forward_derivation", {}).get("update_flaw_inputs")
            and (merged.get("uca_reasoning_block") or {}).get("forward_derivation", {}).get("action_selection_inputs")
        )
        ranked.append(merged)
    ranked.sort(key=lambda x: float(x.get("pathway_score", 0)), reverse=True)
    return {
        "case_id": case_id,
        "event_index": event_index,
        "report_type": "llm_judged_ranked_stpa_hf_pathways",
        "claim_boundary": "Pathway scores are evidence-conditioned explanatory plausibility, not true causal probabilities.",
        "candidate_pathways": candidate_pathways,
        "ranked_pathways": ranked,
        "ranking_summary": judged.get("ranking_summary"),
    }


def _raw_narrative_for_case(case: Dict[str, Any]) -> str:
    meta = case.get("source_metadata", {}) or {}
    parts = [
        str(meta.get("raw_case_summary", "") or ""),
        str(meta.get("reported_consequence", "") or ""),
        str(meta.get("source_reference", "") or ""),
    ]
    return "\n".join(p for p in parts if p.strip()).strip()


def validate_narrative_propositions(obj: Dict[str, Any]) -> None:
    props = obj.get("extracted_propositions")
    if not isinstance(props, list):
        raise SchemaValidationError("extracted_propositions must be list")
    for i, prop in enumerate(props):
        for key in ["proposition_id", "source_span", "proposition", "event_phase", "who_or_what", "action_or_state", "stpa_hf_relevance", "evidence_role", "uncertainty"]:
            if key not in prop:
                raise SchemaValidationError(f"proposition {i} missing {key}")
        rel = prop.get("stpa_hf_relevance")
        if not isinstance(rel, dict) or not isinstance(rel.get("quadrants"), list):
            raise SchemaValidationError(f"proposition {i} stpa_hf_relevance.quadrants invalid")
        for q in rel.get("quadrants", []):
            if q not in ALLOWED_QUADRANTS:
                raise SchemaValidationError(f"proposition {i} invalid quadrant: {q}")
        if prop.get("evidence_role") not in ["supports", "weakly_supports", "blocks", "context"]:
            raise SchemaValidationError(f"proposition {i} invalid evidence_role")
        if prop.get("uncertainty") not in ["low", "medium", "high"]:
            raise SchemaValidationError(f"proposition {i} invalid uncertainty")
    if not isinstance(obj.get("non_inferable_items", []), list):
        raise SchemaValidationError("non_inferable_items must be list")


def mine_case_narrative_propositions(client: LLMClient, case: Dict[str, Any], temperature: float = 0.0) -> Dict[str, Any]:
    case_id = case.get("case_id") or stable_digest(case)
    narrative = _raw_narrative_for_case(case)
    if not narrative:
        return {"case_id": case_id, "extracted_propositions": [], "non_inferable_items": ["No raw narrative text available."]}
    payload = {
        "case_id": case_id,
        "raw_narrative": narrative,
        "pm_quadrant_definitions": PM_QUADRANT_DEFINITIONS,
        "instruction": "Extract free-text evidence propositions only from the raw_narrative. Preserve source spans.",
    }
    obj = client.chat_json_strict(
        make_messages(NARRATIVE_PROPOSITION_PROMPT, payload),
        ["extracted_propositions", "non_inferable_items"],
        validator=validate_narrative_propositions,
        temperature=temperature,
    )
    return {"case_id": case_id, **obj}


def attach_narrative_propositions_to_case(case: Dict[str, Any], mining: Dict[str, Any]) -> Dict[str, Any]:
    new_case = json.loads(json.dumps(case, ensure_ascii=False))
    props = mining.get("extracted_propositions", []) or []
    for event in new_case.get("latent_events", []) or []:
        event["narrative_propositions"] = props
    new_case.setdefault("source_metadata", {})["narrative_proposition_mining"] = {
        "enabled": True,
        "num_propositions": len(props),
        "non_inferable_items": mining.get("non_inferable_items", []),
    }
    return new_case


def mine_narrative_evidence_file(client: LLMClient, cases_path: str | Path, out_cases: str | Path, out_report: str | Path, temperature: float = 0.0) -> Dict[str, Any]:
    cases = load_external_cases(cases_path)
    enriched = []
    reports = []
    for case in cases:
        mining = mine_case_narrative_propositions(client, case, temperature=temperature)
        reports.append(mining)
        enriched.append(attach_narrative_propositions_to_case(case, mining))
    write_jsonl(out_cases, enriched)
    summary = {
        "report_type": "narrative_proposition_mining_report",
        "cases_path": str(cases_path),
        "out_cases": str(out_cases),
        "num_cases": len(cases),
        "total_propositions": sum(len(r.get("extracted_propositions", []) or []) for r in reports),
        "case_rows": [{"case_id": r.get("case_id"), "num_propositions": len(r.get("extracted_propositions", []) or []), "non_inferable_count": len(r.get("non_inferable_items", []) or [])} for r in reports],
        "reports": reports,
    }
    write_json(out_report, summary)
    return summary


ROLE_DISAMBIGUATION_ALLOWED_ADJUDICATIONS = {"supported", "misassigned", "unsupported", "not_inferable"}
ROLE_DISAMBIGUATION_ALLOWED_OWNERS = {"ego_vehicle", "conflict_actor", "scene_level", "unknown"}
ROLE_DISAMBIGUATION_ALLOWED_CERTAINTY = {"high", "medium", "low"}
ROLE_DISAMBIGUATION_UPDATE_BLOCKLIST = {
    "CAR.time_budget_to_handover",
    "CAR.perception_confidence",
    "CAR.planner_confidence",
    "CABIN.pressure",
    "CABIN.distraction",
}


def _case_structured_role_fields(case: Dict[str, Any]) -> Dict[str, Any]:
    event = (case.get("latent_events") or [{}])[0] or {}
    fields = {}
    for group in ["ENV", "ACTOR", "CAR"]:
        fields[group] = event.get(group, {})
    return fields


def _role_update_value(value: Any, certainty: str, source_span: str, reasoning: str = "") -> Dict[str, Any]:
    return {
        "value": value,
        "provenance": "reported_narrative",
        "visibility": "source_reported",
        "certainty": certainty,
        "source_text": source_span,
        "derivation_basis": reasoning or "LLM role disambiguation from raw narrative.",
        "is_driver_visible": "unknown",
        "use_as_negative_evidence": False,
        "timestamp_ms": None,
        "persistence_ms": None,
    }


def validate_role_disambiguation(obj: Dict[str, Any]) -> None:
    if not isinstance(obj.get("case_id"), str) or not obj.get("case_id"):
        raise SchemaValidationError("case_id must be non-empty string")
    if not isinstance(obj.get("role_disambiguation_result"), dict):
        raise SchemaValidationError("role_disambiguation_result must be object")
    for key in ["field_adjudications", "proposed_field_updates", "blocked_inferences"]:
        if not isinstance(obj.get(key), list):
            raise SchemaValidationError(f"{key} must be list")

    for i, adj in enumerate(obj.get("field_adjudications", [])):
        if adj.get("adjudication") not in ROLE_DISAMBIGUATION_ALLOWED_ADJUDICATIONS:
            raise SchemaValidationError(f"field_adjudications[{i}] invalid adjudication")
        if adj.get("corrected_owner") not in ROLE_DISAMBIGUATION_ALLOWED_OWNERS:
            raise SchemaValidationError(f"field_adjudications[{i}] invalid corrected_owner")
        if adj.get("adjudication") in {"misassigned", "supported"} and adj.get("source_span") in {None, ""}:
            raise SchemaValidationError(f"field_adjudications[{i}] requires source_span")

    for i, upd in enumerate(obj.get("proposed_field_updates", [])):
        field_path = str(upd.get("field_path", "")).strip()
        if not field_path or "." not in field_path:
            raise SchemaValidationError(f"proposed_field_updates[{i}] invalid field_path")
        group = field_path.split(".", 1)[0]
        if group not in {"ENV", "ACTOR", "CAR"}:
            raise SchemaValidationError(f"proposed_field_updates[{i}] cannot update {group}")
        if field_path in ROLE_DISAMBIGUATION_UPDATE_BLOCKLIST:
            raise SchemaValidationError(f"proposed_field_updates[{i}] forbidden internal/driver-state update: {field_path}")
        if upd.get("provenance") != "reported_narrative":
            raise SchemaValidationError(f"proposed_field_updates[{i}] provenance must be reported_narrative")
        if upd.get("certainty") not in ROLE_DISAMBIGUATION_ALLOWED_CERTAINTY:
            raise SchemaValidationError(f"proposed_field_updates[{i}] invalid certainty")
        if not upd.get("source_span"):
            raise SchemaValidationError(f"proposed_field_updates[{i}] requires source_span")
        if "new_value" not in upd or str(upd.get("new_value", "")).strip() == "":
            raise SchemaValidationError(f"proposed_field_updates[{i}] requires non-empty new_value")
        if upd.get("update_allowed") is not True:
            raise SchemaValidationError(f"proposed_field_updates[{i}] update_allowed must be true")


def role_disambiguate_case(client: LLMClient, case: Dict[str, Any], temperature: float = 0.0) -> Dict[str, Any]:
    case_id = case.get("case_id") or stable_digest(case)
    narrative = _raw_narrative_for_case(case)
    payload = {
        "case_id": case_id,
        "raw_narrative": narrative,
        "current_structured_fields": _case_structured_role_fields(case),
        "fields_requiring_disambiguation": [
            "ACTOR.primary_intent",
            "ACTOR.primary_type",
            "ACTOR.primary_observability",
            "CAR.event_type",
            "CAR.automation_context",
            "CAR.reported_intervention",
            "CAR.reported_system_issue",
            "ENV.road_geometry",
        ],
        "evidence_policy": {
            "no_hmi_imputation": True,
            "no_driver_state_imputation": True,
            "no_internal_ads_confidence_imputation": True,
            "source_span_required_for_updates": True,
        },
        "task": "Determine whether each ambiguous structured field is supported, misplaced, unsupported, or requires a field update. Cite exact narrative spans.",
    }
    obj = client.chat_json_strict(
        make_messages(ROLE_DISAMBIGUATION_PROMPT, payload),
        ["case_id", "role_disambiguation_result", "field_adjudications", "proposed_field_updates", "blocked_inferences"],
        validator=validate_role_disambiguation,
        temperature=temperature,
    )
    return obj


def apply_role_disambiguation_to_case(case: Dict[str, Any], adjudication: Dict[str, Any]) -> Dict[str, Any]:
    new_case = json.loads(json.dumps(case, ensure_ascii=False))
    events = new_case.get("latent_events") or []
    if not events:
        raise DataCurationError(f"Case {new_case.get('case_id')} has no latent_events")
    for upd in adjudication.get("proposed_field_updates", []) or []:
        field_path = str(upd.get("field_path"))
        group, field = field_path.split(".", 1)
        for event in events:
            if group not in event or field not in (event.get(group) or {}):
                raise DataCurationError(f"Role disambiguation update targets missing field {field_path} in case {new_case.get('case_id')}")
            set_path(
                event,
                field_path,
                _role_update_value(
                    upd.get("new_value"),
                    upd.get("certainty"),
                    upd.get("source_span"),
                    reasoning=f"Role disambiguation: {upd.get('field_path')}",
                ),
            )
    new_case.setdefault("source_metadata", {})["role_disambiguation"] = {
        "enabled": True,
        "num_field_adjudications": len(adjudication.get("field_adjudications", []) or []),
        "num_proposed_field_updates": len(adjudication.get("proposed_field_updates", []) or []),
        "blocked_inference_count": len(adjudication.get("blocked_inferences", []) or []),
        "adjudication": adjudication,
    }
    return new_case


def role_disambiguate_cases_file(
    client: LLMClient,
    cases_path: str | Path,
    out_cases: str | Path,
    out_report: str | Path,
    temperature: float = 0.0,
) -> Dict[str, Any]:
    cases = load_external_cases(cases_path)
    updated_cases = []
    reports = []
    for case in cases:
        adjudication = role_disambiguate_case(client, case, temperature=temperature)
        reports.append(adjudication)
        updated_cases.append(apply_role_disambiguation_to_case(case, adjudication))
    write_jsonl(out_cases, updated_cases)
    summary = {
        "schema_version": SCHEMA_VERSION,
        "report_type": "role_disambiguation_report",
        "claim_boundary": "Role disambiguation may correct ENV/ACTOR/CAR role assignment only when raw narrative source spans support it; it does not infer HMI, driver state, true causality, or responsibility.",
        "cases_path": str(cases_path),
        "out_cases": str(out_cases),
        "num_cases": len(cases),
        "num_field_updates": sum(len(r.get("proposed_field_updates", []) or []) for r in reports),
        "num_blocked_inferences": sum(len(r.get("blocked_inferences", []) or []) for r in reports),
        "case_rows": [
            {
                "case_id": r.get("case_id"),
                "field_update_count": len(r.get("proposed_field_updates", []) or []),
                "blocked_inference_count": len(r.get("blocked_inferences", []) or []),
                "misassigned_count": sum(1 for a in r.get("field_adjudications", []) or [] if a.get("adjudication") == "misassigned"),
            }
            for r in reports
        ],
        "reports": reports,
    }
    write_json(out_report, summary)
    return summary


# =============================================================================
# Baselines
# =============================================================================


def run_direct_case_baseline(client: LLMClient, case_spec: Dict[str, Any], out_dir: str | Path, temperature: float = 0.0) -> Dict[str, Any]:
    return _run_simple_baseline(client, case_spec, out_dir, "direct", DIRECT_BASELINE_PROMPT, temperature)


def run_generic_cot_baseline(client: LLMClient, case_spec: Dict[str, Any], out_dir: str | Path, temperature: float = 0.0) -> Dict[str, Any]:
    return _run_simple_baseline(client, case_spec, out_dir, "generic_cot", GENERIC_COT_BASELINE_PROMPT, temperature)


def run_structured_prompt_only_baseline(client: LLMClient, case_spec: Dict[str, Any], out_dir: str | Path, temperature: float = 0.0) -> Dict[str, Any]:
    return _run_simple_baseline(client, case_spec, out_dir, "structured_prompt_only", STRUCTURED_PROMPT_ONLY_BASELINE_PROMPT, temperature)


def _run_simple_baseline(client: LLMClient, case_spec: Dict[str, Any], out_dir: str | Path, name: str, prompt: str, temperature: float = 0.0) -> Dict[str, Any]:
    case_id = case_spec.get("case_id") or stable_digest(case_spec)
    out = Path(out_dir) / name / case_id
    ensure_dir(out)
    event = case_spec.get("latent_events", [{}])[-1]
    evidence_packet = build_evidence_packet(event, case_spec.get("driver_profile", {}), event_index=0)
    payload = {"case_id": case_id, "baseline": name, "uca_catalog": DRIVER_UCA_CATALOG, **evidence_packet}

    def validator(obj: Dict[str, Any]) -> None:
        if obj.get("commitment_state_fsm") not in ALLOWED_BOUNDARIES:
            raise SchemaValidationError("baseline commitment_state_fsm invalid")
        status = obj.get("uca_activation_status")
        if status not in ALLOWED_UCA_ACTIVATION_STATUS:
            raise SchemaValidationError("baseline uca_activation_status invalid")
        dominant = obj.get("dominant_uca")
        if status == "activated":
            if dominant not in DRIVER_UCA_ID_SET:
                raise SchemaValidationError("baseline dominant_uca invalid")
        else:
            if dominant is not None:
                raise SchemaValidationError("baseline dominant_uca must be null when no UCA is activated")

    obj = client.chat_json_strict(make_messages(prompt, payload), ["commitment_state_fsm", "uca_activation_status", "dominant_uca", "rationale"], validator=validator, temperature=temperature)
    result = {"case_id": case_id, "baseline": name, **obj}
    write_json(out / "baseline_result.json", result)
    return result


def _existing_baseline_result(case_spec: Dict[str, Any], out_dir: str | Path, name: str) -> Optional[Dict[str, Any]]:
    case_id = case_spec.get("case_id") or stable_digest(case_spec)
    path = Path(out_dir) / "baselines" / name / case_id / "baseline_result.json"
    return read_json(path) if path.exists() else None


def _existing_bundle(case_spec: Dict[str, Any], out_dir: str | Path) -> Optional[Dict[str, Any]]:
    case_id = case_spec.get("case_id") or stable_digest(case_spec)
    path = Path(out_dir) / case_id / "bundle_summary.json"
    return read_json(path) if path.exists() else None


def run_no_vulnerability_priority_ablation(client: LLMClient, case_spec: Dict[str, Any], out_dir: str | Path, temperature: float = 0.0) -> Dict[str, Any]:
    return run_case(client, case_spec, Path(out_dir) / "no_vulnerability_priority", use_vulnerability_priority=False, temperature=temperature)


def run_no_update_ablation(client: LLMClient, case_spec: Dict[str, Any], out_dir: str | Path, temperature: float = 0.0) -> Dict[str, Any]:
    return run_case(client, case_spec, Path(out_dir) / "no_update", skip_pm_update=True, temperature=temperature)


def run_full_system_batch(client: LLMClient, cases: Sequence[Dict[str, Any]], out_dir: str | Path, temperature: float = 0.0) -> List[Dict[str, Any]]:
    return [run_case(client, c, out_dir, use_vulnerability_priority=False, temperature=temperature) for c in cases]


def run_baseline_suite(client: LLMClient, cases: Sequence[Dict[str, Any]], out_dir: str | Path, temperature: float = 0.0, resume: bool = False) -> Dict[str, Any]:
    out = Path(out_dir)
    ensure_dir(out)
    direct, generic, full, with_priority, no_update = [], [], [], [], []
    for case in cases:
        direct.append(_existing_baseline_result(case, out, "direct") if resume and _existing_baseline_result(case, out, "direct") else run_direct_case_baseline(client, case, out / "baselines", temperature))
        generic.append(_existing_baseline_result(case, out, "generic_cot") if resume and _existing_baseline_result(case, out, "generic_cot") else run_generic_cot_baseline(client, case, out / "baselines", temperature))
        full_existing = _existing_bundle(case, out / "full_system") if resume else None
        full.append(full_existing or run_case(client, case, out / "full_system", use_vulnerability_priority=False, temperature=temperature))
        priority_existing = _existing_bundle(case, out / "ablations" / "with_vulnerability_priority") if resume else None
        with_priority.append(priority_existing or run_case(client, case, out / "ablations" / "with_vulnerability_priority", use_vulnerability_priority=True, temperature=temperature))
        no_update_existing = _existing_bundle(case, out / "ablations" / "no_update") if resume else None
        no_update.append(no_update_existing or run_case(client, case, out / "ablations" / "no_update", skip_pm_update=True, temperature=temperature))
    summary = {"direct": direct, "generic_cot": generic, "full_system_no_priority": full, "with_vulnerability_priority": with_priority, "no_update": no_update}
    write_json(out / "baseline_suite_summary.json", summary)
    return summary


# =============================================================================
# AAP V2 ablation, expert alignment, and richer-evidence evaluation
# =============================================================================


def _write_csv_rows(path: str | Path, rows: Sequence[Dict[str, Any]]) -> None:
    ensure_dir(Path(path).parent)
    fieldnames: List[str] = []
    for row in rows:
        for key in row.keys():
            if key not in fieldnames:
                fieldnames.append(key)
    with Path(path).open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v for k, v in row.items()})


def _collect_evidence_ids(obj: Any) -> List[str]:
    ids: List[str] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key.endswith("evidence_ids") and isinstance(value, list):
                ids.extend(str(v) for v in value if v is not None)
            else:
                ids.extend(_collect_evidence_ids(value))
    elif isinstance(obj, list):
        for item in obj:
            ids.extend(_collect_evidence_ids(item))
    return sorted(dict.fromkeys(ids))


def _case_evidence_maps_from_case(case_spec: Dict[str, Any]) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    event = (case_spec.get("latent_events") or [{}])[-1]
    evidence_items = build_evidence_items(event, event_index=0)
    evidence_by_id = {item["evidence_id"]: item for item in evidence_items}
    evidence_by_field = {item["field_path"]: item for item in evidence_items}
    return evidence_by_id, evidence_by_field


def _ranked_pathways_from_bundle(bundle_dir: str | Path, case_id: str, bundle: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    case_dir = Path(bundle_dir) / case_id
    pkg = load_final_tabletop_replay_package(case_dir, bundle) if case_dir.exists() else None
    if pkg:
        return pkg.get("ranked_pathways", []) or []
    return get_path(bundle or {}, "final_case_summary.final_uca_pathway_summary", []) or []


def _pathway_evidence_cited_rate(pathways: Sequence[Dict[str, Any]]) -> float:
    if not pathways:
        return 0.0
    cited = 0
    for p in pathways:
        ids = (
            p.get("supporting_evidence_ids")
            or get_path(p, "uca_context_node.supporting_evidence_ids")
            or _collect_evidence_ids(p)
            or []
        )
        if ids:
            cited += 1
    return round(cited / len(pathways), 4)


def _explicit_action_evidence_present_from_case(case_spec: Dict[str, Any]) -> bool:
    event = (case_spec.get("latent_events") or [{}])[-1]
    items = build_evidence_items(event, event_index=0)
    return any(
        item.get("provenance") != "not_reported"
        and classify_evidence_role_for_uca(item) in ACTION_EVIDENCE_ROLES
        for item in items
    )


def _condition_row_from_baseline(
    *,
    case_spec: Dict[str, Any],
    result: Dict[str, Any],
    condition: str,
) -> Dict[str, Any]:
    evidence_by_id, evidence_by_field = _case_evidence_maps_from_case(case_spec)
    boundary = result.get("commitment_state_fsm")
    strength = classify_boundary_evidence_strength(boundary, evidence_by_field, [], evidence_by_id)
    activated = result.get("uca_activation_status") == "activated"
    lacks_action_evidence = not _explicit_action_evidence_present_from_case(case_spec)
    unsupported_takeover = _unsupported_takeover_failure_claim(result) or (activated and lacks_action_evidence)
    return {
        "case_id": result.get("case_id") or case_spec.get("case_id"),
        "condition": condition,
        "condition_type": "baseline",
        "schema_valid": True,
        "boundary_or_posture": boundary,
        "uca_activation_status": result.get("uca_activation_status"),
        "dominant_uca": result.get("dominant_uca"),
        "outcome_only_overreach": bool(strength.get("outcome_only_escalation_warning")),
        "unsupported_driver_state_claim": _unsupported_driver_state_claim(result),
        "unsupported_takeover_failure_claim": unsupported_takeover,
        "complete_pm_update_action_uca_chain": False,
        "evidence_cited_pathway_rate": 0.0,
        "blocked_claim_transparency": False,
        "ranked_pathway_count": 0,
        "notes": "Baseline does not expose a PM-update-action-UCA pathway chain.",
    }


def _condition_row_from_bundle(
    *,
    bundle: Dict[str, Any],
    bundle_dir: str | Path,
    condition: str,
    condition_type: str = "bundle",
) -> Dict[str, Any]:
    case_id = bundle.get("case_id")
    case_dir = Path(bundle_dir) / str(case_id)
    pkg = load_final_tabletop_replay_package(case_dir, bundle) if case_dir.exists() else None
    pathways = (pkg or {}).get("ranked_pathways", []) or get_path(bundle, "final_case_summary.final_uca_pathway_summary", []) or []
    blocked_count = count_blocked_claims_in_artifact(pkg or bundle)
    if not blocked_count:
        blocked_count = int(get_path(bundle, "final_case_summary.final_blocked_claim_count") or 0)
    no_gate_failures = 0
    for p in pathways:
        gates = p.get("stpa_hf_compliance_gates") or {}
        g6 = gates.get("G6_evidence_admissibility_gate") or {}
        if g6.get("status") == "fail":
            no_gate_failures += 1
    return {
        "case_id": case_id,
        "condition": condition,
        "condition_type": condition_type,
        "schema_valid": bool(bundle.get("schema_valid")),
        "boundary_or_posture": get_path(bundle, "final_case_summary.final_driver_replay_posture_fsm") or get_path(bundle, "final_case_summary.final_commitment_state_fsm"),
        "uca_activation_status": get_path(bundle, "final_case_summary.final_uca_activation_status"),
        "dominant_uca": get_path(bundle, "final_case_summary.final_dominant_uca"),
        "outcome_only_overreach": False,
        "unsupported_driver_state_claim": _unsupported_driver_state_claim(bundle),
        "unsupported_takeover_failure_claim": _unsupported_takeover_failure_claim(bundle),
        "complete_pm_update_action_uca_chain": bool(_full_replay_chain_rate(bundle)),
        "evidence_cited_pathway_rate": _pathway_evidence_cited_rate(pathways),
        "blocked_claim_transparency": blocked_count > 0,
        "ranked_pathway_count": len(pathways),
        "blocked_claim_count": blocked_count,
        "evidence_gate_failure_pathway_count": no_gate_failures,
        "notes": "Full replay or deterministic ablation bundle.",
    }


def _pathway_has_not_reported_positive_support(pathway: Dict[str, Any], evidence_by_id: Dict[str, Dict[str, Any]]) -> bool:
    positive_ids = pathway.get("positive_evidence_ids") or pathway.get("supporting_evidence_ids") or []
    for eid in positive_ids:
        if evidence_by_id.get(eid, {}).get("provenance") == "not_reported":
            return True
    for cited in pathway.get("cited_evidence", []) or []:
        if cited.get("evidence_id") in positive_ids and cited.get("provenance") == "not_reported":
            return True
    return False


def _no_evidence_gate_projection_metrics(bundle: Dict[str, Any], bundle_dir: str | Path) -> Dict[str, Any]:
    case_id = str(bundle.get("case_id"))
    case_dir = Path(bundle_dir) / case_id
    pkg = load_final_tabletop_replay_package(case_dir, bundle) if case_dir.exists() else None
    pathways = (pkg or {}).get("ranked_pathways", []) or get_path(bundle, "final_case_summary.final_uca_pathway_summary", []) or []
    evidence_by_id, _ = _case_evidence_maps_from_bundle_dir(bundle_dir, case_id)
    promoted_blocked = 0
    promoted_outcome_only = 0
    promoted_no_action_evidence = 0
    promoted_not_reported = 0
    promoted_any = 0
    examples: List[Dict[str, Any]] = []
    for pathway in pathways:
        status = pathway.get("pathway_status") or pathway.get("claim_status") or pathway.get("abductive_strength")
        blocked = status == "blocked" or pathway.get("claim_status") == "blocked" or bool(pathway.get("blocking_reasons"))
        g7 = (pathway.get("stpa_hf_compliance_gates") or {}).get("G7_outcome_compatibility_gate") or pathway.get("outcome_compatibility_block") or {}
        outcome_only = bool(g7.get("outcome_only_positive_evidence")) or pathway.get("activation_evidence_type") == "outcome_only"
        no_action_evidence = g7.get("action_evidence_present") is False or not (
            pathway.get("linked_action_id")
            or pathway.get("linked_action")
            or get_path(pathway, "uca_reasoning_block.linked_action")
        )
        not_reported_positive = _pathway_has_not_reported_positive_support(pathway, evidence_by_id)
        would_promote = blocked or outcome_only or no_action_evidence or not_reported_positive
        if not would_promote:
            continue
        promoted_any += 1
        promoted_blocked += 1 if blocked else 0
        promoted_outcome_only += 1 if outcome_only else 0
        promoted_no_action_evidence += 1 if no_action_evidence else 0
        promoted_not_reported += 1 if not_reported_positive else 0
        if len(examples) < 5:
            examples.append({
                "pathway_id": pathway.get("pathway_id"),
                "uca_id": pathway.get("uca_id"),
                "linked_action": pathway.get("linked_action"),
                "pathway_status": pathway.get("pathway_status"),
                "claim_status": pathway.get("claim_status"),
                "would_be_promoted_reasons": [
                    reason
                    for reason, flag in [
                        ("blocked_pathway", blocked),
                        ("outcome_only_positive_evidence", outcome_only),
                        ("no_action_evidence", no_action_evidence),
                        ("not_reported_as_positive_support", not_reported_positive),
                    ]
                    if flag
                ],
                "blocking_reasons": pathway.get("blocking_reasons", []),
            })
    return {
        "would_promote_blocked_pathway_count": promoted_blocked,
        "would_promote_outcome_only_pathway_count": promoted_outcome_only,
        "would_promote_no_action_evidence_pathway_count": promoted_no_action_evidence,
        "would_promote_not_reported_supported_pathway_count": promoted_not_reported,
        "would_promote_any_risk_pathway_count": promoted_any,
        "promoted_pathway_examples": examples,
    }


def _condition_row_no_evidence_gate_projection(bundle: Dict[str, Any], bundle_dir: str | Path) -> Dict[str, Any]:
    row = _condition_row_from_bundle(bundle=bundle, bundle_dir=bundle_dir, condition="no_evidence_gate", condition_type="diagnostic_projection")
    projection = _no_evidence_gate_projection_metrics(bundle, bundle_dir)
    row.update(projection)
    row["blocked_claim_transparency"] = False
    row["unsupported_takeover_failure_claim"] = bool(
        row.get("evidence_gate_failure_pathway_count")
        or row.get("would_promote_blocked_pathway_count")
        or row.get("would_promote_no_action_evidence_pathway_count")
        or row.get("unsupported_takeover_failure_claim")
    )
    row["notes"] = "Diagnostic projection: reports risks if evidence-admissibility gates were removed. It is not a valid replay output."
    return row


def summarize_ablation_rows(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    by_condition: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_condition[str(row.get("condition"))].append(dict(row))
    condition_reports = {}
    for condition, crs in sorted(by_condition.items()):
        condition_reports[condition] = {
            "num_cases": len(crs),
            "schema_valid_rate": _safe_mean([1.0 if r.get("schema_valid") else 0.0 for r in crs]),
            "outcome_only_overreach_count": sum(1 for r in crs if r.get("outcome_only_overreach")),
            "unsupported_driver_state_claim_count": sum(1 for r in crs if r.get("unsupported_driver_state_claim")),
            "unsupported_takeover_failure_claim_count": sum(1 for r in crs if r.get("unsupported_takeover_failure_claim")),
            "complete_pm_update_action_uca_chain_rate": _safe_mean([1.0 if r.get("complete_pm_update_action_uca_chain") else 0.0 for r in crs]),
            "mean_evidence_cited_pathway_rate": _safe_mean([float(r.get("evidence_cited_pathway_rate") or 0.0) for r in crs]),
            "blocked_claim_transparency_rate": _safe_mean([1.0 if r.get("blocked_claim_transparency") else 0.0 for r in crs]),
            "mean_ranked_pathway_count": _safe_mean([int(r.get("ranked_pathway_count") or 0) for r in crs]),
            "mean_would_promote_blocked_pathway_count": _safe_mean([int(r.get("would_promote_blocked_pathway_count") or 0) for r in crs]),
            "mean_would_promote_outcome_only_pathway_count": _safe_mean([int(r.get("would_promote_outcome_only_pathway_count") or 0) for r in crs]),
            "mean_would_promote_no_action_evidence_pathway_count": _safe_mean([int(r.get("would_promote_no_action_evidence_pathway_count") or 0) for r in crs]),
            "mean_would_promote_not_reported_supported_pathway_count": _safe_mean([int(r.get("would_promote_not_reported_supported_pathway_count") or 0) for r in crs]),
        }
    return condition_reports


def run_ablation_suite_v2(
    client: LLMClient,
    cases: Sequence[Dict[str, Any]],
    out_dir: str | Path,
    *,
    full_bundle_dir: Optional[str | Path] = None,
    temperature: float = 0.0,
    resume: bool = False,
) -> Dict[str, Any]:
    out = Path(out_dir)
    ensure_dir(out)
    rows: List[Dict[str, Any]] = []
    direct_results, generic_results, structured_results = [], [], []
    full_bundles, no_update_bundles = [], []
    full_root = Path(full_bundle_dir) if full_bundle_dir else out / "condition_outputs" / "full_replay"
    no_update_root = out / "condition_outputs" / "no_update"
    baseline_root = out / "condition_outputs" / "baselines"

    for case in cases:
        case_id = case.get("case_id") or stable_digest(case)
        direct = _existing_baseline_result(case, out / "condition_outputs", "direct") if resume else None
        if not direct:
            direct = run_direct_case_baseline(client, case, baseline_root, temperature)
        direct_results.append(direct)
        rows.append(_condition_row_from_baseline(case_spec=case, result=direct, condition="direct_llm"))

        generic = _existing_baseline_result(case, out / "condition_outputs", "generic_cot") if resume else None
        if not generic:
            generic = run_generic_cot_baseline(client, case, baseline_root, temperature)
        generic_results.append(generic)
        rows.append(_condition_row_from_baseline(case_spec=case, result=generic, condition="generic_cot"))

        structured = _existing_baseline_result(case, out / "condition_outputs", "structured_prompt_only") if resume else None
        if not structured:
            structured = run_structured_prompt_only_baseline(client, case, baseline_root, temperature)
        structured_results.append(structured)
        rows.append(_condition_row_from_baseline(case_spec=case, result=structured, condition="structured_prompt_only"))

        full_existing = _existing_bundle(case, full_root) if resume or full_bundle_dir else None
        if not full_existing:
            full_existing = run_case(client, case, full_root, use_vulnerability_priority=False, temperature=temperature)
        full_bundles.append(full_existing)
        rows.append(_condition_row_from_bundle(bundle=full_existing, bundle_dir=full_root, condition="full_replay"))

        no_update_existing = _existing_bundle(case, no_update_root) if resume else None
        if not no_update_existing:
            no_update_existing = run_case(client, case, no_update_root, skip_pm_update=True, temperature=temperature)
        no_update_bundles.append(no_update_existing)
        rows.append(_condition_row_from_bundle(bundle=no_update_existing, bundle_dir=no_update_root, condition="no_update"))

        rows.append(_condition_row_no_evidence_gate_projection(full_existing, full_root))

    summary = {
        "schema_version": SCHEMA_VERSION,
        "report_type": "aap_v2_ablation_suite",
        "claim_boundary": {
            "allowed": "Compare whether STPA-HF driver process-model mediation and evidence gates reduce outcome-only overreach.",
            "not_allowed": "Treating ablation rows as true accident-cause labels or legal responsibility claims.",
        },
        "num_cases": len(cases),
        "conditions": ["direct_llm", "generic_cot", "structured_prompt_only", "no_update", "no_evidence_gate", "full_replay"],
        "condition_reports": summarize_ablation_rows(rows),
        "rows": rows,
        "outputs": {
            "full_replay_dir": str(full_root),
            "no_update_dir": str(no_update_root),
            "baseline_dir": str(baseline_root),
        },
    }
    write_json(out / "ablation_suite_summary.json", summary)
    write_json(out / "pm_mediation_comparison_v2.json", summary)
    _write_csv_rows(out / "pm_mediation_comparison_v2.csv", rows)
    return summary


# =============================================================================
# Human labels and evaluation
# =============================================================================


def load_master_labels(path: str | Path) -> Dict[str, Dict[str, Any]]:
    labels: Dict[str, Dict[str, Any]] = {}
    for row in read_jsonl(path):
        case_id = row.get("case_id")
        if not case_id:
            raise DataCurationError("label row missing case_id")
        labels[case_id] = row
    return labels


def validate_annotation_completeness(labels_path: str | Path, required_fields: Optional[List[str]] = None) -> Dict[str, Any]:
    required = required_fields or ["case_id", "boundary_label", "update_vulnerability"]
    rows = read_jsonl(labels_path)
    missing = []
    for row in rows:
        miss = [k for k in required if k not in row or row.get(k) in [None, ""]]
        status = row.get("uca_activation_status")
        dominant = row.get("dominant_uca")
        if status in [None, ""]:
            if dominant in [None, ""]:
                miss.append("uca_activation_status_or_dominant_uca")
            else:
                miss.append("uca_activation_status")
        elif status == "activated" and dominant in [None, ""]:
            miss.append("dominant_uca")
        elif status == "no_activated_uca" and dominant not in [None, ""]:
            miss.append("dominant_uca_must_be_empty_when_no_activated_uca")
        if miss:
            missing.append({"case_id": row.get("case_id"), "missing": miss})
    return {"num_rows": len(rows), "num_incomplete": len(missing), "incomplete_rows": missing}


def adjudicate_multirater_labels(raw_label_paths: Sequence[str | Path], output_path: str | Path) -> List[Dict[str, Any]]:
    by_case: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for path in raw_label_paths:
        annotator = Path(path).stem
        for row in read_jsonl(path):
            row = dict(row)
            row.setdefault("annotator_id", annotator)
            if not row.get("case_id"):
                raise DataCurationError(f"Raw label without case_id in {path}")
            by_case[row["case_id"]].append(row)

    adjudicated = []
    fields = ["boundary_label", "update_vulnerability", "uca_activation_status", "dominant_uca", "requirement_focus"]
    for case_id, rows in by_case.items():
        out: Dict[str, Any] = {"case_id": case_id, "num_annotators": len(rows), "raw_labels": rows}
        for field_name in fields:
            label, agree = majority_vote([str(r.get(field_name, "")) for r in rows])
            if label:
                out[field_name] = label
                out[f"{field_name}_agreement"] = agree
        if out.get("uca_activation_status") == "no_activated_uca":
            out["dominant_uca"] = ""
        # Active UCA set: union and majority frequency retained.
        active_counter: Counter[str] = Counter()
        for r in rows:
            for u in r.get("active_uca_set", []) or []:
                active_counter[str(u)] += 1
        if active_counter:
            threshold = max(1, math.ceil(len(rows) / 2))
            out["active_uca_set"] = sorted([u for u, c in active_counter.items() if c >= threshold])
            out["active_uca_vote_counts"] = dict(active_counter)
        # Evidence ids / slots for traceability.
        out["primary_pm_slots"] = sorted({s for r in rows for s in (r.get("primary_pm_slots") or [])})
        out["supporting_evidence_ids"] = sorted({e for r in rows for e in (r.get("supporting_evidence_ids") or [])})
        out["insufficient_information_flags"] = sorted({e for r in rows for e in (r.get("insufficient_information_flags") or [])})
        adjudicated.append(out)
    write_jsonl(output_path, adjudicated)
    return adjudicated


def collect_bundle_summaries(bundle_dir: str | Path) -> Dict[str, Dict[str, Any]]:
    root = Path(bundle_dir)
    bundles: Dict[str, Dict[str, Any]] = {}
    for p in root.glob("*/bundle_summary.json"):
        obj = read_json(p)
        bundles[obj["case_id"]] = obj
    return bundles


def evaluate_bundles(bundle_dir: str | Path, labels_path: str | Path, out_dir: str | Path) -> Dict[str, Any]:
    bundles = collect_bundle_summaries(bundle_dir)
    labels = load_master_labels(labels_path)
    y_boundary_true: List[str] = []
    y_boundary_pred: List[str] = []
    y_vuln_true: List[str] = []
    y_vuln_pred: List[str] = []
    y_uca_status_true: List[str] = []
    y_uca_status_pred: List[str] = []
    y_uca_true: List[str] = []
    y_uca_pred: List[str] = []
    active_exact = []
    active_jaccards = []
    rows = []

    for case_id, gold in labels.items():
        bundle = bundles.get(case_id)
        if not bundle:
            continue
        pred = bundle.get("final_case_summary", {})
        row = {"case_id": case_id, "schema_valid": bundle.get("schema_valid", False)}
        if gold.get("boundary_label"):
            y_boundary_true.append(gold["boundary_label"])
            y_boundary_pred.append(pred.get("final_commitment_state_fsm") or "missing")
            row["gold_boundary"] = gold["boundary_label"]
            row["pred_boundary"] = pred.get("final_commitment_state_fsm")
        if gold.get("update_vulnerability"):
            y_vuln_true.append(gold["update_vulnerability"])
            y_vuln_pred.append(pred.get("final_dominant_update_vulnerability") or "missing")
            row["gold_vulnerability"] = gold["update_vulnerability"]
            row["pred_vulnerability"] = pred.get("final_dominant_update_vulnerability")
        if gold.get("uca_activation_status") not in [None, ""]:
            y_uca_status_true.append(gold["uca_activation_status"])
            y_uca_status_pred.append(pred.get("final_uca_activation_status") or "missing")
            row["gold_uca_activation_status"] = gold["uca_activation_status"]
            row["pred_uca_activation_status"] = pred.get("final_uca_activation_status")
        if gold.get("dominant_uca") not in [None, ""]:
            y_uca_true.append(gold["dominant_uca"])
            y_uca_pred.append(pred.get("final_dominant_uca") or "missing")
            row["gold_dominant_uca"] = gold["dominant_uca"]
            row["pred_dominant_uca"] = pred.get("final_dominant_uca")
        if gold.get("active_uca_set") is not None:
            gt = set(gold.get("active_uca_set") or [])
            pr = set(pred.get("final_active_uca_set") or [])
            active_exact.append(gt == pr)
            active_jaccards.append(len(gt & pr) / len(gt | pr) if gt | pr else 1.0)
            row["gold_active_uca_set"] = sorted(gt)
            row["pred_active_uca_set"] = sorted(pr)
        rows.append(row)

    report = {
        "num_gold_cases": len(labels),
        "num_predicted_cases": len(bundles),
        "num_matched_cases": len(rows),
        "boundary": {
            "accuracy": round(sum(t == p for t, p in zip(y_boundary_true, y_boundary_pred)) / len(y_boundary_true), 4) if y_boundary_true else None,
            "macro_f1": macro_f1(y_boundary_true, y_boundary_pred, ALLOWED_BOUNDARIES) if y_boundary_true else None,
            "balanced_accuracy": balanced_accuracy(y_boundary_true, y_boundary_pred, ALLOWED_BOUNDARIES) if y_boundary_true else None,
            "confusion_matrix": confusion_matrix(y_boundary_true, y_boundary_pred),
        },
        "update_vulnerability": {
            "accuracy": round(sum(t == p for t, p in zip(y_vuln_true, y_vuln_pred)) / len(y_vuln_true), 4) if y_vuln_true else None,
            "macro_f1": macro_f1(y_vuln_true, y_vuln_pred, ALLOWED_VULNERABILITIES) if y_vuln_true else None,
            "balanced_accuracy": balanced_accuracy(y_vuln_true, y_vuln_pred, ALLOWED_VULNERABILITIES) if y_vuln_true else None,
            "confusion_matrix": confusion_matrix(y_vuln_true, y_vuln_pred),
        },
        "uca_activation_status": {
            "accuracy": round(sum(t == p for t, p in zip(y_uca_status_true, y_uca_status_pred)) / len(y_uca_status_true), 4) if y_uca_status_true else None,
            "macro_f1": macro_f1(y_uca_status_true, y_uca_status_pred, ALLOWED_UCA_ACTIVATION_STATUS) if y_uca_status_true else None,
            "confusion_matrix": confusion_matrix(y_uca_status_true, y_uca_status_pred),
        },
        "dominant_uca": {
            "accuracy": round(sum(t == p for t, p in zip(y_uca_true, y_uca_pred)) / len(y_uca_true), 4) if y_uca_true else None,
            "macro_f1": macro_f1(y_uca_true, y_uca_pred, sorted(DRIVER_UCA_ID_SET)) if y_uca_true else None,
            "confusion_matrix": confusion_matrix(y_uca_true, y_uca_pred),
        },
        "active_uca_set": {
            "exact_match": round(sum(active_exact) / len(active_exact), 4) if active_exact else None,
            "mean_jaccard": round(sum(active_jaccards) / len(active_jaccards), 4) if active_jaccards else None,
        },
        "case_level_rows": rows,
    }
    ensure_dir(Path(out_dir))
    write_json(Path(out_dir) / "evaluation_report.json", report)
    return report


def collect_baseline_results(baseline_dir: str | Path) -> Dict[str, Dict[str, Any]]:
    """Collect baseline_result.json files produced by direct/generic_cot baselines."""
    root = Path(baseline_dir)
    results: Dict[str, Dict[str, Any]] = {}
    for p in root.glob("*/baseline_result.json"):
        obj = read_json(p)
        results[obj["case_id"]] = obj
    return results


def evaluate_baselines(baseline_dir: str | Path, labels_path: str | Path, out_dir: str | Path) -> Dict[str, Any]:
    """Evaluate baseline results against human gold labels.

    Baselines output {case_id, commitment_state_fsm, dominant_uca, rationale},
    which is a flat structure unlike the full-system bundle_summary.json.
    """
    results = collect_baseline_results(baseline_dir)
    labels = load_master_labels(labels_path)
    y_boundary_true: List[str] = []
    y_boundary_pred: List[str] = []
    y_uca_status_true: List[str] = []
    y_uca_status_pred: List[str] = []
    y_uca_true: List[str] = []
    y_uca_pred: List[str] = []
    rows = []

    for case_id, gold in labels.items():
        pred = results.get(case_id)
        if not pred:
            continue
        row: Dict[str, Any] = {"case_id": case_id}
        if gold.get("boundary_label"):
            y_boundary_true.append(gold["boundary_label"])
            y_boundary_pred.append(pred.get("commitment_state_fsm") or "missing")
            row["gold_boundary"] = gold["boundary_label"]
            row["pred_boundary"] = pred.get("commitment_state_fsm")
        if gold.get("uca_activation_status") not in [None, ""]:
            y_uca_status_true.append(gold["uca_activation_status"])
            y_uca_status_pred.append(pred.get("uca_activation_status") or "missing")
            row["gold_uca_activation_status"] = gold["uca_activation_status"]
            row["pred_uca_activation_status"] = pred.get("uca_activation_status")
        if gold.get("dominant_uca") not in [None, ""]:
            y_uca_true.append(gold["dominant_uca"])
            y_uca_pred.append(pred.get("dominant_uca") or "missing")
            row["gold_dominant_uca"] = gold["dominant_uca"]
            row["pred_dominant_uca"] = pred.get("dominant_uca")
        rows.append(row)

    report = {
        "baseline": Path(baseline_dir).name,
        "num_gold_cases": len(labels),
        "num_predicted_cases": len(results),
        "num_matched_cases": len(rows),
        "boundary": {
            "accuracy": round(sum(t == p for t, p in zip(y_boundary_true, y_boundary_pred)) / len(y_boundary_true), 4) if y_boundary_true else None,
            "macro_f1": macro_f1(y_boundary_true, y_boundary_pred, ALLOWED_BOUNDARIES) if y_boundary_true else None,
            "balanced_accuracy": balanced_accuracy(y_boundary_true, y_boundary_pred, ALLOWED_BOUNDARIES) if y_boundary_true else None,
            "confusion_matrix": confusion_matrix(y_boundary_true, y_boundary_pred),
        },
        "uca_activation_status": {
            "accuracy": round(sum(t == p for t, p in zip(y_uca_status_true, y_uca_status_pred)) / len(y_uca_status_true), 4) if y_uca_status_true else None,
            "macro_f1": macro_f1(y_uca_status_true, y_uca_status_pred, ALLOWED_UCA_ACTIVATION_STATUS) if y_uca_status_true else None,
            "confusion_matrix": confusion_matrix(y_uca_status_true, y_uca_status_pred),
        },
        "dominant_uca": {
            "accuracy": round(sum(t == p for t, p in zip(y_uca_true, y_uca_pred)) / len(y_uca_true), 4) if y_uca_true else None,
            "macro_f1": macro_f1(y_uca_true, y_uca_pred, sorted(DRIVER_UCA_ID_SET)) if y_uca_true else None,
            "confusion_matrix": confusion_matrix(y_uca_true, y_uca_pred),
        },
        "case_level_rows": rows,
    }
    ensure_dir(Path(out_dir))
    write_json(Path(out_dir) / "baseline_evaluation_report.json", report)
    return report


# =============================================================================
# Annotation packets
# =============================================================================

BOUNDARY_RUBRIC = {
    "supported_monitoring": "ADS reliance remains source-supported; no sufficient source-visible preparation/transfer pressure.",
    "contingent_readiness": "ADS reliance is conditionally supportable but evidence creates preparation pressure.",
    "not_supported_transfer": "ADS support is source-withdrawn, intervention is reported, or transfer is clearly required.",
}

VULNERABILITY_RUBRIC = {
    "none": "No dominant feedback-update vulnerability is identifiable from the source-visible evidence.",
    "missed_feedback": "Important source-visible feedback is likely not taken up or is absent from the process model update.",
    "ambiguous_feedback": "Feedback meaning is underdetermined, conflicting, or insufficiently specified.",
    "misinterpreted_feedback": "Feedback is present but could be mapped to the wrong capability/mode/actor meaning.",
}


def export_annotation_packets(cases_path: str | Path, out_dir: str | Path, csv_path: Optional[str | Path] = None) -> List[Dict[str, Any]]:
    cases = load_external_cases(cases_path)
    out = Path(out_dir)
    ensure_dir(out)
    rows = []
    for case in cases:
        case_id = case.get("case_id") or stable_digest(case)
        packets = []
        for idx, event in enumerate(case.get("latent_events", [])):
            ep = build_evidence_packet(event, case.get("driver_profile", {}), event_index=idx)
            packets.append({"event_index": idx, "evidence_items": ep["evidence_items"], "source_evidence_audit": ep["source_evidence_audit"]})
        packet = {
            "case_id": case_id,
            "source_metadata": case.get("source_metadata", {}),
            "raw_case_summary": get_path(case, "source_metadata.raw_case_summary", ""),
            "functional_scenario": case.get("latent_events", []),
            "annotation_policy": {
                "do_not_view_model_outputs": True,
                "not_reported_is_not_absence": True,
                "label_given_source_visible_evidence": True,
                "uca_activation_status_controls_dominant_uca": True,
                "no_activated_uca_requires_empty_dominant_uca": True,
            },
            "rubrics": {"boundary": BOUNDARY_RUBRIC, "update_vulnerability": VULNERABILITY_RUBRIC, "uca_catalog": DRIVER_UCA_CATALOG},
            "events": packets,
            "empty_label_form": {
                "case_id": case_id,
                "boundary_label": "",
                "update_vulnerability": "",
                "uca_activation_status": "",
                "dominant_uca": "",
                "active_uca_set": [],
                "primary_pm_slots": [],
                "supporting_evidence_ids": [],
                "insufficient_information_flags": [],
                "annotator_notes": "",
            },
        }
        write_json(out / f"{case_id}.annotation_packet.json", packet)
        rows.append(packet["empty_label_form"])
    if csv_path:
        p = Path(csv_path)
        ensure_dir(p.parent)
        with p.open("w", encoding="utf-8", newline="") as f:
            fieldnames = ["case_id", "boundary_label", "update_vulnerability", "uca_activation_status", "dominant_uca", "active_uca_set", "primary_pm_slots", "supporting_evidence_ids", "insufficient_information_flags", "annotator_notes"]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, list) else v for k, v in row.items()})
    return rows


# =============================================================================
# Feedback evidence gaps and requirement candidates
# =============================================================================


HMI_FEEDBACK_FIELDS = [
    "HMI.mode_state_display",
    "HMI.capability_boundary_hint",
    "HMI.time_budget_indicator",
    "HMI.require_ack",
    "HMI.trajectory_display_latency",
]

DRIVER_STATE_FIELDS = [
    "CABIN.pressure",
    "CABIN.distraction",
]

INTERNAL_ADS_FIELDS = [
    "CAR.time_budget_to_handover",
    "CAR.perception_confidence",
    "CAR.planner_confidence",
    "CAR.reported_system_issue",
    "CAR.reported_intervention",
]

BOUNDARY_STRENGTH = {"supported_monitoring": 0, "contingent_readiness": 1, "not_supported_transfer": 2}

FIELD_REQUIREMENT_TARGETS = {
    "HMI.mode_state_display": ("HMI feedback", "mode_state_display"),
    "HMI.capability_boundary_hint": ("HMI feedback", "capability_boundary_hint"),
    "HMI.time_budget_indicator": ("HMI feedback", "takeover_timing"),
    "HMI.require_ack": ("HMI feedback", "takeover_acknowledgement"),
    "HMI.trajectory_display_latency": ("HMI feedback", "trajectory_latency"),
    "CABIN.pressure": ("incident logging", "driver_pressure"),
    "CABIN.distraction": ("incident logging", "driver_distraction"),
    "CAR.time_budget_to_handover": ("incident logging", "handover_time_budget"),
    "CAR.perception_confidence": ("incident logging", "ads_perception_confidence"),
    "CAR.planner_confidence": ("incident logging", "ads_planner_confidence"),
    "CAR.reported_system_issue": ("incident logging", "reported_system_issue"),
    "CAR.reported_intervention": ("incident logging", "reported_intervention"),
}


FIELD_REQUIREMENT_TEXT = {
    "HMI.mode_state_display": "Record whether the driver-visible automation mode/state was displayed during the event window.",
    "HMI.capability_boundary_hint": "Record whether the HMI communicated capability boundaries or operational design limits relevant to the event.",
    "HMI.time_budget_indicator": "Record whether a takeover/degradation time budget was displayed and the available time budget value.",
    "HMI.require_ack": "Record whether the HMI required, received, or missed driver/operator acknowledgement.",
    "HMI.trajectory_display_latency": "Record display timing/latency for trajectory or maneuver feedback visible to the driver/operator.",
    "CABIN.pressure": "Record source-supported driver/operator pressure indicators only when available; do not infer pressure from outcome.",
    "CABIN.distraction": "Record source-supported distraction/attention indicators only when available; do not infer distraction from outcome.",
    "CAR.time_budget_to_handover": "Record the time budget to handover, fallback, driver takeover, or safety-operator intervention.",
    "CAR.perception_confidence": "Preserve ADS perception confidence or uncertainty evidence sufficient to separate perception from planner/HMI issues.",
    "CAR.planner_confidence": "Preserve ADS planner confidence, fallback state, or maneuver feasibility evidence.",
    "CAR.reported_system_issue": "Record whether the report identifies a system issue, disengagement cause, fallback reason, or absence of such evidence.",
    "CAR.reported_intervention": "Record whether intervention occurred and distinguish test-driver takeover, safety-operator intervention, AV-system fallback, retrieval, or no reported intervention.",
}


FIELD_SUPPORT_SCOPE = {
    "HMI.mode_state_display": ["boundary", "vulnerability", "audit"],
    "HMI.capability_boundary_hint": ["boundary", "vulnerability", "audit"],
    "HMI.time_budget_indicator": ["boundary", "UCA", "audit"],
    "HMI.require_ack": ["boundary", "UCA", "audit"],
    "HMI.trajectory_display_latency": ["vulnerability", "audit"],
    "CABIN.pressure": ["vulnerability", "audit"],
    "CABIN.distraction": ["vulnerability", "audit"],
    "CAR.time_budget_to_handover": ["boundary", "UCA", "audit"],
    "CAR.perception_confidence": ["boundary", "vulnerability", "audit"],
    "CAR.planner_confidence": ["boundary", "vulnerability", "audit"],
    "CAR.reported_system_issue": ["boundary", "vulnerability", "audit"],
    "CAR.reported_intervention": ["boundary", "UCA", "audit"],
}


def requirement_blocked_claims_for_field(field_path: str, replay_posture: Optional[str] = None) -> List[str]:
    """Return paper-facing claims that this missing field prevents from being strengthened."""
    claims: List[str] = []
    if field_path in {"HMI.mode_state_display", "HMI.capability_boundary_hint", "HMI.time_budget_indicator", "HMI.require_ack", "CAR.time_budget_to_handover", "CAR.reported_intervention"}:
        claims.append("not_supported_transfer_without_reported_takeover_or_transition_evidence")
    if field_path in {"HMI.mode_state_display", "HMI.capability_boundary_hint", "HMI.time_budget_indicator", "HMI.trajectory_display_latency", "CAR.perception_confidence", "CAR.planner_confidence"}:
        claims.append("supported_monitoring_without_reported_support_or_within_capability_feedback")
    if field_path in {"CABIN.pressure", "CABIN.distraction", "CAR.reported_system_issue", "CAR.lane_keeping_behavior", "CAR.deceleration_behavior"}:
        claims.append("claim_strength_or_mechanism_detail_limited_by_missing_evidence")
    if replay_posture == "not_supported_transfer" and field_path.startswith("HMI."):
        claims.append("transfer_context_explanation_limited_by_missing_hmi_evidence")
    return sorted(dict.fromkeys(claims or ["claim_strength_or_mechanism_detail_limited_by_missing_evidence"]))


def classify_requirement_criticality(
    field_path: str,
    blocked_claims: Sequence[str],
    support_scope: Sequence[str],
    triggering_pathway_ids: Optional[Sequence[str]] = None,
) -> str:
    """Classify requirement utility for AAP V2 tabletop replay reporting."""
    blocked = set(blocked_claims or [])
    scope = set(support_scope or [])
    if "not_supported_transfer_without_reported_takeover_or_transition_evidence" in blocked:
        return "claim_blocking"
    if triggering_pathway_ids and ("UCA" in scope or field_path.startswith("CAR.time_budget")):
        return "pathway_critical"
    if field_path.startswith(("HMI.", "CAR.", "CABIN.")):
        return "global_missing_logging_field"
    return "lower_priority_completeness"


def requirement_priority_reason(
    field_path: str,
    criticality: str,
    blocked_claims: Sequence[str],
    support_scope: Sequence[str],
) -> str:
    if criticality == "claim_blocking":
        return "This missing field blocks a stronger driver-replay-posture or transfer-context claim under the evidence boundary."
    if criticality == "pathway_critical":
        return "This missing field is directly relevant to candidate action or UCA pathway admissibility/ranking."
    if criticality == "global_missing_logging_field":
        return "This field is a recurring incident-reporting or logging gap needed for future driver process-model replay."
    return "This field improves completeness but is not currently decisive for the strongest blocked claims."


def requirement_specificity_level(field_path: str, triggering_pathway_ids: Optional[Sequence[str]] = None) -> str:
    if triggering_pathway_ids:
        return "pathway_specific"
    if field_path in FIELD_REQUIREMENT_TEXT:
        return "field_specific"
    return "generic"


def requirement_triggering_pathways(field_path: str, evidence_id: Optional[str], ranked_pathways: Sequence[Dict[str, Any]]) -> List[str]:
    """Find pathway IDs whose serialized evidence requirements mention the missing evidence slot."""
    ids: List[str] = []
    for pathway in ranked_pathways or []:
        blob = json.dumps(pathway, ensure_ascii=False)
        if (evidence_id and evidence_id in blob) or (field_path and field_path in blob):
            pid = pathway.get("pathway_id")
            if pid:
                ids.append(str(pid))
    return sorted(dict.fromkeys(ids))


def evidence_id_for_field(field_path: str, event_index: int = 0) -> str:
    group, field_name = field_path.split(".", 1)
    return f"E{event_index + 1:02d}-{group}-{field_name}"


def infer_source_regime(source_dataset: Optional[str], event_type: Optional[str]) -> str:
    src = normalize_token(source_dataset or "")
    evt = normalize_token(event_type or "")
    if "nhtsa" in src:
        return "official_nhtsa_crash_csv"
    if "ca_dmv_collision_augmented" in src:
        return "third_party_ca_dmv_collision_augmented_csv"
    if "ca_dmv_disengagement" in src or "disengagement" in evt:
        return "official_ca_dmv_disengagement_csv"
    return src or evt or "unknown_source_regime"


def get_case_source_regime_from_case(case: Dict[str, Any]) -> str:
    meta = case.get("source_metadata") or {}
    event = (case.get("latent_events") or [{}])[0]
    car = event.get("CAR") or {}
    evt = car.get("event_type")
    event_type = evt.get("value") if isinstance(evt, dict) else evt
    return infer_source_regime(meta.get("source_dataset"), event_type)


def get_case_source_regime_from_bundle(bundle: Dict[str, Any]) -> str:
    meta = bundle.get("source_metadata") or {}
    event_type = None
    final = bundle.get("final_case_summary") or {}
    if final.get("final_commitment_state_fsm") == "not_supported_transfer":
        event_type = "disengagement_or_transfer"
    return infer_source_regime(meta.get("source_dataset"), event_type)


def iter_case_dirs(bundle_dir: str | Path) -> List[Path]:
    root = Path(bundle_dir)
    return sorted([p for p in root.iterdir() if p.is_dir() and (p / "bundle_summary.json").exists()]) if root.exists() else []


def collect_bundle_artifacts(case_dir: Path) -> Dict[str, Any]:
    bundle = read_json(case_dir / "bundle_summary.json")
    evidence_items: List[Dict[str, Any]] = []
    packet_by_event: Dict[int, Dict[str, Any]] = {}
    for ep in sorted(case_dir.glob("e*_evidence_packet.json")):
        packet = read_json(ep)
        try:
            idx = int(ep.name.split("_", 1)[0][1:]) - 1
        except Exception:
            idx = len(packet_by_event)
        packet_by_event[idx] = packet
        evidence_items.extend(packet.get("evidence_items", []))
    return {"bundle": bundle, "evidence_items": evidence_items, "packet_by_event": packet_by_event}


def _safe_mean(values: Sequence[float]) -> float:
    return round(statistics.mean(values), 4) if values else 0.0


def _recursive_count_list_key(obj: Any, keys: set[str]) -> int:
    if isinstance(obj, dict):
        total = 0
        for key, value in obj.items():
            if key in keys and isinstance(value, list):
                total += len(value)
            total += _recursive_count_list_key(value, keys)
        return total
    if isinstance(obj, list):
        return sum(_recursive_count_list_key(item, keys) for item in obj)
    return 0


def count_blocked_claims_in_artifact(obj: Any) -> int:
    return _recursive_count_list_key(obj, {"blocked_claims", "blocked_update_claims", "blocked_claim_set"})


def load_final_tabletop_replay_package(case_dir: Path, bundle: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    bundle = bundle or read_json(case_dir / "bundle_summary.json")
    rel = get_path(bundle, "final_case_summary.final_tabletop_replay_package_path")
    if rel and (case_dir / rel).exists():
        return read_json(case_dir / rel)
    pkgs = sorted(case_dir.glob("e*_tabletop_replay_package.json"))
    return read_json(pkgs[-1]) if pkgs else None


def _logical_answer_artifact_present(pkg: Dict[str, Any], key: str) -> bool:
    if key == "pm_context_nodes":
        return bool(get_path(pkg, "driver_process_model.pm_context_nodes", []))
    if key == "evidence_items":
        return bool(get_path(pkg, "evidence_profile.total_evidence_items", 0))
    if key == "update_process_nodes":
        return bool(get_path(pkg, "process_model_update.update_process_nodes", []))
    if key == "action_selection_nodes":
        return bool(pkg.get("candidate_driver_actions", []))
    if key in {"uca_pathway_summary", "ranked_pathways", "missing_requirement_candidates"}:
        return bool(pkg.get(key, []))
    return bool(pkg.get(key))


def count_answerable_replay_questions(pkg: Dict[str, Any]) -> int:
    count = 0
    for q in pkg.get("replay_questions", []) or []:
        refs = q.get("answered_by", []) or []
        if refs and all(_logical_answer_artifact_present(pkg, str(ref)) for ref in refs):
            count += 1
    return count


def _high_priority_requirement_field(field_path: Optional[str]) -> bool:
    if not field_path:
        return False
    scopes = FIELD_SUPPORT_SCOPE.get(field_path, [])
    return bool({"boundary", "UCA", "vulnerability"} & set(scopes))


def audit_tabletop_replay_packages(bundle_dir: str | Path, out_dir: str | Path) -> Dict[str, Any]:
    """Audit whether bundle outputs are usable tabletop replay packages.

    This is a paper-facing audit for AAP V2. It checks artifact presence and
    replay utility, not whether the replay hypotheses are true accident causes.
    """
    case_reports: List[Dict[str, Any]] = []
    target_counts: Counter = Counter()
    high_priority_missing_field_counts: Counter = Counter()
    source_regime_counts: Counter = Counter()

    for case_dir in iter_case_dirs(bundle_dir):
        bundle = read_json(case_dir / "bundle_summary.json")
        pkg = load_final_tabletop_replay_package(case_dir, bundle)
        final = bundle.get("final_case_summary", {}) or {}
        source_regime = get_case_source_regime_from_bundle(bundle)
        source_regime_counts[source_regime] += 1
        if not pkg:
            case_reports.append({
                "case_id": bundle.get("case_id"),
                "source_regime": source_regime,
                "replay_package_present": False,
                "quadrant_coverage_complete": False,
                "update_process_present": False,
                "candidate_action_count": 0,
                "uca_pathway_count": 0,
                "ranked_pathway_count": 0,
                "replay_question_count": 0,
                "answerable_replay_question_count": 0,
                "missing_requirement_count": 0,
                "blocked_claim_count": int(final.get("final_blocked_claim_count") or 0),
                "review_ready_case": False,
            })
            continue

        completeness = pkg.get("replay_package_completeness", {}) or {}
        reqs = pkg.get("missing_requirement_candidates", []) or []
        for req in reqs:
            target_counts[(req.get("target_type") or "unknown", req.get("target_slot") or req.get("field_path") or "unknown")] += 1
            if _high_priority_requirement_field(req.get("field_path")):
                high_priority_missing_field_counts[req.get("field_path")] += 1
        candidate_action_count = len(pkg.get("candidate_driver_actions", []) or [])
        uca_pathway_count = len(pkg.get("uca_pathway_summary", []) or [])
        ranked_pathway_count = len(pkg.get("ranked_pathways", []) or [])
        replay_question_count = len(pkg.get("replay_questions", []) or [])
        answerable_question_count = count_answerable_replay_questions(pkg)
        blocked_claim_count = count_blocked_claims_in_artifact(pkg)
        if not blocked_claim_count:
            blocked_claim_count = int(final.get("final_blocked_claim_count") or 0)
        review_ready = bool(
            bundle.get("schema_valid")
            and completeness.get("quadrant_coverage_complete")
            and completeness.get("update_process_present")
            and completeness.get("candidate_actions_present")
            and completeness.get("ranked_pathways_present")
            and replay_question_count > 0
        )
        case_reports.append({
            "case_id": bundle.get("case_id"),
            "source_regime": source_regime,
            "schema_valid": bundle.get("schema_valid"),
            "replay_package_present": True,
            "quadrant_coverage_complete": bool(completeness.get("quadrant_coverage_complete")),
            "update_process_present": bool(completeness.get("update_process_present")),
            "candidate_action_count": candidate_action_count,
            "uca_pathway_count": uca_pathway_count,
            "ranked_pathway_count": ranked_pathway_count,
            "replay_question_count": replay_question_count,
            "answerable_replay_question_count": answerable_question_count,
            "missing_requirement_count": len(reqs),
            "blocked_claim_count": blocked_claim_count,
            "review_ready_case": review_ready,
            "tabletop_replay_package_path": str(case_dir / (final.get("final_tabletop_replay_package_path") or "")),
            "top_ranked_pathway": (pkg.get("ranked_pathways") or [None])[0],
        })

    n = len(case_reports)
    present = [r for r in case_reports if r.get("replay_package_present")]
    review_ready = [r for r in case_reports if r.get("review_ready_case")]
    summary = {
        "schema_version": SCHEMA_VERSION,
        "report_type": "tabletop_replay_audit",
        "claim_boundary": {
            "allowed": "Audit tabletop replay artifact completeness and workflow utility.",
            "not_allowed": "Treating replay readiness as proof of true driver psychology, true accident cause, or legal responsibility.",
        },
        "source": {"bundle_dir": str(bundle_dir)},
        "num_cases": n,
        "summary": {
            "replay_package_generation_rate": round(len(present) / n, 4) if n else None,
            "quadrant_coverage_rate": round(sum(1 for r in present if r.get("quadrant_coverage_complete")) / len(present), 4) if present else None,
            "update_process_present_rate": round(sum(1 for r in present if r.get("update_process_present")) / len(present), 4) if present else None,
            "mean_candidate_action_count": _safe_mean([r.get("candidate_action_count", 0) for r in present]),
            "mean_uca_pathway_count": _safe_mean([r.get("uca_pathway_count", 0) for r in present]),
            "mean_ranked_pathway_count": _safe_mean([r.get("ranked_pathway_count", 0) for r in present]),
            "mean_replay_question_count": _safe_mean([r.get("replay_question_count", 0) for r in present]),
            "mean_answerable_replay_question_count": _safe_mean([r.get("answerable_replay_question_count", 0) for r in present]),
            "mean_missing_requirement_count": _safe_mean([r.get("missing_requirement_count", 0) for r in present]),
            "mean_blocked_claim_count": _safe_mean([r.get("blocked_claim_count", 0) for r in present]),
            "review_ready_case_rate": round(len(review_ready) / n, 4) if n else None,
            "source_regime_counts": dict(source_regime_counts),
        },
        "workflow_utility": {
            "post_incident_review_support": {
                "review_ready_case_rate": round(len(review_ready) / n, 4) if n else None,
                "mean_ranked_pathways": _safe_mean([r.get("ranked_pathway_count", 0) for r in present]),
                "mean_blocked_claims": _safe_mean([r.get("blocked_claim_count", 0) for r in present]),
                "mean_answerable_replay_questions": _safe_mean([r.get("answerable_replay_question_count", 0) for r in present]),
            },
            "minimum_reporting_logging_requirement_support": {
                "cases_with_requirement_candidates": sum(1 for r in present if r.get("missing_requirement_count", 0) > 0),
                "mean_requirement_candidates_per_case": _safe_mean([r.get("missing_requirement_count", 0) for r in present]),
                "top_requirement_targets": [
                    {"target_type": k[0], "target_slot": k[1], "count": v}
                    for k, v in target_counts.most_common(20)
                ],
                "top_high_priority_missing_fields": [
                    {"field_path": k, "count": v}
                    for k, v in high_priority_missing_field_counts.most_common(20)
                ],
            },
        },
        "case_reports": case_reports,
    }
    ensure_dir(Path(out_dir))
    write_json(Path(out_dir) / "tabletop_replay_audit.json", summary)
    return summary


def _case_evidence_maps_from_bundle_dir(bundle_dir: str | Path, case_id: str) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    case_dir = Path(bundle_dir) / case_id
    evidence_by_id: Dict[str, Dict[str, Any]] = {}
    evidence_by_field: Dict[str, Dict[str, Any]] = {}
    if not case_dir.exists():
        return evidence_by_id, evidence_by_field
    for ep in sorted(case_dir.glob("e*_evidence_packet.json")):
        packet = read_json(ep)
        for item in packet.get("evidence_items", []) or []:
            if item.get("evidence_id"):
                evidence_by_id[item["evidence_id"]] = item
            if item.get("field_path"):
                evidence_by_field[item["field_path"]] = item
    return evidence_by_id, evidence_by_field


def _commitment_support_ids(case_dir: Path) -> List[str]:
    ids: List[str] = []
    for p in audit_stage_files(case_dir, "e*_round2b_commitment.json", "e*_commitment_boundary.json"):
        if not p.exists():
            continue
        obj = read_json(p)
        ids.extend((obj.get("commitment_block") or {}).get("supporting_evidence_ids") or [])
    return list(dict.fromkeys(ids))


def _text_contains_any(obj: Any, needles: Sequence[str]) -> bool:
    text = json.dumps(obj, ensure_ascii=False).lower()
    return any(n.lower() in text for n in needles)


def _iter_text_values(obj: Any) -> Iterable[str]:
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in {"claim_boundary", "not_allowed", "allowed", "outcome_cannot_support", "outcome_not_used_for", "why_not_outcome_derived"}:
                continue
            yield from _iter_text_values(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from _iter_text_values(value)
    elif isinstance(obj, str):
        yield obj


def _unsupported_driver_state_claim(obj: Any) -> bool:
    guard_terms = ["do not", "cannot", "not evidence", "not infer", "not claim", "not_allowed", "disallowed", "never"]
    for text in _iter_text_values(obj):
        low = text.lower()
        if any(g in low for g in guard_terms):
            continue
        if any(pat in low for pat in PSYCHOLOGICAL_OVERCLAIM_PATTERNS):
            return True
    return False


def _unsupported_takeover_failure_claim(obj: Any) -> bool:
    claim_terms = [
        "takeover failure",
        "failed takeover",
        "failed to take over",
        "failure to take over",
        "driver failed to intervene",
        "driver did not intervene",
        "driver failed to resume control",
    ]
    guard_terms = [
        "do not",
        "cannot",
        "not evidence",
        "not infer",
        "not claim",
        "not_allowed",
        "disallowed",
        "never",
        "outcome_cannot_support",
        "inferring takeover failure from crash/collision outcome alone",
        "using collision/disengagement outcome as uca activation evidence",
        "crash/collision outcome alone cannot support takeover failure",
    ]
    for text in _iter_text_values(obj):
        low = text.lower()
        if any(g in low for g in guard_terms):
            continue
        if any(term in low for term in claim_terms):
            return True
    return False


def _condition_bundle_rows(bundle_dir: str | Path) -> Dict[str, Dict[str, Any]]:
    return collect_bundle_summaries(bundle_dir) if bundle_dir and Path(bundle_dir).exists() else {}


def _condition_baseline_rows(baseline_dir: str | Path) -> Dict[str, Dict[str, Any]]:
    return collect_baseline_results(baseline_dir) if baseline_dir and Path(baseline_dir).exists() else {}


def _full_replay_chain_rate(bundle: Dict[str, Any]) -> float:
    top = get_path(bundle, "final_case_summary.final_top_pathway")
    pathways = []
    if isinstance(top, dict):
        pathways.append(top)
    pathways.extend(get_path(bundle, "final_case_summary.final_uca_pathway_summary", []) or [])
    complete = [p for p in pathways if isinstance(p, dict) and p.get("forward_chain_complete")]
    if complete:
        return 1.0
    top_chain = get_path(bundle, "final_case_summary.final_top_pathway.forward_chain_complete")
    return 1.0 if top_chain else 0.0


def build_pm_mediation_comparison_report(
    *,
    out_dir: str | Path,
    full_bundle_dir: str | Path,
    direct_baseline_dir: Optional[str | Path] = None,
    generic_baseline_dir: Optional[str | Path] = None,
    no_update_bundle_dir: Optional[str | Path] = None,
    baseline_suite_dir: Optional[str | Path] = None,
) -> Dict[str, Any]:
    if baseline_suite_dir:
        suite = Path(baseline_suite_dir)
        direct_baseline_dir = direct_baseline_dir or suite / "baselines" / "direct"
        generic_baseline_dir = generic_baseline_dir or suite / "baselines" / "generic_cot"
        no_update_bundle_dir = no_update_bundle_dir or suite / "ablations" / "no_update"
        if not full_bundle_dir and (suite / "full_system").exists():
            full_bundle_dir = suite / "full_system"

    full_rows = _condition_bundle_rows(full_bundle_dir)
    conditions: Dict[str, Dict[str, Any]] = {
        "full_replay": {"type": "bundle", "rows": full_rows, "dir": str(full_bundle_dir)},
    }
    if direct_baseline_dir:
        conditions["direct_llm"] = {"type": "baseline", "rows": _condition_baseline_rows(direct_baseline_dir), "dir": str(direct_baseline_dir)}
    if generic_baseline_dir:
        conditions["generic_cot"] = {"type": "baseline", "rows": _condition_baseline_rows(generic_baseline_dir), "dir": str(generic_baseline_dir)}
    if no_update_bundle_dir:
        conditions["no_update"] = {"type": "bundle", "rows": _condition_bundle_rows(no_update_bundle_dir), "dir": str(no_update_bundle_dir)}

    case_ids = sorted(set().union(*(set(v["rows"].keys()) for v in conditions.values())))
    condition_reports: Dict[str, Any] = {}
    case_rows: List[Dict[str, Any]] = []

    for name, spec in conditions.items():
        typ = spec["type"]
        rows = spec["rows"]
        outcome_only_overreach = 0
        unsupported_driver_state = 0
        unsupported_takeover_failure = 0
        complete_chain_flags: List[float] = []
        blocked_transparency_flags: List[float] = []
        per_case: List[Dict[str, Any]] = []
        for case_id, obj in rows.items():
            evidence_by_id, evidence_by_field = _case_evidence_maps_from_bundle_dir(full_bundle_dir, case_id)
            if typ == "baseline":
                boundary = obj.get("commitment_state_fsm")
                strength = classify_boundary_evidence_strength(boundary, evidence_by_field, [], evidence_by_id)
                overreach = bool(strength.get("outcome_only_escalation_warning"))
                blocked_count = 0
                chain_complete = 0.0
            else:
                boundary = get_path(obj, "final_case_summary.final_commitment_state_fsm")
                case_dir = Path(spec["dir"]) / case_id
                ids = _commitment_support_ids(case_dir)
                strength = classify_boundary_evidence_strength(boundary, evidence_by_field, ids, evidence_by_id)
                overreach = bool(strength.get("outcome_only_escalation_warning"))
                blocked_count = int(get_path(obj, "final_case_summary.final_blocked_claim_count") or 0)
                if case_dir.exists():
                    pkg = load_final_tabletop_replay_package(case_dir, obj)
                    if pkg:
                        blocked_count = max(blocked_count, count_blocked_claims_in_artifact(pkg))
                chain_complete = _full_replay_chain_rate(obj)
            if overreach:
                outcome_only_overreach += 1
            if _unsupported_driver_state_claim(obj):
                unsupported_driver_state += 1
            if _unsupported_takeover_failure_claim(obj):
                unsupported_takeover_failure += 1
            complete_chain_flags.append(chain_complete)
            blocked_transparency_flags.append(1.0 if blocked_count > 0 else 0.0)
            row = {
                "condition": name,
                "case_id": case_id,
                "boundary_or_posture": boundary,
                "outcome_only_overreach": overreach,
                "strong_boundary_evidence_strength": strength.get("strong_boundary_evidence_strength"),
                "unsupported_driver_state_claim": _unsupported_driver_state_claim(obj),
                "unsupported_takeover_failure_claim": _unsupported_takeover_failure_claim(obj),
                "complete_pm_update_action_chain": bool(chain_complete),
                "blocked_claim_count": blocked_count,
                "blocked_claim_transparency": blocked_count > 0,
            }
            per_case.append(row)
            case_rows.append(row)
        n = len(per_case)
        condition_reports[name] = {
            "condition_type": typ,
            "source_dir": spec["dir"],
            "num_cases": n,
            "outcome_only_overreach_count": outcome_only_overreach,
            "unsupported_driver_state_claim_count": unsupported_driver_state,
            "unsupported_takeover_failure_claim_count": unsupported_takeover_failure,
            "abductive_pathway_with_complete_pm_update_action_chain_rate": _safe_mean(complete_chain_flags),
            "blocked_claim_transparency_rate": _safe_mean(blocked_transparency_flags),
            "case_rows": per_case,
        }

    report = {
        "schema_version": SCHEMA_VERSION,
        "report_type": "driver_pm_mediation_comparison",
        "claim_boundary": {
            "allowed": "Compare whether PM/update/action mediation suppresses outcome-driven driver claims.",
            "not_allowed": "Treating this comparison as ground-truth accident-cause validation.",
        },
        "source": {
            "full_bundle_dir": str(full_bundle_dir),
            "baseline_suite_dir": str(baseline_suite_dir) if baseline_suite_dir else None,
            "direct_baseline_dir": str(direct_baseline_dir) if direct_baseline_dir else None,
            "generic_baseline_dir": str(generic_baseline_dir) if generic_baseline_dir else None,
            "no_update_bundle_dir": str(no_update_bundle_dir) if no_update_bundle_dir else None,
        },
        "num_unique_cases": len(case_ids),
        "condition_reports": condition_reports,
        "interpretation": {
            "necessary_mediation_test": "A condition is stronger for the paper if it reduces outcome-only overreach and increases complete PM->update->action->UCA pathway transparency.",
            "expected_pattern": "full_replay should have lower overreach than direct/generic baselines and higher complete-chain and blocked-claim transparency than no_update.",
        },
        "case_rows": case_rows,
    }
    ensure_dir(Path(out_dir))
    write_json(Path(out_dir) / "driver_pm_mediation_comparison.json", report)
    return report


def summarize_evidence_provenance_for_ids(ids: Sequence[str], evidence_by_id: Dict[str, Dict[str, Any]]) -> Dict[str, int]:
    counts = Counter()
    for eid in ids:
        item = evidence_by_id.get(eid)
        counts[item.get("provenance", "missing") if item else "missing"] += 1
    return dict(counts)


def evidence_value_text(item: Optional[Dict[str, Any]]) -> str:
    if not item:
        return ""
    return normalize_token(item.get("value"))


def field_is_reported(evidence_by_field: Dict[str, Dict[str, Any]], field_path: str) -> bool:
    return evidence_by_field.get(field_path, {}).get("provenance") in {"reported", "derived", "reported_narrative", "assumed_for_counterfactual"}


def classify_boundary_evidence_strength(
    boundary: Optional[str],
    evidence_by_field: Dict[str, Dict[str, Any]],
    cited_ids: Sequence[str],
    evidence_by_id: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """Classify whether a strong boundary claim is backed by explicit transition evidence.

    This is an audit guardrail, not a semantic repair step. It surfaces the exact
    failure mode the paper studies: crash/collision outcome being used as a proxy
    for unsupported transfer.
    """
    cited_fields = sorted({evidence_by_id.get(eid, {}).get("field_path", "missing") for eid in cited_ids})
    explicit_fields: List[str] = []
    hmi_fields: List[str] = []
    system_fields: List[str] = []
    indirect_fields: List[str] = []
    outcome_fields: List[str] = []
    not_reported_fields: List[str] = []

    for eid in cited_ids:
        item = evidence_by_id.get(eid)
        if not item:
            continue
        value = evidence_value_text(item)
        field_path = item.get("field_path", eid)
        if item.get("provenance") == "not_reported":
            not_reported_fields.append(field_path)
            continue
        if item.get("source_group") == "NARRATIVE":
            if any(k in value for k in ["disengag", "manual", "takeover", "took over", "operator", "test driver", "resumed control", "interven"]):
                explicit_fields.append(field_path)
            elif any(k in value for k in ["software", "system error", "fault", "failed", "incorrect", "issue"]):
                system_fields.append(field_path)

    for field_path, item in evidence_by_field.items():
        value = evidence_value_text(item)
        prov = item.get("provenance")
        if prov == "not_reported":
            if field_path in cited_fields:
                not_reported_fields.append(field_path)
            continue
        if field_path == "CAR.reported_intervention" and value not in {"", "not_reported", "none", "no", "unknown"}:
            explicit_fields.append(field_path)
        elif field_path == "CAR.event_type" and "disengagement" in value:
            explicit_fields.append(field_path)
        elif field_path == "CAR.time_budget_to_handover" and value not in {"", "not_reported", "unknown", "none"}:
            explicit_fields.append(field_path)
        elif field_path in {"HMI.mode_state_display", "HMI.capability_boundary_hint", "HMI.time_budget_indicator", "HMI.require_ack"}:
            if any(k in value for k in ["takeover", "handover", "withdraw", "boundary_exceeded", "required", "yes", "now"]):
                hmi_fields.append(field_path)
        elif field_path == "CAR.reported_system_issue" and value not in {"", "not_reported", "none", "unknown"}:
            system_fields.append(field_path)
        elif field_path in {"ENV.road_geometry", "ENV.lane_topology", "ACTOR.primary_type", "ACTOR.primary_intent", "CAR.deceleration_behavior"}:
            indirect_fields.append(field_path)
        elif field_path in {"CAR.event_type", "CAR.reported_consequence"} and any(k in value for k in ["crash", "collision", "contact"]):
            outcome_fields.append(field_path)

    if boundary != "not_supported_transfer":
        category = "not_strong_boundary"
    elif explicit_fields:
        category = "explicit_transition_or_intervention"
    elif hmi_fields:
        category = "explicit_hmi_takeover_or_support_withdrawal"
    elif system_fields:
        category = "reported_system_issue_or_disengagement_cause"
    elif outcome_fields and not (explicit_fields or hmi_fields or system_fields):
        category = "outcome_only"
    elif indirect_fields:
        category = "indirect_event_pressure"
    else:
        category = "no_explicit_support_detected"

    warning = bool(boundary == "not_supported_transfer" and category in {"outcome_only", "indirect_event_pressure", "no_explicit_support_detected"})
    not_reported_warning = bool(boundary == "not_supported_transfer" and not_reported_fields)
    return {
        "strong_boundary_evidence_strength": category,
        "strong_boundary_supporting_fields": {
            "explicit_transition_or_intervention": sorted(explicit_fields),
            "explicit_hmi_takeover_or_support_withdrawal": sorted(hmi_fields),
            "reported_system_issue_or_disengagement_cause": sorted(system_fields),
            "indirect_event_pressure": sorted(indirect_fields),
            "outcome_only": sorted(outcome_fields),
            "not_reported_cited_fields": sorted(not_reported_fields),
            "cited_fields": cited_fields,
        },
        "outcome_only_escalation_warning": warning,
        "not_reported_boundary_support_warning": not_reported_warning,
    }


def build_gap_rows_from_evidence(
    case_id: str,
    evidence_by_field: Dict[str, Dict[str, Any]],
    boundary: Optional[str],
    active_uca_set: Optional[Sequence[str]] = None,
    event_index: int = 0,
) -> Tuple[List[Dict[str, Any]], List[str], List[str]]:
    gap_rows: List[Dict[str, Any]] = []
    insufficient_flags: List[str] = []
    blockers: List[str] = []
    fields = HMI_FEEDBACK_FIELDS + DRIVER_STATE_FIELDS + INTERNAL_ADS_FIELDS
    current_strength = BOUNDARY_STRENGTH.get(boundary or "", 1)

    for field_path in fields:
        item = evidence_by_field.get(field_path, {})
        provenance = item.get("provenance", "missing")
        value = item.get("value", "missing")
        gap_category = (
            "hmi_feedback_gap" if field_path.startswith("HMI.")
            else "driver_state_gap" if field_path.startswith("CABIN.")
            else "internal_ads_or_transition_gap"
        )
        if provenance != "not_reported":
            continue

        blocks_stronger = False
        blocks_weaker = False
        rationale = "Source did not report this field; it must remain an explicit evidence gap."
        if field_path in {"HMI.mode_state_display", "HMI.capability_boundary_hint", "HMI.time_budget_indicator", "HMI.require_ack", "CAR.reported_intervention", "CAR.time_budget_to_handover"}:
            blocks_stronger = current_strength < BOUNDARY_STRENGTH["not_supported_transfer"]
            if blocks_stronger:
                blockers.append(field_path)
                rationale = "Missing takeover-demand or transition evidence prevents an unsupported escalation to not_supported_transfer."
        if field_path in {"HMI.mode_state_display", "HMI.capability_boundary_hint", "HMI.time_budget_indicator", "HMI.trajectory_display_latency", "CAR.perception_confidence", "CAR.planner_confidence"}:
            blocks_weaker = current_strength > BOUNDARY_STRENGTH["supported_monitoring"]
            if blocks_weaker and not blocks_stronger:
                rationale = "Missing support/within-capability feedback prevents a strong supported_monitoring claim."

        insufficient_flags.append(f"{field_path.replace('.', '_')}_not_reported")
        gap_rows.append({
            "case_id": case_id,
            "event_index": event_index,
            "field_path": field_path,
            "evidence_id": item.get("evidence_id") or evidence_id_for_field(field_path, event_index),
            "value": value,
            "provenance": provenance,
            "gap_category": gap_category,
            "blocks_stronger_boundary_claim": blocks_stronger,
            "blocks_weaker_boundary_claim": blocks_weaker,
            "linked_boundary": boundary,
            "linked_active_uca_set": list(active_uca_set or []),
            "rationale": rationale,
        })
    return gap_rows, sorted(set(insufficient_flags)), sorted(set(blockers))


def run_feedback_gap_report(
    out_dir: str | Path,
    *,
    cases_path: Optional[str | Path] = None,
    bundle_dir: Optional[str | Path] = None,
) -> Dict[str, Any]:
    if not cases_path and not bundle_dir:
        raise DataCurationError("feedback-gap-report requires --cases or --bundle-dir")
    reports: List[Dict[str, Any]] = []
    source = {"cases": str(cases_path) if cases_path else None, "bundle_dir": str(bundle_dir) if bundle_dir else None}

    if bundle_dir:
        for case_dir in iter_case_dirs(bundle_dir):
            artifacts = collect_bundle_artifacts(case_dir)
            bundle = artifacts["bundle"]
            evidence_items = artifacts["evidence_items"]
            evidence_by_field = {i.get("field_path"): i for i in evidence_items}
            final = bundle.get("final_case_summary", {})
            boundary = final.get("final_commitment_state_fsm")
            active = final.get("final_active_uca_set") or []
            gaps, flags, blockers = build_gap_rows_from_evidence(bundle.get("case_id"), evidence_by_field, boundary, active)
            reports.append({
                "case_id": bundle.get("case_id"),
                "case_source": bundle.get("case_source"),
                "source_dataset": (bundle.get("source_metadata") or {}).get("source_dataset"),
                "source_regime": get_case_source_regime_from_bundle(bundle),
                "boundary": boundary,
                "dominant_uca": final.get("final_dominant_uca"),
                "active_uca_set": active,
                "schema_valid": bundle.get("schema_valid"),
                "gap_count": len(gaps),
                "gap_category_counts": dict(Counter(g["gap_category"] for g in gaps)),
                "stronger_boundary_blockers": blockers,
                "insufficient_information_flags": flags,
                "gaps": gaps,
            })
    else:
        for case in load_external_cases(cases_path):
            event = (case.get("latent_events") or [{}])[0]
            evidence_items = build_evidence_items(event, event_index=0)
            evidence_by_field = {i.get("field_path"): i for i in evidence_items}
            gaps, flags, blockers = build_gap_rows_from_evidence(case.get("case_id"), evidence_by_field, None, [])
            reports.append({
                "case_id": case.get("case_id"),
                "case_source": case.get("case_source"),
                "source_dataset": (case.get("source_metadata") or {}).get("source_dataset"),
                "source_regime": get_case_source_regime_from_case(case),
                "boundary": None,
                "dominant_uca": None,
                "active_uca_set": [],
                "schema_valid": None,
                "gap_count": len(gaps),
                "gap_category_counts": dict(Counter(g["gap_category"] for g in gaps)),
                "stronger_boundary_blockers": blockers,
                "insufficient_information_flags": flags,
                "gaps": gaps,
            })

    gap_category_counts = Counter()
    field_counts = Counter()
    blocker_counts = Counter()
    source_regime_counts = Counter()
    gaps_by_source_regime = Counter()
    for r in reports:
        gap_category_counts.update(r.get("gap_category_counts", {}))
        field_counts.update(g["field_path"] for g in r.get("gaps", []))
        blocker_counts.update(r.get("stronger_boundary_blockers", []))
        source_regime = r.get("source_regime") or "unknown_source_regime"
        source_regime_counts[source_regime] += 1
        gaps_by_source_regime[source_regime] += r.get("gap_count", 0)

    summary = {
        "schema_version": SCHEMA_VERSION,
        "report_type": "feedback_gap_report",
        "claim_boundary": "Evidence gaps are analysis limitations, not claims about true HMI/driver cognition.",
        "source": source,
        "num_cases": len(reports),
        "aggregate": {
            "total_gap_count": sum(r.get("gap_count", 0) for r in reports),
            "gap_category_counts": dict(gap_category_counts),
            "gap_field_counts": dict(field_counts),
            "stronger_boundary_blocker_counts": dict(blocker_counts),
            "source_regime_counts": dict(source_regime_counts),
            "gap_counts_by_source_regime": dict(gaps_by_source_regime),
        },
        "case_reports": reports,
    }
    ensure_dir(Path(out_dir))
    write_json(Path(out_dir) / "feedback_gap_report.json", summary)
    return summary


def generate_requirement_candidates_from_gap_report(gap_report: Dict[str, Any], out_dir: str | Path) -> Dict[str, Any]:
    case_reports = gap_report.get("case_reports", [])
    candidates: List[Dict[str, Any]] = []
    taxonomy = Counter()
    source_regime_taxonomy = Counter()
    for report in case_reports:
        case_id = report.get("case_id")
        boundary = report.get("boundary")
        active = report.get("active_uca_set") or []
        source_regime = report.get("source_regime") or "unknown_source_regime"
        for gap in report.get("gaps", []):
            field_path = gap.get("field_path")
            req_type, target = FIELD_REQUIREMENT_TARGETS.get(field_path, ("incident logging", field_path))
            priority = "high" if gap.get("blocks_stronger_boundary_claim") else "medium" if gap.get("blocks_weaker_boundary_claim") else "low"
            blocked_claims = requirement_blocked_claims_for_field(field_path, boundary)
            if gap.get("blocks_stronger_boundary_claim") and "not_supported_transfer_without_reported_takeover_or_transition_evidence" not in blocked_claims:
                blocked_claims.append("not_supported_transfer_without_reported_takeover_or_transition_evidence")
            if gap.get("blocks_weaker_boundary_claim") and "supported_monitoring_without_reported_support_or_within_capability_feedback" not in blocked_claims:
                blocked_claims.append("supported_monitoring_without_reported_support_or_within_capability_feedback")
            blocked_claims = sorted(dict.fromkeys(blocked_claims))
            supports = FIELD_SUPPORT_SCOPE.get(field_path, ["audit"])
            triggering_pathway_ids = sorted(set(gap.get("triggering_pathway_ids") or []))
            criticality = classify_requirement_criticality(field_path, blocked_claims, supports, triggering_pathway_ids)
            candidate = {
                "case_id": case_id,
                "source_regime": source_regime,
                "requirement_type": req_type,
                "target": target,
                "missing_evidence_slot": field_path,
                "source_gap_field": field_path,
                "evidence_id": gap.get("evidence_id"),
                "blocked_stronger_claim": blocked_claims,
                "candidate_evidence_requirement": FIELD_REQUIREMENT_TEXT.get(field_path, "Record this missing evidence slot in future incident reports or logs."),
                "supports": supports,
                "linked_boundary": boundary,
                "linked_active_uca_set": active,
                "priority": priority,
                "requirement_criticality_class": criticality,
                "requirement_triggering_pathway_ids": triggering_pathway_ids,
                "requirement_blocks_claims": blocked_claims,
                "requirement_priority_reason": requirement_priority_reason(field_path, criticality, blocked_claims, supports),
                "requirement_specificity_level": requirement_specificity_level(field_path, triggering_pathway_ids),
                "status": "analysis_derived_candidate_not_final_design",
                "claim_boundary": "This is an evidence/logging need for future safety analysis, not a validated HMI design requirement.",
                "rationale": (
                    "Record this feedback/logging field because its absence limits STPA-HF boundary and UCA reasoning. "
                    + str(gap.get("rationale", ""))
                ),
            }
            candidates.append(candidate)
            taxonomy[(req_type, target, priority)] += 1
            source_regime_taxonomy[(source_regime, req_type, target, priority)] += 1

    summary = {
        "schema_version": SCHEMA_VERSION,
        "report_type": "evidence_requirement_candidates",
        "legacy_report_type": "requirement_candidates",
        "claim_boundary": "Candidates indicate evidence/logging needs for future analysis; they are not validated HMI design requirements.",
        "num_cases": len(case_reports),
        "num_candidates": len(candidates),
        "taxonomy": [
            {"requirement_type": k[0], "target": k[1], "priority": k[2], "count": v}
            for k, v in sorted(taxonomy.items())
        ],
        "taxonomy_by_source_regime": [
            {"source_regime": k[0], "requirement_type": k[1], "target": k[2], "priority": k[3], "count": v}
            for k, v in sorted(source_regime_taxonomy.items())
        ],
        "candidates": candidates,
    }
    ensure_dir(Path(out_dir))
    write_json(Path(out_dir) / "requirement_candidates.json", summary)
    write_json(Path(out_dir) / "evidence_requirement_candidates.json", summary)
    taxonomy_summary = {
        "schema_version": SCHEMA_VERSION,
        "report_type": "evidence_requirement_taxonomy_summary",
        "claim_boundary": summary["claim_boundary"],
        "num_cases": len(case_reports),
        "num_candidates": len(candidates),
        "by_requirement_type_target_priority": summary["taxonomy"],
        "by_source_regime_requirement_type_target_priority": summary["taxonomy_by_source_regime"],
        "by_missing_evidence_slot": [
            {"missing_evidence_slot": k, "count": v}
            for k, v in sorted(Counter(c["missing_evidence_slot"] for c in candidates).items())
        ],
        "by_requirement_criticality_class": [
            {"requirement_criticality_class": k, "count": v}
            for k, v in sorted(Counter(c["requirement_criticality_class"] for c in candidates).items())
        ],
        "by_specificity_level": [
            {"requirement_specificity_level": k, "count": v}
            for k, v in sorted(Counter(c["requirement_specificity_level"] for c in candidates).items())
        ],
        "by_blocked_stronger_claim": [
            {"blocked_claim": k, "count": v}
            for k, v in sorted(Counter(claim for c in candidates for claim in c.get("blocked_stronger_claim", [])).items())
        ],
        "by_support_scope": [
            {"supports": k, "count": v}
            for k, v in sorted(Counter(scope for c in candidates for scope in c.get("supports", [])).items())
        ],
        "representative_examples": [],
    }
    seen_example_keys = set()
    for c in candidates:
        key = (c.get("source_regime"), c.get("missing_evidence_slot"), c.get("priority"))
        if key in seen_example_keys:
            continue
        seen_example_keys.add(key)
        taxonomy_summary["representative_examples"].append({
            "source_regime": c.get("source_regime"),
            "missing_evidence_slot": c.get("missing_evidence_slot"),
            "priority": c.get("priority"),
            "candidate_evidence_requirement": c.get("candidate_evidence_requirement"),
            "blocked_stronger_claim": c.get("blocked_stronger_claim"),
            "supports": c.get("supports"),
            "example_case_id": c.get("case_id"),
        })
    write_json(Path(out_dir) / "evidence_requirement_taxonomy_summary.json", taxonomy_summary)
    csv_path = Path(out_dir) / "evidence_requirement_taxonomy_summary.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["source_regime", "requirement_type", "target", "priority", "count"])
        writer.writeheader()
        for row in summary["taxonomy_by_source_regime"]:
            writer.writerow(row)
    md_lines = [
        "# Evidence/Logging Requirement Representative Examples",
        "",
        "These are analysis-derived evidence/logging needs for future safety analysis, not validated HMI design requirements.",
        "",
    ]
    for ex in taxonomy_summary["representative_examples"][:30]:
        md_lines.append(f"- `{ex['source_regime']}` / `{ex['missing_evidence_slot']}` / priority `{ex['priority']}`: {ex['candidate_evidence_requirement']} Example case: `{ex['example_case_id']}`.")
    (Path(out_dir) / "evidence_requirement_representative_examples.md").write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    return summary


def build_paper_result_manifest(
    out_path: str | Path,
    *,
    cases_path: Optional[str | Path] = None,
    bundle_dir: Optional[str | Path] = None,
    baseline_dir: Optional[str | Path] = None,
    cf_report: Optional[str | Path] = None,
    missingness_profile: Optional[str | Path] = None,
    evidence_audit: Optional[str | Path] = None,
    feedback_gap_report: Optional[str | Path] = None,
    requirement_candidates: Optional[str | Path] = None,
) -> Dict[str, Any]:
    files: Dict[str, Any] = {}
    for name, path in {
        "cases": cases_path,
        "cf_report": cf_report,
        "missingness_profile": missingness_profile,
        "evidence_audit": evidence_audit,
        "feedback_gap_report": feedback_gap_report,
        "requirement_candidates": requirement_candidates,
    }.items():
        if path and Path(path).exists() and Path(path).is_file():
            files[name] = {
                "path": str(path),
                "bytes": Path(path).stat().st_size,
                "sha256": file_sha256(path),
            }

    case_count = len(read_jsonl(cases_path)) if cases_path and Path(cases_path).exists() else None
    bundle_metrics: Dict[str, Any] = {}
    if bundle_dir and Path(bundle_dir).exists():
        bundles = collect_bundle_summaries(bundle_dir)
        bundle_metrics = {
            "bundle_dir": str(bundle_dir),
            "num_bundles": len(bundles),
            "schema_valid_count": sum(1 for b in bundles.values() if b.get("schema_valid")),
            "analysis_mode_distribution": dict(Counter(b.get("analysis_mode", "unknown") for b in bundles.values())),
            "source_regime_distribution": dict(Counter(b.get("source_regime") or get_path(b, "final_case_summary.final_source_regime") or get_case_source_regime_from_bundle(b) for b in bundles.values())),
            "boundary_distribution": dict(Counter(get_path(b, "final_case_summary.final_commitment_state_fsm") for b in bundles.values())),
            "uca_distribution": dict(Counter(get_path(b, "final_case_summary.final_dominant_uca") or "no_dominant_uca" for b in bundles.values())),
            "uca_activation_distribution": dict(Counter(get_path(b, "final_case_summary.final_uca_activation_status") or "unknown" for b in bundles.values())),
            "top_pathway_status_distribution": dict(Counter(get_path(b, "final_case_summary.final_top_pathway.pathway_status") or "missing" for b in bundles.values())),
            "mean_candidate_pathways_per_case": round(statistics.mean([get_path(b, "final_case_summary.final_num_candidate_pathways") or 0 for b in bundles.values()]), 4) if bundles else 0,
        }
    baseline_metrics: Dict[str, Any] = {}
    if baseline_dir and Path(baseline_dir).exists():
        summary_path = Path(baseline_dir) / "baseline_suite_summary.json"
        if summary_path.exists():
            summary = read_json(summary_path)
            baseline_metrics["baseline_suite_summary"] = str(summary_path)
            baseline_metrics["conditions"] = list(summary.keys())

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "report_type": "paper_result_manifest",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "claim_boundary": {
            "allowed": "Auditable, evidence-bounded STPA-HF driver process-model tabletop replay and replay-package sensitivity analysis.",
            "not_allowed": [
                "reconstructing real accident causality",
                "proving real HMI causal effects",
                "inferring true driver cognition",
                "assigning legal responsibility",
            ],
        },
        "model": {
            "OPENAI_MODEL": os.environ.get("OPENAI_MODEL", "qwen-max-latest"),
            "OPENAI_BASE_URL": os.environ.get("OPENAI_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
        },
        "inputs": {
            "cases_path": str(cases_path) if cases_path else None,
            "num_cases": case_count,
        },
        "outputs": {
            "bundle_metrics": bundle_metrics,
            "baseline_metrics": baseline_metrics,
            "files": files,
        },
    }
    write_json(out_path, manifest)
    return manifest


# =============================================================================
# Evidence-support audit
# =============================================================================


def extract_safety_case_assertions(bundle: Dict[str, Any]) -> List[Dict[str, Any]]:
    assertions = []
    case_id = bundle.get("case_id")
    for e in bundle.get("event_records", []):
        idx = e.get("event_index")
        if e.get("schema_status") != "valid":
            continue
        assertions.append({"case_id": case_id, "event_index": idx, "assertion_type": "boundary", "value": e.get("commitment_state_fsm"), "supporting_evidence_ids": []})
        assertions.append({"case_id": case_id, "event_index": idx, "assertion_type": "vulnerability", "value": e.get("dominant_update_vulnerability"), "supporting_evidence_ids": []})
        assertions.append({"case_id": case_id, "event_index": idx, "assertion_type": "uca_activation_status", "value": e.get("uca_activation_status"), "supporting_evidence_ids": []})
        if e.get("dominant_uca") is not None:
            assertions.append({"case_id": case_id, "event_index": idx, "assertion_type": "dominant_uca", "value": e.get("dominant_uca"), "supporting_evidence_ids": []})
    return assertions


def audit_stage_files(case_dir: Path, alias_pattern: str, canonical_pattern: str) -> List[Path]:
    alias_files = sorted(case_dir.glob(alias_pattern))
    return alias_files if alias_files else sorted(case_dir.glob(canonical_pattern))


def classify_claim_support_row(row: Dict[str, Any]) -> str:
    """Separate unsupported positive claims from negative status and gap-only claims."""
    if int(row.get("supporting_evidence_count") or 0) > 0:
        return "supported_positive_or_status_claim"
    claim_type = str(row.get("claim_type") or "")
    value = row.get("claim_value")
    value_blob = json.dumps(value, ensure_ascii=False).lower()
    if int(row.get("gap_evidence_count") or 0) > 0:
        return "gap_claim_without_positive_support"
    if claim_type in {"uca_activation_status", "observed_update_vulnerability"} and any(
        token in value_blob for token in ["none", "no_activated_uca", "not_admissible", "suppressed"]
    ):
        return "negative_status_claim_without_supporting_evidence"
    if value in [None, "", [], {}]:
        return "negative_status_claim_without_supporting_evidence"
    return "positive_claim_without_supporting_evidence"


def summarize_claim_support_rows(claim_rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    counts = Counter(classify_claim_support_row(row) for row in claim_rows)
    positive_rows = [row for row in claim_rows if classify_claim_support_row(row) == "positive_claim_without_supporting_evidence"]
    negative_rows = [row for row in claim_rows if classify_claim_support_row(row) == "negative_status_claim_without_supporting_evidence"]
    gap_rows = [row for row in claim_rows if classify_claim_support_row(row) == "gap_claim_without_positive_support"]
    return {
        "claim_support_type_counts": dict(counts),
        "positive_claims_without_supporting_evidence_count": len(positive_rows),
        "negative_status_claims_without_supporting_evidence_count": len(negative_rows),
        "gap_claims_without_positive_support_count": len(gap_rows),
        "positive_unsupported_claim_types": sorted({str(r.get("claim_type")) for r in positive_rows}),
    }


def run_evidence_support_audit(bundle_dir: str | Path, out_dir: str | Path) -> Dict[str, Any]:
    root = Path(bundle_dir)
    reports = []
    for bpath in root.glob("*/bundle_summary.json"):
        bundle = read_json(bpath)
        case_dir = bpath.parent
        evidence_by_id: Dict[str, Dict[str, Any]] = {}
        evidence_by_field: Dict[str, Dict[str, Any]] = {}
        provenance_counts = Counter()
        for ep in case_dir.glob("e*_evidence_packet.json"):
            packet = read_json(ep)
            for item in packet.get("evidence_items", []):
                evidence_by_id[item.get("evidence_id")] = item
                evidence_by_field[item.get("field_path")] = item
                provenance_counts[item.get("provenance", "missing")] += 1
        invalid_refs = []
        cited_refs = []
        claim_rows: List[Dict[str, Any]] = []
        citation_provenance_counts = Counter()
        boundary_support_ids: List[str] = []
        outcome_only_uca_activation_count = 0
        g7_status_counts = Counter()
        safe_intervention_failure_pathway_block_count = 0
        boundary_filtered_uca_count = 0
        observed_uca_without_action_evidence_count = 0
        abductive_uca_without_chain_count = 0
        uca_without_linked_action_count = 0
        outcome_only_uca_generation_violation_count = 0
        hmi_absence_inferred_from_nonreporting_count = 0
        pathway_without_outcome_gate_count = 0
        claim_status_counts = Counter()
        abductive_strength_counts = Counter()
        same_uca_abductive_and_blocked_count = 0
        psychological_overclaim_warning_count = 0
        generic_uca_expansion_warning_count = 0
        observed_action_without_action_evidence_count = 0
        outcome_used_in_pm_flaw_warning_count = 0
        case_level_uca_conflict_count = 0
        pathway_level_uca_conflict_count = 0
        abductive_without_case_specific_gate_count = 0
        timing_uca_without_timing_gate_count = 0
        manual_control_uca_without_manual_gate_count = 0
        fallback_uca_without_fallback_gate_count = 0

        for r2ap in audit_stage_files(case_dir, "e*_round2a_update.json", "e*_update_process.json"):
            r2a = read_json(r2ap)
            try:
                idx = int(r2ap.name.split("_", 1)[0][1:]) - 1
            except Exception:
                idx = 0
            vuln_ids = []
            gap_ids = []
            vuln_values = []
            if isinstance(r2a.get("update_process_nodes"), list):
                for node in r2a.get("update_process_nodes", []):
                    observed = node.get("observed_update_vulnerability") or {}
                    gap = node.get("evidence_gap_update_risk") or {}
                    vuln = observed.get("label", node.get("update_vulnerability_type"))
                    if vuln:
                        vuln_values.append(vuln)
                    vuln_ids.extend(observed.get("supporting_evidence_ids", []) or [])
                    gap_ids.extend(gap.get("gap_evidence_ids", []) or [])
                    if not observed.get("supporting_evidence_ids") and node.get("update_vulnerability_type"):
                        vuln_ids.extend(node.get("triggering_evidence_ids", []) or [])
                    if node.get("supporting_evidence_ids"):
                        vuln_ids.extend(node.get("supporting_evidence_ids", []) or [])
            else:
                for slot in r2a.get("slot_updates", []):
                    vuln = slot.get("slot_update_vulnerability", {})
                    if isinstance(vuln, dict) and vuln.get("dominant_vulnerability"):
                        vuln_values.append(vuln.get("dominant_vulnerability"))
                    vuln_ids.extend(vuln.get("supporting_evidence_ids", []) or [])
            all_update_ids = list(dict.fromkeys(vuln_ids + gap_ids))
            for eid in all_update_ids:
                cited_refs.append(eid)
                if eid not in evidence_by_id:
                    invalid_refs.append(eid)
                else:
                    citation_provenance_counts[evidence_by_id[eid].get("provenance", "missing")] += 1
            claim_rows.append({
                "event_index": idx,
                "claim_type": "observed_update_vulnerability",
                "claim_value": sorted(set(vuln_values)) if vuln_values else None,
                "supporting_evidence_ids": sorted(set(vuln_ids)),
                "supporting_evidence_count": len(set(vuln_ids)),
                "supporting_evidence_provenance_counts": summarize_evidence_provenance_for_ids(vuln_ids, evidence_by_id),
                "gap_evidence_ids": sorted(set(gap_ids)),
                "gap_evidence_count": len(set(gap_ids)),
                "gap_evidence_provenance_counts": summarize_evidence_provenance_for_ids(gap_ids, evidence_by_id),
                "not_reported_used_as_observed_update_fact": any(evidence_by_id.get(eid, {}).get("provenance") == "not_reported" for eid in vuln_ids),
            })

        for pmp in case_dir.glob("e*_pm_variables.json"):
            pm = read_json(pmp)
            for node in pm.get("pm_context_nodes", []) or []:
                text_blob = " ".join(str(node.get(k, "")) for k in ["reported_context", "context_hypothesis", "internal_reasoning_text", "display_summary"]).lower()
                if any(pat in text_blob for pat in PSYCHOLOGICAL_OVERCLAIM_PATTERNS):
                    psychological_overclaim_warning_count += 1
                for flaw in node.get("pm_flaw_hypotheses", []) or []:
                    ids = flaw.get("supporting_evidence_ids", []) or []
                    if evidence_ids_are_outcome_only(ids, list(evidence_by_id.values())):
                        outcome_used_in_pm_flaw_warning_count += 1

        for ap in case_dir.glob("e*_candidate_actions.json"):
            actions = read_json(ap)
            for act in actions.get("action_selection_nodes", []) or []:
                if act.get("claim_status") == "observed" and evidence_ids_lack_action_evidence(act.get("supporting_evidence_ids", []) or [], list(evidence_by_id.values())):
                    observed_action_without_action_evidence_count += 1

        for r2bp in audit_stage_files(case_dir, "e*_round2b_commitment.json", "e*_commitment_boundary.json"):
            r2b = read_json(r2bp)
            try:
                idx = int(r2bp.name.split("_", 1)[0][1:]) - 1
            except Exception:
                idx = 0
            ids = r2b.get("commitment_block", {}).get("supporting_evidence_ids", []) or []
            boundary_support_ids.extend(ids)
            for eid in ids:
                cited_refs.append(eid)
                if eid not in evidence_by_id:
                    invalid_refs.append(eid)
                else:
                    citation_provenance_counts[evidence_by_id[eid].get("provenance", "missing")] += 1
            claim_rows.append({
                "event_index": idx,
                "claim_type": "boundary",
                "claim_value": infer_boundary_from_commitment(r2b),
                "supporting_evidence_ids": ids,
                "supporting_evidence_count": len(ids),
                "supporting_evidence_provenance_counts": summarize_evidence_provenance_for_ids(ids, evidence_by_id),
            })

        for r2cp in audit_stage_files(case_dir, "e*_round2c_mechanism.json", "e*_reasoning_graph.json"):
            r2c = read_json(r2cp)
            try:
                idx = int(r2cp.name.split("_", 1)[0][1:]) - 1
            except Exception:
                idx = 0
            if "supporting_evidence_ids" in r2c:
                ids = r2c.get("supporting_evidence_ids", []) or []
            else:
                ids = sorted({
                    eid
                    for node in r2c.get("nodes", []) or []
                    for eid in (node.get("supporting_evidence_ids", []) or [])
                })
            for eid in ids:
                cited_refs.append(eid)
                if eid not in evidence_by_id:
                    invalid_refs.append(eid)
                else:
                    citation_provenance_counts[evidence_by_id[eid].get("provenance", "missing")] += 1
            claim_rows.append({
                "event_index": idx,
                "claim_type": "mechanism_trace",
                "claim_value": "mechanism_paragraph",
                "supporting_evidence_ids": ids,
                "supporting_evidence_count": len(ids),
                "supporting_evidence_provenance_counts": summarize_evidence_provenance_for_ids(ids, evidence_by_id),
            })

        for r3p in audit_stage_files(case_dir, "e*_round3_uca.json", "e*_uca_context.json"):
            r3 = read_json(r3p)
            try:
                idx = int(r3p.name.split("_", 1)[0][1:]) - 1
            except Exception:
                idx = 0
            uca_ids = []
            if isinstance(r3.get("uca_context_nodes"), list):
                abductive_ids_for_case = set()
                blocked_ids_for_case = set()
                pathway_status_by_pair: Dict[Tuple[Any, Any], set[str]] = {}
                for u in r3.get("uca_context_nodes", []):
                    ids_for_u = u.get("supporting_evidence_ids", []) or []
                    if u.get("classification") == "activated" and evidence_ids_are_outcome_only(ids_for_u, list(evidence_by_id.values())):
                        outcome_only_uca_activation_count += 1
                    if u.get("claim_status"):
                        claim_status_counts[u.get("claim_status")] += 1
                    if u.get("abductive_strength"):
                        abductive_strength_counts[u.get("abductive_strength")] += 1
                    if u.get("claim_status") == "abductive_candidate":
                        abductive_ids_for_case.add(u.get("uca_id"))
                    if u.get("claim_status") == "blocked":
                        blocked_ids_for_case.add(u.get("uca_id"))
                    linked_action_id = u.get("linked_action_id") or ((u.get("action_selection_node_ids") or [None])[0])
                    if u.get("uca_id") and linked_action_id:
                        pathway_status_by_pair.setdefault((u.get("uca_id"), linked_action_id), set()).add(u.get("claim_status"))
                    gate_result = u.get("gate_result") or {}
                    if u.get("generated_by") in {"expand_forward_uca_candidates_v241", "expand_forward_uca_candidates_v242", "llm_uca_context_normalized_by_v242_gate"}:
                        if not gate_result or not gate_result.get("case_evidence_features") or not gate_result.get("passed_conditions"):
                            generic_uca_expansion_warning_count += 1
                        if u.get("claim_status") == "abductive_candidate" and not gate_result.get("passed"):
                            abductive_without_case_specific_gate_count += 1
                        if u.get("claim_status") == "abductive_candidate" and u.get("uca_id") == "UCA-H-3" and "timing_context_present" not in (gate_result.get("passed_conditions") or []):
                            timing_uca_without_timing_gate_count += 1
                        if u.get("claim_status") == "abductive_candidate" and u.get("uca_id") == "UCA-H-5" and "manual_control_evidence_or_gap" not in (gate_result.get("passed_conditions") or []):
                            manual_control_uca_without_manual_gate_count += 1
                        if u.get("claim_status") == "abductive_candidate" and u.get("uca_id") == "UCA-H-6" and "fallback_context_present" not in (gate_result.get("passed_conditions") or []):
                            fallback_uca_without_fallback_gate_count += 1
                    if not (u.get("action_selection_node_ids") or u.get("linked_action_id")):
                        uca_without_linked_action_count += 1
                    fd = u.get("forward_derivation") or {}
                    if u.get("claim_status") == "observed_admissible" and evidence_ids_lack_action_evidence(ids_for_u, list(evidence_by_id.values())):
                        observed_uca_without_action_evidence_count += 1
                    if u.get("claim_status") == "abductive_candidate" and not (
                        fd.get("pm_flaw_inputs") and fd.get("update_flaw_inputs") and fd.get("action_selection_inputs")
                    ):
                        abductive_uca_without_chain_count += 1
                    if evidence_ids_are_outcome_only(ids_for_u, list(evidence_by_id.values())):
                        outcome_only_uca_generation_violation_count += 1
                    text_blob = " ".join(str(u.get(k, "")) for k in ["internal_reasoning_text", "display_summary", "unsafe_context_text"]).lower()
                    if "hmi was absent" in text_blob or "no hmi was present" in text_blob:
                        hmi_absence_inferred_from_nonreporting_count += 1
                    for eid in u.get("supporting_evidence_ids", []):
                        cited_refs.append(eid)
                        uca_ids.append(eid)
                        if eid not in evidence_by_id:
                            invalid_refs.append(eid)
                        else:
                            citation_provenance_counts[evidence_by_id[eid].get("provenance", "missing")] += 1
                case_level_overlap = len(set(r3.get("abductive_uca_candidates") or []) & set(r3.get("blocked_uca_set") or []))
                same_uca_abductive_and_blocked_count += case_level_overlap
                case_level_uca_conflict_count += case_level_overlap
                pathway_level_uca_conflict_count += sum(1 for statuses in pathway_status_by_pair.values() if "abductive_candidate" in statuses and "blocked" in statuses)
            else:
                for u in r3.get("activated_ucas", []) + r3.get("suppressed_ucas", []):
                    for eid in u.get("supporting_evidence_ids", []):
                        cited_refs.append(eid)
                        uca_ids.append(eid)
                        if eid not in evidence_by_id:
                            invalid_refs.append(eid)
                        else:
                            citation_provenance_counts[evidence_by_id[eid].get("provenance", "missing")] += 1
            activation_status = r3.get("uca_activation_status")
            claim_rows.append({
                "event_index": idx,
                "claim_type": "uca_activation_status" if activation_status == "no_activated_uca" else "dominant_uca",
                "claim_value": activation_status if activation_status == "no_activated_uca" else r3.get("dominant_uca"),
                "supporting_evidence_ids": sorted(set(uca_ids)),
                "supporting_evidence_count": len(set(uca_ids)),
                "supporting_evidence_provenance_counts": summarize_evidence_provenance_for_ids(uca_ids, evidence_by_id),
            })
        catalog_ok = True
        for r3p in audit_stage_files(case_dir, "e*_round3_uca.json", "e*_uca_context.json"):
            r3 = read_json(r3p)
            ucas = r3.get("uca_context_nodes", []) if isinstance(r3.get("uca_context_nodes"), list) else r3.get("activated_ucas", []) + r3.get("suppressed_ucas", [])
            ids = [u.get("uca_id") for u in ucas]
            if r3.get("dominant_uca") is not None:
                ids.append(r3.get("dominant_uca"))
            if any(x not in DRIVER_UCA_ID_SET for x in ids if x):
                catalog_ok = False
            if any(x in LEGACY_UCA_ID_SET for x in ids if x):
                boundary_filtered_uca_count += 1

        for pp in case_dir.glob("e*_ranked_pathways.json"):
            ranked = read_json(pp)
            for pathway in ranked.get("ranked_pathways", []) or []:
                g7 = (pathway.get("stpa_hf_compliance_gates") or {}).get("G7_outcome_compatibility_gate") or {}
                if g7.get("status"):
                    g7_status_counts[g7.get("status")] += 1
                if not pathway.get("outcome_compatibility") and not pathway.get("outcome_compatibility_block"):
                    pathway_without_outcome_gate_count += 1
                if "safe_intervention_contradicts_failure_pathway" in (pathway.get("blocking_reasons") or []):
                    safe_intervention_failure_pathway_block_count += 1
        final_boundary = get_path(bundle, "final_case_summary.final_commitment_state_fsm")
        strength_audit = classify_boundary_evidence_strength(final_boundary, evidence_by_field, boundary_support_ids, evidence_by_id)
        unsupported_strong_boundary_warning = bool(
            strength_audit["outcome_only_escalation_warning"]
            or strength_audit["not_reported_boundary_support_warning"]
        )
        claim_support_summary = summarize_claim_support_rows(claim_rows)
        reports.append({
            "case_id": bundle.get("case_id"),
            "source_regime": get_case_source_regime_from_bundle(bundle),
            "final_boundary": final_boundary,
            "schema_valid": bundle.get("schema_valid"),
            "evidence_id_count": len(evidence_by_id),
            "reported_field_count": provenance_counts.get("reported", 0),
            "derived_field_count": provenance_counts.get("derived", 0),
            "not_reported_field_count": provenance_counts.get("not_reported", 0),
            "counterfactual_assumption_count": provenance_counts.get("assumed_for_counterfactual", 0),
            "cited_evidence_count": len(cited_refs),
            "unique_cited_evidence_count": len(set(cited_refs)),
            "citation_provenance_counts": dict(citation_provenance_counts),
            "invalid_evidence_id_count": len(invalid_refs),
            "invalid_evidence_ids": sorted(set(invalid_refs)),
            "uca_catalog_consistency": catalog_ok,
            "claim_coverage": claim_rows,
            "claims_without_supporting_evidence_count": sum(1 for r in claim_rows if r["supporting_evidence_count"] == 0),
            **claim_support_summary,
            "not_reported_used_as_observed_update_fact_count": sum(1 for r in claim_rows if r.get("not_reported_used_as_observed_update_fact")),
            "outcome_only_uca_activation_count": outcome_only_uca_activation_count,
            "uca_catalog_boundary_filtering_count": boundary_filtered_uca_count,
            "safe_intervention_failure_pathway_block_count": safe_intervention_failure_pathway_block_count,
            "observed_uca_without_action_evidence_count": observed_uca_without_action_evidence_count,
            "abductive_uca_without_chain_count": abductive_uca_without_chain_count,
            "uca_without_linked_action_count": uca_without_linked_action_count,
            "outcome_only_uca_generation_violation_count": outcome_only_uca_generation_violation_count,
            "hmi_absence_inferred_from_nonreporting_count": hmi_absence_inferred_from_nonreporting_count,
            "pathway_without_outcome_gate_count": pathway_without_outcome_gate_count,
            "uca_claim_status_counts": dict(claim_status_counts),
            "abductive_strength_counts": dict(abductive_strength_counts),
            "same_uca_abductive_and_blocked_count": same_uca_abductive_and_blocked_count,
            "psychological_overclaim_warning_count": psychological_overclaim_warning_count,
            "generic_uca_expansion_warning_count": generic_uca_expansion_warning_count,
            "observed_action_without_action_evidence_count": observed_action_without_action_evidence_count,
            "outcome_used_in_pm_flaw_warning_count": outcome_used_in_pm_flaw_warning_count,
            "case_level_uca_conflict_count": case_level_uca_conflict_count,
            "pathway_level_uca_conflict_count": pathway_level_uca_conflict_count,
            "abductive_without_case_specific_gate_count": abductive_without_case_specific_gate_count,
            "timing_uca_without_timing_gate_count": timing_uca_without_timing_gate_count,
            "manual_control_uca_without_manual_gate_count": manual_control_uca_without_manual_gate_count,
            "fallback_uca_without_fallback_gate_count": fallback_uca_without_fallback_gate_count,
            "G7_outcome_gate_distribution": dict(g7_status_counts),
            "pathway_status_counts": get_path(bundle, "final_case_summary.final_pathway_status_counts") or {},
            "num_candidate_pathways": get_path(bundle, "final_case_summary.final_num_candidate_pathways") or 0,
            "unsupported_strong_boundary_warning": unsupported_strong_boundary_warning,
            **strength_audit,
        })
    summary = {
        "num_cases": len(reports),
        "mean_invalid_evidence_id_count": round(statistics.mean([r["invalid_evidence_id_count"] for r in reports]), 4) if reports else 0,
        "catalog_consistency_rate": round(sum(1 for r in reports if r["uca_catalog_consistency"]) / len(reports), 4) if reports else None,
        "mean_claims_without_supporting_evidence_count": round(statistics.mean([r["claims_without_supporting_evidence_count"] for r in reports]), 4) if reports else 0,
        "mean_positive_claims_without_supporting_evidence_count": round(statistics.mean([r["positive_claims_without_supporting_evidence_count"] for r in reports]), 4) if reports else 0,
        "mean_negative_status_claims_without_supporting_evidence_count": round(statistics.mean([r["negative_status_claims_without_supporting_evidence_count"] for r in reports]), 4) if reports else 0,
        "mean_gap_claims_without_positive_support_count": round(statistics.mean([r["gap_claims_without_positive_support_count"] for r in reports]), 4) if reports else 0,
        "positive_unsupported_claim_warning_case_ids": [r["case_id"] for r in reports if r.get("positive_claims_without_supporting_evidence_count", 0) > 0],
        "claim_support_type_distribution": dict(Counter(kind for r in reports for kind, count in (r.get("claim_support_type_counts") or {}).items() for _ in range(count))),
        "not_reported_used_as_observed_update_fact_count": sum(r.get("not_reported_used_as_observed_update_fact_count", 0) for r in reports),
        "outcome_only_uca_activation_count": sum(r.get("outcome_only_uca_activation_count", 0) for r in reports),
        "uca_catalog_boundary_filtering_count": sum(r.get("uca_catalog_boundary_filtering_count", 0) for r in reports),
        "safe_intervention_failure_pathway_block_count": sum(r.get("safe_intervention_failure_pathway_block_count", 0) for r in reports),
        "observed_uca_without_action_evidence_count": sum(r.get("observed_uca_without_action_evidence_count", 0) for r in reports),
        "abductive_uca_without_chain_count": sum(r.get("abductive_uca_without_chain_count", 0) for r in reports),
        "uca_without_linked_action_count": sum(r.get("uca_without_linked_action_count", 0) for r in reports),
        "outcome_only_uca_generation_violation_count": sum(r.get("outcome_only_uca_generation_violation_count", 0) for r in reports),
        "hmi_absence_inferred_from_nonreporting_count": sum(r.get("hmi_absence_inferred_from_nonreporting_count", 0) for r in reports),
        "pathway_without_outcome_gate_count": sum(r.get("pathway_without_outcome_gate_count", 0) for r in reports),
        "same_uca_abductive_and_blocked_count": sum(r.get("same_uca_abductive_and_blocked_count", 0) for r in reports),
        "psychological_overclaim_warning_count": sum(r.get("psychological_overclaim_warning_count", 0) for r in reports),
        "generic_uca_expansion_warning_count": sum(r.get("generic_uca_expansion_warning_count", 0) for r in reports),
        "observed_action_without_action_evidence_count": sum(r.get("observed_action_without_action_evidence_count", 0) for r in reports),
        "outcome_used_in_pm_flaw_warning_count": sum(r.get("outcome_used_in_pm_flaw_warning_count", 0) for r in reports),
        "case_level_uca_conflict_count": sum(r.get("case_level_uca_conflict_count", 0) for r in reports),
        "pathway_level_uca_conflict_count": sum(r.get("pathway_level_uca_conflict_count", 0) for r in reports),
        "abductive_without_case_specific_gate_count": sum(r.get("abductive_without_case_specific_gate_count", 0) for r in reports),
        "timing_uca_without_timing_gate_count": sum(r.get("timing_uca_without_timing_gate_count", 0) for r in reports),
        "manual_control_uca_without_manual_gate_count": sum(r.get("manual_control_uca_without_manual_gate_count", 0) for r in reports),
        "fallback_uca_without_fallback_gate_count": sum(r.get("fallback_uca_without_fallback_gate_count", 0) for r in reports),
        "mean_candidate_pathways_per_case": round(statistics.mean([r.get("num_candidate_pathways", 0) for r in reports]), 4) if reports else 0,
        "all_pathway_status_distribution": dict(Counter(status for r in reports for status, count in (r.get("pathway_status_counts") or {}).items() for _ in range(count))),
        "uca_claim_status_distribution": dict(Counter(status for r in reports for status, count in (r.get("uca_claim_status_counts") or {}).items() for _ in range(count))),
        "abductive_strength_distribution": dict(Counter(status for r in reports for status, count in (r.get("abductive_strength_counts") or {}).items() for _ in range(count))),
        "G7_outcome_gate_distribution": dict(Counter(status for r in reports for status, count in (r.get("G7_outcome_gate_distribution") or {}).items() for _ in range(count))),
        "unsupported_strong_boundary_warning_count": sum(1 for r in reports if r["unsupported_strong_boundary_warning"]),
        "outcome_only_escalation_warning_count": sum(1 for r in reports if r.get("outcome_only_escalation_warning")),
        "not_reported_boundary_support_warning_count": sum(1 for r in reports if r.get("not_reported_boundary_support_warning")),
        "strong_boundary_evidence_strength_counts": dict(Counter(r.get("strong_boundary_evidence_strength") for r in reports)),
        "warning_case_ids": [r["case_id"] for r in reports if r["unsupported_strong_boundary_warning"]],
            "case_reports": reports,
        }
    ensure_dir(Path(out_dir))
    write_json(Path(out_dir) / "evidence_support_audit.json", summary)
    return summary


SEMANTIC_WARNING_CLASSES = {
    "true_generic_expansion",
    "properly_gated_blocked_hypothesis",
    "under_supported_abductive_candidate",
    "overreaching_positive_claim",
    "needs_human_review",
}
SEMANTIC_WARNING_TREATMENTS = {
    "keep_as_ranked_pathway",
    "keep_as_blocked_claim_only",
    "remove_from_candidate_space",
    "send_to_human_review",
}
SEMANTIC_WARNING_SEVERITIES = {"none", "low", "medium", "high"}
EXPANDED_UCA_GENERATORS = {
    "expand_forward_uca_candidates_v241",
    "expand_forward_uca_candidates_v242",
    "llm_uca_context_normalized_by_v242_gate",
}


def _is_structural_generic_uca_warning_node(node: Dict[str, Any]) -> bool:
    gate_result = node.get("gate_result") or {}
    return (
        node.get("generated_by") in EXPANDED_UCA_GENERATORS
        and (not gate_result or not gate_result.get("case_evidence_features") or not gate_result.get("passed_conditions"))
    )


def validate_semantic_warning_adjudication(obj: Dict[str, Any]) -> None:
    required = ["case_id", "pathway_id", "uca_id", "linked_action_id", "semantic_warning_class", "is_true_warning", "severity", "semantic_verdict", "evidence_assessment", "supporting_evidence_ids", "missing_evidence_ids", "source_spans", "recommended_treatment", "reasoning"]
    for key in required:
        if key not in obj:
            raise SchemaValidationError(f"semantic warning adjudication missing {key}")
    if obj.get("semantic_warning_class") not in SEMANTIC_WARNING_CLASSES:
        raise SchemaValidationError("invalid semantic_warning_class")
    if not isinstance(obj.get("is_true_warning"), bool):
        raise SchemaValidationError("is_true_warning must be bool")
    if obj.get("severity") not in SEMANTIC_WARNING_SEVERITIES:
        raise SchemaValidationError("invalid severity")
    if obj.get("recommended_treatment") not in SEMANTIC_WARNING_TREATMENTS:
        raise SchemaValidationError("invalid recommended_treatment")
    assess = obj.get("evidence_assessment")
    if not isinstance(assess, dict):
        raise SchemaValidationError("evidence_assessment must be object")
    for key in ["has_case_specific_evidence", "has_pm_update_action_chain", "uses_outcome_as_activation_evidence", "uses_not_reported_as_positive_fact", "has_valid_blocking_reason"]:
        if not isinstance(assess.get(key), bool):
            raise SchemaValidationError(f"evidence_assessment.{key} must be bool")
    for key in ["supporting_evidence_ids", "missing_evidence_ids", "source_spans"]:
        if not isinstance(obj.get(key), list):
            raise SchemaValidationError(f"{key} must be list")
    if obj.get("semantic_warning_class") in {"true_generic_expansion", "overreaching_positive_claim"} and obj.get("severity") == "none":
        raise SchemaValidationError("true warning classes cannot have severity=none")


def _load_case_stage_json(case_dir: Path, filename: str, default: Any = None) -> Any:
    path = case_dir / filename
    if not path.exists():
        return default
    return read_json(path)


def collect_structural_warning_candidates(bundle_dir: str | Path) -> List[Dict[str, Any]]:
    root = Path(bundle_dir)
    candidates: List[Dict[str, Any]] = []
    for bpath in sorted(root.glob("*/bundle_summary.json")):
        case_dir = bpath.parent
        bundle = read_json(bpath)
        evidence_packet = _load_case_stage_json(case_dir, "e1_evidence_packet.json", {}) or {}
        pm_context = _load_case_stage_json(case_dir, "e1_pm_context.json", {}) or {}
        update_process = _load_case_stage_json(case_dir, "e1_update_process.json", None)
        if update_process is None:
            update_process = _load_case_stage_json(case_dir, "e1_round2a_update.json", {}) or {}
        action_selection = _load_case_stage_json(case_dir, "e1_action_selection.json", None)
        if action_selection is None:
            action_selection = _load_case_stage_json(case_dir, "e1_candidate_actions.json", {}) or {}
        r3 = _load_case_stage_json(case_dir, "e1_round3_uca.json", None)
        if r3 is None:
            r3 = _load_case_stage_json(case_dir, "e1_uca_context.json", {}) or {}
        actions = action_selection.get("action_selection_nodes", []) if isinstance(action_selection, dict) else []
        action_by_id = {a.get("node_id"): a for a in actions if isinstance(a, dict)}
        for node in r3.get("uca_context_nodes", []) or []:
            if not _is_structural_generic_uca_warning_node(node):
                continue
            linked_action_id = node.get("linked_action_id") or ((node.get("action_selection_node_ids") or [None])[0])
            gate_result = node.get("gate_result") or {}
            structural_reasons = []
            if not gate_result:
                structural_reasons.append("missing_gate_result")
            if gate_result and not gate_result.get("case_evidence_features"):
                structural_reasons.append("missing_case_evidence_features")
            if gate_result and not gate_result.get("passed_conditions"):
                structural_reasons.append("empty_passed_conditions")
            candidates.append({
                "case_id": bundle.get("case_id"),
                "source_regime": get_case_source_regime_from_bundle(bundle),
                "case_dir": str(case_dir),
                "raw_narrative": get_path(bundle, "source_metadata.raw_case_summary", ""),
                "structural_warning": {
                    "warning_type": "generic_uca_expansion_warning",
                    "reason_triggered": structural_reasons,
                },
                "evidence_items": evidence_packet.get("evidence_items", []),
                "pm_context_nodes": pm_context.get("pm_context_nodes", []),
                "update_process_nodes": update_process.get("update_process_nodes", update_process.get("slot_updates", [])),
                "candidate_action": action_by_id.get(linked_action_id, {}),
                "uca_pathway": node,
                "gate_result": gate_result,
                "blocked_reasons": node.get("blocking_reasons", []) or node.get("blocked_claims", []),
                "reported_outcome": {
                    "event_type": get_path(bundle, "final_case_summary.reported_outcome.event_type", None) or get_path(bundle, "event_records.0.reported_outcome.event_type", None) or get_path(bundle, "latent_events.0.CAR.event_type.value", None),
                    "final_boundary": get_path(bundle, "final_case_summary.final_driver_replay_posture_fsm", None) or get_path(bundle, "final_case_summary.final_commitment_state_fsm", None),
                },
                "pathway_id": node.get("pathway_id") or f"{node.get('uca_id')}-{linked_action_id}",
            })
    return candidates


def semantic_warning_adjudicate_candidate(client: LLMClient, candidate: Dict[str, Any], temperature: float = 0.0) -> Dict[str, Any]:
    payload = {
        "case_id": candidate.get("case_id"),
        "source_regime": candidate.get("source_regime"),
        "raw_narrative": candidate.get("raw_narrative"),
        "structural_warning": candidate.get("structural_warning"),
        "evidence_items": candidate.get("evidence_items"),
        "pm_context_nodes": candidate.get("pm_context_nodes"),
        "update_process_nodes": candidate.get("update_process_nodes"),
        "candidate_action": candidate.get("candidate_action"),
        "uca_pathway": candidate.get("uca_pathway"),
        "gate_result": candidate.get("gate_result"),
        "blocked_reasons": candidate.get("blocked_reasons"),
        "reported_outcome": candidate.get("reported_outcome"),
        "task": "Classify whether this warning is a true semantic problem or a properly bounded blocked/adductive hypothesis.",
    }
    obj = client.chat_json_strict(
        make_messages(SEMANTIC_WARNING_AUDIT_PROMPT, payload),
        ["case_id", "pathway_id", "uca_id", "linked_action_id", "semantic_warning_class", "is_true_warning", "severity", "semantic_verdict", "evidence_assessment", "supporting_evidence_ids", "missing_evidence_ids", "source_spans", "recommended_treatment", "reasoning"],
        validator=validate_semantic_warning_adjudication,
        temperature=temperature,
    )
    return {**obj, "structural_warning": candidate.get("structural_warning"), "source_regime": candidate.get("source_regime")}


def run_semantic_warning_audit(
    client: LLMClient,
    bundle_dir: str | Path,
    out_dir: str | Path,
    evidence_audit_path: Optional[str | Path] = None,
    temperature: float = 0.0,
) -> Dict[str, Any]:
    candidates = collect_structural_warning_candidates(bundle_dir)
    adjudications = []
    for candidate in candidates:
        adjudications.append(semantic_warning_adjudicate_candidate(client, candidate, temperature=temperature))
    class_counts = Counter(a.get("semantic_warning_class") for a in adjudications)
    treatment_counts = Counter(a.get("recommended_treatment") for a in adjudications)
    severity_counts = Counter(a.get("severity") for a in adjudications)
    summary = {
        "schema_version": SCHEMA_VERSION,
        "report_type": "semantic_warning_audit",
        "claim_boundary": "Semantic warning adjudication classifies structurally suspicious pathways; it does not prove true driver psychology, true accident cause, HMI presence, or responsibility.",
        "source": {
            "bundle_dir": str(bundle_dir),
            "evidence_audit": str(evidence_audit_path) if evidence_audit_path else None,
        },
        "num_structural_warning_candidates": len(candidates),
        "num_semantically_adjudicated": len(adjudications),
        "true_semantic_warning_count": sum(1 for a in adjudications if a.get("is_true_warning")),
        "semantic_warning_class_counts": dict(class_counts),
        "recommended_treatment_counts": dict(treatment_counts),
        "severity_counts": dict(severity_counts),
        "case_rows": [
            {
                "case_id": a.get("case_id"),
                "pathway_id": a.get("pathway_id"),
                "uca_id": a.get("uca_id"),
                "linked_action_id": a.get("linked_action_id"),
                "semantic_warning_class": a.get("semantic_warning_class"),
                "is_true_warning": a.get("is_true_warning"),
                "severity": a.get("severity"),
                "recommended_treatment": a.get("recommended_treatment"),
            }
            for a in adjudications
        ],
        "adjudications": adjudications,
    }
    ensure_dir(Path(out_dir))
    write_json(Path(out_dir) / "structural_warning_candidates.json", {"candidates": candidates})
    write_json(Path(out_dir) / "semantic_warning_audit.json", summary)
    return summary


# =============================================================================
# Dataset missingness profile (paper Table 1)
# =============================================================================


ENRICH_PROMPT = """\
You are a data enrichment assistant for automated-driving safety analysis.

Given a functional scenario case and the original incident narrative, your task is to fill in missing (not_reported) fields in the ENV, ACTOR, and CAR groups ONLY.

Rules:
- NEVER fill HMI or CABIN fields. Leave them exactly as they are.
- Only fill a field if the narrative provides clear evidence. If uncertain, leave as not_reported.
- For each field you fill, provide the exact text from the narrative that supports your inference.
- Return valid JSON only, no markdown.

Return exactly this structure:
{
  "enriched_fields": [
    {"field_path": "ENV.field_name", "value": "...", "derivation_basis": "narrative excerpt: ..."},
    ...
  ]
}
If no fields can be enriched, return: {"enriched_fields": []}
"""


def enrich_cases_from_narrative(client: "LLMClient", cases_path: str | Path, out_path: str | Path) -> Dict[str, Any]:
    cases = read_jsonl(cases_path)
    enriched_count = 0
    field_fill_count = 0
    out_cases = []
    for case in cases:
        event = case.get("latent_events", [{}])[0]
        narrative = case.get("source_metadata", {}).get("raw_case_summary", "")
        if not narrative or len(narrative) < 20:
            out_cases.append(case)
            continue
        nr_fields = []
        for group_name in ["ENV", "ACTOR", "CAR"]:
            group = event.get(group_name, {})
            for k, v in group.items():
                if isinstance(v, dict) and v.get("provenance") == "not_reported":
                    nr_fields.append(f"{group_name}.{k}")
        if not nr_fields:
            out_cases.append(case)
            continue
        payload = {
            "case_id": case.get("case_id"),
            "not_reported_fields": nr_fields,
            "narrative": narrative[:2000],
        }
        try:
            result = client.chat_json_strict(
                make_messages(ENRICH_PROMPT, payload),
                ["enriched_fields"],
                temperature=0.0,
                retries=1,
            )
            for ef in result.get("enriched_fields", []):
                fp = ef.get("field_path", "")
                val = ef.get("value")
                basis = ef.get("derivation_basis", "")
                if not fp or not val or fp not in nr_fields:
                    continue
                parts = fp.split(".", 1)
                if len(parts) != 2:
                    continue
                group_name, field_name = parts
                if group_name in ("HMI", "CABIN"):
                    continue
                group = event.get(group_name, {})
                if field_name in group:
                    group[field_name] = {
                        "value": val,
                        "provenance": "derived",
                        "visibility": "source_reported",
                        "certainty": "medium",
                        "source_text": "",
                        "derivation_basis": f"LLM narrative enrichment: {basis[:200]}",
                        "is_driver_visible": "unknown",
                        "use_as_negative_evidence": False,
                        "timestamp_ms": None,
                        "persistence_ms": None,
                    }
                    field_fill_count += 1
            enriched_count += 1
        except Exception:
            pass
        out_cases.append(case)
    write_jsonl(out_path, out_cases)
    return {"num_cases": len(out_cases), "enriched_cases": enriched_count, "fields_filled": field_fill_count, "out": str(out_path)}


def export_dataset_missingness_profile(cases_path: str | Path, out_dir: str | Path) -> Dict[str, Any]:
    """Compute per-field and per-case provenance distribution for the external dataset.

    Output maps directly to the paper's dataset & missingness profile table.
    """
    cases = load_external_cases(cases_path)
    field_stats: Dict[str, Counter] = defaultdict(Counter)
    case_rows = []
    source_counter: Counter = Counter()

    for case in cases:
        case_id = case.get("case_id", "unknown")
        source = case.get("case_source", "unknown")
        source_counter[source] += 1
        case_reported = 0
        case_derived = 0
        case_not_reported = 0
        case_counterfactual = 0

        for event in case.get("latent_events", []):
            evidence_items = build_evidence_items(event, event_index=0)
            for item in evidence_items:
                prov = item.get("provenance", "unknown")
                field_key = item.get("field_path", item.get("field", "unknown"))
                field_stats[field_key][prov] += 1
                if prov == "reported":
                    case_reported += 1
                elif prov == "derived":
                    case_derived += 1
                elif prov == "not_reported":
                    case_not_reported += 1
                elif prov == "assumed_for_counterfactual":
                    case_counterfactual += 1

        total = case_reported + case_derived + case_not_reported + case_counterfactual
        case_rows.append({
            "case_id": case_id,
            "source": source,
            "reported": case_reported,
            "derived": case_derived,
            "not_reported": case_not_reported,
            "counterfactual": case_counterfactual,
            "total_fields": total,
            "missingness_rate": round(case_not_reported / total, 4) if total else 0.0,
        })

    field_summary = []
    for field_key in sorted(field_stats.keys()):
        counts = field_stats[field_key]
        total = sum(counts.values())
        field_summary.append({
            "field": field_key,
            "reported": counts.get("reported", 0),
            "derived": counts.get("derived", 0),
            "not_reported": counts.get("not_reported", 0),
            "counterfactual": counts.get("assumed_for_counterfactual", 0),
            "total": total,
            "not_reported_rate": round(counts.get("not_reported", 0) / total, 4) if total else 0.0,
        })

    agg_missingness = [r["missingness_rate"] for r in case_rows]
    profile = {
        "num_cases": len(cases),
        "source_distribution": dict(source_counter),
        "aggregate_missingness": {
            "mean": round(statistics.mean(agg_missingness), 4) if agg_missingness else 0.0,
            "median": round(statistics.median(agg_missingness), 4) if agg_missingness else 0.0,
            "min": round(min(agg_missingness), 4) if agg_missingness else 0.0,
            "max": round(max(agg_missingness), 4) if agg_missingness else 0.0,
        },
        "field_level_profile": field_summary,
        "case_level_profile": case_rows,
    }
    ensure_dir(Path(out_dir))
    write_json(Path(out_dir) / "dataset_missingness_profile.json", profile)
    return profile


def _case_sort_key(case: Dict[str, Any]) -> Tuple[str, str]:
    event = (case.get("latent_events") or [{}])[0]
    actor = str(unwrap_value(get_path(event, "ACTOR.primary_type", "")) or "")
    road = str(unwrap_value(get_path(event, "ENV.road_geometry", "")) or "")
    cid = str(case.get("case_id") or stable_digest(case))
    return (actor + "|" + road, cid)


def select_diverse_cases(rows: Iterable[Dict[str, Any]], n: int, source_regime: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    selected: List[Dict[str, Any]] = []
    seen_case_ids = set()
    seen_actor_road = set()
    candidates = sorted(rows, key=_case_sort_key)
    for case in candidates:
        cid = case.get("case_id")
        if not cid or cid in seen_case_ids:
            continue
        event = (case.get("latent_events") or [{}])[0]
        key = (
            normalize_token(unwrap_value(get_path(event, "ACTOR.primary_type", ""))),
            normalize_token(unwrap_value(get_path(event, "ENV.road_geometry", ""))),
        )
        if key in seen_actor_road:
            continue
        selected.append(case)
        seen_case_ids.add(cid)
        seen_actor_road.add(key)
        if len(selected) >= n:
            break
    for case in candidates:
        if len(selected) >= n:
            break
        cid = case.get("case_id")
        if cid and cid not in seen_case_ids:
            selected.append(case)
            seen_case_ids.add(cid)
    summary = {
        "source_regime": source_regime,
        "requested": n,
        "selected": len(selected),
        "actor_counts": dict(Counter(str(unwrap_value(get_path((c.get("latent_events") or [{}])[0], "ACTOR.primary_type", "unknown"))) for c in selected)),
        "road_geometry_counts": dict(Counter(str(unwrap_value(get_path((c.get("latent_events") or [{}])[0], "ENV.road_geometry", "unknown"))) for c in selected)),
    }
    return selected, summary


def build_paper_50_sample(
    *,
    nhtsa_cases: str | Path,
    ca_collision_cases: str | Path,
    ca_disengagement_cases: str | Path,
    out_cases: str | Path,
    out_summary: str | Path,
    n_nhtsa: int = 20,
    n_collision: int = 15,
    n_disengagement: int = 15,
) -> Dict[str, Any]:
    nhtsa_rows = [c for c in iter_jsonl(nhtsa_cases) if get_case_source_regime_from_case(c) == "official_nhtsa_crash_csv"]
    collision_rows = [c for c in iter_jsonl(ca_collision_cases) if get_case_source_regime_from_case(c) == "third_party_ca_dmv_collision_augmented_csv"]
    disengagement_rows: List[Dict[str, Any]] = []
    for c in iter_jsonl(ca_disengagement_cases):
        if get_case_source_regime_from_case(c) != "official_ca_dmv_disengagement_csv":
            continue
        event = (c.get("latent_events") or [{}])[0]
        evidence_by_field = {i["field_path"]: i for i in build_evidence_items(event)}
        if field_is_reported(evidence_by_field, "CAR.reported_intervention"):
            disengagement_rows.append(c)
        if len(disengagement_rows) >= max(n_disengagement * 8, n_disengagement):
            break

    nhtsa_sel, nhtsa_summary = select_diverse_cases(nhtsa_rows, n_nhtsa, "official_nhtsa_crash_csv")
    collision_sel, collision_summary = select_diverse_cases(collision_rows, n_collision, "third_party_ca_dmv_collision_augmented_csv")
    disengage_sel, disengage_summary = select_diverse_cases(disengagement_rows, n_disengagement, "official_ca_dmv_disengagement_csv")
    selected = nhtsa_sel + collision_sel + disengage_sel
    for case in selected:
        validate_case_no_label_leakage(case)
    write_jsonl(out_cases, selected)
    summary = {
        "schema_version": SCHEMA_VERSION,
        "report_type": "paper_50_sample_summary",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "output_cases": str(out_cases),
        "num_cases": len(selected),
        "requested_composition": {
            "official_nhtsa_crash_csv": n_nhtsa,
            "third_party_ca_dmv_collision_augmented_csv": n_collision,
            "official_ca_dmv_disengagement_csv": n_disengagement,
        },
        "actual_composition": dict(Counter(get_case_source_regime_from_case(c) for c in selected)),
        "source_summaries": [nhtsa_summary, collision_summary, disengage_summary],
        "input_files": {
            "nhtsa_cases": str(nhtsa_cases),
            "ca_collision_cases": str(ca_collision_cases),
            "ca_disengagement_cases": str(ca_disengagement_cases),
        },
        "case_file_sha256": file_sha256(out_cases),
    }
    write_json(out_summary, summary)
    return summary


def _reported_value(evidence_by_field: Dict[str, Dict[str, Any]], field_path: str) -> str:
    item = evidence_by_field.get(field_path, {})
    if item.get("provenance") == "not_reported":
        return ""
    return evidence_value_text(item)


def expert0_label_case(case: Dict[str, Any]) -> Dict[str, Any]:
    event = (case.get("latent_events") or [{}])[0]
    items = build_evidence_items(event, event_index=0)
    evidence_by_field = {i["field_path"]: i for i in items}
    source_regime = get_case_source_regime_from_case(case)
    event_type = _reported_value(evidence_by_field, "CAR.event_type")
    intervention = _reported_value(evidence_by_field, "CAR.reported_intervention")
    system_issue = _reported_value(evidence_by_field, "CAR.reported_system_issue")
    hmi_mode = _reported_value(evidence_by_field, "HMI.mode_state_display")
    hmi_boundary = _reported_value(evidence_by_field, "HMI.capability_boundary_hint")
    time_budget = _reported_value(evidence_by_field, "HMI.time_budget_indicator") or _reported_value(evidence_by_field, "CAR.time_budget_to_handover")
    support_cues = [hmi_mode, hmi_boundary, time_budget]

    explicit_transfer = bool(
        "disengagement" in event_type
        or intervention
        or any(k in " ".join(support_cues) for k in ["takeover", "handover", "boundary_exceeded", "limited_time", "withdraw"])
    )
    explicit_support = bool(
        hmi_mode in {"engaged", "automation_engaged"}
        and any(k in hmi_boundary for k in ["within", "support", "capability"])
        and not explicit_transfer
    )
    if explicit_transfer:
        boundary = "not_supported_transfer"
        dominant_uca = "UCA-H-2"
        active_uca_set = ["UCA-H-2"]
    elif explicit_support and source_regime != "official_ca_dmv_disengagement_csv":
        boundary = "supported_monitoring"
        dominant_uca = "UCA-H-6"
        active_uca_set = ["UCA-H-6"]
    else:
        boundary = "contingent_readiness"
        if system_issue or "uncertain" in hmi_boundary:
            dominant_uca = "UCA-H-2"
        elif any(k in _reported_value(evidence_by_field, "ACTOR.primary_intent") for k in ["cut", "cross", "unknown"]):
            dominant_uca = "UCA-H-3"
        else:
            dominant_uca = "UCA-H-4"
        active_uca_set = [dominant_uca]

    if system_issue or any("uncertain" in v for v in support_cues):
        vulnerability = "ambiguous_feedback"
    elif boundary == "not_supported_transfer" and not any(field_is_reported(evidence_by_field, f) for f in HMI_FEEDBACK_FIELDS):
        vulnerability = "missed_feedback"
    elif boundary == "contingent_readiness":
        vulnerability = "misinterpreted_feedback"
    else:
        vulnerability = "none"

    support_ids = []
    for fp in ["CAR.event_type", "CAR.reported_intervention", "CAR.reported_system_issue", "CAR.automation_context", "ACTOR.primary_type", "ACTOR.primary_intent", "ENV.road_geometry", "HMI.mode_state_display", "HMI.capability_boundary_hint", "HMI.time_budget_indicator"]:
        item = evidence_by_field.get(fp)
        if item and item.get("provenance") != "not_reported":
            support_ids.append(item["evidence_id"])
    gaps, flags, blockers = build_gap_rows_from_evidence(case.get("case_id"), evidence_by_field, boundary, active_uca_set)
    needs_human = bool(
        (boundary == "not_supported_transfer" and not (intervention or "disengagement" in event_type or any("takeover" in v for v in support_cues)))
        or source_regime == "third_party_ca_dmv_collision_augmented_csv"
        or (boundary == "supported_monitoring" and any(field_is_reported(evidence_by_field, f) is False for f in ["HMI.mode_state_display", "HMI.capability_boundary_hint"]))
    )
    return {
        "case_id": case.get("case_id"),
        "annotator_id": "Expert0_Codex",
        "label_scope": "expert_preview_not_publication_gold",
        "source_regime": source_regime,
        "boundary_label": boundary,
        "update_vulnerability": vulnerability,
        "dominant_uca": dominant_uca,
        "active_uca_set": active_uca_set,
        "primary_pm_slots": [],
        "supporting_evidence_ids": sorted(set(support_ids)),
        "insufficient_information_flags": flags,
        "blocked_stronger_claims": ["blocked_not_supported_transfer"] if blockers else [],
        "rationale_short": (
            "Expert preview label under evidence constraints: explicit transfer/intervention evidence supports NS; "
            "otherwise crash/collision scenarios remain CR unless source-supported HMI support justifies SM. "
            "This is not accident-cause labeling."
        ),
        "confidence": "medium" if needs_human or len(gaps) >= 10 else "high",
        "needs_human_adjudication": needs_human,
    }


def generate_expert_preview_labels(cases_path: str | Path, out_labels: str | Path, out_report: str | Path) -> Dict[str, Any]:
    labels = [expert0_label_case(case) for case in iter_jsonl(cases_path)]
    write_jsonl(out_labels, labels)
    report = {
        "schema_version": SCHEMA_VERSION,
        "report_type": "expert_preview_annotation_report",
        "claim_boundary": "Expert-0 labels are protocol debugging labels generated by Codex; they are not publication human-gold labels.",
        "num_labels": len(labels),
        "boundary_distribution": dict(Counter(r["boundary_label"] for r in labels)),
        "vulnerability_distribution": dict(Counter(r["update_vulnerability"] for r in labels)),
        "uca_distribution": dict(Counter(r["dominant_uca"] for r in labels)),
        "needs_human_adjudication_count": sum(1 for r in labels if r.get("needs_human_adjudication")),
        "needs_human_adjudication_case_ids": [r["case_id"] for r in labels if r.get("needs_human_adjudication")][:50],
        "labels_path": str(out_labels),
    }
    write_json(out_report, report)
    return report


def _case_packet_from_bundle(case_dir: Path) -> Dict[str, Any]:
    bundle = read_json(case_dir / "bundle_summary.json")
    pkg = load_final_tabletop_replay_package(case_dir, bundle) or {}
    packets = sorted(case_dir.glob("e*_evidence_packet.json"))
    evidence_packet = read_json(packets[-1]) if packets else {}
    case_id = bundle.get("case_id") or case_dir.name
    return {
        "schema_version": SCHEMA_VERSION,
        "packet_type": "expert_replay_annotation_v2",
        "case_id": case_id,
        "source_regime": bundle.get("source_regime"),
        "label_scope": "expert_replay_admissibility_not_true_cause",
        "annotation_policy": {
            "task": "Label which replay claims are admissible given the available evidence.",
            "not_allowed": [
                "labeling the true accident cause",
                "inferring true driver psychology",
                "treating missing evidence as evidence of absence",
                "assigning legal responsibility",
            ],
        },
        "source_metadata": bundle.get("source_metadata", {}),
        "evidence_packet": evidence_packet,
        "driver_process_model": pkg.get("driver_process_model", {}),
        "process_model_update": pkg.get("process_model_update", {}),
        "other_factors": pkg.get("other_factors", {}),
        "candidate_driver_actions": pkg.get("candidate_driver_actions", []),
        "uca_pathway_candidates": pkg.get("uca_pathway_summary", []),
        "system_ranked_pathways": pkg.get("ranked_pathways", []),
        "blocked_claims": _collect_blocked_claim_texts(pkg),
        "replay_questions": pkg.get("replay_questions", []),
        "missing_requirement_candidates": pkg.get("missing_requirement_candidates", []),
    }


def _collect_blocked_claim_texts(obj: Any) -> List[str]:
    texts: List[str] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in {"blocked_claims", "blocked_update_claims", "blocked_claim_set", "blocking_reasons"} and isinstance(value, list):
                texts.extend(str(v) for v in value)
            else:
                texts.extend(_collect_blocked_claim_texts(value))
    elif isinstance(obj, list):
        for item in obj:
            texts.extend(_collect_blocked_claim_texts(item))
    return sorted(dict.fromkeys(t for t in texts if t.strip()))


def export_expert_replay_packets(bundle_dir: str | Path, out_dir: str | Path) -> Dict[str, Any]:
    out = Path(out_dir)
    ensure_dir(out)
    packets: List[Dict[str, Any]] = []
    label_templates: List[Dict[str, Any]] = []
    for case_dir in iter_case_dirs(bundle_dir):
        packet = _case_packet_from_bundle(case_dir)
        packets.append(packet)
        case_id = packet["case_id"]
        write_json(out / f"{case_id}.expert_replay_packet.json", packet)
        label_templates.append({
            "case_id": case_id,
            "label_scope": "expert_replay_admissibility",
            "supported_quadrant_nodes": [],
            "valid_update_claims": [],
            "admissible_candidate_actions": [],
            "admissible_uca_pathways": [],
            "top1_pathway_id": None,
            "top3_pathway_ids": [],
            "blocked_claims_correct": [],
            "blocked_claims_missing": [],
            "required_missing_evidence": [],
            "requirement_relevance": [],
            "rims_dimension_scores": {
                "evidence_fidelity": None,
                "process_model_alignment": None,
                "update_alignment": None,
                "action_uca_alignment": None,
                "blocked_claim_correctness": None,
                "requirement_relevance": None,
            },
            "notes": "",
        })
    write_jsonl(out / "expert_replay_label_template.jsonl", label_templates)
    guide = [
        "# Expert Replay Annotation Guide",
        "",
        "Label safety-review admissibility under the supplied evidence. Do not label true accident cause, true driver psychology, HMI causality, or legal responsibility.",
        "",
        "- `top1_pathway_id`: the most admissible pathway for tabletop replay.",
        "- `top3_pathway_ids`: up to three admissible pathways in priority order.",
        "- `blocked_claims_correct`: blocked claims that correctly prevent unsupported stronger conclusions.",
        "- `blocked_claims_missing`: claims that should have been blocked but were not.",
        "- `required_missing_evidence`: evidence/logging fields needed for stronger future review.",
        "- `rims_dimension_scores`: optional expert scores 0, 1, or 2 for each RIMS dimension.",
    ]
    (out / "expert_replay_annotation_guide.md").write_text("\n".join(guide) + "\n", encoding="utf-8")
    report = {
        "schema_version": SCHEMA_VERSION,
        "report_type": "expert_replay_packet_export",
        "bundle_dir": str(bundle_dir),
        "out_dir": str(out_dir),
        "num_packets": len(packets),
        "label_template_path": str(out / "expert_replay_label_template.jsonl"),
        "annotation_guide_path": str(out / "expert_replay_annotation_guide.md"),
    }
    write_json(out / "expert_replay_packet_export_report.json", report)
    return report


def _load_expert_packets(packet_dir: str | Path) -> Dict[str, Dict[str, Any]]:
    rows = {}
    for p in sorted(Path(packet_dir).glob("*.expert_replay_packet.json")):
        obj = read_json(p)
        rows[obj["case_id"]] = obj
    return rows


def _packet_supported_ids(packet: Dict[str, Any], key_path: str, id_keys: Sequence[str]) -> List[str]:
    rows = get_path(packet, key_path, []) or []
    ids = []
    for row in rows:
        for key in id_keys:
            value = row.get(key)
            if value:
                ids.append(str(value))
                break
    return sorted(dict.fromkeys(ids))


def _expert0_pathway_admissibility_score(pathway: Dict[str, Any]) -> Tuple[float, List[str]]:
    """Protocol-debug heuristic that does not copy the system ranking."""
    reasons: List[str] = []
    score = 0.0
    positive_count = len(pathway.get("positive_evidence_ids") or pathway.get("supporting_evidence_ids") or [])
    if positive_count:
        score += min(0.30, positive_count * 0.05)
        reasons.append("positive_evidence_present")
    if pathway.get("pathway_status") == "admissible":
        score += 0.25
        reasons.append("admissible_status")
    elif pathway.get("pathway_status") == "weakly_supported":
        score += 0.15
        reasons.append("weakly_supported_status")
    if pathway.get("claim_status") == "abductive_candidate":
        score += 0.10
        reasons.append("abductive_candidate_not_observed")
    gates = pathway.get("stpa_hf_compliance_gates") or {}
    pass_count = sum(1 for gate in gates.values() if isinstance(gate, dict) and gate.get("status") == "pass")
    weak_count = sum(1 for gate in gates.values() if isinstance(gate, dict) and gate.get("status") == "weak")
    score += min(0.20, pass_count * 0.04)
    score += min(0.10, weak_count * 0.015)
    if get_path(pathway, "G7_outcome_compatibility_gate.action_evidence_present") or get_path(pathway, "outcome_compatibility_block.action_evidence_present"):
        score += 0.10
        reasons.append("action_evidence_present")
    if pathway.get("blocking_reasons"):
        score -= 0.25
        reasons.append("blocking_reasons_present")
    if pathway.get("pathway_status") == "blocked" or pathway.get("claim_status") == "blocked":
        score -= 0.30
        reasons.append("blocked_status")
    if pathway.get("missingness_evidence_ids") and not positive_count:
        score -= 0.15
        reasons.append("missingness_only")
    if get_path(pathway, "outcome_compatibility_block.outcome_only_positive_evidence"):
        score -= 0.30
        reasons.append("outcome_only_positive_evidence")
    return round(max(0.0, min(1.0, score)), 4), reasons


def generate_expert_preview_labels_v2(packet_dir: str | Path, out_labels: str | Path, out_report: str | Path) -> Dict[str, Any]:
    packets = _load_expert_packets(packet_dir)
    labels = []
    for case_id, packet in packets.items():
        ranked = packet.get("system_ranked_pathways", []) or []
        scored = []
        for p in ranked:
            if not p.get("pathway_id"):
                continue
            score, reasons = _expert0_pathway_admissibility_score(p)
            scored.append((score, str(p.get("pathway_id")), reasons))
        selected = [row for row in sorted(scored, key=lambda x: (-x[0], x[1])) if row[0] >= 0.25]
        top_ids = [pid for _, pid, _ in selected[:3]]
        blocked_claims = packet.get("blocked_claims", []) or []
        requirements = packet.get("missing_requirement_candidates", []) or []
        label = {
            "case_id": case_id,
            "annotator_id": "Expert0_Codex",
            "label_scope": "expert_preview_not_publication_gold",
            "supported_quadrant_nodes": _packet_supported_ids(packet, "driver_process_model.pm_context_nodes", ["node_id"]),
            "valid_update_claims": _packet_supported_ids(packet, "process_model_update.update_process_nodes", ["node_id"]),
            "admissible_candidate_actions": _packet_supported_ids(packet, "candidate_driver_actions", ["node_id", "action_id", "candidate_action"]),
            "admissible_uca_pathways": top_ids,
            "top1_pathway_id": top_ids[0] if top_ids else None,
            "top3_pathway_ids": top_ids,
            "expert0_independent_pathway_scores": [
                {"pathway_id": pid, "expert0_admissibility_score": score, "score_reasons": reasons}
                for score, pid, reasons in sorted(scored, key=lambda x: (-x[0], x[1]))
            ],
            "blocked_claims_correct": blocked_claims,
            "blocked_claims_missing": [],
            "required_missing_evidence": [r.get("field_path") or r.get("target_slot") for r in requirements if r.get("field_path") or r.get("target_slot")],
            "requirement_relevance": [r.get("field_path") or r.get("target_slot") for r in requirements if r.get("field_path") or r.get("target_slot")],
            "rims_dimension_scores": {
                "evidence_fidelity": 2 if packet.get("evidence_packet", {}).get("evidence_items") else 1,
                "process_model_alignment": 2 if get_path(packet, "driver_process_model.pm_context_nodes", []) else 0,
                "update_alignment": 2 if get_path(packet, "process_model_update.update_process_nodes", []) else 0,
                "action_uca_alignment": 2 if top_ids else 1 if ranked else 0,
                "blocked_claim_correctness": 2 if blocked_claims else 1,
                "requirement_relevance": 2 if requirements else 1,
            },
            "notes": "Strict Expert-0 preview label for protocol debugging only; it scores pathway admissibility from packet evidence and does not copy the system top ranking as gold.",
        }
        labels.append(label)
    write_jsonl(out_labels, labels)
    report = {
        "schema_version": SCHEMA_VERSION,
        "report_type": "expert_preview_annotation_report_v2",
        "claim_boundary": "Expert-0 preview labels are protocol-debug labels, not publication human-gold labels.",
        "strict_mode": True,
        "strict_mode_note": "Pathway labels are selected by an independent admissibility heuristic over packet evidence; they are still not human-gold.",
        "packet_dir": str(packet_dir),
        "num_labels": len(labels),
        "labels_path": str(out_labels),
        "cases_without_top1": [r["case_id"] for r in labels if not r.get("top1_pathway_id")],
    }
    write_json(out_report, report)
    return report


def _safe_set(values: Any) -> set:
    return {str(v) for v in (values or []) if v is not None and str(v) != ""}


def _overlap_score(system_ids: Sequence[str], expert_ids: Sequence[str]) -> int:
    sys_set, exp_set = _safe_set(system_ids), _safe_set(expert_ids)
    if not exp_set:
        return 1
    if sys_set == exp_set:
        return 2
    if sys_set & exp_set:
        return 1
    return 0


def _normalize_rims_score(value: Any, fallback: int) -> int:
    if isinstance(value, (int, float)) and int(value) in {0, 1, 2}:
        return int(value)
    return fallback


def _spearman_rank_correlation(system_ids: Sequence[str], expert_ids: Sequence[str]) -> Optional[float]:
    common = [pid for pid in system_ids if pid in set(expert_ids)]
    if len(common) < 2:
        return None
    sys_rank = {pid: i + 1 for i, pid in enumerate(system_ids)}
    exp_rank = {pid: i + 1 for i, pid in enumerate(expert_ids)}
    n = len(common)
    diff_sq = sum((sys_rank[pid] - exp_rank[pid]) ** 2 for pid in common)
    return round(1 - (6 * diff_sq) / (n * (n * n - 1)), 4)


def _jaccard_similarity(a: Sequence[str], b: Sequence[str]) -> Optional[float]:
    aset, bset = _safe_set(a), _safe_set(b)
    if not aset and not bset:
        return None
    return round(len(aset & bset) / len(aset | bset), 4)


def _pathway_distribution_distance(system_rank_ids: Sequence[str], expert_ids: Sequence[str]) -> Optional[float]:
    if not system_rank_ids or not expert_ids:
        return None
    sys_top = set(system_rank_ids[:3])
    exp_top = set(expert_ids[:3])
    universe = sorted(sys_top | exp_top)
    if not universe:
        return None
    distance = 0.0
    for pid in universe:
        sys_prob = 1 / len(sys_top) if pid in sys_top and sys_top else 0.0
        exp_prob = 1 / len(exp_top) if pid in exp_top and exp_top else 0.0
        distance += abs(sys_prob - exp_prob)
    return round(distance / 2, 4)


def evaluate_replay_alignment(bundle_dir: str | Path, labels_path: str | Path, out_dir: str | Path) -> Dict[str, Any]:
    labels = {r["case_id"]: r for r in read_jsonl(labels_path)}
    rows: List[Dict[str, Any]] = []
    label_errors: List[Dict[str, Any]] = []
    for case_dir in iter_case_dirs(bundle_dir):
        bundle = read_json(case_dir / "bundle_summary.json")
        case_id = bundle.get("case_id") or case_dir.name
        label = labels.get(case_id)
        if not label:
            label_errors.append({"case_id": case_id, "error": "missing_label"})
            continue
        pkg = load_final_tabletop_replay_package(case_dir, bundle) or {}
        ranked = pkg.get("ranked_pathways", []) or []
        system_rank_ids = [p.get("pathway_id") for p in ranked if p.get("pathway_id")]
        top1 = system_rank_ids[0] if system_rank_ids else None
        label_top1 = label.get("top1_pathway_id")
        label_top3 = label.get("top3_pathway_ids") or []
        expert_rank_ids = [row.get("pathway_id") for row in label.get("expert0_independent_pathway_scores", []) if row.get("pathway_id")]
        if label_top3:
            expert_rank_ids = list(dict.fromkeys(list(label_top3) + expert_rank_ids))
        missing_ids = [pid for pid in [label_top1] + list(label_top3) if pid and pid not in system_rank_ids]
        if missing_ids:
            label_errors.append({"case_id": case_id, "error": "label_pathway_id_not_in_system_rankings", "pathway_ids": sorted(set(missing_ids))})
        top1_match = bool(top1 and label_top1 and top1 == label_top1)
        top3_recall = 0.0
        if label_top3:
            top3_recall = round(len(set(system_rank_ids[:3]) & set(label_top3)) / len(set(label_top3)), 4)
        blocked_system = _safe_set(_collect_blocked_claim_texts(pkg))
        blocked_correct = _safe_set(label.get("blocked_claims_correct"))
        blocked_missing = _safe_set(label.get("blocked_claims_missing"))
        blocked_precision = round(len(blocked_system & blocked_correct) / len(blocked_system), 4) if blocked_system else (1.0 if not blocked_correct else 0.0)
        blocked_recall = round(len(blocked_system & blocked_correct) / len(blocked_correct), 4) if blocked_correct else 1.0
        req_system = _safe_set([r.get("field_path") or r.get("target_slot") for r in pkg.get("missing_requirement_candidates", []) or []])
        req_relevant = _safe_set(label.get("requirement_relevance"))
        requirement_relevance_rate = round(len(req_system & req_relevant) / len(req_system), 4) if req_system else (1.0 if not req_relevant else 0.0)
        label_scores = label.get("rims_dimension_scores") or {}
        rims = {
            "rims_evidence_fidelity": _normalize_rims_score(label_scores.get("evidence_fidelity"), 2 if pkg.get("evidence_profile") else 1),
            "rims_pm_alignment": _normalize_rims_score(label_scores.get("process_model_alignment"), _overlap_score(_packet_supported_ids({"driver_process_model": pkg.get("driver_process_model", {})}, "driver_process_model.pm_context_nodes", ["node_id"]), label.get("supported_quadrant_nodes", []))),
            "rims_update_alignment": _normalize_rims_score(label_scores.get("update_alignment"), _overlap_score(_packet_supported_ids({"process_model_update": pkg.get("process_model_update", {})}, "process_model_update.update_process_nodes", ["node_id"]), label.get("valid_update_claims", []))),
            "rims_action_uca_alignment": _normalize_rims_score(label_scores.get("action_uca_alignment"), 2 if top1_match else 1 if top3_recall > 0 else 0),
            "rims_blocked_claim_correctness": _normalize_rims_score(label_scores.get("blocked_claim_correctness"), 2 if blocked_recall >= 0.8 and not blocked_missing else 1 if blocked_recall > 0 else 0),
            "rims_requirement_relevance": _normalize_rims_score(label_scores.get("requirement_relevance"), 2 if requirement_relevance_rate >= 0.8 else 1 if requirement_relevance_rate > 0 else 0),
        }
        rims_total = round(sum(rims.values()) / 12, 4)
        rows.append({
            "case_id": case_id,
            "source_regime": bundle.get("source_regime"),
            "top1_pathway_match": top1_match,
            "top3_pathway_recall": top3_recall,
            "ranking_correlation": _spearman_rank_correlation(system_rank_ids, expert_rank_ids),
            "pathway_distribution_distance": _pathway_distribution_distance(system_rank_ids, expert_rank_ids),
            "top3_jaccard": _jaccard_similarity(system_rank_ids[:3], label_top3),
            "blocked_claim_precision": blocked_precision,
            "blocked_claim_recall": blocked_recall,
            "requirement_relevance_rate": requirement_relevance_rate,
            "rims_total": rims_total,
            **rims,
            "system_top1_pathway_id": top1,
            "expert_top1_pathway_id": label_top1,
            "system_top3_pathway_ids": system_rank_ids[:3],
            "expert_top3_pathway_ids": label_top3,
            "expert_ranked_pathway_ids": expert_rank_ids,
        })
    by_source: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_source[str(row.get("source_regime"))].append(row)
    source_summary = {
        src: {
            "num_cases": len(src_rows),
            "mean_rims_total": _safe_mean([r.get("rims_total", 0) for r in src_rows]),
            "top1_match_rate": _safe_mean([1.0 if r.get("top1_pathway_match") else 0.0 for r in src_rows]),
            "mean_top3_recall": _safe_mean([r.get("top3_pathway_recall", 0.0) for r in src_rows]),
            "mean_top3_jaccard": _safe_mean([r.get("top3_jaccard", 0.0) for r in src_rows if r.get("top3_jaccard") is not None]),
            "mean_ranking_correlation": _safe_mean([r.get("ranking_correlation", 0.0) for r in src_rows if r.get("ranking_correlation") is not None]),
        }
        for src, src_rows in sorted(by_source.items())
    }
    report = {
        "schema_version": SCHEMA_VERSION,
        "report_type": "replay_alignment_eval",
        "claim_boundary": "RIMS evaluates expert-review alignment of replay artifacts; it is not true-cause validation.",
        "bundle_dir": str(bundle_dir),
        "labels_path": str(labels_path),
        "num_evaluated": len(rows),
        "summary": {
            "mean_rims_total": _safe_mean([r.get("rims_total", 0) for r in rows]),
            "top1_match_rate": _safe_mean([1.0 if r.get("top1_pathway_match") else 0.0 for r in rows]),
            "mean_top3_recall": _safe_mean([r.get("top3_pathway_recall", 0.0) for r in rows]),
            "mean_top3_jaccard": _safe_mean([r.get("top3_jaccard", 0.0) for r in rows if r.get("top3_jaccard") is not None]),
            "mean_ranking_correlation": _safe_mean([r.get("ranking_correlation", 0.0) for r in rows if r.get("ranking_correlation") is not None]),
            "mean_pathway_distribution_distance": _safe_mean([r.get("pathway_distribution_distance", 0.0) for r in rows if r.get("pathway_distribution_distance") is not None]),
            "mean_blocked_claim_recall": _safe_mean([r.get("blocked_claim_recall", 0.0) for r in rows]),
            "mean_requirement_relevance_rate": _safe_mean([r.get("requirement_relevance_rate", 0.0) for r in rows]),
            "by_source_regime": source_summary,
        },
        "label_errors": label_errors,
        "case_rows": rows,
    }
    ensure_dir(Path(out_dir))
    write_json(Path(out_dir) / "replay_alignment_eval.json", report)
    _write_csv_rows(Path(out_dir) / "replay_alignment_eval.csv", rows)
    dimension_summary = {
        "schema_version": SCHEMA_VERSION,
        "report_type": "rims_dimension_summary",
        "mean_by_dimension": {
            dim: _safe_mean([r.get(dim, 0) / 2 for r in rows])
            for dim in [
                "rims_evidence_fidelity",
                "rims_pm_alignment",
                "rims_update_alignment",
                "rims_action_uca_alignment",
                "rims_blocked_claim_correctness",
                "rims_requirement_relevance",
            ]
        },
    }
    write_json(Path(out_dir) / "rims_dimension_summary.json", dimension_summary)
    return report


# =============================================================================
# Counterfactual functional patching
# =============================================================================


def apply_counterfactual_patch(case: Dict[str, Any], patch: Dict[str, Any], cf_case_id: Optional[str] = None) -> Dict[str, Any]:
    cf = json.loads(json.dumps(case, ensure_ascii=False))
    cf["case_id"] = cf_case_id or f"{case.get('case_id', stable_digest(case))}__cf_{stable_digest(patch, 8)}"
    cf["case_source"] = "counterfactual_functional"
    cf.setdefault("source_metadata", {})["base_case_id"] = case.get("case_id")
    cf.setdefault("source_metadata", {})["counterfactual_patch"] = patch
    cf.setdefault("source_metadata", {})["not_real_world_evidence"] = True
    events = cf.get("latent_events", [])
    if not events:
        events = [{}]
        cf["latent_events"] = events
    event0 = events[0]
    for dotted, value in patch.items():
        if not isinstance(value, dict) or "value" not in value:
            value = ev(value, provenance="assumed_for_counterfactual", visibility="explicit", certainty="high")
        else:
            value = dict(value)
            value["provenance"] = "assumed_for_counterfactual"
        set_path(event0, dotted, value)
    return cf


def generate_counterfactual_cases(cases_path: str | Path, specs_path: str | Path, output_path: str | Path) -> List[Dict[str, Any]]:
    cases = {c.get("case_id"): c for c in load_external_cases(cases_path)}
    specs = read_jsonl(specs_path)
    out = []
    for spec in specs:
        base_id = spec.get("base_case_id")
        if base_id not in cases:
            raise DataCurationError(f"Counterfactual base_case_id not found: {base_id}")
        cf = apply_counterfactual_patch(cases[base_id], spec.get("patch", {}), spec.get("cf_case_id"))
        cf.setdefault("source_metadata", {})["expected_shift"] = spec.get("expected_shift", {})
        cf.setdefault("source_metadata", {})["counterfactual_template_id"] = spec.get("template_name")
        cf.setdefault("source_metadata", {})["counterfactual_claim_boundary"] = "Injected HMI cues are sensitivity assumptions, not real-world evidence."
        out.append(cf)
    write_jsonl(output_path, out)
    return out


def _package_for_case(bundle_dir: str | Path, case_id: str) -> Optional[Dict[str, Any]]:
    case_dir = Path(bundle_dir) / case_id
    if not case_dir.exists() or not (case_dir / "bundle_summary.json").exists():
        return None
    bundle = read_json(case_dir / "bundle_summary.json")
    return load_final_tabletop_replay_package(case_dir, bundle)


def _update_signature(pkg: Optional[Dict[str, Any]]) -> List[Tuple[Any, Any, Any, Tuple[Any, ...]]]:
    if not pkg:
        return []
    rows = []
    for node in get_path(pkg, "process_model_update.update_process_nodes", []) or []:
        observed = node.get("observed_update_vulnerability") or {}
        gap = node.get("evidence_gap_update_risk") or {}
        rows.append((
            node.get("target_quadrant"),
            node.get("update_evidence_status"),
            observed.get("label"),
            tuple(sorted(gap.get("canonical_gap_labels") or gap.get("labels") or [])),
        ))
    return sorted(rows)


def _action_signature(pkg: Optional[Dict[str, Any]]) -> List[Tuple[Any, Any, Any]]:
    if not pkg:
        return []
    return sorted(
        (
            node.get("candidate_action"),
            node.get("claim_status"),
            node.get("claim_strength"),
        )
        for node in pkg.get("candidate_driver_actions", []) or []
    )


def _rank_signature(pkg: Optional[Dict[str, Any]]) -> List[Tuple[Any, Any, Any, Any]]:
    if not pkg:
        return []
    rows = []
    for i, p in enumerate(pkg.get("ranked_pathways", []) or []):
        rows.append((i, p.get("uca_id"), p.get("linked_action"), p.get("pathway_status")))
    return rows


def _package_change_metrics(base_pkg: Optional[Dict[str, Any]], cf_pkg: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    base_blocked = count_blocked_claims_in_artifact(base_pkg or {})
    cf_blocked = count_blocked_claims_in_artifact(cf_pkg or {})
    base_missing = len((base_pkg or {}).get("missing_requirement_candidates", []) or [])
    cf_missing = len((cf_pkg or {}).get("missing_requirement_candidates", []) or [])
    base_update = _update_signature(base_pkg)
    cf_update = _update_signature(cf_pkg)
    base_action = _action_signature(base_pkg)
    cf_action = _action_signature(cf_pkg)
    base_rank = _rank_signature(base_pkg)
    cf_rank = _rank_signature(cf_pkg)
    return {
        "base_replay_package_present": bool(base_pkg),
        "cf_replay_package_present": bool(cf_pkg),
        "update_status_changed": base_update != cf_update,
        "candidate_action_changed": base_action != cf_action,
        "pathway_rank_changed": base_rank != cf_rank,
        "blocked_claim_count_base": base_blocked,
        "blocked_claim_count_cf": cf_blocked,
        "blocked_claim_reduced": cf_blocked < base_blocked,
        "missing_requirement_count_base": base_missing,
        "missing_requirement_count_cf": cf_missing,
        "missing_requirement_reduced": cf_missing < base_missing,
    }


def _specificity_score_texts(values: Sequence[Any]) -> int:
    return sum(len(str(v).split()) for v in values if v is not None)


def _pm_specificity(pkg: Optional[Dict[str, Any]]) -> int:
    if not pkg:
        return 0
    nodes = get_path(pkg, "driver_process_model.pm_context_nodes", []) or []
    return _specificity_score_texts(
        [
            n.get("reported_context", "")
            + " "
            + n.get("driver_belief_requirement", "")
            + " "
            + n.get("display_summary", "")
            for n in nodes
        ]
    )


def _direct_pm_node_support_count(pkg: Optional[Dict[str, Any]]) -> int:
    if not pkg:
        return 0
    count = 0
    for node in get_path(pkg, "driver_process_model.pm_context_nodes", []) or []:
        if node.get("supporting_evidence_ids") or node.get("observed_belief_evidence_ids"):
            count += 1
    return count


def _missing_pm_evidence_count(pkg: Optional[Dict[str, Any]]) -> int:
    if not pkg:
        return 0
    ids: set[str] = set()
    for node in get_path(pkg, "driver_process_model.pm_context_nodes", []) or []:
        ids.update(str(eid) for eid in (node.get("missing_evidence_ids") or node.get("missing_belief_evidence_ids") or []) if eid)
    for node in get_path(pkg, "process_model_update.update_process_nodes", []) or []:
        ids.update(str(eid) for eid in (node.get("missing_sources") or []) if eid)
        gap = node.get("evidence_gap_update_risk") or {}
        ids.update(str(eid) for eid in (gap.get("gap_evidence_ids") or []) if eid)
    return len(ids)


def _blocked_pm_claim_count(pkg: Optional[Dict[str, Any]]) -> int:
    if not pkg:
        return 0
    count = 0
    for node in get_path(pkg, "driver_process_model.pm_context_nodes", []) or []:
        if node.get("claim_strength") == "blocked":
            count += 1
        for flaw in node.get("pm_flaw_hypotheses", []) or []:
            if flaw.get("claim_status") == "blocked":
                count += 1
            count += len(flaw.get("blocked_claims", []) or [])
    for node in get_path(pkg, "process_model_update.update_process_nodes", []) or []:
        count += len(node.get("blocked_update_claims", []) or [])
        if node.get("claim_status") == "blocked":
            count += 1
    return count


def _pathway_status_entropy(pkg: Optional[Dict[str, Any]]) -> float:
    if not pkg:
        return 0.0
    statuses = [str(p.get("pathway_status") or p.get("claim_status") or "unknown") for p in pkg.get("ranked_pathways", []) or []]
    if not statuses:
        return 0.0
    counts = Counter(statuses)
    total = sum(counts.values())
    return round(-sum((count / total) * math.log2(count / total) for count in counts.values()), 4)


def _top_pathway_margin(pkg: Optional[Dict[str, Any]]) -> Optional[float]:
    if not pkg:
        return None
    scores = [p.get("pathway_score") for p in pkg.get("ranked_pathways", []) or [] if isinstance(p.get("pathway_score"), (int, float))]
    if len(scores) < 2:
        return None
    return round(float(scores[0]) - float(scores[1]), 4)


def _pathway_status_upgrade_count(sparse_pkg: Optional[Dict[str, Any]], richer_pkg: Optional[Dict[str, Any]]) -> int:
    order = {"blocked": 0, "weakly_supported": 1, "admissible": 2}
    sparse = {p.get("pathway_id"): p for p in (sparse_pkg or {}).get("ranked_pathways", []) or [] if p.get("pathway_id")}
    richer = {p.get("pathway_id"): p for p in (richer_pkg or {}).get("ranked_pathways", []) or [] if p.get("pathway_id")}
    count = 0
    for pid, sp in sparse.items():
        rp = richer.get(pid)
        if not rp:
            continue
        if order.get(str(rp.get("pathway_status")), -1) > order.get(str(sp.get("pathway_status")), -1):
            count += 1
    return count


def _structured_specificity(pkg: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "reported_update_source_count": _update_reported_source_count(pkg),
        "direct_pm_node_support_count": _direct_pm_node_support_count(pkg),
        "missing_pm_evidence_count": _missing_pm_evidence_count(pkg),
        "blocked_pm_claim_count": _blocked_pm_claim_count(pkg),
        "pathway_status_entropy": _pathway_status_entropy(pkg),
        "top_pathway_margin": _top_pathway_margin(pkg),
    }


def _update_reported_source_count(pkg: Optional[Dict[str, Any]]) -> int:
    if not pkg:
        return 0
    count = 0
    for node in get_path(pkg, "process_model_update.update_process_nodes", []) or []:
        count += len(node.get("observed_sources_in_report", []) or [])
        if node.get("update_evidence_status") == "observed_update_claim":
            count += 1
    return count


def _requirement_specificity(pkg: Optional[Dict[str, Any]]) -> int:
    if not pkg:
        return 0
    reqs = pkg.get("missing_requirement_candidates", []) or []
    return _specificity_score_texts([r.get("candidate_requirement") or r.get("candidate_evidence_requirement") or r.get("field_path") for r in reqs])


def compare_richer_evidence_pairs(
    sparse_bundle_dir: str | Path,
    richer_bundle_dir: str | Path,
    pair_map_path: str | Path,
    out_dir: str | Path,
) -> Dict[str, Any]:
    rows = []
    for pair in read_jsonl(pair_map_path):
        pair_id = pair.get("pair_id") or stable_digest(pair, 8)
        sparse_id = pair.get("sparse_case_id")
        richer_id = pair.get("richer_case_id")
        sparse_pkg = _package_for_case(sparse_bundle_dir, sparse_id)
        richer_pkg = _package_for_case(richer_bundle_dir, richer_id)
        if not sparse_pkg or not richer_pkg:
            rows.append({
                "pair_id": pair_id,
                "sparse_case_id": sparse_id,
                "richer_case_id": richer_id,
                "status": "missing_package",
            })
            continue
        metrics = _package_change_metrics(sparse_pkg, richer_pkg)
        sparse_rank = _rank_signature(sparse_pkg)
        richer_rank = _rank_signature(richer_pkg)
        sparse_pm_spec = _pm_specificity(sparse_pkg)
        richer_pm_spec = _pm_specificity(richer_pkg)
        sparse_update_sources = _update_reported_source_count(sparse_pkg)
        richer_update_sources = _update_reported_source_count(richer_pkg)
        sparse_structured = _structured_specificity(sparse_pkg)
        richer_structured = _structured_specificity(richer_pkg)
        sparse_actions = len(sparse_pkg.get("candidate_driver_actions", []) or [])
        richer_actions = len(richer_pkg.get("candidate_driver_actions", []) or [])
        pathway_status_upgrades = _pathway_status_upgrade_count(sparse_pkg, richer_pkg)
        structured_specificity_increased = (
            richer_structured["reported_update_source_count"] > sparse_structured["reported_update_source_count"]
            or richer_structured["direct_pm_node_support_count"] > sparse_structured["direct_pm_node_support_count"]
            or richer_structured["missing_pm_evidence_count"] < sparse_structured["missing_pm_evidence_count"]
            or pathway_status_upgrades > 0
        )
        row = {
            "pair_id": pair_id,
            "sparse_case_id": sparse_id,
            "richer_case_id": richer_id,
            "status": "evaluated",
            "evidence_addition_summary": pair.get("evidence_addition_summary", ""),
            "pm_node_specificity_sparse": sparse_pm_spec,
            "pm_node_specificity_richer": richer_pm_spec,
            "pm_node_specificity_increased": richer_pm_spec > sparse_pm_spec,
            "pm_node_specificity_metric_deprecated": True,
            "structured_specificity_sparse": sparse_structured,
            "structured_specificity_richer": richer_structured,
            "structured_specificity_increased": structured_specificity_increased,
            "pathway_status_upgrade_count": pathway_status_upgrades,
            "top_pathway_margin_sparse": sparse_structured["top_pathway_margin"],
            "top_pathway_margin_richer": richer_structured["top_pathway_margin"],
            "update_source_count_sparse": sparse_update_sources,
            "update_source_count_richer": richer_update_sources,
            "update_source_completeness_increased": richer_update_sources > sparse_update_sources,
            "candidate_action_count_sparse": sparse_actions,
            "candidate_action_count_richer": richer_actions,
            "candidate_action_narrowed": richer_actions < sparse_actions,
            "pathway_rank_changed": sparse_rank != richer_rank,
            "blocked_claim_count_sparse": metrics["blocked_claim_count_base"],
            "blocked_claim_count_richer": metrics["blocked_claim_count_cf"],
            "blocked_claim_reduced": metrics["blocked_claim_reduced"],
            "missing_requirement_count_sparse": metrics["missing_requirement_count_base"],
            "missing_requirement_count_richer": metrics["missing_requirement_count_cf"],
            "missing_requirement_reduced": metrics["missing_requirement_reduced"],
            "requirement_specificity_sparse": _requirement_specificity(sparse_pkg),
            "requirement_specificity_richer": _requirement_specificity(richer_pkg),
            "claim_boundary": "Richer evidence may narrow replay boundaries but does not prove true cause.",
        }
        rows.append(row)
    evaluated = [r for r in rows if r.get("status") == "evaluated"]
    summary = {
        "schema_version": SCHEMA_VERSION,
        "report_type": "richer_evidence_pair_comparison",
        "claim_boundary": "This compares evidence density effects on replay artifacts; it is not a video-understanding or true-cause experiment.",
        "sparse_bundle_dir": str(sparse_bundle_dir),
        "richer_bundle_dir": str(richer_bundle_dir),
        "pair_map": str(pair_map_path),
        "num_pairs": len(rows),
        "num_evaluated": len(evaluated),
        "summary": {
            "blocked_claim_reduction_rate": _safe_mean([1.0 if r.get("blocked_claim_reduced") else 0.0 for r in evaluated]),
            "missing_requirement_reduction_rate": _safe_mean([1.0 if r.get("missing_requirement_reduced") else 0.0 for r in evaluated]),
            "update_source_completeness_increase_rate": _safe_mean([1.0 if r.get("update_source_completeness_increased") else 0.0 for r in evaluated]),
            "pm_specificity_increase_rate": _safe_mean([1.0 if r.get("pm_node_specificity_increased") else 0.0 for r in evaluated]),
            "structured_specificity_increase_rate": _safe_mean([1.0 if r.get("structured_specificity_increased") else 0.0 for r in evaluated]),
            "mean_pathway_status_upgrade_count": _safe_mean([int(r.get("pathway_status_upgrade_count") or 0) for r in evaluated]),
            "pm_specificity_metric_deprecated": True,
        },
        "rows": rows,
    }
    ensure_dir(Path(out_dir))
    write_json(Path(out_dir) / "richer_evidence_pair_comparison.json", summary)
    _write_csv_rows(Path(out_dir) / "richer_evidence_pair_comparison.csv", rows)
    md = [
        "# Richer-Evidence Replay Case Study",
        "",
        "This diagnostic artifact compares sparse and richer-evidence replay packages. It does not claim true accident cause.",
        "",
    ]
    for row in rows:
        md.append(f"## Pair `{row.get('pair_id')}`")
        md.append("")
        if row.get("status") != "evaluated":
            md.append("- Status: missing package")
        else:
            md.append(f"- Evidence addition: {row.get('evidence_addition_summary')}")
            md.append(f"- Blocked claims: {row.get('blocked_claim_count_sparse')} -> {row.get('blocked_claim_count_richer')}")
            md.append(f"- Missing requirements: {row.get('missing_requirement_count_sparse')} -> {row.get('missing_requirement_count_richer')}")
            md.append(f"- Update source count: {row.get('update_source_count_sparse')} -> {row.get('update_source_count_richer')}")
            md.append(f"- Structured specificity increased: {row.get('structured_specificity_increased')}")
            md.append(f"- Pathway status upgrades: {row.get('pathway_status_upgrade_count')}")
            md.append(f"- Deprecated text-length PM specificity: {row.get('pm_node_specificity_sparse')} -> {row.get('pm_node_specificity_richer')}")
        md.append("")
    (Path(out_dir) / "richer_evidence_case_study.md").write_text("\n".join(md), encoding="utf-8")
    return summary


def summarize_directional_consistency(base_bundle_dir: str | Path, cf_bundle_dir: str | Path, specs_path: str | Path, out_dir: str | Path) -> Dict[str, Any]:
    base = collect_bundle_summaries(base_bundle_dir)
    cf = collect_bundle_summaries(cf_bundle_dir)
    specs = read_jsonl(specs_path)
    rows = []
    order = {"supported_monitoring": 0, "contingent_readiness": 1, "not_supported_transfer": 2}
    for spec in specs:
        base_id = spec.get("base_case_id")
        cf_id = spec.get("cf_case_id")
        b = base.get(base_id)
        c = cf.get(cf_id)
        if not b or not c:
            rows.append({"base_case_id": base_id, "cf_case_id": cf_id, "status": "missing_bundle"})
            continue
        b_state = get_path(b, "final_case_summary.final_commitment_state_fsm")
        c_state = get_path(c, "final_case_summary.final_commitment_state_fsm")
        expected = spec.get("expected_shift", {}).get("boundary")
        template = spec.get("template_name") or (cf_id.split("__cf_")[-1] if isinstance(cf_id, str) and "__cf_" in cf_id else "unknown")
        source_regime = get_case_source_regime_from_bundle(b)
        replay_changes = _package_change_metrics(
            _package_for_case(base_bundle_dir, base_id),
            _package_for_case(cf_bundle_dir, cf_id),
        )
        ok = None
        if expected == "toward_stronger" and b_state in order and c_state in order:
            ok = order[c_state] >= order[b_state]
        elif expected == "toward_weaker" and b_state in order and c_state in order:
            ok = order[c_state] <= order[b_state]
        elif expected == "maintain_or_toward_weaker" and b_state in order and c_state in order:
            ok = order[c_state] <= max(order[b_state], order["contingent_readiness"])
        rows.append({
            "base_case_id": base_id,
            "cf_case_id": cf_id,
            "template_name": template,
            "source_regime": source_regime,
            "base_boundary": b_state,
            "cf_boundary": c_state,
            "expected_boundary_shift": expected,
            "expected_direction_rule": spec.get("expected_shift", {}).get("rule"),
            "direction_match": ok,
            **replay_changes,
        })
    valid = [r for r in rows if isinstance(r.get("direction_match"), bool)]
    tmpl_stats: Dict[str, Dict[str, int]] = {}
    source_stats: Dict[str, Dict[str, int]] = {}
    for r in valid:
        tname = r.get("template_name") or "unknown"
        ts = tmpl_stats.setdefault(tname, {"total": 0, "match": 0})
        ts["total"] += 1
        if r["direction_match"]:
            ts["match"] += 1
        ss = source_stats.setdefault(r.get("source_regime") or "unknown_source_regime", {"total": 0, "match": 0})
        ss["total"] += 1
        if r["direction_match"]:
            ss["match"] += 1
    per_template = {k: {"total": v["total"], "match": v["match"], "rate": round(v["match"] / v["total"], 4) if v["total"] else None} for k, v in tmpl_stats.items()}
    per_source_regime = {k: {"total": v["total"], "match": v["match"], "rate": round(v["match"] / v["total"], 4) if v["total"] else None} for k, v in source_stats.items()}
    replay_change_summary = {
        "update_status_change_count": sum(1 for r in valid if r.get("update_status_changed")),
        "candidate_action_change_count": sum(1 for r in valid if r.get("candidate_action_changed")),
        "pathway_rank_change_count": sum(1 for r in valid if r.get("pathway_rank_changed")),
        "blocked_claim_reduction_count": sum(1 for r in valid if r.get("blocked_claim_reduced")),
        "missing_requirement_reduction_count": sum(1 for r in valid if r.get("missing_requirement_reduced")),
        "mean_base_missing_requirement_count": _safe_mean([r.get("missing_requirement_count_base", 0) for r in valid]),
        "mean_cf_missing_requirement_count": _safe_mean([r.get("missing_requirement_count_cf", 0) for r in valid]),
        "mean_base_blocked_claim_count": _safe_mean([r.get("blocked_claim_count_base", 0) for r in valid]),
        "mean_cf_blocked_claim_count": _safe_mean([r.get("blocked_claim_count_cf", 0) for r in valid]),
    }
    summary = {
        "num_pairs": len(rows),
        "num_evaluable": len(valid),
        "boundary_direction_match_rate": round(sum(1 for r in valid if r["direction_match"]) / len(valid), 4) if valid else None,
        "replay_package_change_summary": replay_change_summary,
        "per_template": per_template,
        "per_source_regime": per_source_regime,
        "mismatch_case_ids": [r["cf_case_id"] for r in valid if not r["direction_match"]],
        "rows": rows,
    }
    ensure_dir(Path(out_dir))
    write_json(Path(out_dir) / "counterfactual_directional_consistency.json", summary)
    write_json(Path(out_dir) / "counterfactual_replay_package_change.json", {
        "schema_version": SCHEMA_VERSION,
        "report_type": "counterfactual_replay_package_change",
        "claim_boundary": "HMI/logging injections are counterfactual sensitivity assumptions, not real-world causal evidence.",
        **replay_change_summary,
        "rows": rows,
    })
    return summary


HMI_COUNTERFACTUAL_TEMPLATES: List[Dict[str, Any]] = [
    {
        "name": "cf_hmi_takeover_demand",
        "description": "Inject explicit takeover demand HMI signals: mode=takeover_requested, boundary=exceeded, timing=now, ack=required.",
        "patch": {
            "HMI.mode_state_display": {"value": "takeover_requested", "provenance": "assumed_for_counterfactual", "visibility": "explicit", "certainty": "high"},
            "HMI.capability_boundary_hint": {"value": "boundary_exceeded", "provenance": "assumed_for_counterfactual", "visibility": "explicit", "certainty": "high"},
            "HMI.time_budget_indicator": {"value": "takeover_now", "provenance": "assumed_for_counterfactual", "visibility": "explicit", "certainty": "high"},
            "HMI.require_ack": {"value": "yes", "provenance": "assumed_for_counterfactual", "visibility": "explicit", "certainty": "high"},
        },
        "expected_shift": {"boundary": "toward_stronger"},
    },
    {
        "name": "cf_hmi_ambiguous_degradation_no_transition",
        "description": "Inject ambiguous HMI cues suggesting capability uncertainty without explicit takeover or transition demand.",
        "patch": {
            "HMI.mode_state_display": {"value": "engaged_but_uncertain", "provenance": "assumed_for_counterfactual", "visibility": "explicit", "certainty": "medium"},
            "HMI.capability_boundary_hint": {"value": "uncertain_capability", "provenance": "assumed_for_counterfactual", "visibility": "explicit", "certainty": "medium"},
        },
        "expected_shift": {
            "boundary": "maintain_or_toward_weaker",
            "rule": "Ambiguous degradation without transition demand should not by itself escalate to unsupported transfer.",
        },
    },
    {
        "name": "cf_hmi_ambiguous_degradation_with_transition_pressure",
        "description": "Inject ambiguous HMI degradation plus explicit time pressure, without asserting a real-world cause.",
        "patch": {
            "HMI.mode_state_display": {"value": "degraded_support_uncertain", "provenance": "assumed_for_counterfactual", "visibility": "explicit", "certainty": "medium"},
            "HMI.capability_boundary_hint": {"value": "capability_boundary_uncertain", "provenance": "assumed_for_counterfactual", "visibility": "explicit", "certainty": "medium"},
            "HMI.time_budget_indicator": {"value": "limited_time_to_resume_control", "provenance": "assumed_for_counterfactual", "visibility": "explicit", "certainty": "medium"},
        },
        "expected_shift": {
            "boundary": "toward_stronger",
            "rule": "Ambiguous degradation with transition pressure may move toward a stronger replay-posture claim.",
        },
    },
    {
        "name": "cf_hmi_full_support",
        "description": "Inject comprehensive supportive HMI: mode=engaged, capability=within bounds, no time pressure, no ack needed, low latency.",
        "patch": {
            "HMI.mode_state_display": {"value": "engaged", "provenance": "assumed_for_counterfactual", "visibility": "explicit", "certainty": "high"},
            "HMI.capability_boundary_hint": {"value": "within_capability", "provenance": "assumed_for_counterfactual", "visibility": "explicit", "certainty": "high"},
            "HMI.time_budget_indicator": {"value": "no_takeover_needed", "provenance": "assumed_for_counterfactual", "visibility": "explicit", "certainty": "high"},
            "HMI.require_ack": {"value": "no", "provenance": "assumed_for_counterfactual", "visibility": "explicit", "certainty": "high"},
            "HMI.trajectory_display_latency": {"value": "low", "provenance": "assumed_for_counterfactual", "visibility": "explicit", "certainty": "high"},
        },
        "expected_shift": {"boundary": "toward_weaker"},
    },
    {
        "name": "cf_hmi_partial_support",
        "description": "Inject partial supportive HMI: mode=engaged, capability=within bounds, no time pressure. Ack and latency left unreported.",
        "patch": {
            "HMI.mode_state_display": {"value": "engaged", "provenance": "assumed_for_counterfactual", "visibility": "explicit", "certainty": "high"},
            "HMI.capability_boundary_hint": {"value": "within_capability", "provenance": "assumed_for_counterfactual", "visibility": "explicit", "certainty": "high"},
            "HMI.time_budget_indicator": {"value": "no_takeover_needed", "provenance": "assumed_for_counterfactual", "visibility": "explicit", "certainty": "high"},
        },
        "expected_shift": {"boundary": "toward_weaker"},
    },
]


def generate_counterfactual_specs_from_templates(
    cases_path: str | Path, output_path: str | Path, templates: Optional[List[Dict[str, Any]]] = None
) -> List[Dict[str, Any]]:
    """Generate counterfactual spec JSONL from base cases and HMI injection templates.

    Only generates specs for cases where all patched HMI fields are currently not_reported,
    so the counterfactual is a clean injection rather than an override.
    """
    cases = load_external_cases(cases_path)
    use_templates = templates or HMI_COUNTERFACTUAL_TEMPLATES
    specs: List[Dict[str, Any]] = []

    for case in cases:
        case_id = case.get("case_id", "")
        event = (case.get("latent_events") or [{}])[0]
        for tmpl in use_templates:
            patch = tmpl["patch"]
            all_nr = True
            for dotted in patch:
                raw = get_path(event, dotted, None)
                wrapped = wrap_if_plain(raw)
                if wrapped.get("provenance") != "not_reported":
                    all_nr = False
                    break
            if not all_nr:
                continue
            cf_id = f"{case_id}__cf_{tmpl['name']}"
            specs.append({
                "base_case_id": case_id,
                "cf_case_id": cf_id,
                "template_name": tmpl["name"],
                "template_description": tmpl["description"],
                "patch": patch,
                "expected_shift": tmpl["expected_shift"],
            })

    write_jsonl(output_path, specs)
    return specs


# =============================================================================
# Internal demo cases: schema-compatible but not publication-facing gold
# =============================================================================


def build_internal_demo_cases() -> List[Dict[str, Any]]:
    """Return a small schema-compatible internal demo set.

    This preserves the old rule-coded demonstration capability while keeping
    publication-facing evaluation separate from built-in labels. These cases are
    for smoke tests and method demonstrations only.
    """

    def case(case_id: str, label: str, env: Dict[str, Any], actor: Dict[str, Any], car: Dict[str, Any], hmi: Dict[str, Any], cabin: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "case_id": case_id,
            "case_source": "internal_demo",
            "source_metadata": {
                "source_dataset": "internal_demo",
                "source_record_id": case_id,
                "raw_case_summary": label,
                "curation_notes": "Schema-compatible demonstration case; not publication-facing external evidence.",
            },
            "driver_profile": {
                "experience_level": "not_reported",
                "training_exposure": "not_reported",
                "intervention_style": "not_reported",
                "workload": "not_reported",
                "time_pressure": "not_reported",
                "distraction_profile": "not_reported",
                "controllability_awareness": "not_reported",
                "trust_calibration": "not_reported",
                "primary_goal": "safe operation",
            },
            "latent_events": [{"ENV": env, "ACTOR": actor, "CAR": car, "HMI": hmi, "CABIN": cabin}],
            "missingness_policy": {
                "not_reported_is_not_absence": True,
                "forbid_hmi_imputation": True,
                "forbid_driver_state_imputation": True,
                "forbid_internal_ads_imputation": True,
            },
        }

    base_env = {
        "visibility": ev("medium"),
        "weather": ev("clear"),
        "intersection_type": nr(),
        "markings_quality": ev("good"),
        "road_geometry": ev("highway"),
        "lane_topology": ev("straight"),
        "construction_state": nr(),
        "cut_in_event": nr(),
        "pedestrian_crossing_event": nr(),
    }
    base_actor = {
        "primary_type": ev("vehicle"),
        "primary_intent": ev("steady"),
        "primary_observability": ev("clear"),
        "secondary_pressure": nr(),
        "prediction_uncertainty": ev("low"),
    }
    base_car = {
        "automation_context": ev("AV_testing"),
        "event_type": ev("normal_operation"),
        "reported_system_issue": nr(),
        "reported_intervention": nr(),
        "ads_mode": ev("automation_involved", "derived", derivation_basis="internal demo"),
        "time_budget_to_handover": nr(),
        "perception_confidence": nr(),
        "planner_confidence": nr(),
        "lane_keeping_behavior": ev("smooth"),
        "deceleration_behavior": ev("adequate"),
    }
    supported_hmi = {
        "mode_state_display": ev("engaged"),
        "capability_boundary_hint": nr(),
        "time_budget_indicator": nr(),
        "require_ack": nr(),
        "trajectory_display_latency": ev("low"),
    }
    cabin = {"pressure": nr(), "distraction": nr()}

    contingent_env = dict(base_env)
    contingent_env.update({
        "road_geometry": ev("construction_merge"),
        "lane_topology": ev("merge"),
        "construction_state": ev("active"),
        "markings_quality": ev("ambiguous"),
    })
    contingent_actor = dict(base_actor)
    contingent_actor.update({
        "primary_intent": ev("merge_uncertain"),
        "primary_observability": ev("partial"),
        "prediction_uncertainty": ev("high"),
    })
    contingent_car = dict(base_car)
    contingent_car.update({"reported_system_issue": ev("technology_failure_or_other_concern"), "lane_keeping_behavior": ev("hesitant")})
    contingent_hmi = {
        "mode_state_display": ev("conflicting"),
        "capability_boundary_hint": ev("uncertain_capability"),
        "time_budget_indicator": ev("takeover_soon"),
        "require_ack": ev("yes"),
        "trajectory_display_latency": ev("medium"),
    }

    transfer_env = dict(contingent_env)
    transfer_env.update({"visibility": ev("low"), "weather": ev("light_rain"), "cut_in_event": ev("active")})
    transfer_actor = dict(contingent_actor)
    transfer_actor.update({"primary_intent": ev("cut_in")})
    transfer_car = dict(contingent_car)
    transfer_car.update({
        "reported_intervention": ev("test_driver_or_operator"),
        "reported_system_issue": ev("technology_failure"),
        "lane_keeping_behavior": ev("oscillatory"),
        "deceleration_behavior": ev("delayed"),
    })
    transfer_hmi = {
        "mode_state_display": ev("takeover_requested"),
        "capability_boundary_hint": ev("boundary_exceeded"),
        "time_budget_indicator": ev("takeover_now"),
        "require_ack": ev("yes"),
        "trajectory_display_latency": ev("high"),
    }

    return [
        case("internal_demo_supported", "Supported monitoring demonstration case.", base_env, base_actor, base_car, supported_hmi, cabin),
        case("internal_demo_contingent", "Contingent readiness demonstration case.", contingent_env, contingent_actor, contingent_car, contingent_hmi, cabin),
        case("internal_demo_transfer", "Not-supported transfer demonstration case.", transfer_env, transfer_actor, transfer_car, transfer_hmi, cabin),
    ]


def build_internal_demo_labels() -> List[Dict[str, Any]]:
    """Return optional demo labels for smoke tests only, not publication-facing gold."""
    return [
        {"case_id": "internal_demo_supported", "boundary_label": "supported_monitoring", "update_vulnerability": "none", "dominant_uca": "UCA-H-6", "active_uca_set": ["UCA-H-6"], "label_scope": "internal_demo_not_publication"},
        {"case_id": "internal_demo_contingent", "boundary_label": "contingent_readiness", "update_vulnerability": "ambiguous_feedback", "dominant_uca": "UCA-H-2", "active_uca_set": ["UCA-H-2", "UCA-H-3"], "label_scope": "internal_demo_not_publication"},
        {"case_id": "internal_demo_transfer", "boundary_label": "not_supported_transfer", "update_vulnerability": "missed_feedback", "dominant_uca": "UCA-H-3", "active_uca_set": ["UCA-H-2", "UCA-H-3"], "label_scope": "internal_demo_not_publication"},
    ]


# =============================================================================
# Introspection helpers: input schema, prompts, and leakage audit
# =============================================================================


def get_engine_prompt_manifest() -> Dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "shared_system_prompt": SHARED_SYSTEM_PROMPT,
        "pm_context_synthesis_prompt": PM_CONTEXT_SYNTHESIS_PROMPT,
        "process_model_update_prompt": PROCESS_MODEL_UPDATE_PROMPT,
        "other_factors_prompt": OTHER_FACTORS_PROMPT,
        "commitment_boundary_prompt": COMMITMENT_BOUNDARY_PROMPT,
        "control_action_selection_prompt": CONTROL_ACTION_SELECTION_PROMPT,
        "uca_context_classification_prompt": UCA_CONTEXT_CLASSIFICATION_PROMPT,
        "pathway_judge_prompt": PATHWAY_JUDGE_PROMPT,
        "role_disambiguation_prompt": ROLE_DISAMBIGUATION_PROMPT,
        "semantic_warning_audit_prompt": SEMANTIC_WARNING_AUDIT_PROMPT,
        "direct_baseline_prompt": DIRECT_BASELINE_PROMPT,
        "generic_cot_baseline_prompt": GENERIC_COT_BASELINE_PROMPT,
        "driver_uca_catalog": DRIVER_UCA_CATALOG,
        "legacy_uca_id_map": LEGACY_UCA_ID_MAP,
        "core_constraints": [
            "Use only source-visible and driver-visible evidence in evidence_items.",
            "Treat not_reported as absence of source evidence, not evidence of absence.",
            "Do not infer HMI state, driver mental state, or internal ADS variables when not reported.",
            "PM context, update process, action selection, UCA classification, and pathway ranking remain separate stages.",
            "UCA classification uses the full driver-centered catalog; the driver replay posture is context, not a catalog filter.",
            "Reported outcome is used only as a compatibility constraint and cannot activate UCA.",
            "No boundary/UCA/vulnerability labels are allowed in case input.",
        ],
    }


def get_functional_case_input_schema() -> Dict[str, Any]:
    return {
        "required_top_level": ["case_id", "case_source", "source_metadata", "driver_profile", "latent_events", "missingness_policy"],
        "forbidden_top_level_or_nested_keys": sorted(FORBIDDEN_CASE_INPUT_KEYS),
        "latent_event_groups": ["ENV", "ACTOR", "CAR", "HMI", "CABIN"],
        "evidence_value_schema": {
            "value": "reported/derived value or not_reported",
            "provenance": ALLOWED_PROVENANCE,
            "visibility": "source_reported | not_in_source | explicit | ...",
            "certainty": "high | medium | low | uncertain | unknown",
            "source_text": "optional source snippet",
            "derivation_basis": "required when provenance=derived if possible",
            "use_as_negative_evidence": "must be false for not_reported",
        },
        "missingness_policy": {
            "not_reported_is_not_absence": True,
            "forbid_hmi_imputation": True,
            "forbid_driver_state_imputation": True,
            "forbid_internal_ads_imputation": True,
        },
        "llm_payload_contents_by_round": {
            "pm_context": ["case_id", "event_index", "evidence_policy", "evidence_items", "narrative_propositions"],
            "update_process": ["case_id", "event_index", "pm_context", "evidence_items", "source_evidence_audit", "missingness_policy"],
            "other_factors": ["case_id", "event_index", "pm_context", "update_process", "evidence_items"],
            "commitment_boundary": ["case_id", "event_index", "pm_context", "update_process", "other_factors", "evidence_items"],
            "action_selection": ["case_id", "event_index", "pm_context", "update_process", "other_factors", "boundary", "evidence_items"],
            "uca_context": ["committed_fsm_state", "pm_context", "update_process", "other_factors", "boundary", "action_selection", "reported_outcome", "uca_catalog", "evidence_items"],
            "pathway_judge": ["evidence_items", "candidate_pathways"],
        },
    }


def audit_case_input_leakage(cases_path: str | Path) -> Dict[str, Any]:
    cases = load_external_cases(cases_path)
    rows = []
    for case in cases:
        rows.append({"case_id": case.get("case_id"), "forbidden_paths": find_forbidden_input_keys(case)})
    return {
        "cases_path": str(cases_path),
        "num_cases": len(cases),
        "num_cases_with_forbidden_keys": sum(1 for r in rows if r["forbidden_paths"]),
        "rows": rows,
    }


# =============================================================================
# CLI
# =============================================================================


def cmd_show_prompts(args: argparse.Namespace) -> None:
    manifest = get_engine_prompt_manifest()
    if args.out:
        write_json(args.out, manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


def cmd_show_input_schema(args: argparse.Namespace) -> None:
    schema = get_functional_case_input_schema()
    if args.out:
        write_json(args.out, schema)
    print(json.dumps(schema, ensure_ascii=False, indent=2))


def cmd_audit_case_input(args: argparse.Namespace) -> None:
    report = audit_case_input_leakage(args.cases)
    if args.out:
        write_json(args.out, report)
    print(json.dumps({k: v for k, v in report.items() if k != "rows"}, ensure_ascii=False, indent=2))


def cmd_demo_cases(args: argparse.Namespace) -> None:
    cases = build_internal_demo_cases()
    write_jsonl(args.out, cases)
    msg = {"num_cases": len(cases), "out": args.out, "scope": "internal_demo_not_publication"}
    if args.labels:
        write_jsonl(args.labels, build_internal_demo_labels())
        msg["labels"] = args.labels
    print(json.dumps(msg, ensure_ascii=False, indent=2))
def cmd_export_annotation_packets(args: argparse.Namespace) -> None:
    rows = export_annotation_packets(args.cases, args.out, args.csv)
    print(json.dumps({"num_packets": len(rows), "out": args.out, "csv": args.csv}, ensure_ascii=False, indent=2))


def cmd_adjudicate_labels(args: argparse.Namespace) -> None:
    rows = adjudicate_multirater_labels(args.raw_labels, args.out)
    completeness = validate_annotation_completeness(args.out)
    print(json.dumps({"num_cases": len(rows), "out": args.out, "completeness": completeness}, ensure_ascii=False, indent=2))


def cmd_run(args: argparse.Namespace) -> None:
    client = LLMClient.from_env()
    cases = select_case_window(load_external_cases(args.cases), case_start=args.case_start, case_limit=args.case_limit)
    out = Path(args.out)
    ensure_dir(out)
    bundles = []
    for case in cases:
        existing = _existing_bundle(case, out) if args.resume else None
        bundles.append(existing or run_case(client, case, out, use_vulnerability_priority=args.use_vulnerability_priority, temperature=args.temperature))
    print(json.dumps({"num_cases": len(cases), "out": str(out), "schema_valid_cases": sum(1 for b in bundles if b.get("schema_valid")), "use_vulnerability_priority": args.use_vulnerability_priority}, ensure_ascii=False, indent=2))


def cmd_eval(args: argparse.Namespace) -> None:
    report = evaluate_bundles(args.bundle_dir, args.labels, args.out)
    print(json.dumps({k: v for k, v in report.items() if k != "case_level_rows"}, ensure_ascii=False, indent=2))


def cmd_eval_baseline(args: argparse.Namespace) -> None:
    report = evaluate_baselines(args.baseline_dir, args.labels, args.out)
    print(json.dumps({k: v for k, v in report.items() if k != "case_level_rows"}, ensure_ascii=False, indent=2))


def cmd_baseline_suite(args: argparse.Namespace) -> None:
    client = LLMClient.from_env()
    cases = select_case_window(load_external_cases(args.cases), case_start=args.case_start, case_limit=args.case_limit)
    summary = run_baseline_suite(client, cases, args.out, temperature=args.temperature, resume=args.resume)
    print(json.dumps({"num_cases": len(cases), "out": args.out, "keys": list(summary.keys())}, ensure_ascii=False, indent=2))


def cmd_run_ablation_suite(args: argparse.Namespace) -> None:
    client = LLMClient.from_env()
    cases = select_case_window(load_external_cases(args.cases), case_start=args.case_start, case_limit=args.case_limit)
    summary = run_ablation_suite_v2(
        client,
        cases,
        args.out,
        full_bundle_dir=args.full_bundle_dir,
        temperature=args.temperature,
        resume=args.resume,
    )
    print(json.dumps({
        "num_cases": len(cases),
        "out": args.out,
        "conditions": summary.get("conditions"),
        "condition_reports": summary.get("condition_reports"),
    }, ensure_ascii=False, indent=2))


def cmd_evidence_audit(args: argparse.Namespace) -> None:
    report = run_evidence_support_audit(args.bundle_dir, args.out)
    print(json.dumps({k: v for k, v in report.items() if k != "case_reports"}, ensure_ascii=False, indent=2))


def cmd_tabletop_replay_audit(args: argparse.Namespace) -> None:
    report = audit_tabletop_replay_packages(args.bundle_dir, args.out)
    print(json.dumps({k: v for k, v in report.items() if k != "case_reports"}, ensure_ascii=False, indent=2))


def cmd_generate_cf_specs(args: argparse.Namespace) -> None:
    if args.case_start is not None or args.case_limit is not None:
        cases = select_case_window(load_external_cases(args.cases), case_start=args.case_start, case_limit=args.case_limit)
        ensure_dir(Path(args.out).parent)
        tmp_cases = Path(args.out).parent / "_windowed_cases.jsonl"
        write_jsonl(tmp_cases, cases)
        cases_path = tmp_cases
    else:
        cases_path = args.cases
    specs = generate_counterfactual_specs_from_templates(cases_path, args.out)
    if isinstance(cases_path, Path) and cases_path.name == "_windowed_cases.jsonl":
        try:
            cases_path.unlink()
        except Exception:
            pass
    print(json.dumps({"num_specs": len(specs), "out": args.out}, ensure_ascii=False, indent=2))


def cmd_generate_counterfactual(args: argparse.Namespace) -> None:
    if args.case_start is not None or args.case_limit is not None:
        cases = select_case_window(load_external_cases(args.cases), case_start=args.case_start, case_limit=args.case_limit)
        ensure_dir(Path(args.out).parent)
        tmp_cases = Path(args.out).parent / "_windowed_cases.jsonl"
        write_jsonl(tmp_cases, cases)
        cases_path = tmp_cases
    else:
        cases_path = args.cases
    cases = generate_counterfactual_cases(cases_path, args.specs, args.out)
    if isinstance(cases_path, Path) and cases_path.name == "_windowed_cases.jsonl":
        try:
            cases_path.unlink()
        except Exception:
            pass
    print(json.dumps({"num_counterfactual_cases": len(cases), "out": args.out}, ensure_ascii=False, indent=2))


def cmd_counterfactual_eval(args: argparse.Namespace) -> None:
    report = summarize_directional_consistency(args.base_bundle_dir, args.cf_bundle_dir, args.specs, args.out)
    print(json.dumps({k: v for k, v in report.items() if k != "rows"}, ensure_ascii=False, indent=2))


def cmd_pm_mediation_comparison(args: argparse.Namespace) -> None:
    report = build_pm_mediation_comparison_report(
        out_dir=args.out,
        full_bundle_dir=args.full_bundle_dir,
        direct_baseline_dir=args.direct_baseline_dir,
        generic_baseline_dir=args.generic_baseline_dir,
        no_update_bundle_dir=args.no_update_bundle_dir,
        baseline_suite_dir=args.baseline_suite_dir,
    )
    print(json.dumps({k: v for k, v in report.items() if k != "case_rows"}, ensure_ascii=False, indent=2))


def cmd_missingness_profile(args: argparse.Namespace) -> None:
    cases = select_case_window(load_external_cases(args.cases), case_start=args.case_start, case_limit=args.case_limit)
    ensure_dir(Path(args.out))
    tmp_path = Path(args.out) / "_windowed_cases.jsonl"
    write_jsonl(tmp_path, cases)
    profile = export_dataset_missingness_profile(tmp_path, args.out)
    try:
        tmp_path.unlink()
    except Exception:
        pass
    print(json.dumps({k: v for k, v in profile.items() if k not in ("field_level_profile", "case_level_profile")}, ensure_ascii=False, indent=2))


def cmd_feedback_gap_report(args: argparse.Namespace) -> None:
    cases_path = args.cases
    if args.cases and (args.case_start is not None or args.case_limit is not None):
        cases = select_case_window(load_external_cases(args.cases), case_start=args.case_start, case_limit=args.case_limit)
        ensure_dir(Path(args.out))
        tmp_path = Path(args.out) / "_windowed_cases.jsonl"
        write_jsonl(tmp_path, cases)
        cases_path = tmp_path
    report = run_feedback_gap_report(args.out, cases_path=cases_path, bundle_dir=args.bundle_dir)
    if isinstance(cases_path, Path) and cases_path.name == "_windowed_cases.jsonl":
        try:
            cases_path.unlink()
        except Exception:
            pass
    print(json.dumps({k: v for k, v in report.items() if k != "case_reports"}, ensure_ascii=False, indent=2))


def cmd_requirement_candidates(args: argparse.Namespace) -> None:
    if args.gap_report:
        gap_report = read_json(args.gap_report)
    else:
        gap_report = run_feedback_gap_report(args.out, cases_path=args.cases, bundle_dir=args.bundle_dir)
    report = generate_requirement_candidates_from_gap_report(gap_report, args.out)
    print(json.dumps({k: v for k, v in report.items() if k != "candidates"}, ensure_ascii=False, indent=2))


def cmd_paper_manifest(args: argparse.Namespace) -> None:
    manifest = build_paper_result_manifest(
        args.out,
        cases_path=args.cases,
        bundle_dir=args.bundle_dir,
        baseline_dir=args.baseline_dir,
        cf_report=args.cf_report,
        missingness_profile=args.missingness_profile,
        evidence_audit=args.evidence_audit,
        feedback_gap_report=args.feedback_gap_report,
        requirement_candidates=args.requirement_candidates,
    )
    print(json.dumps({k: v for k, v in manifest.items() if k != "outputs"}, ensure_ascii=False, indent=2))


def cmd_build_paper_sample(args: argparse.Namespace) -> None:
    summary = build_paper_50_sample(
        nhtsa_cases=args.nhtsa_cases,
        ca_collision_cases=args.ca_collision_cases,
        ca_disengagement_cases=args.ca_disengagement_cases,
        out_cases=args.out_cases,
        out_summary=args.out_summary,
        n_nhtsa=args.n_nhtsa,
        n_collision=args.n_collision,
        n_disengagement=args.n_disengagement,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def cmd_expert_preview_labels(args: argparse.Namespace) -> None:
    if getattr(args, "packet_dir", None):
        report = generate_expert_preview_labels_v2(args.packet_dir, args.out_labels, args.out_report)
    else:
        if not args.cases:
            raise DataCurationError("expert-preview-labels requires --cases for legacy labels or --packet-dir for v2 labels")
        report = generate_expert_preview_labels(args.cases, args.out_labels, args.out_report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


def cmd_export_expert_replay_packets(args: argparse.Namespace) -> None:
    report = export_expert_replay_packets(args.bundle_dir, args.out)
    print(json.dumps(report, ensure_ascii=False, indent=2))


def cmd_replay_alignment_eval(args: argparse.Namespace) -> None:
    report = evaluate_replay_alignment(args.bundle_dir, args.labels, args.out)
    print(json.dumps({
        "out": args.out,
        "num_evaluated": report.get("num_evaluated"),
        "summary": report.get("summary"),
        "label_error_count": len(report.get("label_errors", [])),
    }, ensure_ascii=False, indent=2))


def cmd_richer_evidence_compare(args: argparse.Namespace) -> None:
    report = compare_richer_evidence_pairs(args.sparse_bundle_dir, args.richer_bundle_dir, args.pair_map, args.out)
    print(json.dumps({
        "out": args.out,
        "num_pairs": report.get("num_pairs"),
        "num_evaluated": report.get("num_evaluated"),
        "summary": report.get("summary"),
    }, ensure_ascii=False, indent=2))


def cmd_enrich_from_narrative(args: argparse.Namespace) -> None:
    client = LLMClient.from_env()
    result = enrich_cases_from_narrative(client, args.cases, args.out)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def _case_is_ads_takeover_related(case: Dict[str, Any]) -> bool:
    text = json.dumps(case, ensure_ascii=False).lower()
    positive = ["ads", "autonomous", "automation", "disengagement", "takeover", "intervention", "test driver", "operator", "manual", "fallback"]
    return any(k in text for k in positive)


def _case_priority_for_takeover(case: Dict[str, Any]) -> Tuple[int, str]:
    src = get_case_source_regime_from_case(case)
    text = json.dumps(case, ensure_ascii=False).lower()
    score = 0
    if "disengagement" in src or "disengagement" in text:
        score += 50
    if any(k in text for k in ["takeover", "intervention", "test driver", "operator", "manual"]):
        score += 25
    if "ads" in text or "autonomous" in text:
        score += 10
    if "ca_dmv" in src:
        score += 5
    return (-score, str(case.get("case_id", "")))


def build_takeover_text_sample(input_paths: Sequence[str | Path], out_path: str | Path, n: int = 10) -> Dict[str, Any]:
    seen = set()
    rows: List[Dict[str, Any]] = []
    for path in input_paths:
        for case in iter_jsonl(path):
            cid = case.get("case_id") or stable_digest(case)
            if cid in seen:
                continue
            seen.add(cid)
            if _case_is_ads_takeover_related(case):
                rows.append(case)
    rows.sort(key=_case_priority_for_takeover)
    selected = rows[:n]
    write_jsonl(out_path, selected)
    return {
        "report_type": "ads_takeover_text_sample",
        "num_candidates": len(rows),
        "num_selected": len(selected),
        "out": str(out_path),
        "source_counts": dict(Counter(get_case_source_regime_from_case(c) for c in selected)),
        "case_ids": [c.get("case_id") for c in selected],
    }


def cmd_build_takeover_sample(args: argparse.Namespace) -> None:
    summary = build_takeover_text_sample(args.inputs, args.out, n=args.n)
    if args.summary:
        write_json(args.summary, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def cmd_mine_narrative_evidence(args: argparse.Namespace) -> None:
    client = LLMClient.from_env()
    summary = mine_narrative_evidence_file(client, args.cases, args.out_cases, args.out_report, temperature=args.temperature)
    print(json.dumps({k: v for k, v in summary.items() if k != "reports"}, ensure_ascii=False, indent=2))


def cmd_role_disambiguate_cases(args: argparse.Namespace) -> None:
    client = LLMClient.from_env()
    summary = role_disambiguate_cases_file(
        client,
        args.cases,
        args.out_cases,
        args.out_report,
        temperature=args.temperature,
    )
    print(json.dumps({k: v for k, v in summary.items() if k != "reports"}, ensure_ascii=False, indent=2))


def cmd_semantic_warning_audit(args: argparse.Namespace) -> None:
    client = LLMClient.from_env()
    summary = run_semantic_warning_audit(
        client,
        args.bundle_dir,
        args.out,
        evidence_audit_path=args.evidence_audit,
        temperature=args.temperature,
    )
    print(json.dumps({k: v for k, v in summary.items() if k not in {"adjudications"}}, ensure_ascii=False, indent=2))



def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="STPA-HF driver process-model tabletop replay engine; external ingestion is separate")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("show-prompts", help="Print all LLM prompts and hard constraints used by the engine")
    p.add_argument("--out")
    p.set_defaults(func=cmd_show_prompts)

    p = sub.add_parser("show-input-schema", help="Print functional case input schema and forbidden leakage keys")
    p.add_argument("--out")
    p.set_defaults(func=cmd_show_input_schema)

    p = sub.add_parser("audit-case-input", help="Check case file for label/expected-output leakage before LLM use")
    p.add_argument("--cases", required=True)
    p.add_argument("--out")
    p.set_defaults(func=cmd_audit_case_input)

    p = sub.add_parser("demo-cases", help="Write schema-compatible internal demo cases; labels are debug-only, not publication gold")
    p.add_argument("--out", required=True)
    p.add_argument("--labels")
    p.set_defaults(func=cmd_demo_cases)

    p = sub.add_parser("export-annotation-packets")
    p.add_argument("--cases", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--csv")
    p.set_defaults(func=cmd_export_annotation_packets)

    p = sub.add_parser("adjudicate-labels")
    p.add_argument("--raw-labels", nargs="+", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_adjudicate_labels)

    p = sub.add_parser("run")
    p.add_argument("--cases", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--temperature", type=float, default=0.0)
    p.add_argument("--use-vulnerability-priority", action="store_true", help="Enable vulnerability-conditioned UCA candidate ordering; default is off for publication-facing runs.")
    p.add_argument("--resume", action="store_true", help="Reuse existing bundle_summary.json outputs in the target directory.")
    p.add_argument("--case-start", type=int, default=0, help="Start index within the loaded case list.")
    p.add_argument("--case-limit", type=int, default=None, help="Maximum number of cases to run from the selected start index.")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("eval")
    p.add_argument("--bundle-dir", required=True)
    p.add_argument("--labels", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_eval)

    p = sub.add_parser("eval-baseline", help="Evaluate direct/generic_cot baseline results against gold labels")
    p.add_argument("--baseline-dir", required=True, help="Directory containing {case_id}/baseline_result.json files")
    p.add_argument("--labels", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--case-start", type=int, default=0)
    p.add_argument("--case-limit", type=int, default=None)
    p.set_defaults(func=cmd_eval_baseline)

    p = sub.add_parser("baseline-suite")
    p.add_argument("--cases", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--temperature", type=float, default=0.0)
    p.add_argument("--resume", action="store_true", help="Reuse existing baseline/bundle outputs in the target directory.")
    p.add_argument("--case-start", type=int, default=0)
    p.add_argument("--case-limit", type=int, default=None)
    p.set_defaults(func=cmd_baseline_suite)

    p = sub.add_parser("run-ablation-suite", help="Run AAP V2 six-condition baseline/ablation suite")
    p.add_argument("--cases", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--full-bundle-dir", help="Optional existing full replay bundle dir to reuse")
    p.add_argument("--temperature", type=float, default=0.0)
    p.add_argument("--resume", action="store_true", help="Reuse existing outputs in the target directory.")
    p.add_argument("--case-start", type=int, default=0)
    p.add_argument("--case-limit", type=int, default=None)
    p.set_defaults(func=cmd_run_ablation_suite)

    p = sub.add_parser("evidence-audit")
    p.add_argument("--bundle-dir", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_evidence_audit)

    p = sub.add_parser("semantic-warning-audit", help="Use an evidence-bounded LLM judge to adjudicate structurally suspicious UCA warning candidates")
    p.add_argument("--bundle-dir", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--evidence-audit")
    p.add_argument("--temperature", type=float, default=0.0)
    p.set_defaults(func=cmd_semantic_warning_audit)

    p = sub.add_parser("tabletop-replay-audit", help="Audit driver process-model tabletop replay package completeness and workflow utility")
    p.add_argument("--bundle-dir", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_tabletop_replay_audit)

    p = sub.add_parser("generate-cf-specs", help="Generate counterfactual HMI injection specs from templates for cases with not_reported HMI")
    p.add_argument("--cases", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--case-start", type=int, default=0)
    p.add_argument("--case-limit", type=int, default=None)
    p.set_defaults(func=cmd_generate_cf_specs)

    p = sub.add_parser("generate-counterfactual")
    p.add_argument("--cases", required=True)
    p.add_argument("--specs", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--case-start", type=int, default=0)
    p.add_argument("--case-limit", type=int, default=None)
    p.set_defaults(func=cmd_generate_counterfactual)

    p = sub.add_parser("counterfactual-eval")
    p.add_argument("--base-bundle-dir", required=True)
    p.add_argument("--cf-bundle-dir", required=True)
    p.add_argument("--specs", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_counterfactual_eval)

    p = sub.add_parser("pm-mediation-comparison", help="Compare direct/CoT/no-update/full replay for driver process-model mediation necessity")
    p.add_argument("--out", required=True)
    p.add_argument("--full-bundle-dir", required=True)
    p.add_argument("--direct-baseline-dir")
    p.add_argument("--generic-baseline-dir")
    p.add_argument("--no-update-bundle-dir")
    p.add_argument("--baseline-suite-dir")
    p.set_defaults(func=cmd_pm_mediation_comparison)

    p = sub.add_parser("missingness-profile", help="Export dataset & missingness profile for paper Table 1")
    p.add_argument("--cases", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--case-start", type=int, default=0)
    p.add_argument("--case-limit", type=int, default=None)
    p.set_defaults(func=cmd_missingness_profile)

    p = sub.add_parser("feedback-gap-report", help="Export missing HMI/driver/internal-ADS evidence gaps for tabletop replay and reporting/logging discussion")
    p.add_argument("--cases")
    p.add_argument("--bundle-dir")
    p.add_argument("--out", required=True)
    p.add_argument("--case-start", type=int, default=0)
    p.add_argument("--case-limit", type=int, default=None)
    p.set_defaults(func=cmd_feedback_gap_report)

    p = sub.add_parser("requirement-candidates", help="Generate analysis-derived HMI/logging requirement candidates from feedback gaps")
    p.add_argument("--gap-report")
    p.add_argument("--cases")
    p.add_argument("--bundle-dir")
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_requirement_candidates)

    p = sub.add_parser("evidence-requirement-candidates", help="Alias for requirement-candidates using paper-facing terminology")
    p.add_argument("--gap-report")
    p.add_argument("--cases")
    p.add_argument("--bundle-dir")
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_requirement_candidates)

    p = sub.add_parser("paper-manifest", help="Write a paper result manifest with frozen inputs, outputs, counts, and hashes")
    p.add_argument("--out", required=True)
    p.add_argument("--cases")
    p.add_argument("--bundle-dir")
    p.add_argument("--baseline-dir")
    p.add_argument("--cf-report")
    p.add_argument("--missingness-profile")
    p.add_argument("--evidence-audit")
    p.add_argument("--feedback-gap-report")
    p.add_argument("--requirement-candidates")
    p.set_defaults(func=cmd_paper_manifest)

    p = sub.add_parser("build-paper-sample", help="Build deterministic mixed-source paper sample")
    p.add_argument("--nhtsa-cases", required=True)
    p.add_argument("--ca-collision-cases", required=True)
    p.add_argument("--ca-disengagement-cases", required=True)
    p.add_argument("--out-cases", required=True)
    p.add_argument("--out-summary", required=True)
    p.add_argument("--n-nhtsa", type=int, default=20)
    p.add_argument("--n-collision", type=int, default=15)
    p.add_argument("--n-disengagement", type=int, default=15)
    p.set_defaults(func=cmd_build_paper_sample)

    p = sub.add_parser("build-takeover-sample", help="Build a deterministic ADS/takeover-related text sample")
    p.add_argument("--inputs", nargs="+", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--summary")
    p.add_argument("--n", type=int, default=10)
    p.set_defaults(func=cmd_build_takeover_sample)

    p = sub.add_parser("mine-narrative-evidence", help="Extract free-text narrative propositions and attach them as evidence")
    p.add_argument("--cases", required=True)
    p.add_argument("--out-cases", required=True)
    p.add_argument("--out-report", required=True)
    p.add_argument("--temperature", type=float, default=0.0)
    p.set_defaults(func=cmd_mine_narrative_evidence)

    p = sub.add_parser("role-disambiguate-cases", help="Use LLM source-span adjudication to disambiguate ego/actor/scene roles in ENV/ACTOR/CAR fields")
    p.add_argument("--cases", required=True)
    p.add_argument("--out-cases", required=True)
    p.add_argument("--out-report", required=True)
    p.add_argument("--temperature", type=float, default=0.0)
    p.set_defaults(func=cmd_role_disambiguate_cases)

    p = sub.add_parser("expert-preview-labels", help="Generate Codex Expert-0 preview labels for protocol debugging only")
    p.add_argument("--cases")
    p.add_argument("--packet-dir", help="Expert replay packet directory for v2 labels")
    p.add_argument("--out-labels", required=True)
    p.add_argument("--out-report", required=True)
    p.set_defaults(func=cmd_expert_preview_labels)

    p = sub.add_parser("export-expert-replay-packets", help="Export AAP V2 expert replay annotation packets from bundle outputs")
    p.add_argument("--bundle-dir", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_export_expert_replay_packets)

    p = sub.add_parser("replay-alignment-eval", help="Evaluate replay package alignment against expert replay labels and compute RIMS")
    p.add_argument("--bundle-dir", required=True)
    p.add_argument("--labels", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_replay_alignment_eval)

    p = sub.add_parser("richer-evidence-compare", help="Compare sparse and richer-evidence replay packages for evidence-density stress test")
    p.add_argument("--sparse-bundle-dir", required=True)
    p.add_argument("--richer-bundle-dir", required=True)
    p.add_argument("--pair-map", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_richer_evidence_compare)

    p = sub.add_parser("enrich-from-narrative", help="Use LLM to fill not_reported ENV/ACTOR/CAR fields from narrative text")
    p.add_argument("--cases", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_enrich_from_narrative)

    return parser


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
