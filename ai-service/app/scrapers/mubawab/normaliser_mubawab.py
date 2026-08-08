import re
from datetime import datetime, timezone

# ==========================================
# TABLES DE CORRESPONDANCE (inchangées)
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

PATTERN_SURFACE_TERRAIN = re.compile(
    r"terrain[^\d]{0,20}(\d+(?:[.,]\d+)?)\s*m", re.IGNORECASE
)
PATTERN_SURFACE_HABITABLE = re.compile(
    r"habitable[^\d]{0,20}(\d+(?:[.,]\d+)?)\s*m", re.IGNORECASE
)


# ==========================================
# HELPERS (privés)
# ==========================================

def _deviner_type_bien(titre: str, description: str = "", type_site: str = None) -> str:
    if type_site:
        type_site_lower = type_site.strip().lower()
        if type_site_lower in TYPES_BIEN_SITE:
            return TYPES_BIEN_SITE[type_site_lower]
    titre_lower = (titre or "").lower()
    for mot_cle, valeur in TYPES_BIEN.items():
        if mot_cle in titre_lower:
            return valeur
    description_lower = (description or "").lower()
    for mot_cle, valeur in TYPES_BIEN.items():
        if mot_cle in description_lower:
            return valeur
    return "appartement"


def _construire_equipements(liste_brute: list) -> dict:
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


def _normaliser_telephones(valeur) -> list:
    if not valeur:
        return []
    if isinstance(valeur, list):
        return [t for t in valeur if t]
    return [valeur]


def _extraire_surfaces_description(description: str) -> dict:
    description = description or ""
    resultat = {"terrain": None, "habitable": None}
    match_terrain = PATTERN_SURFACE_TERRAIN.search(description)
    if match_terrain:
        resultat["terrain"] = float(match_terrain.group(1).replace(",", "."))
    match_habitable = PATTERN_SURFACE_HABITABLE.search(description)
    if match_habitable:
        resultat["habitable"] = float(match_habitable.group(1).replace(",", "."))
    return resultat


def _normaliser_annonce(brute: dict) -> dict | None:
    """
    Transforme une annonce brute en document au format standard PropHunter.
    Retourne None si l'annonce n'a pas de surface fiable.
    """
    match_id  = re.search(r"/a/(\d+)/", brute.get("url", "") or "")
    id_source = match_id.group(1) if match_id else None

    surface = brute.get("surface")
    if surface == 1:
        surface = None

    type_site = brute.get("caracteristiques", {}).get("Type de bien")
    type_bien = _deviner_type_bien(brute.get("titre"), brute.get("description"), type_site)
    est_terrain = type_bien == "terrain"

    surfaces_desc = _extraire_surfaces_description(brute.get("description"))

    if surfaces_desc["terrain"] is not None and surfaces_desc["habitable"] is not None:
        superficie_terrain   = surfaces_desc["terrain"]
        superficie_habitable = surfaces_desc["habitable"]
        superficie_totale    = surface if surface is not None else surfaces_desc["habitable"]
    elif surface is None:
        return None  # aucune surface fiable → exclure
    else:
        superficie_totale    = surface
        superficie_habitable = None if est_terrain else surface
        superficie_terrain   = surface if est_terrain else None

    telephones = _normaliser_telephones(brute.get("telephone"))
    alertes    = [] if telephones else ["Aucun téléphone récupéré pour cette annonce"]

    return {
        "listing": {
            "id_source":        id_source,
            "id_universel":     f"mubawab_{id_source}" if id_source else None,
            "url_source":       brute.get("url"),
            "url_canonique":    brute.get("url"),
            "date_scraping":    datetime.now(timezone.utc).isoformat(),
            "date_publication": None,
            "date_maj":         None,
            "statut":           "actif",
            "langue":           "fr",
        },
        "transaction": {
            "type":              "vente",
            "prix":              brute.get("prix"),
            "devise":            brute.get("devise", "TND"),
            "prix_negociable":   None,
            "prix_m2":           round(brute["prix"] / surface, 2) if brute.get("prix") and surface else None,
            "loyer_mensuel":     None,
            "charges_mensuelles": None,
            "caution":           None,
            "frais_agence":      None,
            "disponibilite":     None,
            "disponibilite_date": None,
        },
        "bien": {
            "type":               type_bien,
            "sous_type":          None,
            "usage":              "commercial" if type_bien == "local_commercial" else "residentiel",
            "superficie_totale":  superficie_totale,
            "superficie_habitable": superficie_habitable,
            "superficie_terrain": superficie_terrain,
            "nombre_pieces":      brute.get("pieces"),
            "nombre_chambres":    brute.get("chambres"),
            "nombre_salles_bain": brute.get("salles_de_bain"),
            "nombre_salles_eau":  None,
            "nombre_etages_total": None,
            "etage":              brute.get("caracteristiques", {}).get("Étage du bien"),
            "dernier_etage":      None,
            "annee_construction": None,
            "etat_general":       brute.get("caracteristiques", {}).get("Etat"),
            "standing":           None,
            "meuble":             None,
            "orientation":        None,
            "vue":                None,
        },
        "localisation": {
            "pays":        "Tunisie",
            "pays_code":   "TN",
            "gouvernorat": None,
            "delegation":  brute.get("ville"),
            "ville":       brute.get("ville"),
            "localite":    None,
            "quartier":    None,
            "adresse":     None,
            "code_postal": None,
            "proximites":  [],
            "coordonnees": {"latitude": None, "longitude": None},
            "zone":        None,
        },
        "equipements": _construire_equipements(brute.get("equipements", [])),
        "description": {
            "titre":            brute.get("titre"),
            "texte":            brute.get("description"),
            "texte_ar":         None,
            "points_forts":     [],
            "mentions_legales": None,
        },
        "medias": {
            "photos":           [{"url": img} for img in (brute.get("images") or [])],
            "videos":           [],
            "plans":            [],
            "visite_virtuelle": None,
            "nombre_photos":    len(brute.get("images") or []),
        },
        "contact": {
            "type_vendeur":     "agence" if brute.get("agence") else None,
            "nom_vendeur":      None,
            "nom_agence":       brute.get("agence"),
            "telephone":        telephones,
            "whatsapp":         None,
            "email":            None,
            "site_web":         None,
            "logo_agence":      None,
            "photo_agence":     None,
            "url_profil":       None,
            "annonces_vendeur": None,
            "membre_depuis":    None,
            "verifie":          None,
        },
        "metadonnees_scraping": {
            "source":            "mubawab",
            "selecteur_html":    {},
            "methode":           "requests+selenium",
            "statut_scraping":   "succes",
            "erreurs":           alertes,
            "temps_scraping_ms": None,
            "user_agent":        None,
            "proxy_utilise":     None,
            "cache":             None,
        },
        "scoring_ia": {
            "prix_estime_marche":   None,
            "decote_pourcentage":   None,
            "score_opportunite":    None,
            "confiance_estimation": None,
            "tendance_quartier":    None,
            "rentabilite_locative": None,
            "delai_vente_estime":   None,
            "alertes":              [],
        },
        "donnees_brutes": {
            "json_ld":      None,
            "html_snippet": None,
        },
    }


# ==========================================
# FONCTION PUBLIQUE
# ==========================================

def normaliser(annonces: list) -> list:
    """
    Reçoit la liste des annonces enrichies avec téléphones
    (sortie de scrape_telephones), applique la normalisation au format
    standard PropHunter et retourne la liste filtrée.

    Les annonces sans surface fiable sont exclues automatiquement.

    Args:
        annonces: liste de dicts enrichis Mubawab (avec téléphone rempli)

    Returns:
        list: liste de dicts au format standard PropHunter TN
    """
    resultats_bruts  = [_normaliser_annonce(a) for a in annonces]
    annonces_valides = [a for a in resultats_bruts if a is not None]
    exclues          = len(resultats_bruts) - len(annonces_valides)
    suspectes        = [a for a in annonces_valides if a["metadonnees_scraping"]["erreurs"]]

    print(f"\n{len(annonces_valides)} annonces normalisées "
          f"({exclues} exclues — surface non fiable)")
    print(f"{len(suspectes)} annonces avec au moins une alerte qualité")

    return annonces_valides
