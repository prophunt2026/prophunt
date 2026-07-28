"""
ÉTAPE 3 (schéma de données commun) : schéma standard des annonces
immobilières tunisiennes. Un seul format, partagé par tous les scrapers
(Tayara, Tunisie-Annonce, et les futurs : Mubawab, Menzili, Fi-Dari,
Home in Tunisia...).

Utilisation :
    from common.schema import new_listing
    listing = new_listing()
    listing["listing"]["id_source"] = "12345"
    ...
"""

import copy

SCHEMA_VERSION = "2.0.0"
SCHEMA_NAME = "tunisia_real_estate_listing_standard"

_TEMPLATE = {
    "schema_version": SCHEMA_VERSION,
    "schema_name": SCHEMA_NAME,
    "listing": {
        "id_source": None,
        "id_universel": None,
        "url_source": None,
        "url_canonique": None,
        "date_scraping": None,
        "date_publication": None,
        "date_maj": None,
        "statut": "inconnu",  # actif | vendu | loue | inconnu
        "langue": "fr",  # fr | ar
    },
    "transaction": {
        "type": None,  # vente | location
        "prix": None,
        "devise": "TND",
        "prix_negociable": None,
        "prix_m2": None,
        "loyer_mensuel": None,
        "charges_mensuelles": None,
        "caution": None,
        "frais_agence": None,
        "disponibilite": None,  # immediat | date_precise | sur_plan
        "disponibilite_date": None,
    },
    "bien": {
        "type": None,  # appartement | villa | immeuble | terrain | local_commercial | duplex | studio
        "sous_type": None,
        "usage": None,  # residentiel | commercial | mixte
        "superficie_totale": None,
        "superficie_habitable": None,
        "superficie_terrain": None,
        "nombre_pieces": None,
        "nombre_chambres": None,
        "nombre_salles_bain": None,
        "nombre_salles_eau": None,
        "nombre_etages_total": None,
        "etage": None,
        "dernier_etage": None,
        "annee_construction": None,
        "etat_general": None,  # neuf | bon | a_renover | ancien | livre | sur_plan
        "standing": None,  # economique | moyen | haut_standing
        "meuble": None,
        "orientation": None,
        "vue": None,
    },
    "localisation": {
        "pays": "Tunisie",
        "pays_code": "TN",
        "gouvernorat": None,
        "delegation": None,
        "ville": None,
        "localite": None,
        "quartier": None,
        "adresse": None,
        "code_postal": None,
        "proximites": [],
        "coordonnees": {
            "latitude": None,
            "longitude": None,
        },
        "zone": None,
    },
    "equipements": {
        "climatisation": None,
        "chauffage": None,
        "ascenseur": None,
        "garage": None,
        "places_parking": None,
        "parking_exterieur": None,
        "cave": None,
        "terrasse": None,
        "balcon": None,
        "jardin": None,
        "superficie_jardin": None,
        "piscine": None,
        "cuisine_equipee": None,
        "cuisine_americaine": None,
        "double_vitrage": None,
        "volets_roulants": None,
        "porte_blindee": None,
        "interphone": None,
        "videophone": None,
        "alarme": None,
        "concierge": None,
        "gardiennage": None,
        "eau_chaude": None,
        "antenne_tv": None,
        "internet": None,
        "adsl": None,
        "fibre_optique": None,
        "cheminee": None,
        "dressing": None,
        "salle_de_sport": None,
        "espace_enfants": None,
        "autres": [],
    },
    "description": {
        "titre": None,
        "texte": None,
        "texte_ar": None,
        "points_forts": [],
        "mentions_legales": None,
    },
    "medias": {
        "photos": [],
        "videos": [],
        "plans": [],
        "visite_virtuelle": None,
        "nombre_photos": None,
    },
    "contact": {
        "type_vendeur": None,  # agence | promoteur | particulier
        "nom_vendeur": None,
        "nom_agence": None,
        "telephone": [],
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
        "source": None,  # mubawab | menzili | fi_dari | tunisie_annonce | home_in_tunisia | tayara
        "selecteur_html": {},
        "methode": None,  # requests | selenium | playwright | api
        "statut_scraping": None,  # succes | echec_partiel | echec
        "erreurs": [],
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


def new_listing() -> dict:
    """Retourne une copie neuve (indépendante) du template d'annonce."""
    return copy.deepcopy(_TEMPLATE)
