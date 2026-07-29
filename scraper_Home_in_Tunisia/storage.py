"""
storage.py - Lecture, écriture atomique et logique de fusion (Merge MD5).
"""

import json
import os
from datetime import datetime, timezone
from parsers import is_valid_record
from config import OUTPUT_PATH
from models import compute_content_hash


def record_key(record):
    """Identifiant stable d'un bien."""
    listing = record.get("listing", {})
    return listing.get("id_source") or listing.get("url_source")


def atomic_save_records(records, path=OUTPUT_PATH):
    """Écriture atomique sécurisée contre les crashs/corruptions."""
    temp_path = f"{path}.tmp"
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    os.replace(temp_path, path)


def load_existing_records(path=OUTPUT_PATH):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"Impossible de lire le fichier existant ({path}) : {e}. On repart de zéro.")
        return {}
    
    result = {}
    for record in data:
        key = record_key(record)
        if key is not None:
            result[key] = record
    return result


def merge_scrape_into_existing(existing_by_key, freshly_scraped, is_full_scrape=False):
    """Fusion rapide basée sur le Hash MD5."""
    now_iso = datetime.now(timezone.utc).isoformat()
    seen_keys = set()
    final_by_key = dict(existing_by_key)
    stats = {"nouveaux": 0, "mis_a_jour": 0, "inchanges": 0, "absents": 0}

    for new_record in freshly_scraped:
        key = record_key(new_record)
        if not key:
            continue
        seen_keys.add(key)

        new_hash = compute_content_hash(new_record)
        new_record["metadonnees_scraping"]["hash_contenu"] = new_hash
        new_record["metadonnees_scraping"]["date_derniere_verification"] = now_iso
        new_record["metadonnees_scraping"]["absences_consecutives"] = 0

        if key not in existing_by_key:
            new_record["listing"]["statut"] = new_record["listing"].get("statut") or "actif"
            final_by_key[key] = new_record
            stats["nouveaux"] += 1
        else:
            old_record = existing_by_key[key]
            old_hash = old_record.get("metadonnees_scraping", {}).get("hash_contenu")

            if old_hash == new_hash:
                old_record["metadonnees_scraping"]["date_derniere_verification"] = now_iso
                old_record["metadonnees_scraping"]["absences_consecutives"] = 0
                final_by_key[key] = old_record
                stats["inchanges"] += 1
            else:
                new_record["listing"]["date_publication"] = (
                    old_record["listing"].get("date_publication") or new_record["listing"].get("date_publication")
                )
                new_record["listing"]["date_maj"] = now_iso
                final_by_key[key] = new_record
                stats["mis_a_jour"] += 1

    if is_full_scrape:
        for key, record in existing_by_key.items():
            if key not in seen_keys:
                meta = record.setdefault("metadonnees_scraping", {})
                meta["absences_consecutives"] = meta.get("absences_consecutives", 0) + 1
                stats["absents"] += 1

    return list(final_by_key.values()), stats

def clean_existing_records(records_dict):
    """Parcourt le dictionnaire BDD existant et supprime tous les biens non valides."""
    cleaned_dict = {}
    removed_count = 0
    reasons = {}

    for key, record in records_dict.items():
        is_valid, reason = is_valid_record(record)
        if is_valid:
            cleaned_dict[key] = record
        else:
            removed_count += 1
            reasons[reason] = reasons.get(reason, 0) + 1

    if removed_count > 0:
        print(f"\n🧹 Nettoyage BDD : {removed_count} biens indésirables supprimés de la BDD existante.")
        for reason, count in reasons.items():
            print(f"   - {count} supprimés car : {reason}")

    return cleaned_dict