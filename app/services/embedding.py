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


# Curated semantic word groups for travel domain.
#
# Design rules to avoid false matches:
#   - Each word should belong to AT MOST ONE group.
#   - Groups represent the *dominant visual subject* of a clip, not just
#     any word that could appear in a description.
#   - Activity-type groups (adventure, food, relax …) must not share words
#     with subject/location groups (mountain, beach, temple …).
SEMANTIC_GROUPS = {
    # ── Physical geography ────────────────────────────────────────────────
    "beach": ["beach", "sand", "shore", "coast", "waves", "bay", "cove", "tropical", "palm"],
    # "ocean" / "sea" moved to water; "surf" moved to adventure
    "mountain": ["mountain", "peak", "hill", "summit", "altitude", "ridge", "plateau", "cliff"],
    # Removed: hiking/trek/climb → moved exclusively to adventure

    # ── Activity types ────────────────────────────────────────────────────
    "adventure": [
        "adventure", "rafting", "zipline", "extreme", "kayak", "kayaking",
        "surfing", "surf", "climbing", "climb", "climber",
        "hike", "hiking", "trek", "trekking", "ascent",
        "cycling", "biking", "paragliding", "abseiling",
    ],
    "food": [
        "food", "cuisine", "spice", "restaurant", "cooking",
        "lunch", "dinner", "breakfast", "brunch", "meal",
        "eat", "eating", "dining", "cafe", "tasting",
        "snack", "drinks", "beverage", "street food",
        "local food", "seafood", "barbecue", "buffet",
    ],
    "relax": [
        "relax", "relaxing", "spa", "pool", "hammock",
        "peaceful", "calm", "meditation", "yoga", "ayurveda",
        "treatment", "massage", "wellness", "retreat", "lounge",
        "sunbathing", "leisure",
    ],
    "shopping": [
        "shopping", "market", "bazaar", "shop", "store",
        "souvenir", "craft", "boutique", "mall", "vendor",
        "purchase", "buy",
    ],

    # ── Natural world ─────────────────────────────────────────────────────
    "nature": [
        "nature", "garden", "botanical", "forest", "jungle",
        "wildlife", "elephant", "bird", "flora", "fauna",
        "trees", "greenery", "rainforest", "mangrove",
    ],
    "water_activity": [
        "whale", "marine", "diving", "snorkeling", "boat", "boating",
        "ocean", "sea", "lake", "river", "waterfall", "lagoon",
        "swimming", "fishermen", "fishing", "cruise", "ferry",
        "water sport", "jet ski", "catamaran",
    ],
    "wildlife_safari": [
        "safari", "leopard", "deer", "crocodile", "peacock",
        "national park", "game drive", "jeep",
    ],

    # ── Built environment ─────────────────────────────────────────────────
    "temple": ["temple", "pagoda", "shrine", "sacred", "relic", "worship", "buddha", "hindu", "religious", "stupa"],
    "heritage": ["heritage", "colonial", "historic", "history", "ancient", "fort", "fortress", "unesco", "ruins", "archaeological"],
    "city": ["city", "urban", "downtown", "street", "nightlife", "modern", "skyline", "architecture"],

    # ── Visual / production style ─────────────────────────────────────────
    "scenic": ["scenic", "view", "panorama", "sunset", "sunrise", "golden", "landscape", "aerial"],
    "drone": ["drone", "flyover", "birds eye", "overhead", "timelapse", "time lapse"],
    "photography": ["photo", "photography", "camera", "instagram", "viewpoint", "panoramic"],

    # ── Transport ─────────────────────────────────────────────────────────
    "train": ["train", "railway", "rail", "station", "track"],
    "road_trip": ["road", "drive", "driving", "highway", "journey", "transfer", "tuk tuk", "bus"],

    # ── Accommodation ─────────────────────────────────────────────────────
    "accommodation": [
        "hotel", "resort", "villa", "guesthouse", "hostel",
        "check in", "check out", "checkin", "checkout",
        "lodge", "bungalow", "treehouse", "glamping",
    ],

    # ── Tea / plantation (Sri Lanka dominant activity type) ───────────────
    "tea": ["tea", "plantation", "tea factory", "tea estate", "picking", "pickers", "estate"],

    # ── Sri Lanka specific locations ──────────────────────────────────────
    "galle": ["galle", "lighthouse", "rampart", "dutch"],
    # Removed "fort" from galle — too generic (heritage group covers forts broadly)
    "ella": ["ella", "nine arches", "demodara"],
    # Removed: "nine", "arches", "little", "adam" — too ambiguous as standalone tokens
    "kandy": ["kandy", "tooth", "peradeniya", "dalada"],
    "sigiriya": ["sigiriya", "pidurangala", "dambulla", "minneriya"],
    # Removed "rock" — too generic; clips labelled "rock climbing" shouldn't fire sigiriya
    "colombo": ["colombo", "pettah", "gangaramaya", "beira", "independence"],
    "mirissa": ["mirissa", "stilt"],
    # Removed "whale", "coconut", "fishermen" from mirissa — already in water_activity/food
    "nuwara": ["nuwara", "eliya", "horton plains", "gregory"],
    "yala": ["yala"],
    # Removed "leopard", "safari", "national", "park" from yala — now in wildlife_safari
    "trincomalee": ["trincomalee", "trinco", "nilaveli", "uppuveli"],
    "arugam": ["arugam", "pottuvil"],
    "bentota": ["bentota", "beruwala", "kalutara"],
    "hikkaduwa": ["hikkaduwa", "coral"],
    "polonnaruwa": ["polonnaruwa", "anuradhapura", "ancient city"],
    "adams_peak": ["adams peak", "sri pada", "footprint", "pilgrimage"],
}


def _tokenize(text: str) -> List[str]:
    """Simple tokenizer: lowercase, split by non-alpha, remove short words."""
    import re
    tokens = re.findall(r'[a-z]+', text.lower())
    return [t for t in tokens if len(t) > 2]


def _make_lookup(text: str) -> set:
    """
    Build a set of unigrams + bigrams from text for group keyword matching.
    Bigrams allow multi-word phrases like "national park", "horton plains" to match.
    """
    import re
    words = re.findall(r'[a-z]+', text.lower())
    unigrams = set(words)
    bigrams = {f"{words[i]} {words[i+1]}" for i in range(len(words) - 1)}
    return unigrams | bigrams


def generate_embedding(text: str) -> List[float]:
    """
    Generate a semantic embedding vector from text.

    Uses a two-layer approach:
    1. Semantic group activation: each group gets a score based on word matches
    2. Character-level hash features: fills remaining dimensions for uniqueness

    This produces vectors where semantically similar texts have high cosine similarity.
    """
    tokens = _tokenize(text)
    lookup = _make_lookup(text)  # unigrams + bigrams for group matching

    # Layer 1: Semantic group scores (first N dimensions = number of groups)
    group_scores = []
    for group_name, keywords in SEMANTIC_GROUPS.items():
        # Count how many keywords from this group appear in the text
        overlap = sum(1 for kw in keywords if kw in lookup)
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
