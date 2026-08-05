"""
Global configuration: logging setup and shared constants.
=============================================================
Every other module in this package imports its constants from here
so there is a single source of truth for random seeds, column names,
default feature groupings, and external benchmark reference data.
"""

import logging
import sys
import warnings
from typing import Dict, Optional

warnings.filterwarnings('ignore')

# ─── Logging Configuration ──────────────────────────────────────────────────
# NOTE: logging.basicConfig() is a no-op if the root logger already has
# handlers configured, so importing this module multiple times (e.g. once
# per submodule import) is safe and will not duplicate log lines.
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S',
    handlers=[
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger('ml_training')

# ─── Constants ──────────────────────────────────────────────────────────────

RANDOM_STATE = 42
TARGET_COL = 'prix_log'
PRICE_COL = 'transaction.prix'

DEFAULT_FEATURES = {
    'numeric': [
        'bien.superficie_totale',
        'bien.nombre_pieces',
        'bien.nombre_chambres',
        'bien.nombre_salles_bain',
        'localisation.coordonnees.latitude',
        'localisation.coordonnees.longitude',
        'prix_m2_cleaned',
        'log_superficie',
        'nb_equipements',
        'medias.nombre_photos',
    ],
    'categorical_high_card': [
        'localisation.gouvernorat',
        'localisation.ville',
    ],
    'categorical_low_card': [
        'bien.type',
        'bien.etat_general',
        'contact.type_vendeur',
    ],
    'binary': [
        'equipements.climatisation',
        'equipements.cuisine_equipee',
        'equipements.terrasse',
        'equipements.garage',
        'equipements.ascenseur',
    ],
    'outlier_clip': [
        'bien.superficie_totale',
        'bien.nombre_pieces',
        'bien.nombre_chambres',
        'bien.nombre_salles_bain',
    ],
    'log_transform': [
        'bien.superficie_totale',
        'prix_m2_cleaned',
    ],
    'rare_category_merge': [
        'localisation.gouvernorat',
        'localisation.ville',
        'localisation.delegation',
        'bien.etat_general',
        'contact.type_vendeur',
    ],
}

MUBAWAB_SALES_BENCHMARK: Dict[str, Dict[str, Optional[float]]] = {
    'Jardins de Carthage': {'ancien': 4540, 'neuf': 5460},
    'Berges du Lac 2': {'ancien': 4980, 'neuf': None},
    'Ain Zaghouan Nord': {'ancien': 2990, 'neuf': 3690},
    'Cité Ennasr 2': {'ancien': 3850, 'neuf': 4410},
    'El Aouina': {'ancien': 2780, 'neuf': 3400},
    'La Soukra': {'ancien': 3350, 'neuf': 3690},
    'El Menzah 9C': {'ancien': 3190, 'neuf': 3700},
    "Jardins d'El Menzah 2": {'ancien': 4150, 'neuf': 4740},
    'La Marsa': {'ancien': 2990, 'neuf': 3660},
    'Riadh El Andalous': {'ancien': 3140, 'neuf': None},
    'La Manouba': {'ancien': 2860, 'neuf': 3530},
    'Ezzahra': {'ancien': 2480, 'neuf': 3030},
    'Boumhel': {'ancien': 2600, 'neuf': 3250},
    'Nouvelle Médina': {'ancien': 1930, 'neuf': 2210},
    'Mourouj 6': {'ancien': 2300, 'neuf': 2520},
    'Nabeul Centre': {'ancien': 3140, 'neuf': 3620},
    'Hammamet Sud': {'ancien': 2980, 'neuf': 3490},
    'Hammamet Nord': {'ancien': 2960, 'neuf': 3300},
    'El Kantaoui': {'ancien': 2600, 'neuf': 3560},
    'Sahloul 4': {'ancien': 4210, 'neuf': 4630},
    'Hammam Sousse': {'ancien': 2630, 'neuf': 3130},
    'Chott Meriem': {'ancien': 3330, 'neuf': 3610},
    'Hergla': {'ancien': 2580, 'neuf': 3170},
}

IPIM_REFERENCE = {
    'Q1_2024': 118.5,
    'Q4_2024': 121,
    'Q1_2025': 123,
    'Q2_2025': 120,
    'base_2015': 100,
    'annual_change_pct': 3.9,
}
