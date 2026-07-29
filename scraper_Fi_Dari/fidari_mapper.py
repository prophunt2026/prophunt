from datetime import datetime


def map_to_standard_schema(raw_item: dict, category_key: str, page_url: str) -> dict:
    """
    Transforme l'objet complet d'une page de détail Fi Dari vers le schéma v2.0.0.
    """
    item_id = str(
        raw_item.get("id") or raw_item.get("_id") or raw_item.get("id_annonce") or ""
    )
    slug = raw_item.get("slug") or raw_item.get("url_slug") or ""

    # URL canonique
    raw_url = raw_item.get("url")
    if raw_url:
        canonical_url = raw_url if raw_url.startswith("http") else f"https://fi-dari.tn{raw_url}"
    elif slug:
        canonical_url = f"https://fi-dari.tn/detail/{slug}"
    elif item_id:
        canonical_url = f"https://fi-dari.tn/detail/{item_id}"
    else:
        canonical_url = page_url

    title = raw_item.get("title") or raw_item.get("titre") or raw_item.get("name") or ""
    description = raw_item.get("description") or raw_item.get("description_fr") or ""

    # Processing Prix
    raw_price = (
        raw_item.get("price")
        or raw_item.get("minPrice")
        or raw_item.get("prix")
        or raw_item.get("prix_tnd")
    )
    price = None
    if raw_price is not None:
        try:
            price = float(str(raw_price).replace(' ', '').replace(',', '.'))
        except (ValueError, TypeError):
            price = None

    tx_type = "location" if category_key == "location" else "vente"
    etat_general = "neuf" if category_key == "neuf" else (raw_item.get("etat_general") or None)

    # Superficie & Pièces
    surface = raw_item.get("surface") or raw_item.get("superficie") or raw_item.get("area") or raw_item.get("minSurface")
    try:
        surface = float(surface) if surface else None
    except (ValueError, TypeError):
        surface = None

    # Coordonnées GPS
    coords = raw_item.get("coordinates") if isinstance(raw_item.get("coordinates"), dict) else {}
    lat = coords.get("lat") or raw_item.get("lat") or raw_item.get("latitude")
    lng = coords.get("lng") or raw_item.get("lng") or raw_item.get("longitude")

    # Extraction Équipements (supporte les booléens ET les listes de tags)
    equipments_raw = raw_item.get("equipments") or raw_item.get("equipements") or raw_item.get("features") or []
    eq_list = [str(e).lower() for e in equipments_raw] if isinstance(equipments_raw, list) else []

    def get_eq(bool_key: str, keywords: list) -> bool:
        if raw_item.get(bool_key) is True:
            return True
        if any(kw in eq_list for kw in keywords):
            return True
        return False if (raw_item.get(bool_key) is False or eq_list) else None

    # Contact & Promoteur / Agence
    contact_obj = raw_item.get("contact") or raw_item.get("agency") or raw_item.get("promoter") or {}
    nom_vendeur = (
        raw_item.get("contactName")
        or contact_obj.get("name")
        or contact_obj.get("nom")
        or raw_item.get("promoterName")
    )
    nom_agence = (
        raw_item.get("agencyName")
        or contact_obj.get("agencyName")
        or contact_obj.get("companyName")
    )
    
    # Téléphones
    phones = raw_item.get("phones") or contact_obj.get("phones") or raw_item.get("phone") or contact_obj.get("phone")
    if isinstance(phones, str):
        phones = [phones]
    elif not isinstance(phones, list):
        phones = []

    email = raw_item.get("contactEmail") or contact_obj.get("email") or raw_item.get("email")

    # Photos
    images_input = raw_item.get("images") or raw_item.get("photos") or []
    photos = []
    if isinstance(images_input, list):
        for idx, img in enumerate(images_input):
            img_url = img if isinstance(img, str) else (img.get("url") if isinstance(img, dict) else None)
            if img_url:
                photos.append({
                    "url": img_url,
                    "url_thumb": None,
                    "legende": None,
                    "ordre": idx + 1,
                    "type": "interieur"
                })

    prop_type = raw_item.get("propertyType") or raw_item.get("type_bien") or raw_item.get("type") or "appartement"

    return {
        "schema_version": "2.0.0",
        "schema_name": "tunisia_real_estate_listing_standard",

        "listing": {
            "id_source": item_id if item_id else None,
            "id_universel": f"fidari_{item_id}" if item_id else None,
            "url_source": page_url,
            "url_canonique": canonical_url,
            "date_scraping": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "date_publication": raw_item.get("createdAt") or raw_item.get("created_at"),
            "date_maj": raw_item.get("updatedAt") or raw_item.get("updated_at"),
            "statut": "actif",
            "langue": "fr"
        },

        "transaction": {
            "type": tx_type,
            "prix": price,
            "devise": "TND",
            "prix_negociable": raw_item.get("isNegotiable"),
            "prix_m2": raw_item.get("pricePerM2"),
            "loyer_mensuel": price if tx_type == "location" else None,
            "charges_mensuelles": None,
            "caution": None,
            "frais_agence": None,
            "disponibilite": "sur_plan" if category_key == "neuf" else "immediat",
            "disponibilite_date": None
        },

        "bien": {
            "type": str(prop_type).lower(),
            "sous_type": None,
            "usage": "residentiel",
            "superficie_totale": surface,
            "superficie_habitable": None,
            "superficie_terrain": raw_item.get("landSurface"),
            "nombre_pieces": raw_item.get("rooms") or raw_item.get("nombre_pieces"),
            "nombre_chambres": raw_item.get("bedrooms") or raw_item.get("nombre_chambres"),
            "nombre_salles_bain": raw_item.get("bathrooms"),
            "nombre_salles_eau": None,
            "nombre_etages_total": None,
            "etage": raw_item.get("floor"),
            "dernier_etage": None,
            "annee_construction": None,
            "etat_general": etat_general,
            "standing": raw_item.get("standing"),
            "meuble": raw_item.get("furnished") or raw_item.get("isFurnished"),
            "orientation": None,
            "vue": None
        },

        "localisation": {
            "pays": "Tunisie",
            "pays_code": "TN",
            "gouvernorat": raw_item.get("district") or raw_item.get("gouvernorat"),
            "delegation": None,
            "ville": raw_item.get("city") or raw_item.get("ville"),
            "localite": None,
            "quartier": raw_item.get("neighborhood") or raw_item.get("quartier"),
            "adresse": raw_item.get("address") or raw_item.get("adresse"),
            "code_postal": None,
            "proximites": [],
            "coordonnees": {
                "latitude": lat,
                "longitude": lng
            },
            "zone": None
        },

        "equipements": {
            "climatisation": get_eq("hasAirConditioning", ["clim", "climatisation"]),
            "chauffage": get_eq("hasHeating", ["chauffage", "chauffage central"]),
            "ascenseur": get_eq("hasElevator", ["ascenseur"]),
            "garage": get_eq("hasGarage", ["garage", "parking couvert"]),
            "places_parking": raw_item.get("parkingSpaces"),
            "parking_exterieur": get_eq("hasParking", ["parking"]),
            "cave": get_eq("hasCellar", ["cave"]),
            "terrasse": get_eq("hasTerrace", ["terrasse"]),
            "balcon": get_eq("hasBalcony", ["balcon"]),
            "jardin": get_eq("hasGarden", ["jardin"]),
            "superficie_jardin": None,
            "piscine": get_eq("hasPool", ["piscine"]),
            "cuisine_equipee": get_eq("hasEquippedKitchen", ["cuisine équipée", "cuisine aménagée"]),
            "cuisine_americaine": None,
            "double_vitrage": get_eq("hasDoubleGlazing", ["double vitrage"]),
            "volets_roulants": None,
            "porte_blindee": None,
            "interphone": get_eq("hasIntercom", ["interphone"]),
            "videophone": get_eq("hasVideophone", ["visiophone", "vidéophone"]),
            "alarme": get_eq("hasAlarm", ["alarme"]),
            "concierge": None,
            "gardiennage": get_eq("hasSecurity", ["gardien", "sécurité"]),
            "eau_chaude": None,
            "antenne_tv": None,
            "internet": None,
            "adsl": None,
            "fibre_optique": None,
            "cheminee": None,
            "dressing": get_eq("hasDressing", ["dressing"]),
            "salle_de_sport": None,
            "espace_enfants": None,
            "autres": []
        },

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
            "telephone": phones,
            "whatsapp": raw_item.get("whatsapp"),
            "email": email,
            "site_web": None,
            "logo_agence": None,
            "photo_agence": None,
            "url_profil": None,
            "annonces_vendeur": None,
            "membre_depuis": None,
            "verifie": True
        },

        "metadonnees_scraping": {
            "source": "fi_dari",
            "selecteur_html": {},
            "methode": "playwright_detail_page",
            "statut_scraping": "succes",
            "erreurs": [],
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
            "json_ld": None,
            "html_snippet": None
        }
    }