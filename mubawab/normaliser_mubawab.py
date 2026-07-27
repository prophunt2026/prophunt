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
    "usine": "local_industriel",
    "immeuble": "immeuble",
}


def deviner_type_bien(titre: str, description: str = "") -> str:
    """Détermine le type de bien à partir du titre et de la description."""
    titre_lower = (titre or "").lower()
    description_lower = (description or "").lower()
    texte_complet = f"{titre_lower} {description_lower}"

    # Mots-clés pour détecter les types spécifiques
    if "usine" in texte_complet or "industrie" in texte_complet or "atelier" in texte_complet:
        return "local_industriel"
    
    for mot_cle, valeur in TYPES_BIEN.items():
        if mot_cle in titre_lower or mot_cle in description_lower:
            return valeur

    return "appartement"


def construire_equipements(liste_brute: list) -> dict:
    """Convertit la liste brute d'équipements en dictionnaire normalisé."""
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
# NORMALISATION DU TÉLÉPHONE
# ==========================================================
def normaliser_telephones(valeur) -> list:
    if not valeur:
        return []
    if isinstance(valeur, list):
        return [t for t in valeur if t]
    return [valeur]


# ==========================================================
# EXTRACTION DES SURFACES DEPUIS LA DESCRIPTION (AMÉLIORÉE)
# ==========================================================
PATTERN_SURFACE_TERRAIN = re.compile(
    r"terrain\s*(?:de\s*)?(\d+(?:[.,]\d+)?)\s*m[²2]?", re.IGNORECASE
)
PATTERN_SURFACE_HABITABLE = re.compile(
    r"(?:habitable|bâtie|batie|couverte|construite)\s*(?:de\s*)?(\d+(?:[.,]\d+)?)\s*m[²2]?", re.IGNORECASE
)
PATTERN_SURFACE_TOTALE = re.compile(
    r"(?:surface|superficie)\s*(?:totale|tot)\s*(?:de\s*)?(\d+(?:[.,]\d+)?)\s*m[²2]?", re.IGNORECASE
)


def extraire_surfaces_description(description: str) -> dict:
    """
    Extrait les surfaces de la description.
    Retourne: {
        "terrain": float or None,
        "habitable": float or None,
        "totale": float or None,
        "batie": float or None  # alias pour habitable
    }
    """
    description = description or ""

    resultat = {
        "terrain": None,
        "habitable": None,
        "totale": None,
        "batie": None
    }

    # Recherche du terrain
    match_terrain = PATTERN_SURFACE_TERRAIN.search(description)
    if match_terrain:
        resultat["terrain"] = float(match_terrain.group(1).replace(",", "."))

    # Recherche de l'habitable/bâtie
    match_habitable = PATTERN_SURFACE_HABITABLE.search(description)
    if match_habitable:
        value = float(match_habitable.group(1).replace(",", "."))
        resultat["habitable"] = value
        resultat["batie"] = value

    # Recherche de la surface totale
    match_totale = PATTERN_SURFACE_TOTALE.search(description)
    if match_totale:
        resultat["totale"] = float(match_totale.group(1).replace(",", "."))

    return resultat


# ==========================================================
# FONCTION PRINCIPALE DE NORMALISATION
# ==========================================================
def normaliser_annonce_mubawab(brute: dict):
    """
    Retourne None si l'annonce n'a pas de surface fiable, sinon le dict normalisé.
    """
    match_id = re.search(r"/a/(\d+)/", brute.get("url", "") or "")
    id_source = match_id.group(1) if match_id else None

    surface = brute.get("surface")
    if surface is None or surface == 1:
        return None

    type_bien = deviner_type_bien(brute.get("titre"), brute.get("description"))
    est_terrain = type_bien == "terrain"
    est_villa = type_bien == "villa"
    est_industriel = type_bien == "local_industriel"

    surfaces_desc = extraire_surfaces_description(brute.get("description"))
    surface_brute = brute.get("surface")

    # ==========================================================
    # LOGIQUE DE GESTION DES SURFACES
    # ==========================================================
    
    # Initialisation
    superficie_totale = surface_brute
    superficie_habitable = None
    superficie_terrain = None

    if est_terrain:
        # Cas 1: C'est un terrain
        superficie_totale = surface_brute
        superficie_habitable = None
        superficie_terrain = surface_brute

    elif est_villa:
        # Cas 2: C'est une villa
        if surfaces_desc["terrain"] is not None and surfaces_desc["habitable"] is not None:
            superficie_terrain = surfaces_desc["terrain"]
            superficie_habitable = surfaces_desc["habitable"]
            superficie_totale = surfaces_desc["habitable"]
        elif surfaces_desc["terrain"] is not None and surfaces_desc["batie"] is not None:
            superficie_terrain = surfaces_desc["terrain"]
            superficie_habitable = surfaces_desc["batie"]
            superficie_totale = surfaces_desc["batie"]
        elif surfaces_desc["terrain"] is not None:
            superficie_terrain = surfaces_desc["terrain"]
            if surfaces_desc["totale"] is not None:
                superficie_totale = surfaces_desc["totale"]
                superficie_habitable = surfaces_desc["totale"]
            else:
                superficie_totale = surface_brute
                superficie_habitable = surface_brute
        else:
            superficie_terrain = surface_brute
            superficie_habitable = surface_brute
            superficie_totale = surface_brute

    elif est_industriel:
        # Cas 3: C'est un bien industriel (usine, atelier, etc.)
        # Le terrain
        if surfaces_desc["terrain"] is not None:
            superficie_terrain = surfaces_desc["terrain"]
        else:
            superficie_terrain = surface_brute

        # La surface habitable = surface couverte/bâtie pour un bien industriel
        if surfaces_desc["totale"] is not None:
            superficie_habitable = surfaces_desc["totale"]
            superficie_totale = surfaces_desc["totale"]
        elif surfaces_desc["habitable"] is not None:
            superficie_habitable = surfaces_desc["habitable"]
            superficie_totale = surfaces_desc["habitable"]
        elif surfaces_desc["batie"] is not None:
            superficie_habitable = surfaces_desc["batie"]
            superficie_totale = surfaces_desc["batie"]
        else:
            # Si aucune surface couverte n'est trouvée, on utilise la surface du JSON-LD
            superficie_habitable = surface_brute
            superficie_totale = surface_brute

    else:
        # Cas 4: Appartement, Duplex, Studio, etc.
        superficie_totale = surface_brute
        superficie_habitable = surface_brute
        superficie_terrain = None

    # Vérification finale pour les villas
    if type_bien == "villa" and superficie_terrain is not None and superficie_habitable is None:
        if surface_brute is not None and surface_brute != superficie_terrain:
            superficie_habitable = surface_brute
            superficie_totale = surface_brute
        elif surfaces_desc["totale"] is not None:
            superficie_habitable = surfaces_desc["totale"]
            superficie_totale = surfaces_desc["totale"]

    # Calcul du prix_m2
    prix_m2 = None
    if brute.get("prix") and superficie_totale and superficie_totale > 0:
        # Pour les biens industriels, on utilise superficie_totale (surface couverte/bâtie)
        # Pour les autres, on utilise superficie_habitable
        if est_industriel:
            surface_calcule = superficie_totale
        else:
            surface_calcule = superficie_habitable or superficie_totale
        
        if surface_calcule and surface_calcule > 0:
            prix_m2 = round(brute["prix"] / surface_calcule, 2)

    telephones = normaliser_telephones(brute.get("telephone"))

    alertes = []
    if not telephones:
        alertes.append("Aucun téléphone récupéré pour cette annonce")
    
    if type_bien == "villa" and superficie_terrain is None:
        alertes.append("Villa sans surface de terrain détectée")
    
    if type_bien == "local_industriel" and superficie_terrain is None:
        alertes.append("Bien industriel sans surface de terrain détectée")

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
            "prix_m2": prix_m2,
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
            "usage": "commercial" if type_bien in ["local_commercial", "local_industriel"] else "residentiel",
            "superficie_totale": superficie_totale,
            "superficie_habitable": superficie_habitable,
            "superficie_terrain": superficie_terrain,
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


# ==========================================================
# SCRIPT PRINCIPAL
# ==========================================================
if __name__ == "__main__":
    try:
        with open("mubawab.json", encoding="utf-8") as f:
            annonces_brutes = json.load(f)
        
        print(f"✅ Chargé {len(annonces_brutes)} annonces brutes")
        
        resultats_bruts = []
        for i, annonce in enumerate(annonces_brutes, 1):
            print(f"\r⏳ Traitement {i}/{len(annonces_brutes)}", end="")
            resultat = normaliser_annonce_mubawab(annonce)
            if resultat:
                resultats_bruts.append(resultat)
        
        print("\n✅ Normalisation terminée")
        
        annonces_normalisees = [a for a in resultats_bruts if a is not None]
        nombre_exclues = len(resultats_bruts) - len(annonces_normalisees)

        with open("mubawab_standard.json", "w", encoding="utf-8") as f:
            json.dump(annonces_normalisees, f, ensure_ascii=False, indent=2)
        
        print(f"📊 Statistiques :")
        print(f"  - Annonces totales : {len(annonces_brutes)}")
        print(f"  - Annonces exclues : {nombre_exclues}")
        print(f"  - Annonces normalisées : {len(annonces_normalisees)}")
        
        suspectes = [a for a in annonces_normalisees if a["metadonnees_scraping"]["erreurs"]]
        print(f"  - Annonces avec alertes : {len(suspectes)}")
        
        # Comptage par type
        types = {}
        for a in annonces_normalisees:
            t = a["bien"]["type"]
            types[t] = types.get(t, 0) + 1
        
        print("\n📋 Répartition par type :")
        for t, count in sorted(types.items(), key=lambda x: x[1], reverse=True):
            print(f"  - {t}: {count}")
        
        print(f"\n✅ Fichier créé : mubawab_standard.json")
        
    except FileNotFoundError:
        print("❌ Erreur : fichier mubawab.json non trouvé")
    except Exception as e:
        print(f"❌ Erreur : {e}")