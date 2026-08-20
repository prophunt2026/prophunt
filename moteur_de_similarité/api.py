from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional
from similarity_engine import SimilarityEngine
import uvicorn

app = FastAPI(
    title="Real Estate Similarity API",
    description="API for finding similar real estate listings based on embeddings.",
    version="1.0.0"
)

# Initialize engine lazily or globally
engine = None

@app.on_event("startup")
def startup_event():
    global engine
    try:
        engine = SimilarityEngine()
        print(f"Similarity Engine initialized. Collection count: {engine.collection.count()}")
    except Exception as e:
        print(f"Failed to initialize engine: {e}")

class PropertyMetadata(BaseModel):
    is_vente: int
    ville: str
    gouvernorat: str
    type_bien: str
    prix: float

class SimilarPropertyResponse(BaseModel):
    id: str
    distance: float
    metadata: PropertyMetadata
    text: str

class ExternalPropertyInput(BaseModel):
    titre: Optional[str] = None
    is_vente: Optional[int] = None
    type_bien: Optional[str] = None
    ville: Optional[str] = None
    gouvernorat: Optional[str] = None
    prix: Optional[float] = None
    superficie: Optional[float] = None
    description: Optional[str] = None

class ExternalSimilarPropertyResponse(BaseModel):
    external_input_text: str
    similar_properties: List[SimilarPropertyResponse]

@app.get("/api/similar/{property_id}", response_model=List[SimilarPropertyResponse])
def get_similar_properties(property_id: str, limit: int = Query(5, ge=1, le=20), threshold: float = Query(0.5, ge=0.0, le=2.0)):
    if engine is None:
        raise HTTPException(status_code=500, detail="Similarity engine is not initialized.")
        
    try:
        results = engine.get_similar_properties(property_id=property_id, top_k=limit, distance_threshold=threshold)
        return results
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/search", response_model=List[SimilarPropertyResponse])
def search_similar_properties(query: str, limit: int = Query(5, ge=1, le=20), threshold: float = Query(0.5, ge=0.0, le=2.0)):
    if engine is None:
        raise HTTPException(status_code=500, detail="Similarity engine is not initialized.")
        
    try:
        results = engine.find_by_text(text_query=query, top_k=limit, distance_threshold=threshold)
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/similar-external", response_model=List[ExternalSimilarPropertyResponse])
def search_similar_for_external(
    properties: List[ExternalPropertyInput], 
    limit: int = Query(6, ge=1, le=20), 
    threshold: float = Query(0.08, ge=0.0, le=2.0)
):
    """
    Takes a list of external properties, formats them, and returns the top K similar properties for each.
    """
    if engine is None:
        raise HTTPException(status_code=500, detail="Similarity engine is not initialized.")
        
    try:
        # Convert pydantic models to dicts
        prop_dicts = [p.dict(exclude_none=True) for p in properties]
        results = engine.find_similar_for_external(prop_dicts, top_k=limit, distance_threshold=threshold)
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
