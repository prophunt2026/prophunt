from datetime import datetime, timezone
from pymongo import UpdateOne
from pymongo.errors import BulkWriteError, PyMongoError

from app.scrapers.registry import SCRAPERS
from app.database.mongodb import get_collection, get_db_collection


def sync_site_to_crud(site: str) -> dict:
    """
    Synchronise les annonces d'un site depuis la collection prophunter_ia.<site>_properties
    vers la collection unifiée prophunter.properties (base lue par le service CRUD).

    Filtre : uniquement les annonces avec date_scraping > last_sync_date pour ce site.
    Mise à jour : enregistre la nouvelle last_sync_date dans prophunter.sync_metadata.

    Args:
        site: identifiant de la source (ex: 'mubawab', 'tecnocasa', 'tayara', etc.)

    Returns:
        dict: { site, synced, inserted, updated, last_sync_date }
    """
    config = SCRAPERS.get(site)
    if not config:
        raise ValueError(f"Source '{site}' inconnue dans le registry.")

    collection_name = config["collection"]

    # Source : prophunter_ia.<site>_properties
    ia_col = get_collection(collection_name)

    # Cibles : prophunter.properties et prophunter.sync_metadata
    crud_col = get_db_collection("prophunter", "properties")
    sync_meta_col = get_db_collection("prophunter", "sync_metadata")

    # 1. Récupération de la dernière date de sync pour ce site
    meta_doc = sync_meta_col.find_one({"_id": site})
    last_sync_date = meta_doc.get("last_sync_date") if meta_doc else None

    # 2. Construction de la requête filtrée par date
    query = {}
    if last_sync_date:
        query = {"listing.date_scraping": {"$gt": last_sync_date}}
        print(f"[Sync:{site}] Recherche des annonces scrapées après : {last_sync_date}")
    else:
        print(f"[Sync:{site}] Première synchronisation (aucune last_sync_date). Récupération de toutes les annonces.")

    docs = list(ia_col.find(query))
    if not docs:
        print(f"[Sync:{site}] Aucune nouvelle annonce à synchroniser.")
        now_iso = datetime.now(timezone.utc).isoformat()
        sync_meta_col.update_one(
            {"_id": site},
            {
                "$set": {
                    "site": site,
                    "last_status": "SUCCESS",
                    "last_synced_count": 0,
                    "updated_at": now_iso,
                }
            },
            upsert=True,
        )
        return {
            "site": site,
            "synced": 0,
            "inserted": 0,
            "updated": 0,
            "last_sync_date": last_sync_date,
        }

    # 3. Préparation du bulkWrite avec upsert sur listing.id_universel
    operations = []
    max_date_scraping = last_sync_date

    for doc in docs:
        # Supprimer la clé _id du document source pour éviter l'erreur d'immutabilité lors de l'upsert
        doc_copy = dict(doc)
        doc_copy.pop("_id", None)

        listing = doc_copy.get("listing", {})
        id_universel = listing.get("id_universel")
        id_source = listing.get("id_source")
        source = doc_copy.get("metadonnees_scraping", {}).get("source") or site

        # Normalisation fallback d'id_universel si absent
        if not id_universel and id_source:
            id_universel = f"{source}_{id_source}"
            if "listing" not in doc_copy:
                doc_copy["listing"] = {}
            doc_copy["listing"]["id_universel"] = id_universel

        if not id_universel:
            continue

        # Suivre la date_scraping la plus récente
        date_scraping = listing.get("date_scraping")
        if date_scraping and (not max_date_scraping or date_scraping > max_date_scraping):
            max_date_scraping = date_scraping

        operations.append(
            UpdateOne(
                filter={"listing.id_universel": id_universel},
                update={"$set": doc_copy},
                upsert=True,
            )
        )

    if not operations:
        print(f"[Sync:{site}] Aucune annonce valide avec id_universel pour la synchronisation.")
        return {
            "site": site,
            "synced": 0,
            "inserted": 0,
            "updated": 0,
            "last_sync_date": last_sync_date,
        }

    # 4. Exécution de l'upsert idempotent dans prophunter.properties
    try:
        result = crud_col.bulk_write(operations, ordered=False)
        inserted = result.upserted_count
        updated = result.modified_count
        synced_count = len(operations)

        now_iso = datetime.now(timezone.utc).isoformat()
        new_sync_date = max_date_scraping or now_iso

        # 5. Mise à jour de la dernière date de sync dans prophunter.sync_metadata
        sync_meta_col.update_one(
            {"_id": site},
            {
                "$set": {
                    "site": site,
                    "last_sync_date": new_sync_date,
                    "last_status": "SUCCESS",
                    "last_synced_count": synced_count,
                    "inserted_count": inserted,
                    "updated_count": updated,
                    "updated_at": now_iso,
                }
            },
            upsert=True,
        )

        print(
            f"[Sync:{site}] Synchronisation réussie vers prophunter.properties : "
            f"{synced_count} annonces (insérées: {inserted}, mises à jour: {updated}) | "
            f"Nouvelle last_sync_date: {new_sync_date}"
        )

        return {
            "site": site,
            "synced": synced_count,
            "inserted": inserted,
            "updated": updated,
            "last_sync_date": new_sync_date,
        }

    except BulkWriteError as e:
        inserted = e.details.get("nUpserted", 0)
        updated = e.details.get("nModified", 0)
        errors = e.details.get("writeErrors", [])
        print(f"[Sync:{site}] Écriture partielle dans prophunter.properties : {inserted} insérées, {len(errors)} erreurs")

        # Marquer l'erreur dans sync_metadata
        now_iso = datetime.now(timezone.utc).isoformat()
        sync_meta_col.update_one(
            {"_id": site},
            {
                "$set": {
                    "site": site,
                    "last_status": "PARTIAL_ERROR",
                    "error": str(errors[:2]),
                    "updated_at": now_iso,
                }
            },
            upsert=True,
        )
        return {
            "site": site,
            "synced": inserted + updated,
            "inserted": inserted,
            "updated": updated,
            "last_sync_date": last_sync_date,
        }

    except PyMongoError as e:
        print(f"[Sync:{site}] Erreur MongoDB lors de la synchronisation : {e}")
        now_iso = datetime.now(timezone.utc).isoformat()
        sync_meta_col.update_one(
            {"_id": site},
            {
                "$set": {
                    "site": site,
                    "last_status": "FAILED",
                    "error": str(e),
                    "updated_at": now_iso,
                }
            },
            upsert=True,
        )
        raise RuntimeError(f"[Sync:{site}] Erreur MongoDB : {e}") from e
