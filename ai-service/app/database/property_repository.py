from pymongo import UpdateOne
from pymongo.errors import BulkWriteError, PyMongoError
from app.database.mongodb import get_collection


def _ensure_index(collection) -> None:
    """Crée l'index unique sur listing.id_universel (idempotent)."""
    collection.create_index(
        [("listing.id_universel", 1)],
        unique=True,
        sparse=True,
        name="idx_id_universel_unique",
    )


def ensure_all_indexes() -> None:

    """
    S'assure que les index uniques sur listing.id_universel existent sur toutes
    les collections de prophunter_ia ainsi que sur prophunter.properties.
    Appelé au démarrage de l'application (lifespan).
    """
    from app.scrapers.registry import SCRAPERS
    from app.database.mongodb import get_db_collection

    try:
        # Index sur toutes les collections de l'IA
        for source, config in SCRAPERS.items():
            collection_name = config["collection"]
            col = get_collection(collection_name)
            _ensure_index(col)

        # Index sur la collection unifiée prophunter.properties
        crud_col = get_db_collection("prophunter", "properties")
        _ensure_index(crud_col)

        print("[Repository] Indexation unique (listing.id_universel) initialisée avec succès sur toutes les collections.")
    except Exception as e:
        print(f"[Repository] Avertissement lors de la création des index : {e}")


def save_to_ia_collection(properties: list, collection_name: str) -> dict:
    """
    Alias pour save_properties.
    Enregistre les annonces normalisées dans la collection MongoDB spécifiée dans prophunter_ia.
    """
    return save_properties(properties, collection_name)



def save_properties(properties: list, collection_name: str) -> dict:
    """
    Enregistre les annonces normalisées dans la collection MongoDB spécifiée.

    Stratégie upsert par listing.id_universel :
      - Inconnue → insertion
      - Existante → mise à jour ($set)
      - Sans id   → ignorée

    Args:
        properties:      liste de dicts au format standard PropHunter.
        collection_name: nom de la collection cible (depuis le registry).

    Returns:
        dict: { inserted, updated, ignored }
    """
    if not properties:
        print(f"[Repository:{collection_name}] Aucune annonce à enregistrer.")
        return {"inserted": 0, "updated": 0, "ignored": 0}

    collection = get_collection(collection_name)
    _ensure_index(collection)

    operations = []
    ignored = 0

    for prop in properties:
        id_universel = prop.get("listing", {}).get("id_universel")
        if not id_universel:
            ignored += 1
            continue
        operations.append(
            UpdateOne(
                filter={"listing.id_universel": id_universel},
                update={"$set": prop},
                upsert=True,
            )
        )

    if not operations:
        print(f"[Repository:{collection_name}] Aucune opération valide ({ignored} ignorées).")
        return {"inserted": 0, "updated": 0, "ignored": ignored}

    try:
        result = collection.bulk_write(operations, ordered=False)
        inserted = result.upserted_count
        updated  = result.modified_count
        print(
            f"[Repository:{collection_name}] "
            f"insérées={inserted} | mises à jour={updated} | ignorées={ignored}"
        )
        return {"inserted": inserted, "updated": updated, "ignored": ignored}

    except BulkWriteError as e:
        inserted = e.details.get("nUpserted", 0)
        updated  = e.details.get("nModified", 0)
        errors   = e.details.get("writeErrors", [])
        print(f"[Repository:{collection_name}] Écriture partielle : {inserted} insérées, {len(errors)} erreurs")
        for err in errors[:5]:
            print(f"  - doc #{err.get('index')} : {err.get('errmsg')}")
        return {"inserted": inserted, "updated": updated, "ignored": ignored}

    except PyMongoError as e:
        raise RuntimeError(f"[Repository:{collection_name}] Erreur MongoDB : {e}") from e
