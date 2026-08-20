import requests
import json

# L'URL de notre endpoint (assurez-vous que l'API FastAPI est en cours d'exécution)
API_URL = "http://localhost:8000/api/similar-external"

# Exemple d'un ensemble de biens externes
external_properties = [
    {
        "titre": "Superbe Appartement S+2",
        "is_vente": 0, # Location
        "type_bien": "appartement",
        "gouvernorat": "Sousse",
        "prix": 650.0,
        "description": "Très bel appartement s+2 haut standing avec grand salon, cuisine équipée, chauffage central et climatisation. Résidence sécurisée."
    },
    {
        "titre": "maison de luxe avec piscine",
        "is_vente": 0, # Vente
        "type_bien": "maison",
        "ville": "Hammamet",
        "gouvernorat": "Nabeul",
        "description": "Magnifique villa indépendante avec grand jardin arboré, piscine privée, suite parentale, garage"
    }
]

def run_demo():
    print(f"Envoi de {len(external_properties)} biens externes à l'API...")
    
    try:
        # On demande les 6 biens les plus similaires, avec un seuil de distance élargi à 1.0 (soit 0% de similarité minimum)
        response = requests.post(
            f"{API_URL}?limit=6&threshold=1.0", 
            json=external_properties
        )
        
        if response.status_code == 200:
            results = response.json()
            
            for i, result in enumerate(results):
                print(f"\n=======================================================")
                print(f"BIEN EXTERNE {i+1} :")
                print(f"{result['external_input_text']}")
                print(f"-------------------------------------------------------")
                
                similar_items = result['similar_properties']
                if not similar_items:
                    print("=> Aucun bien similaire trouvé sous le seuil.")
                else:
                    print(f"=> {len(similar_items)} biens similaires trouvés :")
                    for j, sim in enumerate(similar_items):
                        meta = sim['metadata']
                        # Calcul du score de similarité (1 - distance cosinus)
                        score_similarite = (1 - sim['distance']) * 100
                        print(f"  {j+1}. [ID: {sim['id']}] (Score de similarité : {score_similarite:.1f}%)")
                        print(f"     Prix: {meta.get('prix')} | Ville: {meta.get('ville')} | Type: {meta.get('type_bien')}")
                        # Gérer les caractères spéciaux (émojis, etc.) qui font planter le terminal
                        import sys
                        safe_text = sim['text'].encode(sys.stdout.encoding or 'utf-8', errors='replace').decode(sys.stdout.encoding or 'utf-8')
                        print(f"     Texte: {safe_text}")
        else:
            print(f"Erreur API : {response.status_code}")
            print(response.text)
            
    except requests.exceptions.ConnectionError:
        print("ERREUR : Impossible de se connecter à l'API.")
        print("Veuillez d'abord lancer l'API avec la commande : uvicorn api:app --reload")

if __name__ == "__main__":
    run_demo()
