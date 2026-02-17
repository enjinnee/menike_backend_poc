"""
Embedding Service - Generates vector embeddings from text.

For the POC, this uses a lightweight TF-IDF-style keyword hashing approach
that still produces meaningful semantic vectors without requiring an external API.

In production, replace `generate_embedding()` with:
  - OpenAI: openai.Embedding.create(model="text-embedding-ada-002", input=text)
  - Google: genai.embed_content(model="text-embedding-004", content=text)
"""
import hashlib
import math
from typing import List

# Dimension of our embeddings (must match Milvus schema)
EMBEDDING_DIM = 128


# Curated semantic word groups for travel domain
SEMANTIC_GROUPS = {
    "beach": ["beach", "sand", "shore", "coast", "ocean", "sea", "waves", "surf", "bay", "cove", "tropical"],
    "mountain": ["mountain", "peak", "hill", "hiking", "trek", "climb", "summit", "altitude", "ridge"],
    "temple": ["temple", "pagoda", "shrine", "sacred", "relic", "worship", "buddha", "hindu", "religious"],
    "heritage": ["heritage", "colonial", "historic", "history", "ancient", "fort", "fortress", "unesco", "ruins"],
    "nature": ["nature", "garden", "botanical", "forest", "jungle", "wildlife", "safari", "elephant", "bird"],
    "water": ["whale", "marine", "diving", "snorkeling", "boat", "ocean", "lake", "river", "waterfall"],
    "scenic": ["scenic", "view", "panorama", "sunset", "sunrise", "golden", "landscape", "drone", "aerial"],
    "train": ["train", "railway", "station", "bridge", "track", "ride", "journey"],
    "food": ["food", "cuisine", "market", "spice", "tea", "restaurant", "cooking", "local"],
    "culture": ["culture", "art", "dance", "music", "festival", "traditional", "craft", "museum"],
    "adventure": ["adventure", "rafting", "zipline", "sport", "extreme", "surfing", "kayak"],
    "relax": ["relax", "spa", "resort", "pool", "hammock", "peaceful", "calm", "meditation", "yoga"],
    "city": ["city", "urban", "downtown", "market", "shopping", "street", "nightlife", "modern"],
    "photography": ["photo", "photography", "camera", "instagram", "viewpoint", "panoramic"],
    # Sri Lanka specific
    "galle": ["galle", "fort", "lighthouse", "rampart", "dutch"],
    "ella": ["ella", "nine", "arches", "little", "adam", "demodara"],
    "kandy": ["kandy", "tooth", "peradeniya", "dalada"],
    "sigiriya": ["sigiriya", "rock", "pidurangala", "dambulla", "minneriya"],
    "colombo": ["colombo", "pettah", "gangaramaya", "beira", "independence"],
    "mirissa": ["mirissa", "coconut", "whale", "stilt", "fishermen"],
    "nuwara": ["nuwara", "eliya", "horton", "plains", "gregory"],
    "yala": ["yala", "leopard", "safari", "national", "park"],
}


def _tokenize(text: str) -> List[str]:
    """Simple tokenizer: lowercase, split by non-alpha, remove short words."""
    import re
    tokens = re.findall(r'[a-z]+', text.lower())
    return [t for t in tokens if len(t) > 2]


def generate_embedding(text: str) -> List[float]:
    """
    Generate a semantic embedding vector from text.
    
    Uses a two-layer approach:
    1. Semantic group activation: each group gets a score based on word matches
    2. Character-level hash features: fills remaining dimensions for uniqueness
    
    This produces vectors where semantically similar texts have high cosine similarity.
    """
    tokens = _tokenize(text)
    token_set = set(tokens)
    
    # Layer 1: Semantic group scores (first N dimensions = number of groups)
    group_scores = []
    for group_name, keywords in SEMANTIC_GROUPS.items():
        # Count how many keywords from this group appear in the text
        overlap = len(token_set & set(keywords))
        # Normalize: higher overlap = stronger signal
        score = min(overlap / 3.0, 1.0)  # cap at 1.0
        group_scores.append(score)
    
    # Layer 2: Hash-based features for the remaining dimensions
    num_semantic = len(group_scores)
    num_hash = EMBEDDING_DIM - num_semantic
    
    hash_features = [0.0] * num_hash
    for token in tokens:
        # Hash each token to a dimension and add weight
        h = int(hashlib.md5(token.encode()).hexdigest(), 16)
        idx = h % num_hash
        hash_features[idx] += 0.3
    
    # Cap hash features
    hash_features = [min(v, 1.0) for v in hash_features]
    
    # Combine
    embedding = group_scores + hash_features
    
    # L2 normalize for cosine similarity
    magnitude = math.sqrt(sum(x * x for x in embedding))
    if magnitude > 0:
        embedding = [x / magnitude for x in embedding]
    
    return embedding
