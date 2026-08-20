import chromadb
from chromadb.utils import embedding_functions

CHROMA_DB_PATH = "./chroma_db"
COLLECTION_NAME = "real_estate_listings"

# Defines the maximum distance (for cosine, distance is 1 - similarity)
# Lower distance means higher similarity.
DEFAULT_DISTANCE_THRESHOLD = 0.08 

class SimilarityEngine:
    def __init__(self, db_path=CHROMA_DB_PATH, collection_name=COLLECTION_NAME):
        self.client = chromadb.PersistentClient(path=db_path)
        
        # Load the same embedding function
        self.emb_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="paraphrase-multilingual-MiniLM-L12-v2"
        )
        
        self.collection = self.client.get_collection(
            name=collection_name,
            embedding_function=self.emb_fn
        )
        
    def get_similar_properties(self, property_id: str, top_k: int = 5, distance_threshold: float = DEFAULT_DISTANCE_THRESHOLD):
        """
        Finds properties similar to the given property_id.
        Returns a list of dictionaries with id, metadata, text, and distance.
        """
        # First, fetch the item to get its embedding
        result = self.collection.get(
            ids=[property_id],
            include=["embeddings", "metadatas", "documents"]
        )
        
        if not result["ids"]:
            raise ValueError(f"Property with ID {property_id} not found.")
            
        target_embedding = result["embeddings"][0]
        
        # Query for similar items
        # We query for top_k + 1 because the item itself will be in the results (distance 0)
        query_result = self.collection.query(
            query_embeddings=[target_embedding],
            n_results=top_k + 1,
            include=["metadatas", "documents", "distances"]
        )
        
        similar_items = []
        for i in range(len(query_result["ids"][0])):
            item_id = query_result["ids"][0][i]
            dist = query_result["distances"][0][i]
            
            # Skip the exact same item
            if item_id == property_id:
                continue
                
            # Apply threshold
            if dist > distance_threshold:
                continue
                
            similar_items.append({
                "id": item_id,
                "distance": dist,
                "metadata": query_result["metadatas"][0][i],
                "text": query_result["documents"][0][i]
            })
            
        # Limit to top_k just in case
        return similar_items[:top_k]
        
    def find_by_text(self, text_query: str, top_k: int = 5, distance_threshold: float = DEFAULT_DISTANCE_THRESHOLD):
        """
        Finds properties similar to a free text query.
        """
        query_result = self.collection.query(
            query_texts=[text_query],
            n_results=top_k,
            include=["metadatas", "documents", "distances"]
        )
        
        similar_items = []
        for i in range(len(query_result["ids"][0])):
            item_id = query_result["ids"][0][i]
            dist = query_result["distances"][0][i]
            
            if dist > distance_threshold:
                continue
                
            similar_items.append({
                "id": item_id,
                "distance": dist,
                "metadata": query_result["metadatas"][0][i],
                "text": query_result["documents"][0][i]
            })
            
        return similar_items
        
    @staticmethod
    def format_property_to_text(prop_dict: dict) -> str:
        """
        Formats an external property dictionary into the rich text format used for embeddings.
        Expected keys (optional): titre, is_vente, type_bien, ville, gouvernorat, prix, superficie, description
        """
        parts = []
        
        titre = prop_dict.get("titre", "Bien immobilier")
        parts.append(f"Titre: {titre}")
        
        is_vente = prop_dict.get("is_vente", -1)
        type_trans = "Vente" if is_vente == 1 else "Location" if is_vente == 0 else "Transaction"
        parts.append(f"Type de transaction: {type_trans}")
        
        if "type_bien" in prop_dict:
            parts.append(f"Type de bien: {prop_dict['type_bien']}")
            
        ville = prop_dict.get("ville", "")
        gouvernorat = prop_dict.get("gouvernorat", "")
        if ville or gouvernorat:
            parts.append(f"Localisation: {ville}, {gouvernorat}")
            
        if "prix" in prop_dict:
            parts.append(f"Prix: {prop_dict['prix']}")
            
        if "superficie" in prop_dict:
            parts.append(f"Superficie: {prop_dict['superficie']} m²")
            
        if "description" in prop_dict:
            parts.append(f"Description: {prop_dict['description']}")
            
        return "\n".join(parts)
        
    def find_similar_for_external(self, external_properties: list, top_k: int = 6, distance_threshold: float = DEFAULT_DISTANCE_THRESHOLD):
        """
        Takes a list of external property dictionaries, formats them, and returns similar items for each.
        Applies hard filters on 'is_vente' (transaction type) and 'type_bien' (property type) if present.
        """
        all_results = []
        
        for prop_dict in external_properties:
            formatted_text = self.format_property_to_text(prop_dict)
            
            # Build where clause for strict metadata filtering (only for exact categories)
            where_conditions = []
            if "is_vente" in prop_dict and prop_dict["is_vente"] in [0, 1]:
                where_conditions.append({"is_vente": prop_dict["is_vente"]})
            if "type_bien" in prop_dict and prop_dict["type_bien"]:
                cleaned_type_bien = prop_dict["type_bien"].strip().title()
                where_conditions.append({"type_bien": cleaned_type_bien})
                
            where_clause = None
            if len(where_conditions) == 1:
                where_clause = where_conditions[0]
            elif len(where_conditions) > 1:
                where_clause = {"$and": where_conditions}
                
            # On demande plus de résultats (top_k * 10) pour pouvoir filtrer intelligemment en Python
            query_args = {
                "query_texts": [formatted_text],
                "n_results": top_k * 10,
                "include": ["metadatas", "documents", "distances"]
            }
            if where_clause:
                query_args["where"] = where_clause
                
            query_result = self.collection.query(**query_args)
            
            similar_items = []
            
            # Paramètres de filtre "souple"
            target_ville = prop_dict.get("ville", "").strip().lower()
            target_gouv = prop_dict.get("gouvernorat", "").strip().lower()
            
            try:
                target_prix = float(prop_dict.get("prix", 0))
            except ValueError:
                target_prix = 0
                
            for i in range(len(query_result["ids"][0])):
                item_id = query_result["ids"][0][i]
                dist = query_result["distances"][0][i]
                meta = query_result["metadatas"][0][i]
                
                if dist > distance_threshold:
                    continue
                    
                # Filtre intelligent sur la ville (ex: "Marsa" matche avec "La Marsa")
                if target_ville:
                    db_ville = meta.get("ville", "").lower()
                    if target_ville not in db_ville and db_ville not in target_ville:
                        continue
                        
                # Filtre intelligent sur le gouvernorat
                if target_gouv:
                    db_gouv = meta.get("gouvernorat", "").lower()
                    if target_gouv not in db_gouv and db_gouv not in target_gouv:
                        continue
                        
                # Filtre sur le prix (+/- 40% pour être un peu plus tolérant)
                if target_prix > 0:
                    db_prix = float(meta.get("prix", 0))
                    if not (target_prix * 0.60 <= db_prix <= target_prix * 1.40):
                        continue
                        
                similar_items.append({
                    "id": item_id,
                    "distance": dist,
                    "metadata": meta,
                    "text": query_result["documents"][0][i]
                })
                
                # S'arrêter dès qu'on a le nombre désiré de recommandations valides
                if len(similar_items) == top_k:
                    break
                    
            all_results.append({
                "external_input_text": formatted_text,
                "similar_properties": similar_items
            })
            
        return all_results

if __name__ == "__main__":
    # Simple manual test if executed directly
    try:
        engine = SimilarityEngine()
        print("Engine initialized successfully.")
        count = engine.collection.count()
        print(f"Collection contains {count} items.")
    except Exception as e:
        print(f"Error initializing engine: {e}")
