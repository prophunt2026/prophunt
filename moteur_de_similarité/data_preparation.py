import pandas as pd
import json

INPUT_FILE = "cleaned_unified.csv"
OUTPUT_FILE = "prepared_documents.json"

def prepare_data_for_embeddings():
    print(f"Loading data from {INPUT_FILE}...")
    try:
        df = pd.read_csv(INPUT_FILE, encoding="utf-8-sig", low_memory=False)
    except FileNotFoundError:
        print(f"Error: {INPUT_FILE} not found.")
        return

    # Check that required fields exist
    required_cols = ["listing.id_source"]
    for col in required_cols:
        if col not in df.columns:
            print(f"Error: Required column '{col}' is missing.")
            return

    documents = []
    
    # We will build a text representation of each property
    for idx, row in df.iterrows():
        property_id = str(row.get("listing.id_source", f"unknown_id_{idx}"))
        
        # Build text description
        titre = str(row.get("description.titre", ""))
        titre = titre if titre != "nan" else "Bien immobilier"
        
        desc = str(row.get("description.texte", ""))
        desc = desc if desc != "nan" else ""
        
        ville = str(row.get("localisation.ville", ""))
        gouvernorat = str(row.get("localisation.gouvernorat", ""))
        
        prix = row.get("price_or_rent", "Non spécifié")
        is_vente = row.get("is_vente", -1)
        type_trans = "Vente" if is_vente == 1 else "Location" if is_vente == 0 else "Transaction"
        
        type_bien = str(row.get("bien.type", ""))
        
        superficie = row.get("bien.superficie_totale", "")
        
        # Construct the rich text
        parts = []
        parts.append(f"Titre: {titre}")
        parts.append(f"Type de transaction: {type_trans}")
        parts.append(f"Type de bien: {type_bien}")
        parts.append(f"Localisation: {ville}, {gouvernorat}")
        parts.append(f"Prix: {prix}")
        if pd.notna(superficie):
            parts.append(f"Superficie: {superficie} m²")
            
        if desc:
            parts.append(f"Description: {desc}")
            
        full_text = "\n".join(parts)
        
        # Build metadata for filtering
        metadata = {
            "is_vente": int(is_vente) if pd.notna(is_vente) else -1,
            "ville": ville,
            "gouvernorat": gouvernorat,
            "type_bien": type_bien,
            "prix": float(prix) if pd.notna(prix) and str(prix) != "Non spécifié" else 0.0
        }
        
        documents.append({
            "id": property_id,
            "text": full_text,
            "metadata": metadata
        })
        
    print(f"Prepared {len(documents)} documents.")
    
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(documents, f, ensure_ascii=False, indent=2)
        
    print(f"Saved prepared documents to {OUTPUT_FILE}")

if __name__ == "__main__":
    prepare_data_for_embeddings()
