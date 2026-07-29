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

# Correspondance directe avec les valeurs exactes du champ "Type de bien"
# du site (section "Caractéristiques générales"). Prioritaire sur la
# devinette par mot-clé, car c'est une donnée structurée fournie par
# l'agence elle-même, pas une déduction.
TYPES_BIEN_SITE = {
    "appartement": "appartement",
    "villa": "villa",
    "duplex": "duplex",
    "studio": "studio",
    "terrain": "terrain",
    "bureau": "local_commercial",
    "local commercial": "local_commercial",
    "immeuble": "immeuble",
    "maison": "villa",
    "ferme": "terrain",
}


def deviner_type_bien(titre: str, description: str = "", type_site: str = None) -> str:

    # Priorité 1 : le champ structuré "Type de bien" du site lui-même.
    if type_site:
        type_site_lower = type_site.strip().lower()
        if type_site_lower in TYPES_BIEN_SITE:
            return TYPES_BIEN_SITE[type_site_lower]

    # Priorité 2 : le titre (signal plus fiable que la description, moins
    # de bruit), utilisé seulement si le champ du site est absent/inconnu.
    titre_lower = (titre or "").lower()

    for mot_cle, valeur in TYPES_BIEN.items():
        if mot_cle in titre_lower:
            return valeur

    # Priorité 3 : la description, en dernier recours.
    description_lower = (description or "").lower()

    for mot_cle, valeur in TYPES_BIEN.items():
        if mot_cle in description_lower:
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


# ==========================================================
# NOUVEAU : extraction terrain + habitable depuis la description
# ==========================================================
# Certaines annonces (souvent des villas) donnent les 2 surfaces dans le
# texte libre ("superficie terrain de 1000 m² et habitable de 200 m²"),
# alors que le scraper ne récupère qu'un seul chiffre ("surface"). On essaie
# de repérer ces 2 valeurs explicitement dans la description : quand elles
# sont trouvées, elles priment sur la logique générique par type.
PATTERN_SURFACE_TERRAIN = re.compile(
    r"terrain[^\d]{0,20}(\d+(?:[.,]\d+)?)\s*m", re.IGNORECASE
)
PATTERN_SURFACE_HABITABLE = re.compile(
    r"habitable[^\d]{0,20}(\d+(?:[.,]\d+)?)\s*m", re.IGNORECASE
)


def extraire_surfaces_description(description: str) -> dict:
    description = description or ""

    resultat = {"terrain": None, "habitable": None}

    match_terrain = PATTERN_SURFACE_TERRAIN.search(description)
    if match_terrain:
        resultat["terrain"] = float(match_terrain.group(1).replace(",", "."))

    match_habitable = PATTERN_SURFACE_HABITABLE.search(description)
    if match_habitable:
        resultat["habitable"] = float(match_habitable.group(1).replace(",", "."))

    return resultat


def normaliser_annonce_mubawab(brute: dict):
    """Retourne None si l'annonce n'a pas de surface fiable (elle sera
    exclue du fichier final), sinon le dict normalisé."""

    match_id = re.search(r"/a/(\d+)/", brute.get("url", "") or "")
    id_source = match_id.group(1) if match_id else None

    # Mubawab met parfois "1" comme surface quand l'agence n'a rien
    # renseigné (valeur de remplissage pour garder son JSON-LD valide).
    # Ce n'est pas une vraie mesure, mais avant de l'écarter on vérifie si
    # la description ne contient pas les vraies valeurs (terrain + habitable) :
    # certaines annonces ont un "1" en JSON-LD ET les vrais chiffres en texte.
    surface = brute.get("surface")
    if surface == 1:
        surface = None

    type_site = brute.get("caracteristiques", {}).get("Type de bien")
    type_bien = deviner_type_bien(brute.get("titre"), brute.get("description"), type_site)

    # Un terrain n'a pas de "surface habitable" : la surface va dans
    # superficie_terrain, pas superficie_habitable.
    est_terrain = type_bien == "terrain"

    surfaces_desc = extraire_surfaces_description(brute.get("description"))

    if surfaces_desc["terrain"] is not None and surfaces_desc["habitable"] is not None:
        # Les 2 valeurs sont données explicitement dans le texte (ex: villa
        # avec terrain + habitable) : on leur fait confiance, même si le
        # JSON-LD d'origine avait un "1" ou rien du tout.
        superficie_terrain = surfaces_desc["terrain"]
        superficie_habitable = surfaces_desc["habitable"]
        superficie_totale = surface if surface is not None else surfaces_desc["habitable"]
    elif surface is None:
        # Aucune surface fiable nulle part (ni JSON-LD, ni description) :
        # on exclut l'annonce plutôt que de publier un chiffre faux.
        return None
    else:
        superficie_totale = surface
        superficie_habitable = None if est_terrain else surface
        superficie_terrain = surface if est_terrain else None

    telephones = normaliser_telephones(brute.get("telephone"))

    alertes = []
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
            "type": type_bien,
            "sous_type": None,
            "usage": "commercial" if type_bien == "local_commercial" else "residentiel",
            "superficie_totale": superficie_totale,
            "superficie_habitable": superficie_habitable,
            "superficie_terrain": superficie_terrain,
            "nombre_pieces": brute.get("pieces"),
            "nombre_chambres": brute.get("chambres"),
            "nombre_salles_bain": brute.get("salles_de_bain"),
            "nombre_salles_eau": None,
            "nombre_etages_total": None,
            "etage": brute.get("caracteristiques", {}).get("Étage du bien"),
            "dernier_etage": None,
            "annee_construction": None,
            "etat_general": brute.get("caracteristiques", {}).get("Etat"),
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

    resultats_bruts = [normaliser_annonce_mubawab(a) for a in annonces_brutes]

    annonces_normalisees = [a for a in resultats_bruts if a is not None]
    nombre_exclues = len(resultats_bruts) - len(annonces_normalisees)

    # <-- et celui-ci, pour le fichier de sortie
    with open("mubawab_standard.json", "w", encoding="utf-8") as f:
        json.dump(annonces_normalisees, f, ensure_ascii=False, indent=2)

    print(f"{nombre_exclues} annonce(s) exclue(s) : surface non renseignée ou non fiable")

    suspectes = [a for a in annonces_normalisees if a["metadonnees_scraping"]["erreurs"]]

    print(f"{len(annonces_normalisees)} annonces normalisées")
    print(f"{len(suspectes)} annonces avec une alerte qualité à vérifier")
    for a in suspectes[:10]:
        print(" -", a["listing"]["url_source"], "->", a["metadonnees_scraping"]["erreurs"])