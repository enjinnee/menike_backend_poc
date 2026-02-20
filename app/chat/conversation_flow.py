from typing import Optional, Set, Dict
from datetime import datetime, timedelta


CONVERSATION_STEPS = [
    {
        "field": "language",
        "question": "What language would you prefer for your itinerary? (e.g., English, Spanish, French, German, etc.)",
        "required": False,
    },
    {
        "field": "destination",
        "question": "Where would you like to travel? (City, country, or region)",
        "required": True,
    },
    {
        "field": "start_date",
        "question": "What is your travel start date? (Please use YYYY-MM-DD format)",
        "required": True,
    },
    {
        "field": "end_date",
        "question": "What is your travel end date? (Please use YYYY-MM-DD format)",
        "required": True,
    },
    {
        "field": "budget",
        "question": "What's your total budget for this trip? (You can skip this if you prefer)",
        "required": True,
    },
    {
        "field": "travelers",
        "question": "How many people will be traveling? (Just the number, e.g., 1, 2, 3, etc.)",
        "required": True,
    },
    {
        "field": "preferences",
        "question": "What type of experiences do you prefer? (e.g., adventure, relaxation, cultural, food, nightlife, history)",
        "required": True,
    },
    {
        "field": "accommodations",
        "question": "Do you have any accommodation preferences? (e.g., luxury hotels, budget hostels, Airbnb, resorts)",
        "required": True,
    },
    {
        "field": "special_requirements",
        "question": "Any special requirements or constraints? (e.g., vegetarian food, wheelchair accessible, family-friendly)",
        "required": False,
    },
]

REQUIRED_FIELDS = ["destination", "start_date", "end_date", "travelers"]


class ConversationFlow:
    """Manages the conversation step progression and user requirements state."""

    def __init__(self):
        self.user_requirements: Dict[str, Optional[str]] = {
            "name": None,
            "language": None,
            "destination": None,
            "start_date": None,
            "end_date": None,
            "budget": None,
            "travelers": None,
            "preferences": None,
            "accommodations": None,
            "special_requirements": None,
        }
        self.answered_fields: Set[str] = set()
        self.trip_duration: Optional[int] = None

    def get_next_question(self) -> Optional[str]:
        """Get the next unanswered required question."""
        for step in CONVERSATION_STEPS:
            field = step["field"]
            is_required = step.get("required", True)

            if self.user_requirements[field] is not None:
                continue

            # Auto-calculate end_date from start_date + duration
            if field == "end_date" and self.user_requirements.get("start_date"):
                if self.trip_duration:
                    try:
                        start = datetime.strptime(self.user_requirements["start_date"], "%Y-%m-%d")
                        end = start + timedelta(days=self.trip_duration - 1)
                        self.user_requirements["end_date"] = end.strftime("%Y-%m-%d")
                        self.answered_fields.add("end_date")
                        print(f"DEBUG - Auto-calculated end_date from duration: {self.user_requirements['end_date']}")
                        continue
                    except Exception as e:
                        print(f"DEBUG - Error auto-calculating end_date: {e}")

            if is_required:
                return step["question"]

        return None

    def update_field(self, field: str, value) -> None:
        if field in self.user_requirements and value is not None:
            self.user_requirements[field] = value
            self.answered_fields.add(field)

    def is_complete(self) -> bool:
        return all(self.user_requirements.get(f) for f in REQUIRED_FIELDS)

    def get_current_field(self) -> Optional[str]:
        """Get the field corresponding to the current next question."""
        next_question = self.get_next_question()
        if next_question is None:
            return None
        for step in CONVERSATION_STEPS:
            if step["question"] == next_question:
                return step["field"]
        return None

    def is_field_required(self, field: str) -> bool:
        for step in CONVERSATION_STEPS:
            if step["field"] == field:
                return step.get("required", True)
        return True
