# Real Estate Similarity Engine

An AI-powered recommendation engine that finds similar real estate properties using NLP (Natural Language Processing), while applying smart constraints on price and location.

## Features
- **Semantic Search**: Uses SentenceTransformers to understand property descriptions.
- **Smart Filters**: Enforces exact matches for property/transaction types, and flexible matching for locations and prices (+/- 40%).
- **Vector DB**: Uses ChromaDB for fast similarity searches.
- **REST API**: Powered by FastAPI.

## How to Run

### 1. Install Dependencies
```bash
pip install pandas numpy sentence-transformers chromadb fastapi uvicorn requests matplotlib scipy
```

### 2. Prepare Data & Build Database
Format the data and generate embeddings (run once):
```bash
python clean_data_feature_engineering.py
python data_preparation.py
python vector_store.py
```

### 3. Start the API Server
Start the local server:
```bash
uvicorn api:app --reload
```
*API docs will be available at `http://localhost:8000/docs`*

### 4. Run the Demo
Open a **new terminal** and run the test script to see recommendations:
```bash
python demo_external_properties.py
```
