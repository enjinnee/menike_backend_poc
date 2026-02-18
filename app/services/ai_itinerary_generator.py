"""
AI-powered itinerary generator.
Uses an LLM provider (Gemini/Claude) to generate a rich, structured
travel itinerary JSON from a conversation summary.
"""
import json
from typing import Optional
from app.providers.base import AIProvider, AIProviderError


def _build_itinerary_prompt(conversation_summary: str, user_email: str) -> str:
    return f"""Generate a complete, detailed travel itinerary in JSON format.

IMPORTANT: The response MUST be valid, complete JSON with NO markdown formatting and NO truncation.

Conversation Summary (extract all travel details from this):
{conversation_summary}

User Email: {user_email}

Required JSON format:
{{
  "user_email": "{user_email}",
  "destination": "string",
  "start_date": "YYYY-MM-DD",
  "end_date": "YYYY-MM-DD",
  "duration_days": number,
  "budget": number or null,
  "currency": "USD",
  "travelers": number,
  "preferences": "string describing travel style",
  "accommodations": "string describing accommodation preferences",
  "special_requirements": "string or null",
  "days": [
    {{
      "day": 1,
      "date": "YYYY-MM-DD",
      "activities": [
        {{
          "id": "act_1_1",
          "title": "Activity name",
          "description": "Detailed description of the activity",
          "location": "Specific location name",
          "coordinates": {{"latitude": 0.0, "longitude": 0.0}},
          "cost": 0,
          "currency": "USD",
          "duration_hours": 2.0,
          "category": "cultural|adventure|nature|food|relaxation|heritage",
          "keywords": "comma,separated,keywords,for,semantic,search"
        }}
      ],
      "stays": [
        {{
          "id": "stay_1",
          "name": "Hotel name",
          "location": "Location",
          "coordinates": {{"latitude": 0.0, "longitude": 0.0}},
          "check_in_date": "YYYY-MM-DD",
          "check_out_date": "YYYY-MM-DD",
          "cost_per_night": 0,
          "currency": "USD",
          "total_cost": 0,
          "category": "hotel|hostel|resort|airbnb",
          "amenities": ["wifi", "breakfast", "pool"]
        }}
      ],
      "rides": [
        {{
          "id": "ride_1",
          "from_location": "Origin",
          "to_location": "Destination",
          "from_coordinates": {{"latitude": 0.0, "longitude": 0.0}},
          "to_coordinates": {{"latitude": 0.0, "longitude": 0.0}},
          "transportation_type": "flight|train|car|bus|tuk-tuk|ferry",
          "cost": 0,
          "currency": "USD",
          "duration_hours": 1.0,
          "departure_time": "HH:MM",
          "arrival_time": "HH:MM"
        }}
      ]
    }}
  ]
}}

Instructions:
1. Return ONLY raw JSON, no markdown code blocks, no ```json``` wrappers
2. Include all required closing braces and brackets
3. Ensure all coordinates have both latitude and longitude values
4. Create 2-4 realistic activities per day based on the conversation details
5. Include realistic stays for each night
6. Include rides/transportation between locations when applicable
7. Use reasonable cost estimates based on the user's budget
8. Make activities relevant to the user's stated preferences
9. Each activity MUST have a "keywords" field with 4-8 relevant comma-separated keywords for image/video matching
10. Ensure the itinerary respects any special requirements mentioned"""


def _extract_json_from_response(response_text: str) -> Optional[dict]:
    """Extract and parse JSON from an AI response, handling markdown wrappers."""
    text = response_text

    if "```json" in text:
        json_start = text.find("```json") + 7
        json_end = text.find("```", json_start)
        text = text[json_start:json_end].strip()
    elif "```" in text:
        json_start = text.find("```") + 3
        json_end = text.find("```", json_start)
        text = text[json_start:json_end].strip()

    if not text.rstrip().endswith("}"):
        print("Warning: JSON response appears to be incomplete/truncated. Attempting to fix...")
        text = _fix_truncated_json(text)

    return json.loads(text)


def _fix_truncated_json(truncated: str) -> str:
    """Attempt to fix truncated JSON by closing unclosed structures."""
    open_braces = truncated.count('{') - truncated.count('}')
    open_brackets = truncated.count('[') - truncated.count(']')

    fixed = truncated.rstrip()

    if fixed.endswith(','):
        fixed = fixed[:-1]

    for _ in range(open_brackets):
        fixed += ']'

    for _ in range(open_braces):
        fixed += '}'

    print(f"Attempted to fix JSON: closed {open_brackets} arrays and {open_braces} objects")

    try:
        json.loads(fixed)
        return fixed
    except json.JSONDecodeError as e:
        print(f"JSON fix failed validation: {str(e)}")
        return truncated


class AIItineraryGenerator:
    """
    Generates a rich, structured travel itinerary using an LLM provider.
    Uses the conversation summary to produce a detailed day-by-day plan
    with activities, stays, and rides - then augmented with Milvus media matching.
    """

    def __init__(self, provider: AIProvider):
        self.provider = provider

    def generate_itinerary(
        self, conversation_summary: str, user_email: str
    ) -> Optional[dict]:
        """
        Generate a structured itinerary from the conversation summary.
        Returns a dict following the rich itinerary JSON schema.
        """
        prompt = _build_itinerary_prompt(conversation_summary, user_email)

        try:
            response_text = self.provider.generate_content(prompt)
            return _extract_json_from_response(response_text)
        except json.JSONDecodeError as e:
            print(f"Error parsing JSON response: {str(e)}")
            if 'response_text' in locals():
                print(f"Last 200 chars of response: {response_text[-200:]}")
            return None
        except AIProviderError as e:
            print(f"AI provider error generating itinerary: {str(e)}")
            return None
        except Exception as e:
            print(f"Unexpected error generating itinerary: {str(e)}")
            return None

    def extract_activities_for_matching(self, rich_itinerary: dict) -> list:
        """
        Flatten the rich itinerary into a list of activities ready for Milvus matching.
        Returns:
            [
              {
                "day": 1,
                "activity_name": "Visit Galle Fort",
                "location": "Galle",
                "keywords": "galle,fort,heritage,colonial",
                "_day_idx": 0,
                "_act_idx": 0,
              },
              ...
            ]
        """
        flat = []
        for day_idx, day_data in enumerate(rich_itinerary.get("days", [])):
            day_num = day_data.get("day", day_idx + 1)
            for act_idx, act in enumerate(day_data.get("activities", [])):
                keywords = act.get("keywords", "")
                if not keywords:
                    # Build keywords from available fields
                    parts = [
                        act.get("title", ""),
                        act.get("location", ""),
                        act.get("category", ""),
                        act.get("description", "")[:50],
                    ]
                    keywords = ",".join(p for p in parts if p)

                flat.append({
                    "day": day_num,
                    "activity_name": act.get("title", "Activity"),
                    "location": act.get("location", ""),
                    "keywords": keywords,
                    "description": act.get("description", ""),
                    "_day_idx": day_idx,
                    "_act_idx": act_idx,
                    "_act_id": act.get("id", ""),
                })
        return flat
