# Marasoft KPI ETL — Guide d'installation & cron

## Prérequis

- Python 3.10+
- PostgreSQL 14+
- Accès réseau vers `external02.marad.ms`
- Clé API Marasoft

---

## 1. Installation

```bash
# Cloner / déposer le projet
mkdir -p /opt/marasoft_etl
cp -r . /opt/marasoft_etl/
cd /opt/marasoft_etl

# Environnement virtuel
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Configuration
cp .env.example .env
nano .env   # → renseigner MARASOFT_API_KEY et DATABASE_URL
```

---

## 2. Base de données PostgreSQL

```bash
# Créer la base et l'utilisateur
sudo -u postgres psql <<EOF
CREATE DATABASE marasoft_kpi;
CREATE USER marasoft_etl WITH PASSWORD 'motdepasse_fort';
GRANT ALL PRIVILEGES ON DATABASE marasoft_kpi TO marasoft_etl;
EOF

# Appliquer le schéma
psql -U marasoft_etl -d marasoft_kpi -f /opt/marasoft_etl/sql/schema.sql
```

---

## 3. Premier chargement complet

```bash
cd /opt/marasoft_etl
source .venv/bin/activate

# Charge toutes les données historiques (peut prendre plusieurs minutes)
python etl_run.py --full

# Test à blanc (sans écriture en base)
python etl_run.py --dry-run
```

---

## 4. Configuration cron (chargement delta quotidien)

```bash
# Éditer la crontab de l'utilisateur système dédié
crontab -e
```

Ajouter ces lignes :

```cron
# ── Marasoft KPI ETL ────────────────────────────────────────────────────────

# Chargement delta quotidien à 03h00
0 3 * * * /opt/marasoft_etl/.venv/bin/python /opt/marasoft_etl/etl_run.py >> /var/log/marasoft_etl/daily.log 2>&1

# Chargement complet hebdomadaire (dimanche 02h00) pour rattraper les deltas manqués
0 2 * * 0 /opt/marasoft_etl/.venv/bin/python /opt/marasoft_etl/etl_run.py --full >> /var/log/marasoft_etl/weekly.log 2>&1

# Rafraîchissement certif seul à 08h00 (alerte matin pour les armateurs)
0 8 * * * /opt/marasoft_etl/.venv/bin/python /opt/marasoft_etl/etl_run.py --module certificates >> /var/log/marasoft_etl/certs.log 2>&1
```

```bash
# Créer le dossier de logs
mkdir -p /var/log/marasoft_etl
chown $(whoami) /var/log/marasoft_etl

# Rotation des logs (logrotate)
sudo tee /etc/logrotate.d/marasoft_etl <<EOF
/var/log/marasoft_etl/*.log {
    daily
    rotate 30
    compress
    missingok
    notifempty
    dateext
}
EOF
```

---

## 5. Commandes utiles

```bash
# Exécuter un seul module
python etl_run.py --module certificates
python etl_run.py --module running_hours
python etl_run.py --module rest_hours

# Modules disponibles :
# vessels | components | running_hours | maintenance_jobs
# certificates | crew_members | rest_hours | voyages | parts | qhse_reports

# Vérifier le résultat dans PostgreSQL
psql -U marasoft_etl -d marasoft_kpi -c "SELECT * FROM mv_kpi_vessel_daily LIMIT 10;"

# Rafraîchir la vue manuellement
psql -U marasoft_etl -d marasoft_kpi -c "REFRESH MATERIALIZED VIEW CONCURRENTLY mv_kpi_vessel_daily;"
```

---

## 6. Requêtes KPI typiques pour le dashboard

```sql
-- Navires avec certificats expirés ou critiques
SELECT v.name, c.cert_name, c.expires_at, c.status, c.days_until_expiry
FROM certificates c
JOIN vessels v ON v.vessel_id = c.vessel_id
WHERE c.status IN ('expired', 'critical')
ORDER BY c.days_until_expiry ASC;

-- Heures moteur par navire (dernière valeur)
SELECT v.name, kpi.engine_hours_total, kpi.engine_hours_last_7d
FROM mv_kpi_vessel_daily kpi
JOIN vessels v ON v.vessel_id = kpi.vessel_id
ORDER BY kpi.engine_hours_total DESC;

-- Violations MLC 30 derniers jours
SELECT cm.first_name || ' ' || cm.last_name AS marin, v.name AS navire,
       COUNT(*) AS nb_violations,
       SUM(rhv.deficit_hours) AS heures_manquantes
FROM rest_hours_violations rhv
JOIN crew_members cm ON cm.crew_member_id = rhv.crew_member_id
JOIN vessels v ON v.vessel_id = cm.vessel_id
WHERE rhv.period_date >= CURRENT_DATE - 30
GROUP BY marin, navire
ORDER BY nb_violations DESC;

-- Snapshot KPI complet du jour
SELECT vessel_name,
       engine_hours_total,
       jobs_open, jobs_overdue,
       certs_expired, certs_expiring_7d, certs_expiring_30d,
       rest_violations_30d,
       crew_onboard,
       parts_below_min,
       qhse_overdue
FROM mv_kpi_vessel_daily
ORDER BY jobs_overdue DESC, certs_expired DESC;
```

---

## 7. Structure du projet

```
marasoft_etl/
├── etl_run.py              ← Point d'entrée principal
├── requirements.txt
├── .env.example            ← Template de configuration
├── .env                    ← Configuration locale (ne pas commiter)
├── etl/
│   ├── config.py           ← Settings via variables d'environnement
│   ├── api_client.py       ← Client HTTP avec retry & rate-limiting
│   ├── extractors.py       ← Appels API Marasoft
│   ├── transformers.py     ← Normalisation & calculs KPI dérivés
│   └── db.py               ← Connexion PostgreSQL & upsert
├── sql/
│   └── schema.sql          ← DDL tables + vue matérialisée
└── logs/                   ← Logs locaux (dev)
```
