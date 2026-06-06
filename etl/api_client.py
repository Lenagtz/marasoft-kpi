"""
etl/api_client.py — Client HTTP Marasoft
Gère : authentification Bearer, retry exponentiel, rate-limiting, pagination.
"""

import logging
import time
from typing import Any, Dict, Iterator, List, Optional
from urllib.parse import urljoin

import httpx

from etl.config import settings

log = logging.getLogger(__name__)

# ─── Client singleton ────────────────────────────────────────────────────────

_client: Optional[httpx.Client] = None


def get_client() -> httpx.Client:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.Client(
            base_url=settings.api_base_url,
            headers={
                "ApiKey": settings.api_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            timeout=settings.api_timeout,
            follow_redirects=True,
        )
    return _client


# ─── Rate limiter simple (token bucket) ──────────────────────────────────────

class _RateLimiter:
    def __init__(self, rps: float):
        self._min_interval = 1.0 / rps
        self._last_call = 0.0

    def wait(self):
        now = time.monotonic()
        elapsed = now - self._last_call
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_call = time.monotonic()


_limiter = _RateLimiter(settings.api_rate_limit_rps)


# ─── Requête avec retry ───────────────────────────────────────────────────────

def get(path: str, params: Optional[Dict[str, Any]] = None) -> Any:
    """
    GET avec retry exponentiel.
    Retourne le body JSON parsé (list ou dict).
    """
    params = params or {}
    last_exc = None

    for attempt in range(1, settings.api_max_retries + 1):
        _limiter.wait()
        try:
            resp = get_client().get(path, params=params)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status in (401, 403):
                log.error("Erreur d'authentification (%d) sur %s — vérifiez MARASOFT_API_KEY", status, path)
                raise
            if status == 429:
                retry_after = int(exc.response.headers.get("Retry-After", "10"))
                log.warning("Rate limit 429 sur %s — attente %ds", path, retry_after)
                time.sleep(retry_after)
            elif status >= 500:
                wait = settings.api_retry_delay * (2 ** (attempt - 1))
                log.warning("Erreur serveur %d sur %s (tentative %d/%d) — retry dans %.1fs",
                            status, path, attempt, settings.api_max_retries, wait)
                time.sleep(wait)
            else:
                raise
            last_exc = exc
        except (httpx.TimeoutException, httpx.ConnectError) as exc:
            wait = settings.api_retry_delay * (2 ** (attempt - 1))
            log.warning("Timeout/connexion sur %s (tentative %d/%d) — retry dans %.1fs",
                        path, attempt, settings.api_max_retries, wait)
            time.sleep(wait)
            last_exc = exc

    raise RuntimeError(f"Échec après {settings.api_max_retries} tentatives sur {path}") from last_exc


def get_paginated(path: str, params: Optional[Dict[str, Any]] = None) -> List[Dict]:
    """
    Gère la pagination Marasoft via GetRequisitionDetails / GetNextRequisitionDetails.
    Pour les endpoints standards, retourne directement la liste.
    """
    params = params or {}
    first_batch = get(path, params)

    if not isinstance(first_batch, list):
        return [first_batch] if first_batch else []

    results = list(first_batch)

    # Pagination spécifique PNPurchase (1000 lignes par page)
    if "/PNPurchase/GetRequisitionDetails" in path and len(first_batch) == 1000:
        next_path = path.replace("GetRequisitionDetails", "GetNextRequisitionDetails")
        while True:
            batch = get(next_path, params)
            if not batch:
                break
            results.extend(batch)
            if len(batch) < 1000:
                break
            log.debug("  pagination: %d enregistrements récupérés", len(results))

    return results
