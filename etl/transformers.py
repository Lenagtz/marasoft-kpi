"""
etl/transformers.py — Normalisation et calcul des champs dérivés KPI
Chaque fonction reçoit la liste brute de l'extracteur et retourne
une liste de dicts prêts à être insérés en base (snake_case, types Python).

NOTE : Les noms de champs API Marasoft peuvent varier selon la version.
Les helpers _get() gèrent plusieurs variantes connues.
"""

import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from etl.config import settings

log = logging.getLogger(__name__)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _get(d: Dict, *keys: str, default=None) -> Any:
    """Essaie plusieurs clés alternatives (API Marasoft inconsistente)."""
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return default


def _parse_date(val: Any) -> Optional[date]:
    if val is None:
        return None
    if isinstance(val, date):
        return val
    s = str(val)[:10]  # Tronque les timestamps ISO
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def _parse_dt(val: Any) -> Optional[datetime]:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    try:
        return datetime.fromisoformat(str(val).replace("Z", "+00:00"))
    except ValueError:
        return None


def _cert_status(expires_at: Optional[date]) -> str:
    if expires_at is None:
        return "unknown"
    today = date.today()
    delta = (expires_at - today).days
    if delta < 0:
        return "expired"
    if delta <= settings.cert_expiry_critical_days:
        return "critical"
    if delta <= settings.cert_expiry_warning_days:
        return "expiring_soon"
    return "valid"


def _rest_severity(deficit: float) -> str:
    if deficit <= 0:
        return "none"
    if deficit < 1:
        return "minor"
    if deficit < 2:
        return "major"
    return "critical"


# ─── Transformeurs ────────────────────────────────────────────────────────────

def transform_vessels(raw: List[Dict]) -> List[Dict]:
    out = []
    for r in raw:
        vessel_id = _get(r, "vesselId", "VesselId", "id", "Id", "Number", "number")
        if not vessel_id:
            continue
        out.append({
            "vessel_id":  str(vessel_id),
            "name":       _get(r, "name", "Name", "vesselName", "VesselName"),
            "imo_number": _get(r, "imoNumber", "IMONumber", "imo", "Number", "number"),
            "flag":       _get(r, "flag", "Flag", "flagState"),
            "synced_at":  datetime.utcnow(),
        })
    return out


def transform_components(raw: List[Dict]) -> List[Dict]:
    out = []
    for r in raw:
        comp_id = _get(r, "componentId", "ComponentId", "id", "Id")
        if not comp_id:
            continue
        out.append({
            "component_id":   str(comp_id),
            "vessel_id":      str(r.get("_vessel_id", "")),
            "name":           _get(r, "name", "Name", "componentName"),
            "code":           _get(r, "code", "Code", "componentCode"),
            "component_type": _get(r, "type", "Type", "componentType"),
            "is_counter":     bool(_get(r, "isCounter", "IsCounter", "hasCounter", default=False)),
        })
    return out


def transform_running_hours(raw: List[Dict]) -> List[Dict]:
    out = []
    for r in raw:
        comp_id = _get(r, "componentId", "ComponentId")
        recorded = _parse_dt(_get(r, "date", "Date", "recordedAt", "RecordedAt", "timestamp"))
        hours = _get(r, "hours", "Hours", "value", "Value", "runningHours")
        if not comp_id or hours is None:
            continue
        try:
            hours_val = float(hours)
        except (TypeError, ValueError):
            continue
        out.append({
            "component_id": str(comp_id),
            "vessel_id":    str(r.get("_vessel_id", "")),
            "recorded_at":  recorded,
            "hours_value":  round(hours_val, 2),
            # delta_hours calculé en base via trigger ou UPDATE post-insert
        })
    return out


def transform_maintenance_jobs(raw: List[Dict]) -> List[Dict]:
    out = []
    for r in raw:
        job_id = _get(r, "jobId", "JobId", "id", "Id")
        if not job_id:
            continue
        due_raw  = _get(r, "dueDate", "DueDate", "nextDueDate", "NextDueDate")
        done_raw = _get(r, "closedDate", "ClosedDate", "doneDate", "completedAt")
        due_date  = _parse_date(due_raw)
        closed_at = _parse_dt(done_raw)

        # Calcul status
        source = r.get("_source", "active")
        if source == "history" or closed_at:
            status = "done"
        elif due_date and due_date < date.today():
            status = "overdue"
        else:
            status = "open"

        out.append({
            "job_id":           str(job_id),
            "component_id":     str(_get(r, "componentId", "ComponentId") or ""),
            "vessel_id":        str(r.get("_vessel_id", "")),
            "job_name":         _get(r, "name", "Name", "jobName", "description"),
            "status":           status,
            "due_date":         due_date,
            "closed_at":        closed_at,
            "maintenance_type": _get(r, "type", "Type", "maintenanceType", default="unknown"),
            "hours_at_due":     float(_get(r, "hoursAtDue", "HoursAtDue") or 0) or None,
        })
    return out


def transform_certificates(raw: List[Dict]) -> List[Dict]:
    out = []
    for r in raw:
        cert_id = _get(r, "certificateId", "CertificateId", "id", "Id")
        if not cert_id:
            continue
        expires_at  = _parse_date(_get(r, "expiryDate", "ExpiryDate", "expireDate", "validTo"))
        issued_at   = _parse_date(_get(r, "issueDate",  "IssueDate",  "issuedDate", "validFrom"))
        today       = date.today()
        days_left   = (expires_at - today).days if expires_at else None

        out.append({
            "cert_id":         str(cert_id),
            "vessel_id":       str(r.get("_vessel_id") or ""),
            "crew_member_id":  str(_get(r, "crewMemberId", "CrewMemberId") or "") or None,
            "cert_type":       _get(r, "type", "Type", "certificateType", "certType"),
            "cert_name":       _get(r, "name", "Name", "certificateName"),
            "issued_at":       issued_at,
            "expires_at":      expires_at,
            "status":          _cert_status(expires_at),
            "days_until_expiry": days_left,
        })
    return out


def transform_crew_members(raw: List[Dict]) -> List[Dict]:
    out = []
    for r in raw:
        mid = _get(r, "crewMemberId", "CrewMemberId", "id", "Id")
        if not mid:
            continue
        contract = r.get("_contract") or {}
        out.append({
            "crew_member_id": str(mid),
            "vessel_id":      str(_get(r, "vesselId", "VesselId") or ""),
            "first_name":     _get(r, "firstName", "FirstName"),
            "last_name":      _get(r, "lastName",  "LastName"),
            "rank":           _get(r, "rank", "Rank", "rankName"),
            "nationality":    _get(r, "nationality", "Nationality"),
            "contract_start": _parse_date(_get(contract, "startDate", "StartDate",
                                               r, "contractStart")),
            "contract_end":   _parse_date(_get(contract, "endDate",   "EndDate",
                                               r, "contractEnd")),
        })
    return out


def transform_rest_hours(raw: List[Dict]) -> List[Dict]:
    out = []
    for r in raw:
        mid = _get(r, "crewMemberId", "CrewMemberId")
        period = _parse_date(_get(r, "date", "Date", "period", "Period"))
        actual = _get(r, "restHours", "RestHours", "hoursRest", "actualRestHours")
        if not mid or actual is None:
            continue
        try:
            actual_f = float(actual)
        except (TypeError, ValueError):
            continue

        required = settings.rest_hours_min_daily
        deficit  = max(0.0, required - actual_f)

        if deficit == 0:
            continue  # Pas de violation, pas de ligne

        out.append({
            "crew_member_id":       str(mid),
            "period_date":          period,
            "rest_hours_actual":    round(actual_f, 2),
            "rest_hours_required":  required,
            "deficit_hours":        round(deficit, 2),
            "severity":             _rest_severity(deficit),
        })
    return out


def transform_voyages(raw: List[Dict]) -> List[Dict]:
    out = []
    for r in raw:
        voyage_id = _get(r, "voyageId", "VoyageId", "id", "Id")
        if not voyage_id:
            continue
        dep = _parse_dt(_get(r, "departureDate", "DepartureDate", "startDate"))
        arr = _parse_dt(_get(r, "arrivalDate",   "ArrivalDate",   "endDate"))
        out.append({
            "voyage_id":        str(voyage_id),
            "vessel_id":        str(r.get("_vessel_id", "")),
            "departure_port":   _get(r, "departurePort", "DeparturePort", "from"),
            "arrival_port":     _get(r, "arrivalPort",   "ArrivalPort",   "to"),
            "departure_date":   dep,
            "arrival_date":     arr,
            "duration_days":    round((arr - dep).total_seconds() / 86400, 1)
                                if dep and arr else None,
            "voyage_type":      _get(r, "type", "Type", "voyageType", default="sea"),
        })
    return out


def transform_parts(raw: List[Dict]) -> List[Dict]:
    out = []
    for r in raw:
        part_id = _get(r, "partId", "PartId", "id", "Id")
        if not part_id:
            continue
        qty = _get(r, "quantity", "Quantity", "stockQuantity", "qty")
        min_qty = _get(r, "minimumQuantity", "MinimumQuantity", "minStock",
                       default=settings.parts_min_stock_default)
        try:
            qty_i = int(float(qty)) if qty is not None else None
            min_i = int(float(min_qty)) if min_qty is not None else settings.parts_min_stock_default
        except (TypeError, ValueError):
            qty_i = None
            min_i = settings.parts_min_stock_default

        out.append({
            "part_id":        str(part_id),
            "vessel_id":      str(r.get("_vessel_id", "")),
            "part_name":      _get(r, "name", "Name", "partName"),
            "part_number":    _get(r, "partNumber", "PartNumber", "number"),
            "quantity":       qty_i,
            "min_quantity":   min_i,
            "below_minimum":  (qty_i is not None and qty_i < min_i),
            "unit":           _get(r, "unit", "Unit", default="pcs"),
        })
    return out


def transform_qhse_reports(raw: List[Dict]) -> List[Dict]:
    out = []
    for r in raw:
        report_id = _get(r, "reportId", "ReportId", "id", "Id")
        if not report_id:
            continue
        due_date   = _parse_date(_get(r, "dueDate", "DueDate"))
        closed_at  = _parse_dt(_get(r, "closedDate", "ClosedDate", "completedAt"))
        today      = date.today()

        if closed_at:
            status = "closed"
        elif due_date and due_date < today:
            status = "overdue"
        elif due_date and (due_date - today).days <= settings.qhse_due_before_days:
            status = "due_soon"
        else:
            status = "open"

        out.append({
            "report_id":   str(report_id),
            "vessel_id":   str(r.get("_vessel_id", "")),
            "report_type": _get(r, "type", "Type", "reportType"),
            "title":       _get(r, "title", "Title", "name", "Name"),
            "due_date":    due_date,
            "closed_at":   closed_at,
            "status":      status,
            "priority":    _get(r, "priority", "Priority", default="normal"),
        })
    return out
