#!/usr/bin/env python3
"""
Marasoft KPI ETL — Point d'entrée principal
Exécution : python etl_run.py [--full] [--module MODULE]
Cron typique : 0 3 * * * /usr/bin/python3 /opt/marasoft_etl/etl_run.py >> /var/log/marasoft_etl.log 2>&1
"""

import argparse
import logging
import sys
import time
from datetime import datetime, timezone

from etl.config import settings
from etl.db import get_engine, refresh_materialized_view
from etl.extractors import (
    extract_vessels,
    extract_components,
    extract_running_hours,
    extract_maintenance_jobs,
    extract_certificates,
    extract_crew_members,
    extract_rest_hours,
    extract_voyages,
    extract_parts,
    extract_qhse_reports,
)
from etl.loaders import (
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
from etl.transformers import (
    transform_vessels,
    transform_components,
    transform_running_hours,
    transform_maintenance_jobs,
    transform_certificates,
    transform_crew_members,
    transform_rest_hours,
    transform_voyages,
    transform_parts,
    transform_qhse_reports,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("marasoft_etl")


PIPELINE = [
    # (nom, extracteur, transformeur, chargeur, priorité)
    ("vessels",          extract_vessels,         transform_vessels,         upsert_vessels,                 1),
    ("components",       extract_components,      transform_components,      upsert_components,              2),
    ("running_hours",    extract_running_hours,   transform_running_hours,   insert_running_hours_snapshots, 3),
    ("maintenance_jobs", extract_maintenance_jobs,transform_maintenance_jobs,upsert_maintenance_jobs,        3),
    ("certificates",     extract_certificates,    transform_certificates,    upsert_certificates,            3),
    ("crew_members",     extract_crew_members,    transform_crew_members,    upsert_crew_members,            2),
    ("rest_hours",       extract_rest_hours,      transform_rest_hours,      insert_rest_hours_violations,   3),
    ("voyages",          extract_voyages,         transform_voyages,         upsert_voyages,                 3),
    ("parts",            extract_parts,           transform_parts,           upsert_parts,                   3),
    ("qhse_reports",     extract_qhse_reports,    transform_qhse_reports,    upsert_qhse_reports,            3),
]


def run_module(name, extractor, transformer, loader, engine, full_load=False):
    t0 = time.time()
    log.info("▶ [%s] extraction...", name)
    try:
        raw = extractor(full_load=full_load)
        log.info("  [%s] %d enregistrements bruts extraits", name, len(raw))

        rows = transformer(raw)
        log.info("  [%s] %d lignes transformées", name, len(rows))

        n = loader(rows, engine)
        elapsed = time.time() - t0
        log.info("✓ [%s] %d lignes chargées en %.1fs", name, n, elapsed)
        return True, n
    except Exception as exc:
        log.error("✗ [%s] ERREUR : %s", name, exc, exc_info=True)
        return False, 0


def main():
    parser = argparse.ArgumentParser(description="Marasoft KPI ETL")
    parser.add_argument("--full",   action="store_true", help="Charge toutes les données (pas seulement le delta)")
    parser.add_argument("--module", type=str,            help="Exécute un seul module (ex: certificates)")
    parser.add_argument("--dry-run",action="store_true", help="Extrait et transforme sans écrire en base")
    args = parser.parse_args()

    start = datetime.now(timezone.utc)
    log.info("═══ Marasoft ETL démarré — %s (full=%s) ═══", start.isoformat(), args.full)

    engine = get_engine(settings.database_url)

    pipeline = PIPELINE
    if args.module:
        pipeline = [p for p in PIPELINE if p[0] == args.module]
        if not pipeline:
            log.error("Module inconnu : %s. Modules disponibles : %s",
                      args.module, [p[0] for p in PIPELINE])
            sys.exit(1)

    # Tri par priorité
    pipeline = sorted(pipeline, key=lambda p: p[4])

    results = {}
    for name, extractor, transformer, loader, _ in pipeline:
        ok, count = run_module(
            name, extractor, transformer,
            (lambda rows, e: log.info("  [dry-run] %d lignes non écrites", len(rows)) or len(rows))
            if args.dry_run else loader,
            engine,
            full_load=args.full,
        )
        results[name] = (ok, count)

    if not args.dry_run:
        log.info("▶ Rafraîchissement vue matérialisée mv_kpi_vessel_daily...")
        try:
            refresh_materialized_view(engine, "mv_kpi_vessel_daily")
            log.info("✓ Vue matérialisée rafraîchie")
        except Exception as exc:
            log.error("✗ Échec rafraîchissement vue : %s", exc)

    elapsed_total = (datetime.now(timezone.utc) - start).total_seconds()
    ok_count  = sum(1 for ok, _ in results.values() if ok)
    err_count = sum(1 for ok, _ in results.values() if not ok)
    rows_total = sum(n for _, n in results.values())

    log.info("═══ ETL terminé en %.1fs — %d modules OK / %d erreurs / %d lignes ═══",
             elapsed_total, ok_count, err_count, rows_total)

    sys.exit(1 if err_count else 0)


if __name__ == "__main__":
    main()
