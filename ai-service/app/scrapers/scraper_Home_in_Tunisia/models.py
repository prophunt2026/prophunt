"""
models.py - Modèle de données standard et utilitaires de hachage.
"""

import hashlib
import json
from app.scrapers.scraper_Home_in_Tunisia.config import USER_AGENT


def empty_record():
    """Squelette vide conforme au schéma standard."""
    return {
        "listing": {
            "id_source": None, "id_universel": None, "url_source": None,
            "url_canonique": None, "date_scraping": None, "date_publication": None,
            "date_maj": None, "statut": "inconnu", "langue": "fr",
        },
        "transaction": {
            "type": "vente", "prix": None, "devise": "TND", "prix_negociable": None,
            "prix_m2": None, "loyer_mensuel": None, "charges_mensuelles": None,
            "caution": None, "frais_agence": None, "disponibilite": None,
            "disponibilite_date": None,
        },
        "bien": {
            "type": None, "sous_type": None, "usage": "residentiel",
            "superficie_totale": None, "superficie_habitable": None,
            "superficie_terrain": None, "nombre_pieces": None, "nombre_chambres": None,
            "nombre_salles_bain": None, "nombre_salles_eau": None,
            "nombre_etages_total": None, "etage": None, "dernier_etage": None,
            "annee_construction": None, "etat_general": None, "standing": None,
            "meuble": None, "orientation": None, "vue": None,
        },
        "localisation": {
            "pays": "Tunisie", "pays_code": "TN", "gouvernorat": None,
            "delegation": None, "ville": None, "localite": None, "quartier": None,
            "adresse": None, "code_postal": None, "proximites": [],
            "coordonnees": {"latitude": None, "longitude": None}, "zone": None,
        },
        "equipements": {k: None for k in [
            "climatisation", "chauffage", "ascenseur", "garage", "places_parking",
            "parking_exterieur", "cave", "terrasse", "balcon", "jardin",
            "superficie_jardin", "piscine", "cuisine_equipee", "cuisine_americaine",
            "double_vitrage", "volets_roulants", "porte_blindee", "interphone",
            "videophone", "alarme", "concierge", "gardiennage", "eau_chaude",
            "antenne_tv", "internet", "adsl", "fibre_optique", "cheminee",
            "dressing", "salle_de_sport", "espace_enfants",
        ]} | {"autres": []},
        "description": {
            "titre": None, "texte": None, "texte_ar": None,
            "points_forts": [], "mentions_legales": None,
        },
        "medias": {
            "photos": [], "videos": [], "plans": [],
            "visite_virtuelle": None, "nombre_photos": None,
        },
        "contact": {
            "type_vendeur": "agence", "nom_vendeur": None, "nom_agence": None,
            "telephone": [], "whatsapp": None, "email": None, "site_web": None,
            "logo_agence": None, "photo_agence": None, "url_profil": None,
            "annonces_vendeur": None, "membre_depuis": None, "verifie": None,
        },
        "metadonnees_scraping": {
            "source": "home_in_tunisia", "selecteur_html": {}, "methode": "playwright",
            "statut_scraping": "echec", "erreurs": [], "temps_scraping_ms": None,
            "user_agent": USER_AGENT, "proxy_utilise": None, "cache": None,
            "hash_contenu": None, "date_derniere_verification": None, "absences_consecutives": 0,
        },
        "scoring_ia": {
            "prix_estime_marche": None, "decote_pourcentage": None,
            "score_opportunite": None, "confiance_estimation": None,
            "tendance_quartier": None, "rentabilite_locative": None,
            "delai_vente_estime": None, "alertes": [],
        },
        "donnees_brutes": {"json_ld": None, "html_snippet": None},
    }


def compute_content_hash(record):
    """Génère un MD5 unique basé sur le contenu commercial du bien."""
    business_data = {
        "transaction": record.get("transaction"),
        "bien": record.get("bien"),
        "localisation": record.get("localisation"),
        "equipements": record.get("equipements"),
        "description": record.get("description"),
        "medias": record.get("medias"),
    }
    raw_str = json.dumps(business_data, sort_keys=True, ensure_ascii=False)
    return hashlib.md5(raw_str.encode("utf-8")).hexdigest()