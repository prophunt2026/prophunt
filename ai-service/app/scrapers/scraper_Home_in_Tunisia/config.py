"""
config.py - Paramètres globaux du scraper.
"""

BASE_URL = "https://www.homeintunisia.com"
LISTING_URL = BASE_URL + "/fr/acheter"

# Page de recherche filtrée sur la catégorie "Location" (bail annuel, hors
# location saisonnière = catégorie 3, exclue ici).
# Valeur confirmée en inspectant le fil d'Ariane d'une vraie fiche de location
# (lien href="/fr/recherche?search_property_category=2" -> "Location") :
# category=1 Vente, category=2 Location, category=3 Location saisonnière.
# (Le premier essai avec juste "/fr/recherche" sans paramètre retombait par
# défaut sur la catégorie Vente -> d'où le bug des ventes scrapées à la place.)
LISTING_URL_LOCATION = BASE_URL + "/fr/recherche?search_property_category=2"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)

HEADERS = {"User-Agent": USER_AGENT}
OUTPUT_PATH = "properties_schema.json"

TYPES_VOULUS = {"appartement", "maison", "villa", "studio", "s3", "s4", "s2", "s1", "s0"}
# Critères de géographie et transaction
PAYS_VOULUS = {"tunisie", "tn", "tunisia"}
DEVISES_VOULUES = {"TND"}

# Mots-clés qui entraînent l'EXCLUSION automatique du bien
# (même si le type de bien indiquait "maison" ou "villa")
MOTS_CLES_EXCLUS = [
    "hôtel", "maison d'hôte", "maison d'hote", "maisons d'hôtes",
    "chambre d'hôte", "chambre d'hote", "auberge", "complexe hôtelier",
    "fonds de commerce", "fond de commerce", "local commercial", "bureau",
    "dépôt", "depot",
    "résidence hôtelière", "residence hoteliere",
]
ETAT_MAP = {
    "excellent état": "bon",
    "bon état": "bon",
    "neuf": "neuf",
    "à rénover": "a_renover",
    "ancien": "ancien",
    "livré": "livre",
    "sur plan": "sur_plan",
}

EQUIPEMENT_KEYWORDS = {
    "climatisation": ["climatis"],
    "ascenseur": ["ascenseur"],
    "garage": ["garage"],
    "cave": ["cave"],
    "terrasse": ["terrasse"],
    "balcon": ["balcon"],
    "jardin": ["jardin"],
    "piscine": ["piscine"],
    "cuisine_equipee": ["cuisine équipée", "cuisine equipee"],
    "cuisine_americaine": ["cuisine américaine"],
    "double_vitrage": ["double vitrage"],
    "volets_roulants": ["volet"],
    "porte_blindee": ["porte blindée"],
    "interphone": ["interphone"],
    "videophone": ["vidéophone", "videophone"],
    "alarme": ["alarme"],
    "concierge": ["concierge"],
    "gardiennage": ["gardien"],
    "cheminee": ["cheminée"],
    "dressing": ["dressing"],
    "salle_de_sport": ["salle de sport"],
}