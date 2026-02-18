import json
import re
from typing import Optional
from datetime import datetime, timedelta
from app.providers.base import AIProvider, AIProviderError
from .conversation_flow import CONVERSATION_STEPS


class FieldExtractor:
    """Extracts travel information from user messages using AI and regex."""

    def __init__(self, provider: AIProvider):
        self.provider = provider

    def extract_name(self, message: str) -> Optional[str]:
        """Extract user's name from their message."""
        extraction_prompt = f"""Extract the person's name from this message.
User message: "{message}"

Return a JSON object with a "name" key. If a name is mentioned, return it. Otherwise return null.
Examples:
- User says "Hi, I'm John" -> {{"name": "John"}}
- User says "My name is Sarah" -> {{"name": "Sarah"}}
- User says "Hi there" -> {{"name": null}}

Return ONLY the JSON object, no other text."""

        try:
            response_text = self.provider.generate_content(extraction_prompt)

            cleaned_response = response_text.strip()
            if cleaned_response.startswith("```"):
                cleaned_response = cleaned_response.split("```")[1]
                if cleaned_response.startswith("json"):
                    cleaned_response = cleaned_response[4:]
                cleaned_response = cleaned_response.strip()

            extracted = json.loads(cleaned_response)
            return extracted.get("name")
        except Exception as e:
            print(f"Error extracting name: {str(e)}")
            return None

    def extract_all_fields(self, message: str, current_requirements: dict) -> dict:
        """Extract ALL travel information from a user message using AI."""
        fields_description = "\n".join([
            f"- {step['field']}: {step['question']}"
            for step in CONVERSATION_STEPS
        ])

        current_data = json.dumps(current_requirements, indent=2)

        extraction_prompt = f"""You are an intelligent travel information extractor. Your job is to understand the user's intent and extract ALL relevant travel information, even when expressed informally or indirectly. Please Prioritize to answer user's questions first before taking the next iteration.

User message: "{message}"

Current extracted data (already collected):
{current_data}

Fields to extract:
{fields_description}

## CRITICAL: MERGING WITH EXISTING DATA
When the user mentions NEW information for a field that ALREADY has a value, you MUST merge/update it intelligently:
- DESTINATION: If current is "Sigiriya" and user says "I also want to visit Galle and Ella", return "Sigiriya, Galle, Ella" (merge all locations)
- DATES: If user provides corrected dates, use the new dates (replace)
- TRAVELERS: If user updates traveler count, use the new count (replace)
- BUDGET: If user updates budget, use the new value (replace)
- SPECIAL_REQUIREMENTS: If user adds new requirements, combine with existing ones (merge)
- PREFERENCES: If user adds new preferences, combine with existing ones (merge)
- For fields that should MERGE (destination, special_requirements, preferences): combine old + new, removing duplicates
- For fields that should REPLACE (dates, travelers, budget, email): use the new value
- If there is a CONFLICT (e.g., user changes destination entirely: "Actually, forget Sigiriya, let's go to Kandy"), use the user's latest intent
- If NO new information is mentioned for a field, return the CURRENT value (not null)

## EXTRACTION INTELLIGENCE RULES:

## Kindly answer any question ask by the user before going to achieve your goal at priority.

### 1. DESTINATION - Extract ALL travel locations mentioned, MERGE with existing
- Direct: "I want to visit Paris" → "Paris"
- Multiple: "Sigiriya, Galle and Sri Lanka" → "Sigiriya, Galle, Sri Lanka"
- Additive: If current is "Sigiriya" and user says "also Galle and Ella" → "Sigiriya, Galle, Ella"
- Indirect: "thinking about somewhere tropical" → null (too vague)
- With country: "Tokyo and Kyoto in Japan" → "Tokyo, Kyoto, Japan"

### 2. DATES - Be smart about date interpretation (assume year 2025)
- Specific: "April 15th" → "2025-04-15"
- Relative: "mid April" → "2025-04-15", "early May" → "2025-05-05", "late June" → "2025-06-25"
- Ranges: "April 10-15" → start: "2025-04-10", end: "2025-04-15"
- Duration: "5 days starting mid April" → start: "2025-04-15", end: "2025-04-19"
- Vague: "sometime in spring" → null (ask for specifics)

### 3. TRAVELERS - Count ALL people intelligently
- "me and my wife" → 2
- "my two kids and father coming with me" → 4 (speaker + 2 kids + father)
- "family of 5" → 5
- "just me" or "solo trip" → 1
- "couple" → 2
- "me, my husband, and our 3 children" → 5
- ALWAYS include the speaker in the count unless explicitly excluded

### 4. SPECIAL REQUIREMENTS - Infer from context
- "wheelchair father" or "elderly parent" → "wheelchair accessible, mobility assistance needed"
- "two kids" or "children" → "family-friendly, child-friendly activities"
- "baby" or "infant" → "baby-friendly, stroller accessible"
- "vegetarian" → "vegetarian food options"
- "halal" → "halal food available"
- "pet" → "pet-friendly accommodations"
- Combine multiple: kids + wheelchair → "family-friendly, wheelchair accessible"

### 5. BUDGET - Understand various formats
- "$5000" or "5000 dollars" → 5000
- "around 3k" → 3000
- "budget trip" or "cheap" → extract as preference, not number
- "luxury" → extract as preference for accommodations

### 6. PREFERENCES - Extract travel style
- "adventure" → "adventure, outdoor activities"
- "relaxing" or "chill" → "relaxation, spa, beach"
- "culture" or "history" → "cultural, historical sites, museums"
- "food" or "foodie" → "culinary experiences, local food"
- "nature" → "nature, wildlife, scenic views"

### 7. EMAIL - Look for email patterns
- Any text with @ symbol that looks like email

### 8. LANGUAGE - Detect language preferences
- "in Spanish" or "Spanish speaking guide" → "Spanish"
- If user writes in non-English, note that language

## OUTPUT FORMAT:
Return a JSON object with these exact keys: {", ".join(current_requirements.keys())}
- If the user mentions NEW info for a field: return the MERGED/UPDATED value (combining with existing data where appropriate)
- If the user does NOT mention a field: return the CURRENT value from "Current extracted data" above (preserve what was already collected)
- Use null ONLY for fields that have no current value AND no new information
- For travelers, ALWAYS return a number, not a description
- For special_requirements, combine all relevant needs

Return ONLY valid JSON, no markdown, no explanation."""

        try:
            response_text = self.provider.generate_content(extraction_prompt)
            print(f"DEBUG - Raw response from AI: {repr(response_text)}")

            if not response_text or response_text.strip() == "":
                print("DEBUG - Empty response from AI provider")
                return {key: None for key in current_requirements.keys()}

            cleaned_response = response_text.strip()
            if cleaned_response.startswith("```"):
                cleaned_response = cleaned_response.split("```")[1]
                if cleaned_response.startswith("json"):
                    cleaned_response = cleaned_response[4:]
                cleaned_response = cleaned_response.strip()

            extracted = json.loads(cleaned_response)

            for key in current_requirements.keys():
                if key not in extracted:
                    extracted[key] = None

            # Post-processing: calculate end_date from start_date + duration
            if extracted.get("start_date") and not extracted.get("end_date"):
                duration_match = self.extract_trip_duration(message)
                if duration_match:
                    try:
                        start = datetime.strptime(extracted["start_date"], "%Y-%m-%d")
                        end = start + timedelta(days=duration_match - 1)
                        extracted["end_date"] = end.strftime("%Y-%m-%d")
                        print(f"DEBUG - Calculated end_date from duration: {extracted['end_date']}")
                    except Exception as e:
                        print(f"DEBUG - Error calculating end_date: {e}")

            return extracted
        except (json.JSONDecodeError, AIProviderError) as e:
            print(f"Error extracting information: {str(e)}")
            print(f"DEBUG - Response text that failed to parse: {repr(response_text) if 'response_text' in locals() else 'N/A'}")
            return {key: None for key in current_requirements.keys()}

    def extract_trip_duration(self, message: str) -> Optional[int]:
        """Extract trip duration in days from user message using regex."""
        message_lower = message.lower()

        patterns = [
            r'(\d+)\s*(?:day|d)\s*trip',
            r'trip\s*(?:of\s*)?(\d+)\s*(?:day|d)',
            r'(\d+)\s*(?:day|d)(?:\s+trip)?',
        ]

        for pattern in patterns:
            match = re.search(pattern, message_lower)
            if match:
                try:
                    duration = int(match.group(1))
                    if 1 <= duration <= 365:
                        print(f"DEBUG - Extracted trip duration: {duration} days")
                        return duration
                except (ValueError, IndexError):
                    continue

        return None

    def is_skip_request(self, message: str) -> bool:
        """Check if user is trying to skip an optional question."""
        skip_keywords = [
            'skip', 'no thanks', 'pass', 'not needed', 'dont care',
            'no preference', 'whatever', 'anything', 'nope',
            'dont worry', "don't worry",
        ]
        message_lower = message.lower().strip()

        for keyword in skip_keywords:
            if keyword in message_lower:
                return True

        if message_lower in ['no', 'nah', 'nope', 'n', 'na']:
            return True

        return False
