#!/usr/bin/env python3
"""
dry_run_mock.py — Dry-run complet du pipeline ETL avec données mockées.
Aucun accès réseau, aucune écriture en base. Valide extract→transform→(mock load).

Usage : python dry_run_mock.py
"""

import logging
import os
import sys
import time
from datetime import date, datetime, timezone
from unittest.mock import patch

# Fournit une clé API factice pour satisfaire Settings (obligatoire)
os.environ.setdefault("MARASOFT_API_KEY", "dry-run-mock-key")
os.environ.setdefault("DATABASE_URL",     "postgresql://mock:mock@localhost/mock")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("dry_run_mock")

# ─── Données mockées ──────────────────────────────────────────────────────────

MOCK_VESSELS = [
    {"vesselId": "V001", "name": "Atlantic Pioneer", "imoNumber": "IMO9876543", "flag": "NO"},
    {"vesselId": "V002", "name": "Nordic Star",      "imoNumber": "IMO1234567", "flag": "FI"},
]

MOCK_COMPONENTS = {
    "V001": [
        {"componentId": "C001", "name": "Main Engine",   "code": "ME-01", "type": "engine",  "isCounter": True},
        {"componentId": "C002", "name": "Aux Generator", "code": "AG-01", "type": "generator","isCounter": True},
    ],
    "V002": [
        {"componentId": "C003", "name": "Main Engine",   "code": "ME-01", "type": "engine",  "isCounter": True},
    ],
}

MOCK_RUNNING_HOURS = {
    "V001": [
        {"componentId": "C001", "date": "2026-05-28T08:00:00", "hours": 12450.5},
        {"componentId": "C001", "date": "2026-05-29T08:00:00", "hours": 12474.0},
        {"componentId": "C002", "date": "2026-05-28T08:00:00", "hours": 3210.0},
    ],
    "V002": [
        {"componentId": "C003", "date": "2026-05-29T08:00:00", "hours": 8800.0},
    ],
}

MOCK_JOBS = {
    "V001": [
        {"jobId": "J001", "componentId": "C001", "name": "Oil change",    "dueDate": "2026-06-15", "type": "preventive"},
        {"jobId": "J002", "componentId": "C002", "name": "Filter check",  "dueDate": "2026-04-01", "type": "preventive"},  # overdue
    ],
    "V002": [
        {"jobId": "J003", "componentId": "C003", "name": "Overhaul",      "closedDate": "2026-05-20T10:00:00", "type": "corrective"},
    ],
}

MOCK_CERTS = {
    "V001": [
        {"certificateId": "CERT001", "type": "SOLAS",    "name": "Safety Certificate", "issueDate": "2024-01-01", "expiryDate": "2026-06-05"},  # critical
        {"certificateId": "CERT002", "type": "MARPOL",   "name": "Oil Record Book",    "issueDate": "2023-06-01", "expiryDate": "2027-06-01"},  # valid
    ],
    "V002": [
        {"certificateId": "CERT003", "type": "MLC",      "name": "MLC Certificate",    "issueDate": "2022-01-01", "expiryDate": "2026-05-10"},  # expired
    ],
}

MOCK_CREW = [
    {"crewMemberId": "CM001", "vesselId": "V001", "firstName": "Erik",   "lastName": "Hansen",  "rank": "Master",        "nationality": "NO"},
    {"crewMemberId": "CM002", "vesselId": "V001", "firstName": "Anna",   "lastName": "Lindqvist","rank": "Chief Officer", "nationality": "SE"},
    {"crewMemberId": "CM003", "vesselId": "V002", "firstName": "Mikael", "lastName": "Virtanen", "rank": "Chief Engineer","nationality": "FI"},
]

MOCK_CONTRACTS = {
    "CM001": {"startDate": "2026-01-15", "endDate": "2026-07-15"},
    "CM002": {"startDate": "2026-02-01", "endDate": "2026-08-01"},
    "CM003": {"startDate": "2025-12-01", "endDate": "2026-06-01"},
}

MOCK_REST_HOURS = {
    "V001": [
        {"crewMemberId": "CM001", "date": "2026-05-27", "restHours": 11.0},  # OK
        {"crewMemberId": "CM001", "date": "2026-05-28", "restHours": 8.5},   # violation
        {"crewMemberId": "CM002", "date": "2026-05-28", "restHours": 9.0},   # violation
    ],
    "V002": [
        {"crewMemberId": "CM003", "date": "2026-05-28", "restHours": 10.5},  # OK
    ],
}

MOCK_VOYAGES = {
    "V001": [
        {"voyageId": "VOY001", "departurePort": "Oslo",      "arrivalPort": "Rotterdam",
         "departureDate": "2026-05-01T06:00:00", "arrivalDate": "2026-05-03T14:00:00", "type": "sea"},
        {"voyageId": "VOY002", "departurePort": "Rotterdam", "arrivalPort": "Hamburg",
         "departureDate": "2026-05-04T08:00:00", "arrivalDate": "2026-05-04T18:00:00", "type": "sea"},
    ],
    "V002": [
        {"voyageId": "VOY003", "departurePort": "Helsinki",  "arrivalPort": "Tallinn",
         "departureDate": "2026-05-20T07:00:00", "arrivalDate": "2026-05-20T10:00:00", "type": "sea"},
    ],
}

MOCK_PARTS = {
    "V001": [
        {"partId": "P001", "name": "Oil Filter",   "partNumber": "OF-123", "quantity": 5,  "minimumQuantity": 3, "unit": "pcs"},
        {"partId": "P002", "name": "Fuel Filter",  "partNumber": "FF-456", "quantity": 1,  "minimumQuantity": 3, "unit": "pcs"},  # below min
        {"partId": "P003", "name": "V-Belt",       "partNumber": "VB-789", "quantity": 0,  "minimumQuantity": 2, "unit": "pcs"},  # critical
    ],
    "V002": [
        {"partId": "P004", "name": "Impeller",     "partNumber": "IMP-01", "quantity": 4,  "minimumQuantity": 2, "unit": "pcs"},
    ],
}

MOCK_QHSE = {
    "V001": [
        {"reportId": "Q001", "type": "Near Miss", "title": "Slippery deck incident", "dueDate": "2026-06-10", "priority": "high"},
        {"reportId": "Q002", "type": "Inspection", "title": "PSC Inspection prep",   "dueDate": "2026-04-01", "priority": "critical"},  # overdue
    ],
    "V002": [
        {"reportId": "Q003", "type": "Drill",     "title": "Fire drill report",      "closedDate": "2026-05-25T09:00:00", "priority": "normal"},
    ],
}


# ─── Mock API : remplace etl.api_client.get ──────────────────────────────────

def mock_get(path: str, params=None):
    params = params or {}
    vid = params.get("vesselId")
    mid = params.get("crewMemberId")

    if path == "/api/vessels/getVessels":
        return MOCK_VESSELS
    if path == "/api/Components/GetVesselComponents":
        return MOCK_COMPONENTS.get(vid, [])
    if path == "/api/Components/GetRunningHoursHistories":
        return MOCK_RUNNING_HOURS.get(vid, [])
    if path == "/api/JobOperations":
        return [j for j in MOCK_JOBS.get(vid, []) if "closedDate" not in j]
    if path == "/api/JobHistoryOperations":
        return [j for j in MOCK_JOBS.get(vid, []) if "closedDate" in j]
    if path == "/api/Certificates":
        return MOCK_CERTS.get(vid, [])
    if path == "/api/Crewing":
        return MOCK_CREW
    if path == "/api/Contract":
        return MOCK_CONTRACTS.get(mid)
    if path == "/api/CrewingRestHours":
        return MOCK_REST_HOURS.get(vid, [])
    if path == "/api/Voyages/GetVoyages":
        return MOCK_VOYAGES.get(vid, [])
    if path == "/api/Parts/GetPartsPerVessel":
        return MOCK_PARTS.get(vid, [])
    if path == "/api/Reports/GetQHSEReports":
        return MOCK_QHSE.get(vid, [])
    log.warning("  [mock] endpoint non couvert : %s %s", path, params)
    return []


# ─── Exécution du pipeline ────────────────────────────────────────────────────

def run_pipeline():
    from etl.extractors import (
        extract_vessels, extract_components, extract_running_hours,
        extract_maintenance_jobs, extract_certificates, extract_crew_members,
        extract_rest_hours, extract_voyages, extract_parts, extract_qhse_reports,
    )
    from etl.transformers import (
        transform_vessels, transform_components, transform_running_hours,
        transform_maintenance_jobs, transform_certificates, transform_crew_members,
        transform_rest_hours, transform_voyages, transform_parts, transform_qhse_reports,
    )

    PIPELINE = [
        ("vessels",          extract_vessels,          transform_vessels),
        ("components",       extract_components,       transform_components),
        ("running_hours",    extract_running_hours,    transform_running_hours),
        ("maintenance_jobs", extract_maintenance_jobs, transform_maintenance_jobs),
        ("certificates",     extract_certificates,     transform_certificates),
        ("crew_members",     extract_crew_members,     transform_crew_members),
        ("rest_hours",       extract_rest_hours,       transform_rest_hours),
        ("voyages",          extract_voyages,           transform_voyages),
        ("parts",            extract_parts,             transform_parts),
        ("qhse_reports",     extract_qhse_reports,     transform_qhse_reports),
    ]

    start = datetime.now(timezone.utc)
    log.info("═══ DRY-RUN (données mockées) démarré — %s ═══", start.isoformat())

    errors = []
    total_rows = 0

    for name, extractor, transformer in PIPELINE:
        t0 = time.time()
        try:
            raw = extractor(full_load=False)
            rows = transformer(raw)
            elapsed = time.time() - t0
            log.info("✓ %-20s  %2d bruts → %2d transformés  (%.3fs)", name, len(raw), len(rows), elapsed)
            total_rows += len(rows)

            # Assertions de sanité basiques
            _assert_module(name, rows)

        except Exception as exc:
            log.error("✗ %-20s  ERREUR : %s", name, exc, exc_info=True)
            errors.append((name, exc))

    elapsed_total = (datetime.now(timezone.utc) - start).total_seconds()
    log.info("═══ Terminé en %.2fs — %d modules OK / %d erreurs / %d lignes totales ═══",
             elapsed_total, len(PIPELINE) - len(errors), len(errors), total_rows)

    if errors:
        log.error("Modules en erreur : %s", [e[0] for e in errors])
        sys.exit(1)

    log.info("✅ Dry-run réussi — pipeline validé sans accès réseau ni base de données")


def _assert_module(name: str, rows: list):
    """Vérifie les invariants métier des données transformées."""
    if name == "vessels":
        assert all("vessel_id" in r and r["vessel_id"] for r in rows), "vessel_id manquant"
        assert len(rows) == 2, f"attendu 2 vessels, obtenu {len(rows)}"

    elif name == "components":
        assert all("component_id" in r for r in rows), "component_id manquant"
        assert all("vessel_id" in r for r in rows), "vessel_id manquant dans components"

    elif name == "running_hours":
        assert all("hours_value" in r and isinstance(r["hours_value"], float) for r in rows)

    elif name == "maintenance_jobs":
        statuses = {r["status"] for r in rows}
        assert statuses <= {"open", "overdue", "done"}, f"status invalide : {statuses}"

    elif name == "certificates":
        statuses = {r["status"] for r in rows}
        assert statuses <= {"valid", "expiring_soon", "critical", "expired", "unknown"}, \
            f"cert status invalide : {statuses}"
        # CERT003 (expired) doit être détecté
        expired = [r for r in rows if r["status"] == "expired"]
        assert expired, "aucun certificat expiré détecté"

    elif name == "rest_hours":
        # Seules les violations sont conservées (restHours < 10)
        assert all(r["deficit_hours"] > 0 for r in rows), "ligne sans déficit dans rest_hours"
        severities = {r["severity"] for r in rows}
        assert severities <= {"none", "minor", "major", "critical"}

    elif name == "parts":
        below = [r for r in rows if r["below_minimum"]]
        assert below, "aucune pièce sous le stock minimum détectée"

    elif name == "voyages":
        assert all("duration_days" in r for r in rows)
        durations = [r["duration_days"] for r in rows if r["duration_days"] is not None]
        assert all(d >= 0 for d in durations), "durée négative détectée"


if __name__ == "__main__":
    with patch("etl.api_client.get", side_effect=mock_get):
        run_pipeline()
