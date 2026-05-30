"""
etl/loaders.py — Re-export des loaders depuis db.py (compat etl_run.py)
"""

from etl.db import (
    upsert_vessels,
    upsert_components,
    insert_running_hours_snapshots,
    upsert_maintenance_jobs,
    upsert_certificates,
    upsert_crew_members,
    insert_rest_hours_violations,
    upsert_voyages,
    upsert_parts,
    upsert_qhse_reports,
)

__all__ = [
    "upsert_vessels",
    "upsert_components",
    "insert_running_hours_snapshots",
    "upsert_maintenance_jobs",
    "upsert_certificates",
    "upsert_crew_members",
    "insert_rest_hours_violations",
    "upsert_voyages",
    "upsert_parts",
    "upsert_qhse_reports",
]
