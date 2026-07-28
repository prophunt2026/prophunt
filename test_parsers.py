"""Test rapide (hors réseau) des fonctions de parsing avec des extraits
reproduisant la structure réelle observée sur chaque site."""

from tunisie_annonce.scraper import parse_listing_page as parse_ta
from tayara.scraper import parse_api_page as parse_tay_api

SAMPLE_TA_HTML = """
<table>
<tr>
  <td><a href="AnnoncesImmobilier.asp?rech_cod_loc=1020115">Cite Ennasr 2</a></td>
  <td>Vente</td>
  <td>App. 2 pièc</td>
  <td><a href="Details_Annonces_Immobilier.asp?cod_ann=3457498&titre=S1 standing enasser2">S1 standing enasser2</a></td>
  <td>205 000</td>
  <td>22/07/2026</td>
</tr>
<tr>
  <td><a href="AnnoncesImmobilier.asp?rech_cod_loc=1011701">Berge Du Lac</a></td>
  <td>Location</td>
  <td>App. 4 pièc</td>
  <td><a href="Details_Annonces_Immobilier.asp?cod_ann=3436662&titre=S3 avec jardin">S3 avec jardin et veranda lac 2</a></td>
  <td>4 800</td>
  <td>22/07/2026</td>
</tr>
</table>
"""

# Extrait réel de l'API interne Tayara (capturé via analyse réseau)
SAMPLE_TAYARA_API = {
    "pageProps": {
        "searchedListingsAction": {
            "newHits": [
                {
                    "id": "6a56299b7b31d9554f3d9e4e",
                    "title": "À Vendre – Appartement S+2 avec vue mer hammam Sousse",
                    "description": (
                        "Dahmen Immobilier vous propose à la vente un magnifique "
                        "appartement S+2. Superficie totale : 90 m². Composition : "
                        "Grand salon, 02 chambres à coucher, Salle de bain avec baignoire."
                    ),
                    "images": ["https://cdn.tayara.tn/a.jpg", "https://cdn.tayara.tn/b.jpg"],
                    "price": 230000,
                    "metadata": {
                        "publisher": {"name": "Dahmen immobilier", "isShop": True},
                        "subCategory": "60be84bd50ab95b45b08a09c",
                        "publishedOn": "2026-07-25T11:55:48.000Z",
                    },
                    "location": {"governorate": "Sousse", "delegation": "Hammam Sousse"},
                },
                {
                    "id": "6a5f5c4b7b31d9554f422a0c",
                    "title": "Villa de 427 m² à Borj Cedria",
                    "description": "Surface totale du terrain : 427 m². Configuration : 4 pièces.",
                    "images": [],
                    "price": 560000,
                    "metadata": {
                        "publisher": {"name": "agence EL BORJ", "isShop": True},
                        "subCategory": "60be84bd50ab95b45b08a09d",
                        "publishedOn": "2026-07-28T00:16:10.000Z",
                    },
                    "location": {"governorate": "Ben Arous", "delegation": "Borj Cedria"},
                },
            ]
        }
    }
}


def test_tunisie_annonce():
    records = parse_ta(SAMPLE_TA_HTML, transaction_code="10102")
    assert len(records) == 2, f"Attendu 2 annonces, obtenu {len(records)}"

    r0 = records[0]
    assert r0["schema_version"] == "2.0.0"
    assert r0["listing"]["id_source"] == "3457498"
    assert r0["transaction"]["prix"] == 205000
    assert r0["transaction"]["type"] == "vente"
    assert r0["listing"]["date_maj"] == "22/07/2026"
    assert r0["localisation"]["localite"] == "Cite Ennasr 2"

    r1 = records[1]
    assert r1["transaction"]["prix"] == 4800
    print("tunisie_annonce OK")


def test_tayara():
    records = parse_tay_api(SAMPLE_TAYARA_API)
    assert len(records) == 2, f"Attendu 2 annonces, obtenu {len(records)}"

    r0 = records[0]
    assert r0["transaction"]["prix"] == 230000
    assert r0["bien"]["type"] == "appartement"
    assert r0["bien"]["superficie_totale"] == 90.0
    assert r0["bien"]["nombre_chambres"] == 2
    assert r0["bien"]["nombre_salles_bain"] == 1
    assert r0["localisation"]["gouvernorat"] == "Sousse"
    assert r0["contact"]["type_vendeur"] == "agence"
    assert r0["medias"]["nombre_photos"] == 2

    r1 = records[1]
    assert r1["bien"]["type"] == "villa"
    assert r1["bien"]["superficie_totale"] == 427.0
    print("tayara OK")


if __name__ == "__main__":
    test_tunisie_annonce()
    test_tayara()
    print("\nTous les tests sont passés.")
