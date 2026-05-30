"""
etl/db.py — Connexion PostgreSQL et loaders (upsert via ON CONFLICT)
"""

import logging
from typing import Any, Dict, List

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.pool import QueuePool

from etl.config import settings

log = logging.getLogger(__name__)

_engine: Any = None


def get_engine(url: str) -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(
            url,
            poolclass=QueuePool,
            pool_size=settings.db_pool_size,
            max_overflow=2,
            pool_pre_ping=True,
        )
    return _engine


def refresh_materialized_view(engine: Engine, view_name: str):
    with engine.begin() as conn:
        conn.execute(text(f"REFRESH MATERIALIZED VIEW CONCURRENTLY {view_name}"))


def _bulk_upsert(engine: Engine, table: str, rows: List[Dict],
                 pk_cols: List[str], update_cols: List[str]) -> int:
    """Upsert générique via INSERT … ON CONFLICT DO UPDATE."""
    if not rows:
        return 0

    cols = list(rows[0].keys())
    col_list  = ", ".join(cols)
    val_list  = ", ".join(f":{c}" for c in cols)
    conflict  = ", ".join(pk_cols)
    updates   = ", ".join(f"{c} = EXCLUDED.{c}" for c in update_cols)

    sql = text(f"""
        INSERT INTO {table} ({col_list})
        VALUES ({val_list})
        ON CONFLICT ({conflict}) DO UPDATE SET {updates}
    """)

    with engine.begin() as conn:
        conn.execute(sql, rows)
    return len(rows)


def _bulk_insert_ignore(engine: Engine, table: str, rows: List[Dict],
                        pk_cols: List[str]) -> int:
    """Insert sans mise à jour (pour tables snapshot/append-only)."""
    if not rows:
        return 0

    cols     = list(rows[0].keys())
    col_list = ", ".join(cols)
    val_list = ", ".join(f":{c}" for c in cols)
    conflict = ", ".join(pk_cols)

    sql = text(f"""
        INSERT INTO {table} ({col_list})
        VALUES ({val_list})
        ON CONFLICT ({conflict}) DO NOTHING
    """)

    with engine.begin() as conn:
        conn.execute(sql, rows)
    return len(rows)


# ─── Loaders publics ─────────────────────────────────────────────────────────

def upsert_vessels(rows: List[Dict], engine: Engine) -> int:
    return _bulk_upsert(engine, "vessels", rows,
                        pk_cols=["vessel_id"],
                        update_cols=["name", "imo_number", "flag", "synced_at"])


def upsert_components(rows: List[Dict], engine: Engine) -> int:
    return _bulk_upsert(engine, "components", rows,
                        pk_cols=["component_id"],
                        update_cols=["vessel_id", "name", "code", "component_type", "is_counter"])


def insert_running_hours_snapshots(rows: List[Dict], engine: Engine) -> int:
    if not rows:
        return 0
    # Insert, puis calcul delta via UPDATE en une passe
    n = _bulk_insert_ignore(engine, "running_hours_snapshots", rows,
                            pk_cols=["component_id", "recorded_at"])
    # Mise à jour des deltas pour les nouvelles lignes
    sql = text("""
        UPDATE running_hours_snapshots rhs
        SET delta_hours = rhs.hours_value - prev.hours_value
        FROM (
            SELECT snapshot_id,
                   LAG(hours_value) OVER (
                       PARTITION BY component_id ORDER BY recorded_at
                   ) AS hours_value
            FROM running_hours_snapshots
        ) prev
        WHERE rhs.snapshot_id = prev.snapshot_id
          AND prev.hours_value IS NOT NULL
          AND rhs.delta_hours IS NULL
    """)
    with engine.begin() as conn:
        conn.execute(sql)
    return n


def upsert_maintenance_jobs(rows: List[Dict], engine: Engine) -> int:
    return _bulk_upsert(engine, "maintenance_jobs", rows,
                        pk_cols=["job_id"],
                        update_cols=["status", "closed_at", "due_date",
                                     "maintenance_type", "hours_at_due"])


def upsert_certificates(rows: List[Dict], engine: Engine) -> int:
    return _bulk_upsert(engine, "certificates", rows,
                        pk_cols=["cert_id"],
                        update_cols=["expires_at", "issued_at", "status",
                                     "days_until_expiry", "cert_name", "cert_type"])


def upsert_crew_members(rows: List[Dict], engine: Engine) -> int:
    return _bulk_upsert(engine, "crew_members", rows,
                        pk_cols=["crew_member_id"],
                        update_cols=["vessel_id", "rank", "nationality",
                                     "contract_start", "contract_end"])


def insert_rest_hours_violations(rows: List[Dict], engine: Engine) -> int:
    return _bulk_insert_ignore(engine, "rest_hours_violations", rows,
                               pk_cols=["crew_member_id", "period_date"])


def upsert_voyages(rows: List[Dict], engine: Engine) -> int:
    return _bulk_upsert(engine, "voyages", rows,
                        pk_cols=["voyage_id"],
                        update_cols=["departure_date", "arrival_date",
                                     "duration_days", "departure_port",
                                     "arrival_port", "voyage_type"])


def upsert_parts(rows: List[Dict], engine: Engine) -> int:
    return _bulk_upsert(engine, "parts", rows,
                        pk_cols=["part_id", "vessel_id"],
                        update_cols=["quantity", "min_quantity",
                                     "below_minimum", "part_name",
                                     "part_number", "unit"])


def upsert_qhse_reports(rows: List[Dict], engine: Engine) -> int:
    return _bulk_upsert(engine, "qhse_reports", rows,
                        pk_cols=["report_id"],
                        update_cols=["status", "due_date", "closed_at",
                                     "priority", "title"])
