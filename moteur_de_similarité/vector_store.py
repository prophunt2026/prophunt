import json
import chromadb
from chromadb.utils import embedding_functions
from tqdm import tqdm
import math

INPUT_FILE = "prepared_documents.json"
CHROMA_DB_PATH = "./chroma_db"
COLLECTION_NAME = "real_estate_listings"
BATCH_SIZE = 100

def initialize_vector_store():
    print("Loading documents...")
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        documents = json.load(f)
        
    print(f"Loaded {len(documents)} documents.")
    
    print("Initializing ChromaDB in local persistent mode...")
    client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
    
    print("Loading SentenceTransformers embedding model...")
    # paraphrase-multilingual-MiniLM-L12-v2 is lightweight and supports French/Arabic
    emb_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="paraphrase-multilingual-MiniLM-L12-v2"
    )
    
    print(f"Creating or loading collection '{COLLECTION_NAME}'...")
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=emb_fn,
        metadata={"hnsw:space": "cosine"}
    )
    
    total_docs = len(documents)
    total_batches = math.ceil(total_docs / BATCH_SIZE)
    
    print(f"Starting ingestion in {total_batches} batches of size {BATCH_SIZE}...")
    
    for i in tqdm(range(total_batches)):
        batch = documents[i*BATCH_SIZE : (i+1)*BATCH_SIZE]
        
        ids = [doc["id"] for doc in batch]
        texts = [doc["text"] for doc in batch]
        metadatas = [doc["metadata"] for doc in batch]
        
        # This will compute embeddings and add to chroma
        collection.upsert(
            ids=ids,
            documents=texts,
            metadatas=metadatas
        )
        
    print(f"Successfully ingested {total_docs} records into ChromaDB collection '{COLLECTION_NAME}'.")
    
if __name__ == "__main__":
    initialize_vector_store()
