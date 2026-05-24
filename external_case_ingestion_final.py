from __future__ import annotations
"""
external_case_ingestion.py

Standalone, publication-facing input module for converting external functional
scenario sources into the common case schema consumed by the STPA-HF engine.

Design rules
------------
1. This module never assigns STPA-HF labels: no boundary, no UCA, no vulnerability.
2. This module never imputes missing HMI, driver-state, or internal ADS facts.
3. Missing values are encoded as provenance='not_reported', not as evidence of absence.
4. Counterfactual assumptions are not part of this module; they are handled by the engine/evaluation layer.
5. Output cases are compatible with stpa_hf_dan_eswa_engine.py.
"""

import argparse
import csv
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse, unquote

import requests
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

SCHEMA_VERSION = "external_ingestion_v1.0"
ALLOWED_PROVENANCE = ["reported", "derived", "not_reported", "assumed_for_counterfactual"]

CA_DMV_COLLISION_INDEX_URL = "https://www.dmv.ca.gov/portal/vehicle-industry-services/autonomous-vehicles/autonomous-vehicle-collision-reports/"
CA_DMV_DISENGAGEMENT_INDEX_URL = "https://www.dmv.ca.gov/portal/vehicle-industry-services/autonomous-vehicles/disengagement-reports/"
NHTSA_SGO_URLS = {
    "ads": [
        "https://static.nhtsa.gov/odi/ffdd/sgo-2021-01/SGO-2021-01_Incident_Reports_ADS.csv",
        "https://static.nhtsa.gov/odi/ffdd/sgo-2021-01/Archive-2021-2025/SGO-2021-01_Incident_Reports_ADS.csv",
    ],
    "adas": [
        "https://static.nhtsa.gov/odi/ffdd/sgo-2021-01/SGO-2021-01_Incident_Reports_ADAS.csv",
        "https://static.nhtsa.gov/odi/ffdd/sgo-2021-01/Archive-2021-2025/SGO-2021-01_Incident_Reports_ADAS.csv",
    ],
    "other": [
        "https://static.nhtsa.gov/odi/ffdd/sgo-2021-01/SGO-2021-01_Incident_Reports_OTHER.csv",
        "https://static.nhtsa.gov/odi/ffdd/sgo-2021-01/Archive-2021-2025/SGO-2021-01_Incident_Reports_OTHER.csv",
    ],
}

FORBIDDEN_LABEL_KEYS = {
    "boundary_label", "gold_boundary_label", "expected_primary_axis",
    "dominant_uca", "gold_dominant_uca", "active_uca_set", "gold_active_uca_set",
    "update_vulnerability", "gold_update_vulnerability", "expected_update_vulnerability_family",
    "requirement_focus", "gold_requirement_focus", "label_scope",
}


class DataCurationError(RuntimeError):
    """Raised when an external source cannot be safely represented as a functional case."""


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
            raise DataCurationError(f"JSONL row must be an object at {p}:{line_no}")
        rows.append(obj)
    return rows


def write_jsonl(path: str | Path, rows: Iterable[Dict[str, Any]]) -> None:
    p = Path(path)
    ensure_dir(p.parent)
    with p.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def stable_digest(obj: Any, n: int = 16) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:n]


def normalize_token(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")



def find_forbidden_label_keys(obj: Any, prefix: str = "") -> List[str]:
    """Recursively find gold/expected-output keys that must never enter ingestion outputs."""
    hits: List[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            path = f"{prefix}.{k}" if prefix else str(k)
            if k in FORBIDDEN_LABEL_KEYS:
                hits.append(path)
            hits.extend(find_forbidden_label_keys(v, path))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            hits.extend(find_forbidden_label_keys(v, f"{prefix}[{i}]"))
    return hits


def assert_no_label_leakage(obj: Any, *, context: str = "object") -> None:
    hits = find_forbidden_label_keys(obj)
    if hits:
        raise DataCurationError(f"Forbidden label-like keys in {context}; ingestion must remain label-free: {hits[:20]}")


def file_sha256(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _safe_filename_from_url(url: str, fallback: str) -> str:
    parsed = urlparse(url)
    name = unquote(Path(parsed.path).name) or fallback
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._") or fallback
    return name


def fetch_text(url: str, timeout_s: int = 60) -> str:
    resp = requests.get(url, timeout=timeout_s, headers={"User-Agent": "STPA-HF-ESWA-ingestion/1.0"})
    resp.raise_for_status()
    return resp.text


def discover_links(index_url: str, *, contains_any: Sequence[str] = (), suffix_any: Sequence[str] = ()) -> List[str]:
    html = fetch_text(index_url)
    links: List[str] = []
    for href in re.findall(r"href=[\"']([^\"']+)[\"']", html, flags=re.I):
        url = urljoin(index_url, href)
        lower = url.lower()
        if contains_any and not any(x.lower() in lower for x in contains_any):
            continue
        if suffix_any and not any(lower.split("?")[0].endswith(s.lower()) for s in suffix_any) and "/portal/file/" not in lower:
            continue
        if url not in links:
            links.append(url)
    return links


def discover_ca_dmv_collision_pdf_links(limit: Optional[int] = None) -> List[str]:
    links = discover_links(
        CA_DMV_COLLISION_INDEX_URL,
        contains_any=["collision", "ol-316", "autonomous"],
        suffix_any=[".pdf"],
    )
    pdf_like = [u for u in links if ".pdf" in u.lower() or "/portal/file/" in u.lower()]
    return pdf_like[:limit] if limit else pdf_like


def discover_ca_dmv_disengagement_links() -> List[str]:
    return discover_links(
        CA_DMV_DISENGAGEMENT_INDEX_URL,
        contains_any=["disengagement", "autonomous", "csv", "xlsx", "zip"],
        suffix_any=[".csv", ".xlsx", ".xls", ".zip", ".pdf"],
    )


def download_url(url: str, out_dir: str | Path, *, source_dataset: str, preferred_name: Optional[str] = None, timeout_s: int = 120) -> Dict[str, Any]:
    out = Path(out_dir)
    ensure_dir(out)
    started = datetime.now(timezone.utc).isoformat()
    filename = preferred_name or _safe_filename_from_url(url, stable_digest(url, 12))
    target = out / filename
    row: Dict[str, Any] = {
        "source_dataset": source_dataset,
        "url": url,
        "local_path": str(target),
        "download_time_utc": started,
        "status": "pending",
    }
    try:
        resp = requests.get(url, timeout=timeout_s, headers={"User-Agent": "STPA-HF-ESWA-ingestion/1.0"})
        resp.raise_for_status()
        ctype = resp.headers.get("content-type", "")
        if target.suffix == "" and "pdf" in ctype.lower():
            target = target.with_suffix(".pdf")
            row["local_path"] = str(target)
        elif target.suffix == "" and "csv" in ctype.lower():
            target = target.with_suffix(".csv")
            row["local_path"] = str(target)
        target.write_bytes(resp.content)
        row.update({
            "status": "downloaded",
            "http_status": resp.status_code,
            "content_type": ctype,
            "bytes": len(resp.content),
            "sha256": file_sha256(target),
        })
    except Exception as exc:
        row.update({"status": "failed", "error": repr(exc)})
    return row


def download_first_available(urls: Sequence[str], out_dir: str | Path, *, source_dataset: str, preferred_name: str) -> Dict[str, Any]:
    failures: List[Dict[str, Any]] = []
    for url in urls:
        row = download_url(url, out_dir, source_dataset=source_dataset, preferred_name=preferred_name)
        if row.get("status") == "downloaded":
            row["attempted_urls"] = list(urls)
            return row
        failures.append(row)
    return {
        "source_dataset": source_dataset,
        "url": urls[0] if urls else "",
        "local_path": str(Path(out_dir) / preferred_name),
        "download_time_utc": datetime.now(timezone.utc).isoformat(),
        "status": "failed",
        "attempted_urls": list(urls),
        "failures": failures,
    }

@dataclass
class EvidenceValue:
    value: Any
    provenance: str = "reported"
    visibility: str = "source_reported"
    certainty: str = "high"
    source_text: str = ""
    derivation_basis: str = ""
    is_driver_visible: Any = "unknown"
    use_as_negative_evidence: bool = False
    timestamp_ms: Optional[int] = None
    persistence_ms: Optional[int] = None

    def __post_init__(self) -> None:
        if self.provenance not in ALLOWED_PROVENANCE:
            raise DataCurationError(f"Invalid provenance: {self.provenance}")
        if self.provenance == "not_reported":
            self.value = "not_reported"
            self.visibility = "not_in_source"
            self.certainty = "unknown"
            self.is_driver_visible = False
            self.use_as_negative_evidence = False


def ev(value: Any, provenance: str = "reported", **kwargs: Any) -> Dict[str, Any]:
    """Create an evidence value object with explicit provenance."""
    if value is None or str(value).strip() == "":
        return nr()
    return asdict(EvidenceValue(value=value, provenance=provenance, **kwargs))


def nr() -> Dict[str, Any]:
    """Create an explicit not-reported evidence object."""
    return asdict(EvidenceValue(value="not_reported", provenance="not_reported"))


def unwrap_value(x: Any) -> Any:
    if isinstance(x, dict) and "value" in x:
        return x.get("value")
    return x


def wrap_if_plain(value: Any, default_provenance: str = "reported") -> Dict[str, Any]:
    if isinstance(value, dict) and "value" in value and "provenance" in value:
        return value
    if value is None or str(value).strip() == "":
        return nr()
    return ev(value, provenance=default_provenance)


@dataclass
class RawFunctionalRecord:
    """Source-normalized, label-free functional scenario record.

    The record is intentionally upstream of STPA-HF labels. It only captures
    reported or conservatively derived source facts.
    """

    source_dataset: str
    source_record_id: str
    source_reference: str = ""
    raw_case_summary: str = ""
    narrative: str = ""
    event_type: str = "unknown"
    automation_context: str = "unknown"
    road_context: str = "not_reported"
    roadway_type: str = "not_reported"
    roadway_surface: str = "not_reported"
    roadway_description: str = "not_reported"
    posted_speed_limit: str = "not_reported"
    precrash_speed: str = "not_reported"
    within_odd: str = "not_reported"
    conflict_actor: str = "not_reported"
    pre_event_trigger: str = "not_reported"
    reported_system_issue: str = "not_reported"
    reported_intervention: str = "not_reported"
    reported_consequence: str = "unknown"
    weather: str = "not_reported"
    weather_clear: str = ""
    weather_rain: str = ""
    weather_snow: str = ""
    weather_fog: str = ""
    lighting: str = "not_reported"
    curation_notes: str = ""
    extra_fields: Dict[str, Any] = field(default_factory=dict)
    provenance_map: Dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, obj: Dict[str, Any]) -> "RawFunctionalRecord":
        assert_no_label_leakage(obj, context="raw functional record")
        known = {name for name in cls.__dataclass_fields__.keys()}  # type: ignore[attr-defined]
        base = {k: obj.get(k) for k in known if k in obj}
        extra = {k: v for k, v in obj.items() if k not in known}
        if "extra_fields" not in base:
            base["extra_fields"] = extra
        return cls(**base)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def not_reported_group(fields: Sequence[str]) -> Dict[str, Dict[str, Any]]:
    return {k: nr() for k in fields}


def _reported_or_nr(value: Any, *, source_text: str = "") -> Dict[str, Any]:
    if value is None or str(value).strip() == "" or normalize_token(value) in {"not_reported", "unknown", "na", "n/a", "none"}:
        return nr()
    return ev(value, "reported", source_text=source_text)


def raw_record_to_functional_case(record: RawFunctionalRecord) -> Dict[str, Any]:
    """Map a raw functional record to ENV/ACTOR/CAR/HMI/CABIN without labels.

    This mapper only performs conservative field mapping. It does not infer
    commitment boundary, UCA, update vulnerability, HMI display content, driver
    state, or internal ADS confidence.
    """
    rid = record.source_record_id or stable_digest(record.to_dict(), 10)
    road = normalize_token(record.road_context)
    roadway_type = normalize_token(record.roadway_type)
    roadway_desc = normalize_token(record.roadway_description)
    weather = normalize_token(record.weather)
    lighting = normalize_token(record.lighting)
    trigger = normalize_token(record.pre_event_trigger)
    actor = normalize_token(record.conflict_actor)
    issue = normalize_token(record.reported_system_issue)
    intervention = normalize_token(record.reported_intervention)
    automation = normalize_token(record.automation_context)
    precrash_speed = normalize_token(record.precrash_speed)
    within_odd = normalize_token(record.within_odd)

    # Synthesize weather from multi-column flags if single Weather column is empty
    resolved_weather = record.weather
    if normalize_token(resolved_weather) in {"not_reported", "unknown", ""}:
        if record.weather_rain == "Y":
            resolved_weather = "rain"
        elif record.weather_snow == "Y":
            resolved_weather = "snow"
        elif record.weather_fog == "Y":
            resolved_weather = "fog"
        elif record.weather_clear == "Y":
            resolved_weather = "clear"

    # Determine intersection from Roadway Type
    is_intersection = "intersection" in roadway_type or "intersection" in road
    # Determine construction from Roadway Description
    is_construction = any(k in roadway_desc for k in ["work_zone", "work zone", "construction"]) or any(k in road for k in ["construction", "work_zone", "workzone", "work"])

    env = {
        "visibility": _reported_or_nr(record.lighting, source_text="lighting"),
        "weather": _reported_or_nr(resolved_weather, source_text="weather/weather_flags"),
        "intersection_type": ev(roadway_type, "reported", source_text="Roadway Type") if is_intersection else nr(),
        "markings_quality": _reported_or_nr(record.roadway_surface, source_text="Roadway Surface") if normalize_token(record.roadway_surface) not in {"not_reported", "unknown", ""} else nr(),
        "road_geometry": _reported_or_nr(record.roadway_type, source_text="Roadway Type"),
        "lane_topology": ev("merge", "derived", derivation_basis="road_context/pre_event_trigger mentions merge or lane change") if any(k in road or k in trigger for k in ["merge", "lane_change", "lane"]) else nr(),
        "construction_state": ev("active", "derived", derivation_basis="Roadway Description indicates work zone") if is_construction else ev("none", "derived", derivation_basis="Roadway Description: no unusual conditions") if "no_unusual" in roadway_desc or "no unusual" in roadway_desc else nr(),
        "cut_in_event": ev("active", "derived", derivation_basis="pre_event_trigger mentions cut-in") if "cut" in trigger else nr(),
        "pedestrian_crossing_event": ev("possible", "derived", derivation_basis="conflict_actor mentions pedestrian") if "pedestrian" in actor else nr(),
    }

    actor_group = {
        "primary_type": _reported_or_nr(record.conflict_actor, source_text="conflict_actor"),
        "primary_intent": _reported_or_nr(record.pre_event_trigger, source_text="pre_event_trigger"),
        "primary_observability": nr(),
        "secondary_pressure": nr(),
        "prediction_uncertainty": ev("high", "derived", derivation_basis="actor/trigger reported but behavior details absent") if actor != "not_reported" or trigger != "not_reported" else nr(),
    }

    # Derive deceleration_behavior from precrash speed
    decel = nr()
    if precrash_speed not in {"not_reported", "unknown", ""}:
        try:
            speed_val = int(precrash_speed)
            if speed_val == 0:
                decel = ev("stopped", "derived", derivation_basis=f"SV Precrash Speed={speed_val} MPH")
            elif speed_val <= 5:
                decel = ev("decelerating", "derived", derivation_basis=f"SV Precrash Speed={speed_val} MPH (low speed)")
            else:
                decel = ev("maintaining_speed", "derived", derivation_basis=f"SV Precrash Speed={speed_val} MPH")
        except (ValueError, TypeError):
            pass

    # Derive reported_system_issue from Within ODD
    sys_issue = _reported_or_nr(record.reported_system_issue, source_text="reported_system_issue")
    if normalize_token(record.reported_system_issue) in {"not_reported", "unknown", ""} and within_odd not in {"not_reported", "unknown", ""}:
        if within_odd in {"no", "no, see narrative"}:
            sys_issue = ev("odd_departure", "derived", derivation_basis=f"Within ODD?={record.within_odd}")

    car = {
        "automation_context": _reported_or_nr(record.automation_context, source_text="automation_context"),
        "event_type": _reported_or_nr(record.event_type, source_text="event_type"),
        "reported_system_issue": sys_issue,
        "reported_intervention": _reported_or_nr(record.reported_intervention, source_text="reported_intervention"),
        "ads_mode": ev("automation_involved", "derived", derivation_basis="automation_context/source dataset reports automation involvement") if automation not in {"unknown", "not_reported", ""} else nr(),
        "time_budget_to_handover": nr(),
        "perception_confidence": nr(),
        "planner_confidence": nr(),
        "lane_keeping_behavior": nr(),
        "deceleration_behavior": decel,
    }

    # Critical rule: HMI and driver/cabin state are not imputed from incident reports.
    hmi = not_reported_group([
        "mode_state_display",
        "capability_boundary_hint",
        "time_budget_indicator",
        "require_ack",
        "trajectory_display_latency",
    ])
    cabin = not_reported_group(["pressure", "distraction"])

    case = {
        "case_id": f"external_{record.source_dataset}_{rid}",
        "case_source": "external_functional",
        "schema_version": SCHEMA_VERSION,
        "source_metadata": {
            "source_dataset": record.source_dataset,
            "source_record_id": rid,
            "source_reference": record.source_reference,
            "raw_case_summary": record.raw_case_summary,
            "curation_notes": record.curation_notes,
            "reported_consequence": record.reported_consequence,
            "provenance_map": record.provenance_map,
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
        "latent_events": [{"ENV": env, "ACTOR": actor_group, "CAR": car, "HMI": hmi, "CABIN": cabin}],
        "missingness_policy": {
            "not_reported_is_not_absence": True,
            "forbid_hmi_imputation": True,
            "forbid_driver_state_imputation": True,
            "forbid_internal_ads_imputation": True,
        },
    }
    case["case_id"] = f"external_{record.source_dataset}_{stable_digest(case, 12)}"
    return case


def load_functional_records(path: str | Path) -> List[RawFunctionalRecord]:
    return [RawFunctionalRecord.from_dict(row) for row in read_jsonl(path)]


def load_ca_dmv_collision_curated(path: str | Path) -> List[RawFunctionalRecord]:
    """Load manually curated CA DMV collision records.

    Input is JSONL because DMV collision reports are usually narrative/PDF-like.
    Each row may already follow RawFunctionalRecord or use a subset of its fields.
    """
    records: List[RawFunctionalRecord] = []
    for row in read_jsonl(path):
        row = dict(row)
        row.setdefault("source_dataset", "ca_dmv_collision")
        row.setdefault("event_type", "collision")
        row.setdefault("automation_context", "AV_testing")
        row.setdefault("curation_notes", "Curated from CA DMV autonomous vehicle collision report; HMI/driver state not imputed.")
        records.append(RawFunctionalRecord.from_dict(row))
    return records


def _csv_yes(value: Any) -> bool:
    return normalize_token(value) in {"yes", "y", "1", "true", "x"}


def _csv_first_yes(row: Dict[str, Any], fields: Sequence[str]) -> Optional[str]:
    for field_name in fields:
        if _csv_yes(row.get(field_name)):
            return field_name
    return None


def _derive_ca_dmv_actor(row: Dict[str, Any], narrative: str) -> str:
    lower = narrative.lower()
    if _csv_yes(row.get("Pedestrian Involved")) or _csv_yes(row.get("Pedestrian_2")) or "pedestrian" in lower:
        return "Pedestrian"
    if _csv_yes(row.get("Bicyclist Involved")) or _csv_yes(row.get("Bicyclist_2")) or any(k in lower for k in ["bicyclist", "bicycle", "cyclist"]):
        return "Bicyclist"
    if any(k in lower for k in ["scooter", "scooterist", "motorcycl"]):
        return "Two-wheeler"
    if _csv_yes(row.get("Parked Vehicles")) or "parked vehicle" in lower:
        return "Parked vehicle"
    if _csv_yes(row.get("Other_2")) or _csv_yes(row.get("Other")):
        return "Other, see Narrative"
    return row.get("Model_2") or "Vehicle"


def _derive_ca_dmv_trigger(row: Dict[str, Any], narrative: str) -> str:
    lower = narrative.lower()
    if _csv_yes(row.get("Stopped In Traffic")):
        return "Stopped"
    if _csv_yes(row.get("Stopped In Traffic_2")):
        return "Other party stopped"
    if "rear-ended" in lower or "struck from behind" in lower or "approaching from behind" in lower:
        return "Rear-end / struck from behind"
    if "lane change" in lower or "changed lanes" in lower or "merge" in lower:
        return "Lane change or merge"
    if "left turn" in lower:
        return "Making left turn"
    if "right turn" in lower:
        return "Making right turn"
    if _csv_yes(row.get("Moving")):
        return "Moving"
    return "not_reported"


def load_ca_dmv_collision_augmented_csv(path: str | Path, mode_filter: str = "autonomous") -> List[RawFunctionalRecord]:
    """Load a third-party CA DMV-derived collision CSV as functional records.

    This loader is for curated/enhanced tabular datasets derived from CA DMV
    collision PDFs, such as the Zenodo CA_AV_Collision_2019-2024.csv release.
    It must not be described as an official DMV CSV. HMI, driver-state, and
    internal ADS fields are still intentionally left to the downstream
    not_reported policy.
    """
    records: List[RawFunctionalRecord] = []
    with Path(path).open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for idx, row in enumerate(reader, start=1):
            autonomous = _csv_yes(row.get("Autonomous Mode"))
            conventional = _csv_yes(row.get("Conventional Mode"))
            if mode_filter == "autonomous" and not autonomous:
                continue
            if mode_filter == "conventional" and not conventional:
                continue

            narrative = (row.get("Accident Detail Description") or "").strip()
            text_blob = " | ".join(str(v) for v in row.values() if str(v).strip())[:3000]
            city = (row.get("City") or "").strip()
            address = (row.get("Address Of Accident") or "").strip()
            date = (row.get("Date Of Accident") or "").strip()
            manufacturer = (row.get("Manufacturers Name") or row.get("Business Name") or "unknown_mfr").strip()
            source_row_id = row.get("") or f"row_{idx}"

            roadway_type = "Intersection" if _csv_yes(row.get("Intersection")) else "Street"
            road_notes: List[str] = []
            if _csv_yes(row.get("Narrow Roadway")):
                road_notes.append("narrow_roadway")
            if _csv_yes(row.get("Parked Vehicles")):
                road_notes.append("parked_vehicles_present")
            if _csv_yes(row.get("Struck by Others")):
                road_notes.append("struck_by_other_party")

            consequence = "property_damage"
            if "injur" in narrative.lower():
                consequence = "injury_reported_or_mentioned"
            elif _csv_first_yes(row, ["Damage: Major", "Damage: Moderate", "Damage: Minor"]):
                consequence = _csv_first_yes(row, ["Damage: Major", "Damage: Moderate", "Damage: Minor"]) or "property_damage"

            raw = {
                "source_dataset": "ca_dmv_collision_augmented",
                "source_record_id": f"{source_row_id}_{stable_digest({'date': date, 'mfr': manufacturer, 'address': address, 'narrative': narrative}, 8)}",
                "source_reference": "Zenodo DOI 10.5281/zenodo.15937591; derived from CA DMV AV collision reports",
                "raw_case_summary": text_blob,
                "narrative": narrative[:3000],
                "event_type": "collision",
                "automation_context": "ADS" if autonomous else "conventional_AV_testing" if conventional else "AV_testing_unknown_mode",
                "road_context": " | ".join(x for x in [address, city] if x) or "not_reported",
                "roadway_type": roadway_type,
                "roadway_surface": "not_reported",
                "roadway_description": "; ".join(road_notes) if road_notes else "not_reported",
                "conflict_actor": _derive_ca_dmv_actor(row, narrative),
                "pre_event_trigger": _derive_ca_dmv_trigger(row, narrative),
                "reported_consequence": consequence,
                "weather": "not_reported",
                "lighting": "not_reported",
                "curation_notes": "Auto-ingested from third-party augmented CA DMV collision CSV; not an official DMV CSV; HMI/driver/internal ADS not imputed.",
                "extra_fields": row,
                "provenance_map": {
                    "source_type": "third_party_augmented_csv",
                    "derived_from": "CA DMV AV collision report PDFs",
                    "mode_filter": mode_filter,
                },
            }
            records.append(RawFunctionalRecord.from_dict(raw))
    return records


def _read_csv_rows_with_fallback(path: str | Path) -> List[Dict[str, Any]]:
    last_exc: Optional[Exception] = None
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            with Path(path).open("r", encoding=encoding, newline="") as f:
                return [dict(row) for row in csv.DictReader(f)]
        except UnicodeDecodeError as exc:
            last_exc = exc
    raise DataCurationError(f"Could not decode CSV {path}: {last_exc!r}")


def _row_get_contains(row: Dict[str, Any], needle: str) -> str:
    needle_norm = needle.lower()
    for key, value in row.items():
        if key and needle_norm in key.lower():
            return str(value or "").strip()
    return ""


def _derive_disengagement_issue(description: str, initiator: str) -> str:
    lower = description.lower()
    if not description.strip():
        return "not_reported"
    if any(k in lower for k in ["collision", "crash", "contact"]):
        return "collision_or_contact_related_disengagement"
    if any(k in lower for k in ["perception", "object detection", "lane detection", "lidar", "radar", "camera", "tracking"]):
        return "perception_or_detection_issue"
    if any(k in lower for k in ["planning", "planner", "trajectory", "maneuver", "route", "lane change"]):
        return "planning_or_trajectory_issue"
    if any(k in lower for k in ["software", "module", "latency", "diagnostic", "fault", "error", "failure", "fail-safe", "failsafe"]):
        return "software_or_system_fault"
    if any(k in lower for k in ["map", "locali", "navigation"]):
        return "map_localization_or_navigation_issue"
    if any(k in lower for k in ["traffic", "vehicle", "pedestrian", "bicycl", "obstacle", "debris"]):
        return "external_actor_or_traffic_complexity"
    if "av system" in initiator.lower():
        return "av_system_initiated_disengagement"
    return "technology_failure_or_other_concern"


def _derive_disengagement_trigger(description: str, initiator: str) -> str:
    lower = description.lower()
    if "test driver" in initiator.lower() or "safety driver" in lower or "operator intervened" in lower:
        return "test_driver_or_operator_intervention"
    if "av system" in initiator.lower() or "fail-safe" in lower or "failsafe" in lower:
        return "av_system_disengagement"
    if any(k in lower for k in ["brake", "steering", "take over", "takeover", "intervened", "disengaged"]):
        return "manual_control_intervention"
    return initiator or "disengagement"


def _load_ca_dmv_disengagement_csv_file(path: str | Path, source_tag: str = "ca_dmv_disengagement") -> List[RawFunctionalRecord]:
    records: List[RawFunctionalRecord] = []
    rows = _read_csv_rows_with_fallback(path)
    year_hint = next((part for part in Path(path).parts if str(part).isdigit() and len(str(part)) == 4), "")
    driverless_hint = "driverless" in Path(path).name.lower()
    for idx, row in enumerate(rows, start=1):
        if not any(str(v).strip() for v in row.values()):
            continue
        manufacturer = str(row.get("Manufacturer") or row.get("Manufacturer Name") or "").strip()
        permit = str(row.get("Permit Number") or "").strip()
        date = str(row.get("DATE") or row.get("Date") or "").strip()
        vin = str(_row_get_contains(row, "VIN") or "").strip()
        driver_present = _row_get_contains(row, "DRIVER PRESENT")
        driverless_capable = _row_get_contains(row, "WITHOUT A DRIVER")
        initiator = _row_get_contains(row, "DISENGAGEMENT INITIATED BY")
        location = _row_get_contains(row, "DISENGAGEMENT\nLOCATION") or _row_get_contains(row, "LOCATION")
        description = _row_get_contains(row, "DESCRIPTION OF FACTS")
        record_seed = {
            "file": str(path),
            "idx": idx,
            "manufacturer": manufacturer,
            "date": date,
            "vin": vin,
            "description": description[:500],
        }
        raw = {
            "source_dataset": source_tag,
            "source_record_id": f"{year_hint or 'unknown_year'}_{idx}_{stable_digest(record_seed, 10)}",
            "source_reference": str(path),
            "raw_case_summary": " | ".join(str(v) for v in row.values() if str(v).strip())[:3000],
            "narrative": description[:3000],
            "event_type": "disengagement",
            "automation_context": "driverless_AV_testing" if driverless_hint or normalize_token(driver_present) == "no" else "AV_testing",
            "road_context": location or "not_reported",
            "roadway_type": location or "not_reported",
            "roadway_surface": "not_reported",
            "roadway_description": "not_reported",
            "conflict_actor": "not_reported",
            "pre_event_trigger": _derive_disengagement_trigger(description, initiator),
            "reported_system_issue": _derive_disengagement_issue(description, initiator),
            "reported_intervention": initiator or "disengagement_reported",
            "reported_consequence": "disengagement_reported",
            "weather": "not_reported",
            "lighting": "not_reported",
            "curation_notes": "Auto-ingested from CA DMV official autonomous vehicle disengagement report CSV; HMI/driver cognition/internal ADS confidence not imputed.",
            "extra_fields": row,
            "provenance_map": {
                "source_type": "official_ca_dmv_disengagement_csv",
                "year_hint": year_hint,
                "driver_present": driver_present,
                "driverless_capable": driverless_capable,
                "manufacturer": manufacturer,
                "permit_number": permit,
            },
        }
        records.append(RawFunctionalRecord.from_dict(raw))
    return records


def load_ca_dmv_disengagement_csv(path: str | Path, overrides_path: Optional[str | Path] = None) -> List[RawFunctionalRecord]:
    """Load CA DMV disengagement CSV-like records with optional JSONL overrides."""
    overrides: Dict[str, Dict[str, Any]] = {}
    if overrides_path:
        for row in read_jsonl(overrides_path):
            key = str(row.get("source_record_id", ""))
            if key:
                overrides[key] = row

    records = _load_ca_dmv_disengagement_csv_file(path)
    if overrides:
        patched: List[RawFunctionalRecord] = []
        for rec in records:
            raw = rec.to_dict()
            raw.update(overrides.get(str(raw.get("source_record_id")), {}))
            patched.append(RawFunctionalRecord.from_dict(raw))
        return patched
    return records


def load_ca_dmv_disengagement_dir(path: str | Path) -> List[RawFunctionalRecord]:
    records: List[RawFunctionalRecord] = []
    for csv_path in sorted(Path(path).rglob("*.csv")):
        name = csv_path.name.lower()
        if "disengagement" not in name:
            continue
        records.extend(_load_ca_dmv_disengagement_csv_file(csv_path))
    return records


def load_nhtsa_sgo_csv(ads_csv: str | Path, adas_csv: Optional[str | Path] = None, curated_path: Optional[str | Path] = None) -> List[RawFunctionalRecord]:
    """Load NHTSA SGO ADS and optional L2 ADAS CSV files.

    The output is still functional scenario input, not SAE L3 ground truth.
    """
    curated: Dict[str, Dict[str, Any]] = {}
    if curated_path:
        for row in read_jsonl(curated_path):
            key = str(row.get("source_record_id", ""))
            if key:
                curated[key] = row

    def _load(path: str | Path, automation_context: str) -> List[RawFunctionalRecord]:
        out: List[RawFunctionalRecord] = []
        with Path(path).open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for idx, row in enumerate(reader, start=1):
                record_id = row.get("Report ID") or row.get("report_id") or row.get("Incident ID") or f"{automation_context}_{idx}"
                text_blob = " | ".join(str(v) for v in row.values() if v)
                conflict_actor = row.get("Crash With") or row.get("Object Struck") or row.get("CP Pre-Crash Movement") or "not_reported"
                raw = {
                    "source_dataset": "nhtsa_sgo",
                    "source_record_id": str(record_id),
                    "source_reference": "NHTSA SGO CSV",
                    "raw_case_summary": text_blob[:2000],
                    "narrative": (row.get("Narrative") or "")[:3000],
                    "event_type": "crash",
                    "automation_context": automation_context,
                    "conflict_actor": conflict_actor or "not_reported",
                    "pre_event_trigger": row.get("Pre-Crash Movement") or row.get("SV Pre-Crash Movement") or "not_reported",
                    "reported_consequence": row.get("Highest Injury Severity Alleged") or row.get("Highest Injury Severity") or "unknown",
                    "weather": row.get("Weather") or "not_reported",
                    "weather_clear": row.get("Weather - Clear") or "",
                    "weather_rain": row.get("Weather - Rain") or "",
                    "weather_snow": row.get("Weather - Snow") or "",
                    "weather_fog": row.get("Weather - Fog/Smoke") or "",
                    "lighting": row.get("Lighting") or "not_reported",
                    "roadway_type": row.get("Roadway Type") or "not_reported",
                    "roadway_surface": row.get("Roadway Surface") or "not_reported",
                    "roadway_description": row.get("Roadway Description") or "not_reported",
                    "posted_speed_limit": row.get("Posted Speed Limit (MPH)") or "not_reported",
                    "precrash_speed": row.get("SV Precrash Speed (MPH)") or row.get("SV Pre-crash Speed (MPH)") or "not_reported",
                    "within_odd": row.get("Within ODD?") or "not_reported",
                    "curation_notes": "Auto-ingested from NHTSA SGO CSV; verify field mapping before publication.",
                    "extra_fields": row,
                }
                raw.update(curated.get(str(record_id), {}))
                out.append(RawFunctionalRecord.from_dict(raw))
        return out

    records = _load(ads_csv, "ADS")
    if adas_csv:
        records.extend(_load(adas_csv, "L2_ADAS"))
    return records


def export_raw_records(records: Sequence[RawFunctionalRecord], output_path: str | Path) -> List[Dict[str, Any]]:
    rows = [r.to_dict() for r in records]
    for row in rows:
        assert_no_label_leakage(row, context="raw record export")
    write_jsonl(output_path, rows)
    return rows


def export_external_cases(records: Sequence[RawFunctionalRecord], output_path: str | Path) -> List[Dict[str, Any]]:
    cases = [raw_record_to_functional_case(r) for r in records]
    for case in cases:
        assert_no_label_leakage(case, context="external functional case export")
    write_jsonl(output_path, cases)
    return cases


def load_external_cases(path: str | Path) -> List[Dict[str, Any]]:
    return read_jsonl(path)


def build_records_from_sources(args: argparse.Namespace) -> List[RawFunctionalRecord]:
    records: List[RawFunctionalRecord] = []
    if args.functional_records:
        records.extend(load_functional_records(args.functional_records))
    if args.ca_dmv_collision:
        records.extend(load_ca_dmv_collision_curated(args.ca_dmv_collision))
    if args.ca_dmv_collision_csv:
        records.extend(load_ca_dmv_collision_augmented_csv(args.ca_dmv_collision_csv, args.ca_dmv_collision_csv_mode))
    if args.ca_dmv_disengagement:
        records.extend(load_ca_dmv_disengagement_csv(args.ca_dmv_disengagement, args.ca_dmv_disengagement_overrides))
    if args.ca_dmv_disengagement_dir:
        records.extend(load_ca_dmv_disengagement_dir(args.ca_dmv_disengagement_dir))
    if args.nhtsa_sgo_ads:
        records.extend(load_nhtsa_sgo_csv(args.nhtsa_sgo_ads, args.nhtsa_sgo_adas, args.nhtsa_sgo_curated))
    return records


def cmd_build_records(args: argparse.Namespace) -> None:
    records = build_records_from_sources(args)
    rows = export_raw_records(records, args.out)
    print(json.dumps({"num_records": len(rows), "out": args.out}, ensure_ascii=False, indent=2))


def cmd_build_cases(args: argparse.Namespace) -> None:
    records = load_functional_records(args.records)
    cases = export_external_cases(records, args.out)
    print(json.dumps({"num_records": len(records), "num_cases": len(cases), "out": args.out}, ensure_ascii=False, indent=2))


def cmd_build_external_cases(args: argparse.Namespace) -> None:
    records = build_records_from_sources(args)
    if args.records_out:
        export_raw_records(records, args.records_out)
    cases = export_external_cases(records, args.out)
    print(json.dumps({"num_records": len(records), "num_cases": len(cases), "records_out": args.records_out, "out": args.out}, ensure_ascii=False, indent=2))


def cmd_write_templates(args: argparse.Namespace) -> None:
    ensure_dir(Path(args.out_dir))
    curated = {
        "source_dataset": "ca_dmv_collision",
        "source_record_id": "example_collision_001",
        "source_reference": "source file or URL",
        "raw_case_summary": "Brief source-grounded narrative. Do not add HMI or driver-state assumptions.",
        "event_type": "collision",
        "automation_context": "AV_testing",
        "road_context": "urban_intersection",
        "conflict_actor": "vehicle",
        "pre_event_trigger": "lane_change_or_cut_in",
        "reported_system_issue": "not_reported",
        "reported_intervention": "not_reported",
        "reported_consequence": "property_damage",
        "weather": "not_reported",
        "lighting": "not_reported",
        "curation_notes": "Template row. Fill only source-supported content.",
    }
    write_jsonl(Path(args.out_dir) / "ca_dmv_collision_curated_template.jsonl", [curated])
    write_json(Path(args.out_dir) / "README_ingestion_schema.json", {
        "schema_version": SCHEMA_VERSION,
        "principle": "The ingestion module creates functional cases without STPA-HF labels and without HMI/driver/internal-ADS imputation.",
        "raw_functional_record_fields": list(RawFunctionalRecord.__dataclass_fields__.keys()),  # type: ignore[attr-defined]
    })
    print(json.dumps({"out_dir": args.out_dir}, ensure_ascii=False, indent=2))



def cmd_discover_sources(args: argparse.Namespace) -> None:
    discovery: Dict[str, Any] = {
        "ca_dmv_collision_index_url": CA_DMV_COLLISION_INDEX_URL,
        "ca_dmv_disengagement_index_url": CA_DMV_DISENGAGEMENT_INDEX_URL,
        "nhtsa_sgo_urls": NHTSA_SGO_URLS,
    }
    if args.ca_dmv_collision:
        discovery["ca_dmv_collision_links"] = discover_ca_dmv_collision_pdf_links(limit=args.collision_limit)
    if args.ca_dmv_disengagement:
        discovery["ca_dmv_disengagement_links"] = discover_ca_dmv_disengagement_links()
    write_json(args.out, discovery)
    print(json.dumps({"out": args.out, "keys": list(discovery.keys())}, ensure_ascii=False, indent=2))


def cmd_download_official(args: argparse.Namespace) -> None:
    out_dir = Path(args.out_dir)
    ensure_dir(out_dir)
    manifest: List[Dict[str, Any]] = []

    if args.nhtsa_sgo:
        nhtsa_dir = out_dir / "nhtsa_sgo"
        ensure_dir(nhtsa_dir)
        manifest.append(download_first_available(NHTSA_SGO_URLS["ads"], nhtsa_dir, source_dataset="nhtsa_sgo_ads", preferred_name="SGO-2021-01_Incident_Reports_ADS.csv"))
        manifest.append(download_first_available(NHTSA_SGO_URLS["adas"], nhtsa_dir, source_dataset="nhtsa_sgo_adas", preferred_name="SGO-2021-01_Incident_Reports_ADAS.csv"))
        if args.include_nhtsa_other:
            manifest.append(download_first_available(NHTSA_SGO_URLS["other"], nhtsa_dir, source_dataset="nhtsa_sgo_other", preferred_name="SGO-2021-01_Incident_Reports_OTHER.csv"))

    if args.ca_dmv_collision:
        collision_dir = out_dir / "ca_dmv_collision"
        ensure_dir(collision_dir)
        links = discover_ca_dmv_collision_pdf_links(limit=args.collision_limit)
        for i, url in enumerate(links, start=1):
            manifest.append(download_url(url, collision_dir, source_dataset="ca_dmv_collision", preferred_name=None))
        write_jsonl(collision_dir / "ca_dmv_collision_manifest.jsonl", manifest)

    if args.discover_dmv_disengagement:
        links = discover_ca_dmv_disengagement_links()
        manifest.append({
            "source_dataset": "ca_dmv_disengagement",
            "url": CA_DMV_DISENGAGEMENT_INDEX_URL,
            "local_path": "",
            "download_time_utc": datetime.now(timezone.utc).isoformat(),
            "status": "links_discovered",
            "links": links,
        })

    if args.ca_dmv_disengagement_links:
        dis_dir = out_dir / "ca_dmv_disengagement"
        ensure_dir(dis_dir)
        for url in args.ca_dmv_disengagement_links:
            manifest.append(download_url(url, dis_dir, source_dataset="ca_dmv_disengagement", preferred_name=None))

    manifest_path = Path(args.manifest) if args.manifest else out_dir / "official_download_manifest.jsonl"
    write_jsonl(manifest_path, manifest)
    print(json.dumps({"num_manifest_rows": len(manifest), "manifest": str(manifest_path)}, ensure_ascii=False, indent=2))


def extract_collision_pdf_texts(pdf_dir: str | Path, output_path: str | Path, max_chars: int = 4000) -> List[Dict[str, Any]]:
    """Best-effort text extraction from downloaded CA DMV collision PDFs.

    This function does not OCR and does not infer safety labels. It only creates
    RawFunctionalRecord rows with raw_case_summary populated from extractable text.
    If pypdf is unavailable or a PDF is scanned, use the curated JSONL template instead.
    """
    try:
        from pypdf import PdfReader  # type: ignore
    except Exception as exc:  # pragma: no cover - optional dependency
        raise DataCurationError("pypdf is required for PDF text extraction; install pypdf or use curated JSONL input.") from exc

    rows: List[Dict[str, Any]] = []
    for pdf in sorted(Path(pdf_dir).glob("*.pdf")):
        text_parts: List[str] = []
        try:
            reader = PdfReader(str(pdf))
            for page in reader.pages:
                txt = page.extract_text() or ""
                if txt:
                    text_parts.append(txt)
        except Exception as exc:
            rows.append({
                "source_dataset": "ca_dmv_collision",
                "source_record_id": pdf.stem,
                "source_reference": str(pdf),
                "raw_case_summary": "",
                "event_type": "collision",
                "automation_context": "AV_testing",
                "curation_notes": f"PDF text extraction failed: {exc!r}; curate manually.",
            })
            continue
        summary = "\n".join(text_parts).strip()[:max_chars]
        rows.append({
            "source_dataset": "ca_dmv_collision",
            "source_record_id": pdf.stem,
            "source_reference": str(pdf),
            "raw_case_summary": summary,
            "event_type": "collision",
            "automation_context": "AV_testing",
            "curation_notes": "Best-effort text extraction from downloaded CA DMV collision PDF; verify before publication.",
        })
    for row in rows:
        assert_no_label_leakage(row, context="collision pdf extracted row")
    write_jsonl(output_path, rows)
    return rows


def cmd_extract_collision_pdf_text(args: argparse.Namespace) -> None:
    rows = extract_collision_pdf_texts(args.pdf_dir, args.out, max_chars=args.max_chars)
    print(json.dumps({"num_rows": len(rows), "out": args.out}, ensure_ascii=False, indent=2))


def cmd_validate_no_labels(args: argparse.Namespace) -> None:
    rows = read_jsonl(args.path)
    report = {"path": args.path, "num_rows": len(rows), "violations": []}
    for idx, row in enumerate(rows, start=1):
        hits = find_forbidden_label_keys(row)
        if hits:
            report["violations"].append({"row": idx, "paths": hits[:20]})
    if args.out:
        write_json(args.out, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["violations"]:
        raise SystemExit(2)

def add_source_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--functional-records")
    p.add_argument("--ca-dmv-collision")
    p.add_argument("--ca-dmv-collision-csv")
    p.add_argument("--ca-dmv-collision-csv-mode", choices=["autonomous", "conventional", "all"], default="autonomous")
    p.add_argument("--ca-dmv-disengagement")
    p.add_argument("--ca-dmv-disengagement-dir")
    p.add_argument("--ca-dmv-disengagement-overrides")
    p.add_argument("--nhtsa-sgo-ads")
    p.add_argument("--nhtsa-sgo-adas")
    p.add_argument("--nhtsa-sgo-curated")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="External functional-case ingestion for STPA-HF ESWA pipeline")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("build-records", help="Build raw functional records from external source files")
    add_source_args(p)
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_build_records)

    p = sub.add_parser("build-cases", help="Map raw functional records into external functional cases")
    p.add_argument("--records", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_build_cases)

    p = sub.add_parser("build-external-cases", help="One-step build from source files to functional cases")
    add_source_args(p)
    p.add_argument("--records-out")
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_build_external_cases)

    p = sub.add_parser("write-templates", help="Write input templates for manual curation")
    p.add_argument("--out-dir", required=True)
    p.set_defaults(func=cmd_write_templates)

    p = sub.add_parser("discover-sources", help="Discover official DMV/NHTSA source links without downloading files")
    p.add_argument("--ca-dmv-collision", action="store_true")
    p.add_argument("--ca-dmv-disengagement", action="store_true")
    p.add_argument("--collision-limit", type=int)
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_discover_sources)

    p = sub.add_parser("download-official", help="Download official NHTSA SGO CSVs and/or DMV source files and write a manifest")
    p.add_argument("--out-dir", required=True)
    p.add_argument("--manifest")
    p.add_argument("--nhtsa-sgo", action="store_true")
    p.add_argument("--include-nhtsa-other", action="store_true")
    p.add_argument("--ca-dmv-collision", action="store_true")
    p.add_argument("--collision-limit", type=int)
    p.add_argument("--discover-dmv-disengagement", action="store_true")
    p.add_argument("--ca-dmv-disengagement-links", nargs="*")
    p.set_defaults(func=cmd_download_official)

    p = sub.add_parser("extract-collision-pdf-text", help="Best-effort non-OCR text extraction from downloaded CA DMV collision PDFs")
    p.add_argument("--pdf-dir", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--max-chars", type=int, default=4000)
    p.set_defaults(func=cmd_extract_collision_pdf_text)

    p = sub.add_parser("validate-no-labels", help="Fail if a JSONL file contains forbidden label/expected-output keys")
    p.add_argument("--path", required=True)
    p.add_argument("--out")
    p.set_defaults(func=cmd_validate_no_labels)

    return parser


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
