-- =============================================================================
-- Marasoft KPI — DDL PostgreSQL
-- Ordre d'exécution : psql -d marasoft_kpi -f sql/schema.sql
-- =============================================================================

-- Extensions
CREATE EXTENSION IF NOT EXISTS pg_trgm;  -- recherche texte
CREATE EXTENSION IF NOT EXISTS btree_gin;

-- =============================================================================
-- 1. Référentiels
-- =============================================================================

CREATE TABLE IF NOT EXISTS vessels (
    vessel_id   TEXT PRIMARY KEY,
    name        TEXT,
    imo_number  TEXT,
    flag        TEXT,
    synced_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS components (
    component_id    TEXT PRIMARY KEY,
    vessel_id       TEXT REFERENCES vessels(vessel_id) ON DELETE CASCADE,
    name            TEXT,
    code            TEXT,
    component_type  TEXT,
    is_counter      BOOLEAN DEFAULT FALSE
);
CREATE INDEX IF NOT EXISTS idx_components_vessel ON components(vessel_id);

-- =============================================================================
-- 2. Heures moteur (append-only, une ligne par mesure)
-- =============================================================================

CREATE TABLE IF NOT EXISTS running_hours_snapshots (
    snapshot_id     BIGSERIAL PRIMARY KEY,
    component_id    TEXT REFERENCES components(component_id) ON DELETE CASCADE,
    vessel_id       TEXT REFERENCES vessels(vessel_id)       ON DELETE CASCADE,
    recorded_at     TIMESTAMPTZ NOT NULL,
    hours_value     NUMERIC(10,2) NOT NULL,
    delta_hours     NUMERIC(8,2),                         -- calculé après insert
    UNIQUE (component_id, recorded_at)
);
CREATE INDEX IF NOT EXISTS idx_rhs_component ON running_hours_snapshots(component_id, recorded_at DESC);
CREATE INDEX IF NOT EXISTS idx_rhs_vessel    ON running_hours_snapshots(vessel_id, recorded_at DESC);

-- =============================================================================
-- 3. Jobs de maintenance
-- =============================================================================

CREATE TABLE IF NOT EXISTS maintenance_jobs (
    job_id              TEXT PRIMARY KEY,
    component_id        TEXT,
    vessel_id           TEXT REFERENCES vessels(vessel_id) ON DELETE CASCADE,
    job_name            TEXT,
    status              TEXT CHECK (status IN ('open','done','overdue')),
    due_date            DATE,
    closed_at           TIMESTAMPTZ,
    maintenance_type    TEXT,
    hours_at_due        NUMERIC(10,2)
);
CREATE INDEX IF NOT EXISTS idx_jobs_vessel  ON maintenance_jobs(vessel_id, status);
CREATE INDEX IF NOT EXISTS idx_jobs_due     ON maintenance_jobs(due_date) WHERE status != 'done';

-- =============================================================================
-- 4. Certificats
-- =============================================================================

CREATE TABLE IF NOT EXISTS certificates (
    cert_id             TEXT PRIMARY KEY,
    vessel_id           TEXT REFERENCES vessels(vessel_id) ON DELETE CASCADE,
    crew_member_id      TEXT,
    cert_type           TEXT,
    cert_name           TEXT,
    issued_at           DATE,
    expires_at          DATE,
    status              TEXT CHECK (status IN ('valid','expiring_soon','critical','expired','unknown')),
    days_until_expiry   INT
);
CREATE INDEX IF NOT EXISTS idx_certs_vessel     ON certificates(vessel_id, status);
CREATE INDEX IF NOT EXISTS idx_certs_expires    ON certificates(expires_at);
CREATE INDEX IF NOT EXISTS idx_certs_crew       ON certificates(crew_member_id) WHERE crew_member_id IS NOT NULL;

-- Vue pour rafraîchir le status au moment de la requête (optionnelle)
CREATE OR REPLACE VIEW v_certificates_live AS
SELECT *,
       (expires_at - CURRENT_DATE)                 AS days_left_live,
       CASE
           WHEN expires_at IS NULL              THEN 'unknown'
           WHEN expires_at < CURRENT_DATE       THEN 'expired'
           WHEN expires_at - CURRENT_DATE <= 7  THEN 'critical'
           WHEN expires_at - CURRENT_DATE <= 30 THEN 'expiring_soon'
           ELSE 'valid'
       END AS live_status
FROM certificates;

-- =============================================================================
-- 5. Équipage
-- =============================================================================

CREATE TABLE IF NOT EXISTS crew_members (
    crew_member_id  TEXT PRIMARY KEY,
    vessel_id       TEXT REFERENCES vessels(vessel_id) ON DELETE SET NULL,
    first_name      TEXT,
    last_name       TEXT,
    rank            TEXT,
    nationality     TEXT,
    contract_start  DATE,
    contract_end    DATE
);
CREATE INDEX IF NOT EXISTS idx_crew_vessel ON crew_members(vessel_id);
CREATE INDEX IF NOT EXISTS idx_crew_rank   ON crew_members(rank);

-- =============================================================================
-- 6. Violations heures de repos (append-only)
-- =============================================================================

CREATE TABLE IF NOT EXISTS rest_hours_violations (
    violation_id        BIGSERIAL PRIMARY KEY,
    crew_member_id      TEXT REFERENCES crew_members(crew_member_id) ON DELETE CASCADE,
    period_date         DATE NOT NULL,
    rest_hours_actual   NUMERIC(5,2),
    rest_hours_required NUMERIC(5,2) DEFAULT 10.0,
    deficit_hours       NUMERIC(5,2),
    severity            TEXT CHECK (severity IN ('minor','major','critical')),
    UNIQUE (crew_member_id, period_date)
);
CREATE INDEX IF NOT EXISTS idx_rviol_crew   ON rest_hours_violations(crew_member_id);
CREATE INDEX IF NOT EXISTS idx_rviol_date   ON rest_hours_violations(period_date DESC);
CREATE INDEX IF NOT EXISTS idx_rviol_sev    ON rest_hours_violations(severity);

-- =============================================================================
-- 7. Voyages
-- =============================================================================

CREATE TABLE IF NOT EXISTS voyages (
    voyage_id       TEXT PRIMARY KEY,
    vessel_id       TEXT REFERENCES vessels(vessel_id) ON DELETE CASCADE,
    departure_port  TEXT,
    arrival_port    TEXT,
    departure_date  TIMESTAMPTZ,
    arrival_date    TIMESTAMPTZ,
    duration_days   NUMERIC(6,1),
    voyage_type     TEXT DEFAULT 'sea'
);
CREATE INDEX IF NOT EXISTS idx_voyages_vessel ON voyages(vessel_id, departure_date DESC);

-- =============================================================================
-- 8. Pièces & Stock
-- =============================================================================

CREATE TABLE IF NOT EXISTS parts (
    part_id         TEXT,
    vessel_id       TEXT REFERENCES vessels(vessel_id) ON DELETE CASCADE,
    part_name       TEXT,
    part_number     TEXT,
    quantity        INT,
    min_quantity    INT DEFAULT 2,
    below_minimum   BOOLEAN GENERATED ALWAYS AS (quantity < min_quantity) STORED,
    unit            TEXT DEFAULT 'pcs',
    PRIMARY KEY (part_id, vessel_id)
);
CREATE INDEX IF NOT EXISTS idx_parts_vessel   ON parts(vessel_id);
CREATE INDEX IF NOT EXISTS idx_parts_critical ON parts(vessel_id) WHERE below_minimum;

-- =============================================================================
-- 9. Rapports QHSE
-- =============================================================================

CREATE TABLE IF NOT EXISTS qhse_reports (
    report_id   TEXT PRIMARY KEY,
    vessel_id   TEXT REFERENCES vessels(vessel_id) ON DELETE CASCADE,
    report_type TEXT,
    title       TEXT,
    due_date    DATE,
    closed_at   TIMESTAMPTZ,
    status      TEXT CHECK (status IN ('open','due_soon','overdue','closed')),
    priority    TEXT DEFAULT 'normal'
);
CREATE INDEX IF NOT EXISTS idx_qhse_vessel  ON qhse_reports(vessel_id, status);
CREATE INDEX IF NOT EXISTS idx_qhse_due     ON qhse_reports(due_date) WHERE status != 'closed';

-- =============================================================================
-- 10. Vue matérialisée KPI — agrégation quotidienne par navire
-- =============================================================================

CREATE MATERIALIZED VIEW IF NOT EXISTS mv_kpi_vessel_daily AS
WITH base_date AS (SELECT CURRENT_DATE AS kpi_date)

SELECT
    v.vessel_id,
    v.name                              AS vessel_name,
    bd.kpi_date,

    -- Heures moteur cumulées (dernier snapshot par composant)
    COALESCE((
        SELECT SUM(latest.hours_value)
        FROM (
            SELECT DISTINCT ON (component_id) hours_value
            FROM running_hours_snapshots rhs
            WHERE rhs.vessel_id = v.vessel_id
            ORDER BY component_id, recorded_at DESC
        ) latest
    ), 0)                               AS engine_hours_total,

    -- Heures ajoutées sur les 7 derniers jours
    COALESCE((
        SELECT SUM(delta_hours)
        FROM running_hours_snapshots rhs
        WHERE rhs.vessel_id = v.vessel_id
          AND rhs.recorded_at >= NOW() - INTERVAL '7 days'
    ), 0)                               AS engine_hours_last_7d,

    -- Jobs maintenance
    COUNT(DISTINCT mj.job_id) FILTER (WHERE mj.status = 'open')     AS jobs_open,
    COUNT(DISTINCT mj.job_id) FILTER (WHERE mj.status = 'overdue')  AS jobs_overdue,

    -- Certificats
    COUNT(DISTINCT c.cert_id) FILTER (WHERE c.status = 'valid')         AS certs_valid,
    COUNT(DISTINCT c.cert_id) FILTER (WHERE c.status = 'expiring_soon') AS certs_expiring_30d,
    COUNT(DISTINCT c.cert_id) FILTER (WHERE c.status = 'critical')      AS certs_expiring_7d,
    COUNT(DISTINCT c.cert_id) FILTER (WHERE c.status = 'expired')       AS certs_expired,

    -- Violations MLC heures de repos (30 derniers jours)
    COALESCE((
        SELECT COUNT(*)
        FROM rest_hours_violations rhv
        JOIN crew_members cm ON cm.crew_member_id = rhv.crew_member_id
        WHERE cm.vessel_id = v.vessel_id
          AND rhv.period_date >= CURRENT_DATE - 30
    ), 0)                               AS rest_violations_30d,

    -- Équipage
    COUNT(DISTINCT cm.crew_member_id)   AS crew_onboard,

    -- Pièces sous seuil
    COUNT(DISTINCT p.part_id) FILTER (WHERE p.below_minimum) AS parts_below_min,

    -- Rapports QHSE ouverts / en retard
    COUNT(DISTINCT qr.report_id) FILTER (WHERE qr.status IN ('open','due_soon')) AS qhse_open,
    COUNT(DISTINCT qr.report_id) FILTER (WHERE qr.status = 'overdue')            AS qhse_overdue

FROM vessels v
CROSS JOIN base_date bd
LEFT JOIN maintenance_jobs mj    ON mj.vessel_id = v.vessel_id
LEFT JOIN certificates c         ON c.vessel_id  = v.vessel_id
LEFT JOIN crew_members cm        ON cm.vessel_id = v.vessel_id
LEFT JOIN parts p                ON p.vessel_id  = v.vessel_id
LEFT JOIN qhse_reports qr        ON qr.vessel_id = v.vessel_id
GROUP BY v.vessel_id, v.name, bd.kpi_date
WITH DATA;

-- Index pour requêtes dashboard rapides
CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_kpi_vessel
    ON mv_kpi_vessel_daily (vessel_id, kpi_date);

COMMENT ON MATERIALIZED VIEW mv_kpi_vessel_daily IS
    'Snapshot KPI quotidien par navire — rafraîchi chaque nuit via REFRESH MATERIALIZED VIEW CONCURRENTLY';
