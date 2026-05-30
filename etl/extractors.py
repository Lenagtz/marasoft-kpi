"""
etl/extractors.py — Extraction depuis l'API Marasoft
Chaque fonction retourne une liste brute de dicts (JSON as-is).
full_load=False  → delta sur ETL_DELTA_DAYS jours
full_load=True   → toutes les données disponibles
"""

import logging
from datetime import date, timedelta
from typing import Dict, List

from etl.api_client import get, get_paginated
from etl.config import settings

log = logging.getLogger(__name__)


def _delta_start(full_load: bool) -> str:
    """Retourne la date ISO de début pour les requêtes delta."""
    if full_load:
        return "2000-01-01"
    return (date.today() - timedelta(days=settings.delta_days)).isoformat()


def _today() -> str:
    return date.today().isoformat()


# ─── Référentiels ─────────────────────────────────────────────────────────────

def extract_vessels(full_load: bool = False) -> List[Dict]:
    log.debug("extract_vessels")
    data = get("/api/vessels/getVessels")
    return data if isinstance(data, list) else []


def extract_components(full_load: bool = False) -> List[Dict]:
    log.debug("extract_components")
    vessels = get("/api/vessels/getVessels") or []
    results = []
    for vessel in vessels:
        vessel_id = vessel.get("vesselId") or vessel.get("id") or vessel.get("VesselId")
        if not vessel_id:
            continue
        comps = get("/api/Components/GetVesselComponents", {"vesselId": vessel_id})
        for c in (comps or []):
            c["_vessel_id"] = vessel_id
        results.extend(comps or [])
    return results


# ─── Maintenance ──────────────────────────────────────────────────────────────

def extract_running_hours(full_load: bool = False) -> List[Dict]:
    log.debug("extract_running_hours")
    vessels = get("/api/vessels/getVessels") or []
    results = []
    for vessel in vessels:
        vessel_id = vessel.get("vesselId") or vessel.get("id") or vessel.get("VesselId")
        if not vessel_id:
            continue
        rows = get("/api/Components/GetRunningHoursHistories", {
            "vesselId": vessel_id,
            "fromDate": _delta_start(full_load),
            "toDate": _today(),
        })
        for r in (rows or []):
            r["_vessel_id"] = vessel_id
        results.extend(rows or [])
    return results


def extract_maintenance_jobs(full_load: bool = False) -> List[Dict]:
    log.debug("extract_maintenance_jobs")
    vessels = get("/api/vessels/getVessels") or []
    results = []
    for vessel in vessels:
        vessel_id = vessel.get("vesselId") or vessel.get("id") or vessel.get("VesselId")
        if not vessel_id:
            continue
        # Jobs actifs
        jobs = get("/api/JobOperations", {"vesselId": vessel_id}) or []
        for j in jobs:
            j["_vessel_id"] = vessel_id
            j["_source"] = "active"
        results.extend(jobs)
        # Historique (delta)
        history = get("/api/JobHistoryOperations", {
            "vesselId": vessel_id,
            "fromDate": _delta_start(full_load),
            "toDate": _today(),
        }) or []
        for h in history:
            h["_vessel_id"] = vessel_id
            h["_source"] = "history"
        results.extend(history)
    return results


# ─── Certifications ───────────────────────────────────────────────────────────

def extract_certificates(full_load: bool = False) -> List[Dict]:
    log.debug("extract_certificates")
    vessels = get("/api/vessels/getVessels") or []
    results = []
    for vessel in vessels:
        vessel_id = vessel.get("vesselId") or vessel.get("id") or vessel.get("VesselId")
        if not vessel_id:
            continue
        certs = get("/api/Certificates", {"vesselId": vessel_id}) or []
        for c in certs:
            c["_vessel_id"] = vessel_id
        results.extend(certs)
    return results


def extract_qhse_reports(full_load: bool = False) -> List[Dict]:
    log.debug("extract_qhse_reports")
    vessels = get("/api/vessels/getVessels") or []
    results = []
    for vessel in vessels:
        vessel_id = vessel.get("vesselId") or vessel.get("id") or vessel.get("VesselId")
        if not vessel_id:
            continue
        # dueBefore=30 jours, type=2 (Days)
        reports = get("/api/Reports/GetQHSEReports", {
            "vesselId": vessel_id,
            "dueBefore": settings.qhse_due_before_days,
            "dueBeforeType": 2,
        }) or []
        for r in reports:
            r["_vessel_id"] = vessel_id
        results.extend(reports)
    return results


# ─── Équipage ─────────────────────────────────────────────────────────────────

def extract_crew_members(full_load: bool = False) -> List[Dict]:
    log.debug("extract_crew_members")
    data = get("/api/Crewing") or []
    # Enrichissement contrats
    for member in data:
        mid = member.get("crewMemberId") or member.get("id")
        if mid:
            try:
                contract = get("/api/Contract", {"crewMemberId": mid})
                member["_contract"] = contract
            except Exception:
                member["_contract"] = None
    return data


def extract_rest_hours(full_load: bool = False) -> List[Dict]:
    log.debug("extract_rest_hours")
    vessels = get("/api/vessels/getVessels") or []
    results = []
    for vessel in vessels:
        vessel_id = vessel.get("vesselId") or vessel.get("id") or vessel.get("VesselId")
        if not vessel_id:
            continue
        rows = get("/api/CrewingRestHours", {
            "vesselId": vessel_id,
            "fromDate": _delta_start(full_load),
            "toDate": _today(),
        }) or []
        for r in rows:
            r["_vessel_id"] = vessel_id
        results.extend(rows)
    return results


# ─── Opérations ──────────────────────────────────────────────────────────────

def extract_voyages(full_load: bool = False) -> List[Dict]:
    log.debug("extract_voyages")
    vessels = get("/api/vessels/getVessels") or []
    results = []
    for vessel in vessels:
        vessel_id = vessel.get("vesselId") or vessel.get("id") or vessel.get("VesselId")
        if not vessel_id:
            continue
        voyages = get("/api/Voyages/GetVoyages", {
            "vesselId": vessel_id,
            "fromDate": _delta_start(full_load),
            "toDate": _today(),
        }) or []
        for v in voyages:
            v["_vessel_id"] = vessel_id
        results.extend(voyages)
    return results


def extract_parts(full_load: bool = False) -> List[Dict]:
    log.debug("extract_parts")
    vessels = get("/api/vessels/getVessels") or []
    results = []
    for vessel in vessels:
        vessel_id = vessel.get("vesselId") or vessel.get("id") or vessel.get("VesselId")
        if not vessel_id:
            continue
        parts = get("/api/Parts/GetPartsPerVessel", {"vesselId": vessel_id}) or []
        for p in parts:
            p["_vessel_id"] = vessel_id
        results.extend(parts)
    return results
