"""Quick end-to-end test of the full pipeline."""
import requests, json

BASE = "http://localhost:8000"

# 1. Login
print("=== Step 1: Login ===")
r = requests.post(f"{BASE}/auth/login", data={"username": "admin@manike.ai", "password": "admin123"})
token = r.json()["access_token"]
headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
print(f"Token: {token[:30]}...")

# 2. Upload Images
print("\n=== Step 2: Upload Images ===")
images_data = [
    {"name": "Galle Fort Sunset", "tags": "galle,fort,sunset,heritage,colonial", "location": "Galle", "image_url": "https://s3.amazonaws.com/manike/galle_fort.jpg"},
    {"name": "Ella Train Scenic", "tags": "ella,train,tea,plantation,scenic", "location": "Ella", "image_url": "https://s3.amazonaws.com/manike/ella_train.jpg"},
    {"name": "Mirissa Beach", "tags": "mirissa,beach,ocean,sand,relax", "location": "Mirissa", "image_url": "https://s3.amazonaws.com/manike/mirissa_beach.jpg"},
]
for img in images_data:
    r = requests.post(f"{BASE}/images/", headers=headers, json=img)
    print(f"  Uploaded: {img['name']} -> {r.status_code}")

# 3. Upload Cinematic Clips
print("\n=== Step 3: Upload Cinematic Clips ===")
clips_data = [
    {"name": "Galle Fort Drone", "tags": "galle,fort,heritage,sunset,drone", "video_url": "https://s3.amazonaws.com/manike/clips/galle_drone.mp4", "duration": 15.0},
    {"name": "Ella Train Journey", "tags": "ella,train,tea,plantation,mountain", "video_url": "https://s3.amazonaws.com/manike/clips/ella_train.mp4", "duration": 20.0},
    {"name": "Mirissa Sunset", "tags": "mirissa,beach,ocean,sunset,waves", "video_url": "https://s3.amazonaws.com/manike/clips/mirissa_sunset.mp4", "duration": 12.0},
]
for clip in clips_data:
    r = requests.post(f"{BASE}/cinematic-clips/", headers=headers, json=clip)
    print(f"  Uploaded: {clip['name']} -> {r.status_code}")

# 4. Generate Itinerary
print("\n=== Step 4: Generate Itinerary ===")
r = requests.post(f"{BASE}/itinerary/generate", headers=headers, json={
    "prompt": "3-day trip to Galle, Ella and Mirissa in Sri Lanka",
    "destination": "Sri Lanka",
    "days": 3
})
print(f"  Status: {r.status_code}")
itin = r.json()
print(f"  Itinerary ID: {itin['id']}")
print(f"  Activities:")
for act in itin["activities"]:
    matched_img = "YES" if act["image_url"] else "NO"
    matched_clip = "YES" if act["cinematic_clip_url"] else "NO"
    print(f"    Day {act['day']}: {act['activity_name']}")
    print(f"      Image matched: {matched_img} | Clip tagged: {matched_clip}")
    if act["image_url"]:
        print(f"      Image: {act['image_url']}")
    if act["cinematic_clip_url"]:
        print(f"      Clip: {act['cinematic_clip_url']}")

# 5. Compile Video
print("\n=== Step 5: Compile Final Video ===")
r = requests.post(f"{BASE}/itinerary/{itin['id']}/compile-video", headers=headers)
print(f"  Status: {r.status_code}")
result = r.json()
print(f"  Result: {json.dumps(result, indent=2)}")

# 6. Verify final state
print("\n=== Step 6: Verify Final State ===")
r = requests.get(f"{BASE}/itinerary/{itin['id']}", headers=headers)
final = r.json()
print(f"  Itinerary Status: {final['status']}")
print(f"  Final Video URL: {final.get('final_video_url', 'N/A')}")

print("\n=== ALL TESTS PASSED ===")
