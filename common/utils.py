"""
Utilitaires partagés par les scrapers PropHunter TN :
- requêtes HTTP robustes (retries, backoff, timeout)
- limitation de fréquence (rate limiting) pour rester poli avec les serveurs
- export des résultats en JSON et CSV
- logging des erreurs
"""

import csv
import json
import logging
import random
import time
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "scraping.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------
class RateLimiter:
    """ÉTAPE 5 (limites de requêtes) : impose un délai (+ un peu de hasard)
    entre deux requêtes, pour éviter de surcharger le serveur cible et
    réduire le risque de blocage/ban."""

    def __init__(self, min_delay: float = 1.5, max_delay: float = 3.0):
        self.min_delay = min_delay
        self.max_delay = max_delay
        self._last_request_time = 0.0

    def wait(self):
        elapsed = time.time() - self._last_request_time
        delay = random.uniform(self.min_delay, self.max_delay)
        remaining = delay - elapsed
        if remaining > 0:
            time.sleep(remaining)
        self._last_request_time = time.time()


# ---------------------------------------------------------------------------
# Requêtes HTTP robustes
# ---------------------------------------------------------------------------
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9,ar;q=0.8,en;q=0.7",
}

logger = get_logger("utils")


def safe_get(
    url: str,
    session: requests.Session | None = None,
    max_retries: int = 3,
    timeout: int = 15,
    headers: dict | None = None,
) -> requests.Response | None:
    """ÉTAPE 5 (gestion des erreurs) : GET avec retries + backoff exponentiel.
    Retourne None si toutes les tentatives échouent (l'erreur est loggée, le
    scraping continue sans planter)."""
    s = session or requests
    merged_headers = {**DEFAULT_HEADERS, **(headers or {})}

    for attempt in range(1, max_retries + 1):
        try:
            resp = s.get(url, headers=merged_headers, timeout=timeout)
            if resp.status_code == 200:
                return resp
            if resp.status_code == 429:
                # Trop de requêtes : on attend plus longtemps avant de réessayer
                wait_time = 5 * attempt
                logger.warning(f"429 Too Many Requests sur {url} — pause {wait_time}s")
                time.sleep(wait_time)
                continue
            if resp.status_code in (403, 404, 410):
                logger.warning(f"{resp.status_code} sur {url} — abandon (non temporaire)")
                return None
            logger.warning(f"Statut {resp.status_code} sur {url} (tentative {attempt}/{max_retries})")
        except requests.RequestException as exc:
            logger.warning(f"Erreur réseau sur {url} (tentative {attempt}/{max_retries}) : {exc}")

        time.sleep(2 ** attempt)  # backoff exponentiel : 2s, 4s, 8s...

    logger.error(f"Échec définitif après {max_retries} tentatives : {url}")
    return None


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------
def export_to_json(records: list[dict], path: str):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    logger.info(f"{len(records)} annonces exportées vers {path}")


def flatten(d: dict, parent_key: str = "", sep: str = ".") -> dict:
    """Aplati un dict imbriqué en clés 'a.b.c' -> valeur, pour l'export CSV.
    Les listes sont converties en chaîne JSON compacte (CSV ne gère pas
    nativement les structures imbriquées)."""
    items = {}
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.update(flatten(v, new_key, sep=sep))
        elif isinstance(v, list):
            items[new_key] = json.dumps(v, ensure_ascii=False) if v else ""
        else:
            items[new_key] = v
    return items


def export_to_csv(records: list[dict], path: str):
    if not records:
        logger.warning("Aucune donnée à exporter en CSV.")
        return
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    flat_records = [flatten(r) for r in records]
    # Union de toutes les colonnes rencontrées (au cas où certaines annonces
    # ont des clés en plus/en moins, ex. proximites de longueur variable)
    fieldnames = []
    seen = set()
    for r in flat_records:
        for k in r.keys():
            if k not in seen:
                seen.add(k)
                fieldnames.append(k)
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(flat_records)
    logger.info(f"{len(records)} annonces exportées vers {path}")


def _get_nested(record: dict, dotted_key: str):
    value = record
    for part in dotted_key.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def deduplicate(records: list[dict], key: str = "listing.url_source") -> list[dict]:
    """Supprime les doublons en se basant sur une clé unique (par défaut :
    listing.url_source). Le paramètre 'key' accepte un chemin en notation
    pointée pour les schémas imbriqués."""
    seen = set()
    unique = []
    for r in records:
        k = _get_nested(r, key)
        if k and k not in seen:
            seen.add(k)
            unique.append(r)
    return unique
