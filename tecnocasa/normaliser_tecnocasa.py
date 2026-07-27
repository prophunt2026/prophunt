import json
import re
from datetime import datetime, timezone

TYPES_BIEN_URL = {
    "appartement": "appartement",
    "villa": "villa",
    "terrain": "terrain",
    "bureau": "local_commercial",
    "immeubles": "immeuble",
    "immeuble": "immeuble",
    "duplex": "duplex",
    "studio": "studio",
    "local-commercial": "local_commercial",
}

# Traduction "libellé français Tecnocasa" -> clé standard equipements
EQUIPEMENT_LABELS = {
    "climatisation": "climatisation",
    "ascenseur": "ascenseur",
    "chauffage": "chauffage",
    "jardin": "jardin",
    "concierge": "concierge",
    "balcon": "balcon",
    "terrasse": "terrasse",
}


def extraire_transaction_et_type(url: str) -> tuple:
    """Lit /vendre/appartement/... ou /louer/villa/... dans l'URL."""
    match = re.match(r"https://www\.tecnocasa\.tn/(vendre|louer)/([^/]+)/", url or "")
    if not match:
        return "vente", "autre"
    transaction_brute, type_brut = match.groups()
    type_transaction = "location" if transaction_brute == "louer" else "vente"
    type_bien = TYPES_BIEN_URL.get(type_brut, "autre")
    return type_transaction, type_bien


def extraire_nombre(texte):
    if texte is None:
        return None
    if isinstance(texte, (int, float)):
        return int(texte)
    match = re.search(r"\d+", str(texte))
    return int(match.group()) if match else None


def separer_ville(ville_brute: str) -> tuple:
    """Tecnocasa donne 'Mahdia, Rue hiboun - Hiboun' : on sépare
    ville principale (avant la 1ère virgule) et le reste (adresse/quartier)."""
    if not ville_brute:
        return None, None
    parties = [p.strip() for p in ville_brute.split(",", 1)]
    ville = parties[0] if parties else None
    reste = parties[1] if len(parties) > 1 else None
    return ville, reste


def construire_equipements(liste_brute: list) -> dict:
    """Transforme ['Climatisation', 'Garage (2 places)', 'Vitrine']
    en dict de booléens + une entrée 'autres' pour ce qui n'est pas reconnu."""
    equip = {}
    autres = []

    for label in liste_brute or []:
        label_lower = label.strip().lower()

        # Cas particulier : "Garage (N places)"
        match_garage = re.match(r"garage \((\d+) places?\)", label_lower)
        if match_garage:
            equip["garage"] = True
            equip["places_parking"] = int(match_garage.group(1))
            continue

        cle = EQUIPEMENT_LABELS.get(label_lower)
        if cle:
            equip[cle] = True
        else:
            autres.append(label)

    if autres:
        equip["autres"] = autres

    return equip


# ==========================================================
# NOUVEAU : normalisation du téléphone
# ==========================================================
# Le scraper (tecnocasa_details.py) fournit maintenant "telephone" comme
# une liste (ex: ["+21628800424", "28800424"]). On sécurise quand même
# le cas où une valeur brute serait une simple chaîne.
def normaliser_telephones(valeur) -> list:
    if not valeur:
        return []
    if isinstance(valeur, list):
        return [t for t in valeur if t]
    return [valeur]


def normaliser_annonce_tecnocasa(brute: dict) -> dict:
    match_id = re.search(r"/(\d+)\.html", brute.get("url", "") or "")
    id_source = match_id.group(1) if match_id else None

    type_transaction, type_bien = extraire_transaction_et_type(brute.get("url"))
    surface = brute.get("surface")
    ville, quartier = separer_ville(brute.get("ville"))

    # Un terrain n'a pas de "surface habitable" : la surface va dans
    # superficie_terrain, pas superficie_habitable.
    est_terrain = type_bien == "terrain"

    superficie_totale = surface
    superficie_habitable = None if est_terrain else surface
    superficie_terrain = surface if est_terrain else None

    titre = brute.get("titre") or None
    description = brute.get("description")
    if not titre and description:
        titre = description[:80].rsplit(" ", 1)[0] + "…"

    telephones = normaliser_telephones(brute.get("telephone"))

    alertes = []
    if surface is not None and surface < 5:
        alertes.append(f"Surface suspecte ({surface} m²) — à vérifier manuellement")
    if not brute.get("titre"):
        alertes.append("Titre manquant à la source")
    if not brute.get("equipements"):
        alertes.append("Aucun équipement détecté pour cette annonce")
    if not telephones:
        alertes.append("Aucun téléphone récupéré pour cette annonce")

    return {
        "listing": {
            "id_source": id_source,
            "id_universel": f"tecnocasa_{id_source}" if id_source else None,
            "url_source": brute.get("url"),
            "url_canonique": brute.get("url"),
            "date_scraping": datetime.now(timezone.utc).isoformat(),
            "date_publication": None,
            "date_maj": None,
            "statut": "actif",
            "langue": "fr",
        },
        "transaction": {
            "type": type_transaction,
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
            "type": type_bien,
            "sous_type": None,
            "usage": "residentiel" if type_bien != "local_commercial" else "commercial",
            "superficie_totale": superficie_totale,
            "superficie_habitable": superficie_habitable,
            "superficie_terrain": superficie_terrain,
            "nombre_pieces": extraire_nombre(brute.get("pieces")),
            "nombre_chambres": extraire_nombre(brute.get("chambres")),
            "nombre_salles_bain": extraire_nombre(brute.get("salles_de_bain")),
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
            "delegation": ville,
            "ville": ville,
            "localite": quartier,
            "quartier": quartier,
            "adresse": brute.get("adresse_agence"),
            "code_postal": None,
            "proximites": [],
            "coordonnees": {"latitude": None, "longitude": None},
            "zone": None,
        },
        "equipements": construire_equipements(brute.get("equipements", [])),
        "description": {
            "titre": titre,
            "texte": description,
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
            "whatsapp": brute.get("whatsapp"),
            "email": brute.get("email"),
            "site_web": None,
            "logo_agence": None,
            "photo_agence": None,
            "url_profil": None,
            "annonces_vendeur": None,
            "membre_depuis": None,
            "verifie": None,
        },
        "metadonnees_scraping": {
            "source": "tecnocasa",
            "selecteur_html": {},
            "methode": "requests",
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
    # <-- changez ce chemin par le vôtre
    with open("tecnocasa.json", encoding="utf-8") as f:
        annonces_brutes = json.load(f)

    annonces_normalisees = [normaliser_annonce_tecnocasa(a) for a in annonces_brutes]

    # <-- et celui-ci
    with open("tecnocasa_standard.json", "w", encoding="utf-8") as f:
        json.dump(annonces_normalisees, f, ensure_ascii=False, indent=2)

    suspectes = [a for a in annonces_normalisees if a["metadonnees_scraping"]["erreurs"]]

    print(f"{len(annonces_normalisees)} annonces normalisées")
    print(f"{len(suspectes)} annonces avec au moins une alerte qualité")