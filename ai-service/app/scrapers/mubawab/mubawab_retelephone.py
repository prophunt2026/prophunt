"""
Reprise ciblée : ne réessaie que les annonces de mubawab.json dont le
téléphone est vide, au lieu de tout relancer depuis mubawab_scraper.py
(qui recollecterait inutilement tous les liens).

Utilise la même logique de récupération/redémarrage de Chrome que
mubawab_scraper.py en cas de crash (InvalidSessionIdException).
"""

import json
import time

from mubawab_telephone import creer_driver, scraper_telephone_mubawab
from selenium.common.exceptions import InvalidSessionIdException

FICHIER = "mubawab.json"
SAUVEGARDE_TOUTES_LES = 25
REDEMARRAGE_DRIVER_TOUTES_LES = 200


def sauvegarder(annonces):
    with open(FICHIER, "w", encoding="utf-8") as f:
        json.dump(annonces, f, ensure_ascii=False, indent=4)


with open(FICHIER, encoding="utf-8") as f:
    annonces = json.load(f)

a_faire = [a for a in annonces if not a.get("telephone")]

print(f"{len(a_faire)} annonces avec téléphone vide à retenter (sur {len(annonces)} au total)")

driver = creer_driver(headless=True)

try:

    for index, annonce in enumerate(a_faire, start=1):

        print(f"\nTéléphone {index}/{len(a_faire)} - {annonce['url']}")

        try:
            telephones = scraper_telephone_mubawab(annonce["url"], driver)

        except InvalidSessionIdException as e:
            print(f"Session Chrome perdue ({e.__class__.__name__}), redémarrage du navigateur...")

            try:
                driver.quit()
            except Exception:
                pass

            driver = creer_driver(headless=True)

            try:
                telephones = scraper_telephone_mubawab(annonce["url"], driver)
            except Exception as e2:
                print("Echec même après redémarrage :", e2)
                telephones = []

        annonce["telephone"] = telephones

        print("Trouvé :", telephones if telephones else "aucun")

        if index % SAUVEGARDE_TOUTES_LES == 0:
            sauvegarder(annonces)
            print(f"Sauvegarde intermédiaire ({index}/{len(a_faire)} traités)")

        if index % REDEMARRAGE_DRIVER_TOUTES_LES == 0:
            print(f"Redémarrage préventif du navigateur (après {index} annonces)")
            driver.quit()
            driver = creer_driver(headless=True)

        time.sleep(1)

finally:
    try:
        driver.quit()
    except Exception:
        pass

sauvegarder(annonces)

toujours_vides = sum(1 for a in annonces if not a.get("telephone"))

print("\n==============================")
print("TERMINE")
print("Annonces encore sans téléphone :", toujours_vides, "/", len(annonces))
print(f"Fichier mis à jour : {FICHIER}")