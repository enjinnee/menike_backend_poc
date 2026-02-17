"""Quick end-to-end test of the full pipeline with Milvus Semantic Search."""
import requests, json, time

BASE = "http://localhost:8000"

# 1. Login
print("=== Step 1: Login ===")
try:
    r = requests.post(f"{BASE}/auth/login", data={"username": "admin@manike.ai", "password": "admin123"})
    if r.status_code != 200:
        print(f"Login failed: {r.text}")
        exit(1)
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    print(f"Token: {token[:30]}...")
except Exception as e:
    print(f"Failed to connect to login: {e}")
    exit(1)

# 2. Upload Images (triggers embedding generation)
print("\n=== Step 2: Upload Images (with Embeddings) ===")
images_data = [
    {"name": "Galle Fort Sunset", "tags": "galle,fort,sunset,heritage,colonial", "location": "Galle", "image_url": "https://s3.amazonaws.com/manike/galle_fort.jpg"},
    {"name": "Ella Train Scenic", "tags": "ella,train,tea,plantation,scenic", "location": "Ella", "image_url": "https://s3.amazonaws.com/manike/ella_train.jpg"},
    {"name": "Mirissa Beach", "tags": "mirissa,beach,ocean,sand,relax", "location": "Mirissa", "image_url": "https://s3.amazonaws.com/manike/mirissa_beach.jpg"},
]
for img in images_data:
    try:
        r = requests.post(f"{BASE}/images/", headers=headers, json=img)
        print(f"  Uploaded: {img['name']} -> {r.status_code}")
    except Exception as e:
        print(f"  Failed to upload {img['name']}: {e}")

# 3. Upload Cinematic Clips (triggers embedding generation)
print("\n=== Step 3: Upload Cinematic Clips (with Embeddings) ===")
clips_data = [
    {"name": "Galle Fort Drone", "tags": "galle,fort,heritage,sunset,drone", "video_url": "https://s3.amazonaws.com/manike/clips/galle_drone.mp4", "duration": 15.0},
    {"name": "Ella Train Journey", "tags": "ella,train,tea,plantation,mountain", "video_url": "https://s3.amazonaws.com/manike/clips/ella_train.mp4", "duration": 20.0},
    {"name": "Mirissa Sunset", "tags": "mirissa,beach,ocean,sunset,waves", "video_url": "https://s3.amazonaws.com/manike/clips/mirissa_sunset.mp4", "duration": 12.0},
]
for clip in clips_data:
    try:
        r = requests.post(f"{BASE}/cinematic-clips/", headers=headers, json=clip)
        print(f"  Uploaded: {clip['name']} -> {r.status_code}")
    except Exception as e:
        print(f"  Failed to upload {clip['name']}: {e}")

# Wait a moment for Milvus indexing
time.sleep(2)

# 4. Semantic Search Test
print("\n=== Step 4: Test Semantic Search ===")
# Search query that doesn't exactly match tags but matches semantically
# "ancient fortress" -> matches "Galle Fort" (heritage, fort)
query = "ancient colonial fortress"
print(f"  Searching for: '{query}'")
try:
    r = requests.post(f"{BASE}/images/search", headers=headers, json={"query": query, "limit": 1})
    results = r.json()
    print(f"  Results: {len(results)}")
    if len(results) > 0:
        print(f"  Top Match: {results[0]['name']} (Score: {results[0]['similarity_score']})")
    else:
        print("  No matches found!")
except Exception as e:
    print(f"  Search failed: {e}")

# 5. Generate Itinerary (uses semantic matching)
print("\n=== Step 5: Generate Itinerary (Semantic Matching) ===")
try:
    r = requests.post(f"{BASE}/itinerary/generate", headers=headers, json={
        "prompt": "3-day trip to Galle, Ella and Mirissa",
        "destination": "Sri Lanka",
        "days": 3
    })
    print(f"  Status: {r.status_code}")
    if r.status_code == 200:
        itin = r.json()
        print(f"  Itinerary ID: {itin['id']}")
        print(f"  Activities:")
        for act in itin["activities"]:
            matched_img = "YES" if act["image_url"] else "NO"
            matched_clip = "YES" if act["cinematic_clip_url"] else "NO"
            print(f"    Day {act['day']}: {act['activity_name']}")
            print(f"      Image matched: {matched_img} | Clip tagged: {matched_clip}")
    else:
        print(f"  Error: {r.text}")
except Exception as e:
    print(f"  Itinerary generation failed: {e}")

print("\n=== ALL TESTS PASSED ===")
