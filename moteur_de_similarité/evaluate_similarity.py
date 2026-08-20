import numpy as np
import random
from similarity_engine import SimilarityEngine
import matplotlib.pyplot as plt

def evaluate_threshold():
    print("Initializing Similarity Engine for evaluation...")
    try:
        engine = SimilarityEngine()
    except Exception as e:
        print(f"Error initializing engine: {e}")
        return
        
    all_docs = engine.collection.get(include=["metadatas"])
    all_ids = all_docs["ids"]
    
    if not all_ids:
        print("No documents found in ChromaDB.")
        return
        
    print(f"Total documents available: {len(all_ids)}")
    
    # Sample 50 random properties
    sample_size = min(50, len(all_ids))
    sample_ids = random.sample(all_ids, sample_size)
    
    distances = []
    
    print(f"Evaluating distances for {sample_size} random properties...")
    
    for pid in sample_ids:
        # Get top 20 similar for each to observe distribution
        # We use threshold 2.0 to get everything
        try:
            results = engine.get_similar_properties(pid, top_k=20, distance_threshold=2.0)
            for res in results:
                distances.append(res["distance"])
        except Exception as e:
            pass
            
    if not distances:
        print("No distances computed.")
        return
        
    distances = np.array(distances)
    
    # Basic Stats
    print("\n--- DISTANCE STATISTICS ---")
    print(f"Total pairs evaluated: {len(distances)}")
    print(f"Min Distance: {np.min(distances):.4f}")
    print(f"Max Distance: {np.max(distances):.4f}")
    print(f"Mean Distance: {np.mean(distances):.4f}")
    print(f"Median Distance: {np.median(distances):.4f}")
    print(f"10th Percentile: {np.percentile(distances, 10):.4f}")
    print(f"25th Percentile: {np.percentile(distances, 25):.4f}")
    print(f"50th Percentile: {np.percentile(distances, 50):.4f}")
    print(f"75th Percentile: {np.percentile(distances, 75):.4f}")
    print(f"90th Percentile: {np.percentile(distances, 90):.4f}")
    
    # Recommendation
    # Cosine distance: 0 means identical, 1 means orthogonal, 2 means opposite
    # Typically, a distance < 0.4 or 0.5 is considered very similar for sentence-transformers
    recommended = np.percentile(distances, 25)
    print(f"\n=> RECOMMENDED THRESHOLD: ~{recommended:.4f}")
    print("Items with distance below this threshold are the most similar 25% among top-20 neighbors.")
    
    # Plot histogram if possible
    try:
        plt.figure(figsize=(10, 6))
        plt.hist(distances, bins=50, color='skyblue', edgecolor='black')
        plt.axvline(recommended, color='red', linestyle='dashed', linewidth=2, label=f'Recommended: {recommended:.4f}')
        plt.title('Distribution of Cosine Distances for Top-20 Similar Properties')
        plt.xlabel('Cosine Distance')
        plt.ylabel('Frequency')
        plt.legend()
        plt.grid(axis='y', alpha=0.75)
        plt.savefig('distance_distribution.png')
        print("Saved distance distribution plot to 'distance_distribution.png'")
    except Exception as e:
        print(f"Could not plot histogram: {e}")

if __name__ == "__main__":
    evaluate_threshold()
