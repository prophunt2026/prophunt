import pytest
from similarity_engine import SimilarityEngine
import os

# We skip these tests if the DB is not built
DB_PATH = "./chroma_db"
SKIP_TESTS = not os.path.exists(DB_PATH)

@pytest.fixture(scope="module")
def engine():
    if SKIP_TESTS:
        pytest.skip("ChromaDB not found, skipping tests.")
    return SimilarityEngine(db_path=DB_PATH)

def test_engine_initialization(engine):
    assert engine is not None
    assert engine.collection is not None
    count = engine.collection.count()
    assert count > 0, "Collection should not be empty."

def test_exact_match_similarity(engine):
    # Get a random ID to test
    all_docs = engine.collection.get(include=["metadatas"])
    test_id = all_docs["ids"][0]
    
    # We query the engine for similar properties. The exact same property might be filtered out
    # by the engine (as it is currently coded to skip `if item_id == property_id`).
    # Let's test the threshold logic.
    results = engine.get_similar_properties(test_id, top_k=5, distance_threshold=2.0)
    
    # The results should not contain the original item
    for res in results:
        assert res["id"] != test_id
        
    assert len(results) > 0, "Should return at least 1 similar item with max threshold."

def test_free_text_search(engine):
    results = engine.find_by_text("Appartement S+2 avec jardin à la Marsa", top_k=3, distance_threshold=2.0)
    assert len(results) > 0
    assert "distance" in results[0]
    assert "metadata" in results[0]
    assert "text" in results[0]

def test_threshold_filtering(engine):
    # Test that setting a very low threshold returns fewer results or empty list
    all_docs = engine.collection.get(include=["metadatas"])
    test_id = all_docs["ids"][0]
    
    results_strict = engine.get_similar_properties(test_id, top_k=10, distance_threshold=0.01)
    results_loose = engine.get_similar_properties(test_id, top_k=10, distance_threshold=2.0)
    
    assert len(results_strict) <= len(results_loose)
