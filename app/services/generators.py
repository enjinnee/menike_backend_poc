import random
from abc import ABC, abstractmethod


class LLMPromptEngine:
    """Generates structured prompts for image/video generation."""
    def generate_scene_prompts(self, description: str) -> dict:
        # MOCK: LLM (GPT-4/Claude) analysis
        return {
            "image_prompt": f"Photorealistic cinematic wide shot of {description}, 8k, highly detailed.",
            "video_prompt": f"A smooth camera pan through {description}, sunset lighting, 4k.",
            "negative_prompt": "blurry, low quality, distorted"
        }


class Generator(ABC):
    @abstractmethod
    async def generate(self, prompt: str) -> str:
        pass


class ImageGenerator(Generator):
    async def generate(self, prompt: str) -> str:
        # MOCK: AI Image Model (e.g. Stable Diffusion)
        return "/tmp/mock_image.png"


class VideoGenerator(Generator):
    async def generate(self, prompt: str) -> str:
        # MOCK: Video Model (e.g. Veo 3)
        return "/tmp/mock_video.mp4"


class ItineraryGenerator:
    """
    Generates a structured multi-day itinerary from a user prompt.
    In production, this would call an LLM (GPT-4, Gemini, etc.).
    Currently returns a well-structured mock for the POC.
    """

    # Knowledge base of Sri Lankan destinations/activities
    DESTINATION_DATA = {
        "colombo": [
            {"activity": "City walk through Colombo Fort and Pettah Market", "location": "Colombo", "keywords": "colombo,city,fort,market,pettah"},
            {"activity": "Visit Gangaramaya Temple and Beira Lake", "location": "Colombo", "keywords": "colombo,temple,lake,gangaramaya"},
            {"activity": "Explore Independence Square and National Museum", "location": "Colombo", "keywords": "colombo,museum,independence,history"},
        ],
        "galle": [
            {"activity": "Walk through the historic Galle Fort", "location": "Galle", "keywords": "galle,fort,heritage,colonial,unesco"},
            {"activity": "Visit the Galle Lighthouse at sunset", "location": "Galle", "keywords": "galle,lighthouse,sunset,coast"},
            {"activity": "Explore Japanese Peace Pagoda", "location": "Galle", "keywords": "galle,pagoda,peace,temple"},
        ],
        "ella": [
            {"activity": "Hike to Little Adam's Peak", "location": "Ella", "keywords": "ella,hiking,peak,mountain,nature"},
            {"activity": "Ride the famous Ella Train through tea plantations", "location": "Ella", "keywords": "ella,train,tea,plantation,scenic"},
            {"activity": "Visit Nine Arches Bridge", "location": "Ella", "keywords": "ella,bridge,nine,arches,railway"},
        ],
        "kandy": [
            {"activity": "Visit the Temple of the Sacred Tooth Relic", "location": "Kandy", "keywords": "kandy,temple,tooth,relic,sacred"},
            {"activity": "Explore the Royal Botanical Gardens", "location": "Kandy", "keywords": "kandy,botanical,garden,nature,flowers"},
            {"activity": "Walk around Kandy Lake at sunset", "location": "Kandy", "keywords": "kandy,lake,sunset,walk"},
        ],
        "mirissa": [
            {"activity": "Whale watching boat tour", "location": "Mirissa", "keywords": "mirissa,whale,ocean,boat,marine"},
            {"activity": "Relax at Mirissa Beach", "location": "Mirissa", "keywords": "mirissa,beach,sand,ocean,relax"},
            {"activity": "Visit Coconut Tree Hill for sunset views", "location": "Mirissa", "keywords": "mirissa,coconut,hill,sunset,palm"},
        ],
        "sigiriya": [
            {"activity": "Climb Sigiriya Rock Fortress", "location": "Sigiriya", "keywords": "sigiriya,rock,fortress,climb,ancient"},
            {"activity": "Explore Pidurangala Rock at sunrise", "location": "Sigiriya", "keywords": "sigiriya,pidurangala,sunrise,rock,view"},
            {"activity": "Safari in Minneriya National Park", "location": "Sigiriya", "keywords": "sigiriya,safari,elephant,minneriya,wildlife"},
        ],
    }

    # Fallback generic activities
    GENERIC_ACTIVITIES = [
        {"activity": "Explore local markets and cuisine", "location": "Local Area", "keywords": "market,food,cuisine,local,culture"},
        {"activity": "Visit historical landmarks and temples", "location": "Local Area", "keywords": "temple,history,heritage,landmark"},
        {"activity": "Scenic coastal drive along the beach", "location": "Coastal Area", "keywords": "coast,beach,drive,scenic,ocean"},
    ]

    def generate(self, prompt: str, destination: str, days: int) -> list:
        """
        Generate a list of activities for a multi-day itinerary.
        Returns: [{"day": 1, "activity": "...", "location": "...", "keywords": "..."}, ...]
        """
        # Parse prompt/destination for known locations
        prompt_lower = prompt.lower()
        dest_lower = destination.lower()

        # Collect all matching activities from known destinations
        all_activities = []
        for key, activities in self.DESTINATION_DATA.items():
            if key in prompt_lower or key in dest_lower:
                all_activities.extend(activities)

        # If nothing matched, use generic activities
        if not all_activities:
            all_activities = self.GENERIC_ACTIVITIES * 3  # repeat for enough days

        # Assign activities to days
        result = []
        for day_num in range(1, days + 1):
            if all_activities:
                activity = all_activities.pop(0)
            else:
                # Cycle back if we run out
                idx = (day_num - 1) % len(self.GENERIC_ACTIVITIES)
                activity = self.GENERIC_ACTIVITIES[idx]

            result.append({
                "day": day_num,
                "activity_name": activity["activity"],
                "location": activity["location"],
                "keywords": activity["keywords"],
            })

        return result
