import random
from typing import Optional
from app.providers.base import AIProvider


class ResponseGenerator:
    """Generates friendly conversational responses using AI."""

    def __init__(self, provider: AIProvider):
        self.provider = provider

    def get_greeting(self) -> str:
        return (
            "Hello! 👋 I'm so excited to meet you! I'm Manike, and I absolutely LOVE helping people "
            "discover amazing destinations and create unforgettable adventures! ✨\n\n"
            "Let's get started! First things first - what's your name? 😊"
        )

    def generate_response(
        self,
        user_message: str,
        user_name: Optional[str],
        user_requirements: dict,
        next_question: Optional[str],
        chat_history_length: int,
        chat_history: Optional[list] = None,
    ) -> str:
        """Generate a warm, friendly response."""
        name_greeting = f"{user_name}, " if user_name else ""

        fields_extracted = sum(1 for v in user_requirements.values() if v is not None)

        # First exchange with name + lots of info
        if user_name and chat_history_length == 2:
            if fields_extracted >= 3:
                if next_question is None:
                    return (
                        f"Wow, {user_name}! 🎉 You've given me everything I need in one go - that's fantastic! "
                        f"I can see you're heading to {user_requirements.get('destination', 'an amazing destination')}. "
                        "Let me start crafting your perfect itinerary right away! ✨"
                    )
                else:
                    return (
                        f"Wonderful to meet you, {user_name}! 😊 Thank you for sharing so many details - "
                        f"I can see you're planning an exciting trip to {user_requirements.get('destination', 'a great destination')}! "
                        f"I just need a bit more info:\n\n{next_question}"
                    )
            else:
                if next_question:
                    return f"What a lovely name, {user_name}! 😊 I'm thrilled to work with you! Now, let me ask you:\n\n{next_question}"
                else:
                    return f"Great to meet you, {user_name}! 😊 Let's plan your amazing trip!"

        # Build collected info summary
        collected_info = []
        if user_requirements.get('destination'):
            collected_info.append(f"Destination: {user_requirements['destination']}")
        if user_requirements.get('start_date'):
            collected_info.append(f"Dates: {user_requirements['start_date']} to {user_requirements.get('end_date', 'TBD')}")
        if user_requirements.get('travelers'):
            collected_info.append(f"Travelers: {user_requirements['travelers']} people")
        if user_requirements.get('special_requirements'):
            collected_info.append(f"Special needs: {user_requirements['special_requirements']}")

        collected_summary = "\n".join(collected_info) if collected_info else "None yet"

        if next_question is None:
            # Build conversation context for the AI
            conversation_context = ""
            if chat_history:
                recent_messages = chat_history[-10:]  # Last 10 messages for context
                conversation_context = "\n".join(
                    f"{msg['role'].upper()}: {msg['content']}" for msg in recent_messages
                )

            completion_prompt = f"""You are a warm, enthusiastic, and knowledgeable travel planning assistant named Manike. The user has provided all their travel details and you are ready to generate their itinerary. The user may also be refining an already-generated itinerary by requesting changes.

User: {user_name or 'Guest'}
Trip summary:
{collected_summary}

Conversation so far:
{conversation_context}

Their latest message: "{user_message}"

IMPORTANT INSTRUCTIONS:
- If the user is asking a QUESTION (about their destination, activities, recommendations, travel tips, safety, things to do, etc.), you MUST answer their question helpfully and thoroughly using your travel knowledge.
- If the user is requesting CHANGES to their itinerary (e.g., "add a beach day", "swap the hotel", "remove Day 3 activity"), acknowledge the change request enthusiastically and let them know you'll update it.
- If the user is NOT asking a question (just chatting, confirming details, saying thanks, etc.), generate a SHORT excited response (2-3 sentences) acknowledging their trip. Let them know you're ready to help with any questions or changes.
- NEVER tell the user to click a button to generate their itinerary - it happens automatically.
- NEVER list out a day-by-day itinerary schedule in your response — the itinerary is shown in the panel on the right, not in the chat.
- NEVER mention downloading, exporting, or refreshing the page.
- NEVER mention video compilation, background processing, or tell the user to wait or refresh — the UI handles that automatically.
- Always use their name naturally and add 1-2 relevant emojis.
- Be a helpful travel expert! Keep responses conversational and brief (2-4 sentences max)."""

            try:
                return self.provider.generate_content(completion_prompt)
            except Exception:
                dest = user_requirements.get('destination', 'your destination')
                return (
                    f"Perfect, {name_greeting}I have everything I need for your trip to {dest}! 🎉 "
                    "Let me put together your itinerary now! ✨"
                )
        else:
            response_prompt = f"""You are Manike, a warm and intelligent travel planning assistant.

User: {user_name or 'Guest'}
Their message: "{user_message}"

Information I've collected so far:
{collected_summary}

What I still need to ask: {next_question}

Generate a SHORT, natural response (2-3 sentences) that:
1. If they shared lots of info: Briefly acknowledge the KEY details (destination, who's traveling, special needs) - show you understood
2. Smoothly transition to the next question
3. Use their name naturally
4. Sound like a real human, not a robot
5. Use 1-2 emojis

IMPORTANT:
- Do NOT repeat back everything they said
- Do NOT ask to confirm what they told you
- Do NOT re-ask about information already collected (check the "collected so far" list)
- Keep it conversational and brief

Example good response: "How exciting, Chamil! A family trip to Sri Lanka with the kids sounds amazing! 🌴 I'll make sure to find wheelchair-accessible options. What type of experiences are you looking for?"

Example bad response: "So you want to go to Sigiriya, Galle and Sri Lanka in mid April for 5 days with 2 kids and your father who needs a wheelchair. Is that correct? Now, where would you like to travel?"
"""

            try:
                return self.provider.generate_content(response_prompt)
            except Exception:
                if len(collected_info) >= 3:
                    dest = user_requirements.get('destination', 'there')
                    return f"This is going to be an amazing trip to {dest}, {name_greeting}! 🌟 {next_question}"
                else:
                    acknowledgments = [
                        f"That's wonderful, {name_greeting}",
                        f"Great, {name_greeting}",
                        f"Perfect, {name_greeting}",
                    ]
                    ack = random.choice(acknowledgments)
                    return f"{ack}! {next_question}"
