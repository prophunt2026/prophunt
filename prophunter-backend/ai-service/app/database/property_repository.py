from pymongo import UpdateOne
from pymongo.errors import BulkWriteError, PyMongoError
from app.database.mongodb import get_collection

COLLECTION_NAME = "tecnocasa_properties"


def _ensure_index(collection) -> None:
    """Crée l'index unique sur listing.id_universel si absent (opération idempotente)."""
    collection.create_index(
        [("listing.id_universel", 1)],
        unique=True,
        sparse=True,
        name="idx_id_universel_unique",
    )


def save_properties(properties: list) -> dict:
   
    if not properties:
        print("[Repository] Aucune annonce à enregistrer.")
        return {"inserted": 0, "updated": 0, "ignored": 0}

    try:
        collection = get_collection(COLLECTION_NAME)
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
            print(f"[Repository] Aucune opération valide ({ignored} ignorées).")
            return {"inserted": 0, "updated": 0, "ignored": ignored}

        result = collection.bulk_write(operations, ordered=False)

        inserted = result.upserted_count
        updated  = result.modified_count

        print(
            f"[Repository] Résultat — "
            f"insérées : {inserted} | mises à jour : {updated} | ignorées : {ignored}"
        )
        return {"inserted": inserted, "updated": updated, "ignored": ignored}

    except BulkWriteError as e:
        # Certaines opérations ont réussi malgré l'erreur bulk
        inserted = e.details.get("nUpserted", 0)
        updated  = e.details.get("nModified", 0)
        errors   = e.details.get("writeErrors", [])
        print(f"[Repository] Écriture partielle : insérées={inserted}, mises à jour={updated}, erreurs={len(errors)}")
        for err in errors[:5]:
            print(f"  - doc #{err.get('index')} : {err.get('errmsg')}")
        return {"inserted": inserted, "updated": updated, "ignored": ignored}

    except PyMongoError as e:
        raise RuntimeError(f"[Repository] Erreur MongoDB : {e}") from e
