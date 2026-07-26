import json
import re
from datetime import datetime, timezone

# ==========================================
# Tables de correspondance
# ==========================================

EQUIPEMENT_LABELS = {
    "garage": "garage",
    "ascenseur": "ascenseur",
    "concierge": "concierge",
    "climatisation": "climatisation",
    "chauffage central": "chauffage",
    "chauffage": "chauffage",
    "terrasse": "terrasse",
    "balcon": "balcon",
    "jardin": "jardin",
    "piscine": "piscine",
    "cuisine équipée": "cuisine_equipee",
    "porte blindée": "porte_blindee",
    "interphone": "interphone",
    "vidéophone": "videophone",
    "cheminée": "cheminee",
    "dressing": "dressing",
    "salle de sport": "salle_de_sport",
}

TYPES_BIEN = {
    "appartement": "appartement",
    "villa": "villa",
    "duplex": "duplex",
    "studio": "studio",
    "terrain": "terrain",
    "bureau": "local_commercial",
    "local commercial": "local_commercial",
    "immeuble": "immeuble",
}


def deviner_type_bien(titre: str) -> str:
    titre_lower = (titre or "").lower()
    for mot_cle, valeur in TYPES_BIEN.items():
        if mot_cle in titre_lower:
            return valeur
    return "appartement"


def construire_equipements(liste_brute: list) -> dict:
    equip = {}
    autres = []
    for item in liste_brute or []:
        if not item:
            continue
        label = item[0].strip().lower()
        cle = EQUIPEMENT_LABELS.get(label)
        if cle:
            equip[cle] = True
            if cle == "garage" and len(item) > 1:
                match = re.search(r"\d+", item[1])
                if match:
                    equip["places_parking"] = int(match.group())
        else:
            autres.append(item[0])
    if autres:
        equip["autres"] = autres
    return equip


# ==========================================================
# NOUVEAU : normalisation du téléphone
# ==========================================================
# mubawab_details.py + mubawab_telephone.py fournissent "telephone" comme
# une liste (via Selenium). On sécurise quand même le cas d'une chaîne seule.
def normaliser_telephones(valeur) -> list:
    if not valeur:
        return []
    if isinstance(valeur, list):
        return [t for t in valeur if t]
    return [valeur]


def normaliser_annonce_mubawab(brute: dict) -> dict:
    match_id = re.search(r"/a/(\d+)/", brute.get("url", "") or "")
    id_source = match_id.group(1) if match_id else None

    surface = brute.get("surface")
    telephones = normaliser_telephones(brute.get("telephone"))

    alertes = []
    if surface is not None and surface < 5:
        alertes.append(f"Surface suspecte ({surface} m²) — à vérifier manuellement")
    if not telephones:
        alertes.append("Aucun téléphone récupéré pour cette annonce")

    return {
        "listing": {
            "id_source": id_source,
            "id_universel": f"mubawab_{id_source}" if id_source else None,
            "url_source": brute.get("url"),
            "url_canonique": brute.get("url"),
            "date_scraping": datetime.now(timezone.utc).isoformat(),
            "date_publication": None,
            "date_maj": None,
            "statut": "actif",
            "langue": "fr",
        },
        "transaction": {
            "type": "vente",
            "prix": brute.get("prix"),
            "devise": brute.get("devise", "TND"),
            "prix_negociable": None,
            "prix_m2": (
                round(brute["prix"] / surface, 2)
                if brute.get("prix") and surface
                else None
            ),
            "loyer_mensuel": None,
            "charges_mensuelles": None,
            "caution": None,
            "frais_agence": None,
            "disponibilite": None,
            "disponibilite_date": None,
        },
        "bien": {
            "type": deviner_type_bien(brute.get("titre")),
            "sous_type": None,
            "usage": "residentiel",
            "superficie_totale": surface,
            "superficie_habitable": surface,
            "superficie_terrain": None,
            "nombre_pieces": brute.get("pieces"),
            "nombre_chambres": brute.get("chambres"),
            "nombre_salles_bain": brute.get("salles_de_bain"),
            "nombre_salles_eau": None,
            "nombre_etages_total": None,
            "etage": None,
            "dernier_etage": None,
            "annee_construction": None,
            "etat_general": None,
            "standing": None,
            "meuble": None,
            "orientation": None,
            "vue": None,
        },
        "localisation": {
            "pays": "Tunisie",
            "pays_code": "TN",
            "gouvernorat": None,
            "delegation": brute.get("ville"),
            "ville": brute.get("ville"),
            "localite": None,
            "quartier": None,
            "adresse": None,
            "code_postal": None,
            "proximites": [],
            "coordonnees": {"latitude": None, "longitude": None},
            "zone": None,
        },
        "equipements": construire_equipements(brute.get("equipements", [])),
        "description": {
            "titre": brute.get("titre"),
            "texte": brute.get("description"),
            "texte_ar": None,
            "points_forts": [],
            "mentions_legales": None,
        },
        "medias": {
            "photos": [{"url": img} for img in (brute.get("images") or [])],
            "videos": [],
            "plans": [],
            "visite_virtuelle": None,
            "nombre_photos": len(brute.get("images") or []),
        },
        "contact": {
            "type_vendeur": "agence" if brute.get("agence") else None,
            "nom_vendeur": None,
            "nom_agence": brute.get("agence"),
            "telephone": telephones,
            "whatsapp": None,
            "email": None,
            "site_web": None,
            "logo_agence": None,
            "photo_agence": None,
            "url_profil": None,
            "annonces_vendeur": None,
            "membre_depuis": None,
            "verifie": None,
        },
        "metadonnees_scraping": {
            "source": "mubawab",
            "selecteur_html": {},
            "methode": "requests+selenium",
            "statut_scraping": "succes",
            "erreurs": alertes,
            "temps_scraping_ms": None,
            "user_agent": None,
            "proxy_utilise": None,
            "cache": None,
        },
        "scoring_ia": {
            "prix_estime_marche": None,
            "decote_pourcentage": None,
            "score_opportunite": None,
            "confiance_estimation": None,
            "tendance_quartier": None,
            "rentabilite_locative": None,
            "delai_vente_estime": None,
            "alertes": [],
        },
        "donnees_brutes": {
            "json_ld": None,
            "html_snippet": None,
        },
    }


if __name__ == "__main__":
    # <-- changez ce chemin par le vôtre (là où se trouve votre mubawab.json)
    with open("mubawab.json", encoding="utf-8") as f:
        annonces_brutes = json.load(f)

    annonces_normalisees = [normaliser_annonce_mubawab(a) for a in annonces_brutes]

    # <-- et celui-ci, pour le fichier de sortie
    with open("mubawab_standard.json", "w", encoding="utf-8") as f:
        json.dump(annonces_normalisees, f, ensure_ascii=False, indent=2)

    suspectes = [a for a in annonces_normalisees if a["metadonnees_scraping"]["erreurs"]]

    print(f"{len(annonces_normalisees)} annonces normalisées")
    print(f"{len(suspectes)} annonces avec une alerte qualité à vérifier")
    for a in suspectes[:10]:
        print(" -", a["listing"]["url_source"], "->", a["metadonnees_scraping"]["erreurs"])