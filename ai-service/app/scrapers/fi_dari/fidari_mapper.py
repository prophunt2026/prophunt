from datetime import datetime
import re


def _first(*values):
    """Retourne la première valeur non-None/non-vide."""
    for v in values:
        if v not in (None, "", [], {}):
            return v
    return None


def _to_float(value):
    if value is None:
        return None
    try:
        return float(str(value).replace(' ', '').replace(',', '.'))
    except (ValueError, TypeError):
        return None


# Mapping des libellés d'équipements (FR bruts du JSON-LD/RSC + clés anglaises du RSC)
# vers les clés standard du schéma.
_EQUIPMENT_ALIASES = {
    "climatisation": ["clim", "climatiseur", "climatisation", "airconditioning", "air conditioning"],
    "chauffage": ["chauffage", "heating"],
    "ascenseur": ["ascenseur", "elevator"],
    "garage": [
        "garage", "parking couvert", "parking au sous-sol", "parking souterrain",
        "parking sous-sol", "sous-sol", "sous sol", "souterrain", "undergroundparking",
    ],
    "parking_exterieur": ["parking exterieur", "parking extérieur", "parking"],
    "cave": ["cave"],
    "terrasse": ["terrasse", "terrace"],
    "balcon": ["balcon", "balcony"],
    "jardin": ["jardin", "garden"],
    "piscine": ["piscine", "pool"],
    "cuisine_equipee": ["cuisine équipée", "cuisine equipee", "equipped kitchen"],
    "double_vitrage": ["double vitrage", "doubleglazing", "double glazing"],
    "interphone": ["interphone", "intercom"],
    "videophone": ["visiophone", "vidéophone", "videophone"],
    "alarme": ["alarme", "alarm"],
    "gardiennage": ["gardien", "sécurité", "security", "digicode", "accèes  sécurisé", "acces securise"],
    "dressing": ["dressing"],
    "internet": ["wifi", "wi-fi", "internet"],
}


def _dedupe_preserve_order(items: list) -> list:
    seen = set()
    result = []
    for item in items:
        key = str(item).strip().lower()
        if key and key not in seen:
            seen.add(key)
            result.append(item)
    return result


# Textes de menu/navigation ou de pied de page qui n'ont rien à voir avec des
# équipements, mais qui peuvent se glisser dans les extractions DOM génériques.
_NAV_BLOCKLIST = {
    "accueil", "propriétés", "proprietes", "à propos", "a propos", "contact",
    "blog", "connexion", "inscription", "favoris", "mon compte", "se connecter",
    "s'inscrire", "recherche", "annonces", "acheter", "louer", "neuf",
    "qui sommes-nous", "mentions légales", "mentions legales",
    "politique de confidentialité", "politique de confidentialite",
    "conditions d'utilisation", "cgu", "cgv", "aide", "faq", "accueil immobilier",
}


def _build_equipements(amenity_names: list) -> dict:
    """
    Transforme une liste de libellés d'équipements (FR ou EN, bruts du site)
    en dict standard {climatisation: bool, ...}. Tout ce qui ne matche aucun
    alias connu est conservé tel quel dans 'autres'.

    Un même libellé ne peut déclencher qu'UNE seule clé (le premier match,
    dans l'ordre du dict ci-dessus) : évite qu'un texte comme "Parking
    souterrain" ne déclenche à la fois 'garage' ET 'parking_exterieur'
    simplement parce qu'il contient le mot générique "parking".
    """
    filtered = [a for a in amenity_names if a and str(a).strip().lower() not in _NAV_BLOCKLIST]
    lowered_pairs = [(str(a).strip().lower(), a) for a in filtered]
    result = {k: False for k in [
        "climatisation", "chauffage", "ascenseur", "garage", "parking_exterieur",
        "cave", "terrasse", "balcon", "jardin", "piscine", "cuisine_equipee",
        "double_vitrage", "interphone", "videophone", "alarme", "gardiennage",
        "dressing", "internet",
    ]}
    matched_raw = set()
    for key, aliases in _EQUIPMENT_ALIASES.items():
        for name_lower, _ in lowered_pairs:
            if name_lower in matched_raw:
                continue  # déjà attribué à une autre clé : on ne le réattribue pas
            if any(alias in name_lower for alias in aliases):
                result[key] = True
                matched_raw.add(name_lower)
                break

    autres = [a for name_lower, a in lowered_pairs if name_lower not in matched_raw]

    # Champs non déterminables depuis cette liste : laissés à None (inconnu, pas "absent")
    for k in [
        "places_parking", "superficie_jardin", "cuisine_americaine", "volets_roulants",
        "porte_blindee", "concierge", "eau_chaude", "antenne_tv", "adsl",
        "fibre_optique", "cheminee", "salle_de_sport", "espace_enfants",
    ]:
        result[k] = None

    result["autres"] = autres
    return result


def _feature_bool_equipements(features: dict) -> dict:
    """Équipements directement booléens fournis par le champ 'features' d'un bien individuel."""
    underground = features.get("undergroundParking")
    outdoor = features.get("outdoorParking")
    generic_parking = features.get("parking")
    # Si seul le flag générique 'parking' existe (sans détail sous-sol/extérieur),
    # et qu'il n'y a pas de garage confirmé, on considère qu'il s'agit d'un
    # parking extérieur par défaut plutôt que de ne rien enregistrer.
    if outdoor is None and generic_parking is True and not underground:
        outdoor = True

    mapping = {
        "chauffage": features.get("heating"),
        "climatisation": features.get("airConditioning"),
        "ascenseur": features.get("elevator"),
        "jardin": features.get("garden"),
        "piscine": features.get("pool"),
        "salle_de_sport": features.get("gym"),
        "internet": features.get("wifi"),
        "garage": underground,
        "parking_exterieur": outdoor,
    }
    return {k: v for k, v in mapping.items() if v is not None}


def map_to_standard_schema(raw_item: dict, category_key: str, page_url: str) -> dict:
    """
    Transforme l'objet extrait d'une page de détail Fi Dari (JSON-LD + payload RSC)
    vers le schéma standard v2.0.0.

    Deux formes possibles pour le payload RSC, selon le type de page :
    - "property" (clé 'features' présente) : un bien individuel — logement
      d'une résidence neuve (via 'Voir détails'), ou annonce directe
      acheter/louer. C'est le cas le plus courant et le plus riche.
    - "project" (clé 'units' présente) : la page d'une résidence elle-même,
      utilisée seulement en repli si aucun logement individuel n'a été trouvé.
    """
    ld = raw_item.get("_ld") or {}
    rsc = raw_item.get("_rsc") or {}
    dom_equipments = raw_item.get("_dom_equipments") or []
    description_dom = raw_item.get("_description_dom") or ""
    proximites_raw = raw_item.get("_proximites") or []
    characteristics = raw_item.get("_characteristics") or {}
    equipment_grid_labels = raw_item.get("_equipment_grid") or []
    contact_card = raw_item.get("_contact_card") or {}

    # --- Identifiants ---
    item_id = str(_first(rsc.get("id"), raw_item.get("id"), raw_item.get("_id")) or "")
    reference = rsc.get("reference")
    slug = rsc.get("slug") or ""
    raw_url = raw_item.get("url") or ld.get("url")
    if raw_url:
        canonical_url = raw_url if raw_url.startswith("http") else f"https://fi-dari.tn{raw_url}"
    elif slug:
        canonical_url = f"https://fi-dari.tn/detail/{slug}"
    else:
        canonical_url = page_url

    title = _first(rsc.get("title"), rsc.get("name"), ld.get("name")) or ""

    # La description RSC est parfois juste un pointeur "$xx" vers un chunk
    # résolu ailleurs dans le flux : on privilégie toujours le DOM, complet et fiable.
    rsc_description = rsc.get("description")
    if isinstance(rsc_description, str) and rsc_description.startswith("$"):
        rsc_description = None
    description = _first(
        description_dom,
        rsc_description,
        (ld.get("description") or {}).get("@value") if isinstance(ld.get("description"), dict) else ld.get("description"),
    ) or ""

    # --- Prix ---
    # Si le RSC ne donne pas de prix numérique exploitable (0, absent, masqué),
    # on se rabat sur le texte affiché tel quel dans la barre de caractéristiques
    # (ex: "sur demande") plutôt que de laisser un défaut null trompeur.
    features = rsc.get("features") or {}
    price_range = rsc.get("priceRange") or {}
    offers = ld.get("offers") or {}
    prix = _to_float(_first(rsc.get("price"), price_range.get("min"), offers.get("lowPrice")))
    prix_max = _to_float(_first(price_range.get("max"), offers.get("highPrice")))
    if prix == 0:
        prix = None
    if prix_max == 0:
        prix_max = None

    prix_affiche_brut = characteristics.get("prix_text")
    if prix is None and prix_affiche_brut:
        prix_parsed = _to_float(re.sub(r"[^\d.,]", "", prix_affiche_brut)) if any(c.isdigit() for c in prix_affiche_brut) else None
        prix = prix_parsed if prix_parsed else prix_affiche_brut  # texte brut si pas de chiffre exploitable (ex: "sur demande")

    tx_type = "location" if category_key == "location" else "vente"
    etat_general = "neuf" if _first(rsc.get("is_new"), category_key == "neuf") else None

    # --- Superficie / pièces ---
    surface = _to_float(_first(features.get("area"), raw_item.get("surface")))
    prix_m2 = round(prix / surface, 0) if (isinstance(prix, (int, float)) and surface) else None

    etage_raw = rsc.get("nb_etage")
    try:
        etage = int(etage_raw) if etage_raw is not None else None
    except (ValueError, TypeError):
        etage = etage_raw

    # --- Localisation ---
    rsc_location = rsc.get("location") or {}
    coords = rsc_location.get("coordinates") or {}
    ld_geo = ld.get("geo") or {}
    ld_addr = ld.get("address") or {}
    lat = _first(coords.get("lat"), ld_geo.get("latitude"))
    lng = _first(coords.get("lng"), ld_geo.get("longitude"))

    # Un logement appartenant à une résidence (rubrique "neuf") porte le nom
    # de la résidence dans "projectName" : on le range dans "localite".
    localite = rsc.get("projectName")

    proximites = [
        f"{p['libelle']}: {p['valeur']}" if p.get("valeur") else p["libelle"]
        for p in proximites_raw
    ]

    # --- Équipements ---
    amenity_names = list(rsc.get("amenities") or [])
    amenity_names += [a.get("label") or a.get("value") for a in (features.get("atouts") or []) if isinstance(a, dict)]
    amenity_names += [a.get("label") or a.get("value") for a in (features.get("equipement_bien") or []) if isinstance(a, dict)]
    amenity_names += [a.get("name") for a in (ld.get("amenityFeature") or []) if a.get("name")]
    amenity_names += equipment_grid_labels
    amenity_names += dom_equipments
    amenity_names = _dedupe_preserve_order([a for a in amenity_names if a])
    equipements = _build_equipements(amenity_names)
    # Les booléens explicites de 'features' priment sur le matching approximatif par libellé
    equipements.update(_feature_bool_equipements(features))

    if features.get("type_cuisine"):
        equipements["cuisine_americaine"] = features["type_cuisine"].lower() == "américaine"
    meuble = features.get("furnished")

    # --- Médias ---
    images_input = _first(rsc.get("images"), ld.get("image")) or []
    photos = [
        {"url": img, "url_thumb": None, "legende": None, "ordre": idx + 1, "type": "interieur"}
        for idx, img in enumerate(images_input) if isinstance(img, str)
    ]

    # --- Contact / promoteur ---
    # La carte contact scrapée dans le DOM (logo + nom, présente sur toutes
    # les pages de bien, résidence ou acheter/louer) est privilégiée : plus
    # systématiquement présente que les champs RSC équivalents.
    agent = rsc.get("agent") or {}
    developer = rsc.get("developer") or {}
    ld_developer = ld.get("developer") or {}
    nom_vendeur = agent.get("name") or None
    nom_agence = _first(contact_card.get("nom"), developer.get("name"), ld_developer.get("name"))
    logo_agence = contact_card.get("logo")
    email = _first(agent.get("email") or None, developer.get("email") if isinstance(developer, dict) else None, ld_developer.get("email"))
    agent_phone = agent.get("phone")
    telephone = list(raw_item.get("phones") or [])
    if agent_phone and agent_phone not in telephone:
        telephone.append(agent_phone)

    # --- Type / usage : la barre de caractéristiques donne la valeur exacte
    # affichée sur la page (ex: "Appartement" + sous-type "S+1"), à privilégier
    # sur le champ RSC brut ("type") qui peut être moins précis.
    prop_type = _first(characteristics.get("type"), rsc.get("type"), raw_item.get("propertyType")) or "appartement"
    sous_type = characteristics.get("sous_type")
    usage = characteristics.get("usage") or "residentiel"

    nombre_pieces = features.get("rooms")
    nombre_chambres = features.get("bedrooms")
    nombre_salles_bain = features.get("bathrooms")
    nombre_salles_eau = features.get("nb_salle_eau")
    superficie_terrain = _to_float(features.get("surface_terrain"))

    record = {
        "schema_version": "2.0.0",
        "schema_name": "tunisia_real_estate_listing_standard",

        "listing": {
            "id_source": _first(reference, item_id) if (reference or item_id) else None,
            "id_universel": f"fidari_{item_id}" if item_id else None,
            "url_source": page_url,
            "url_canonique": canonical_url,
            "date_scraping": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "date_publication": _first(rsc.get("createdAt"), ld.get("dateCreated")),
            "date_maj": _first(rsc.get("updatedAt"), ld.get("dateModified")),
            "statut": "actif" if rsc.get("status") in ("available", None) else rsc.get("status"),
            "langue": "fr"
        },

        "transaction": {
            "type": tx_type,
            "prix": prix,
            "devise": "TND",
            "prix_negociable": None,
            "prix_m2": prix_m2,
            "loyer_mensuel": prix if tx_type == "location" else None,
            "charges_mensuelles": None,
            "caution": None,
            "frais_agence": None,
            "disponibilite": "sur_plan" if category_key == "neuf" else "immediat",
            "disponibilite_date": rsc.get("deliveryDate")
        },

        "bien": {
            "type": str(prop_type).lower(),
            "sous_type": sous_type,
            "usage": usage,
            "superficie_totale": surface,
            "superficie_habitable": None,
            "superficie_terrain": superficie_terrain,
            "nombre_pieces": nombre_pieces,
            "nombre_chambres": nombre_chambres,
            "nombre_salles_bain": nombre_salles_bain,
            "nombre_salles_eau": nombre_salles_eau,
            "nombre_etages_total": rsc.get("floors"),
            "etage": etage,
            "dernier_etage": None,
            "annee_construction": None,
            "etat_general": etat_general,
            "standing": None,
            "meuble": meuble,
            "orientation": None,
            "vue": None
        },

        "localisation": {
            "pays": "Tunisie",
            "pays_code": "TN",
            "gouvernorat": _first(rsc_location.get("district"), ld_addr.get("addressLocality")),
            "delegation": None,
            "ville": _first(rsc_location.get("city"), ld_addr.get("addressRegion")),
            "localite": localite,
            "quartier": None,
            "adresse": _first(rsc_location.get("address"), ld_addr.get("streetAddress")),
            "code_postal": None,
            "proximites": proximites,
            "coordonnees": {"latitude": lat, "longitude": lng},
            "zone": None
        },

        "equipements": equipements,

        "description": {
            "titre": title,
            "texte": description,
            "texte_ar": None,
            "points_forts": [],
            "mentions_legales": None
        },

        "medias": {
            "photos": photos,
            "videos": [],
            "plans": [],
            "visite_virtuelle": None,
            "nombre_photos": len(photos)
        },

        "contact": {
            "type_vendeur": "promoteur" if category_key == "neuf" else "agence",
            "nom_vendeur": nom_vendeur,
            "nom_agence": nom_agence,
            "telephone": telephone,
            "whatsapp": None,
            "email": email,
            "site_web": None,
            "logo_agence": logo_agence,
            "photo_agence": None,
            "url_profil": None,
            "annonces_vendeur": None,
            "membre_depuis": None,
            "verifie": True
        },

        "metadonnees_scraping": {
            "source": "fi_dari",
            "selecteur_html": {},
            "methode": "playwright_detail_page_ld_rsc",
            "statut_scraping": "succes" if (ld or rsc) else "partiel",
            "erreurs": [] if (ld or rsc) else ["ni json-ld ni payload rsc trouvés"],
            "temps_scraping_ms": None,
            "user_agent": "Mozilla/5.0",
            "proxy_utilise": None,
            "cache": None
        },

        "scoring_ia": {
            "prix_estime_marche": None,
            "decote_pourcentage": None,
            "score_opportunite": None,
            "confiance_estimation": None,
            "tendance_quartier": None,
            "rentabilite_locative": None,
            "delai_vente_estime": None,
            "alertes": []
        },

        "donnees_brutes": {
            "json_ld": ld or None,
            "html_snippet": None
        }
    }

    return record