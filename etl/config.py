"""
etl/config.py — Configuration centralisée via variables d'environnement
Fichier .env supporté via python-dotenv (optionnel)
"""

import os
from dataclasses import dataclass, field
from datetime import timedelta

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv optionnel


@dataclass
class Settings:
    # ── API Marasoft ──────────────────────────────────────────────
    api_base_url: str       = field(default_factory=lambda: os.environ.get("MARASOFT_BASE_URL", "https://external02.marad.ms"))
    api_key: str            = field(default_factory=lambda: os.environ["MARASOFT_API_KEY"])  # obligatoire
    api_timeout: int        = field(default_factory=lambda: int(os.environ.get("MARASOFT_TIMEOUT", "30")))
    api_max_retries: int    = field(default_factory=lambda: int(os.environ.get("MARASOFT_MAX_RETRIES", "3")))
    api_retry_delay: float  = field(default_factory=lambda: float(os.environ.get("MARASOFT_RETRY_DELAY", "2.0")))
    api_rate_limit_rps: float = field(default_factory=lambda: float(os.environ.get("MARASOFT_RATE_LIMIT_RPS", "5")))

    # ── PostgreSQL ────────────────────────────────────────────────
    database_url: str       = field(default_factory=lambda: os.environ.get(
        "DATABASE_URL",
        "postgresql://marasoft_etl:password@localhost:5432/marasoft_kpi"
    ))
    db_pool_size: int       = field(default_factory=lambda: int(os.environ.get("DB_POOL_SIZE", "5")))

    # ── Fenêtre delta (charge incrémentale) ───────────────────────
    # Chargement delta = seulement les données modifiées depuis N jours
    delta_days: int         = field(default_factory=lambda: int(os.environ.get("ETL_DELTA_DAYS", "7")))

    # ── Seuils KPI (paramétrables) ────────────────────────────────
    cert_expiry_warning_days: int   = field(default_factory=lambda: int(os.environ.get("CERT_EXPIRY_WARNING_DAYS", "30")))
    cert_expiry_critical_days: int  = field(default_factory=lambda: int(os.environ.get("CERT_EXPIRY_CRITICAL_DAYS", "7")))
    rest_hours_min_daily: float     = field(default_factory=lambda: float(os.environ.get("REST_HOURS_MIN_DAILY", "10.0")))  # MLC 2006
    parts_min_stock_default: int    = field(default_factory=lambda: int(os.environ.get("PARTS_MIN_STOCK", "2")))
    qhse_due_before_days: int       = field(default_factory=lambda: int(os.environ.get("QHSE_DUE_BEFORE_DAYS", "30")))

    # ── Logging ───────────────────────────────────────────────────
    log_level: str = field(default_factory=lambda: os.environ.get("LOG_LEVEL", "INFO"))


settings = Settings()
