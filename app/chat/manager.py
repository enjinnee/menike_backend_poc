from typing import Optional
from app.providers.base import AIProvider, AIProviderError
from .conversation_flow import ConversationFlow
from .extractors import FieldExtractor
from .response_generator import ResponseGenerator


class ChatManager:
    """Orchestrates conversational flow for step-by-step travel planning."""

    MAX_CONSECUTIVE_FAILURES = 2

    def __init__(self, provider: AIProvider):
        self.provider = provider
        self.flow = ConversationFlow()
        self.extractor = FieldExtractor(provider)
        self.responder = ResponseGenerator(provider)
        self.chat_history = []
        self.user_name = None
        self._consecutive_failures = 0
        self._changed_since_generation = False

    @property
    def user_requirements(self):
        return self.flow.user_requirements

    def get_greeting(self) -> str:
        return self.responder.get_greeting()

    def send_message(self, user_message: str) -> str:
        try:
            self.chat_history.append({
                "role": "user",
                "content": user_message
            })

            # Extract name if not captured yet
            if self.user_name is None:
                name_extracted = self.extractor.extract_name(user_message)
                if name_extracted:
                    self.user_name = name_extracted
                    self.flow.update_field("name", name_extracted)

            # Extract all fields from the message
            extracted_data, had_api_error = self.extractor.extract_all_fields(
                user_message, self.flow.user_requirements
            )

            print(f"DEBUG - Extracted data: {extracted_data}")
            print(f"DEBUG - Current user_requirements: {self.flow.user_requirements}")

            # Track consecutive API failures
            if had_api_error:
                self._consecutive_failures += 1
                print(f"DEBUG - Consecutive API failures: {self._consecutive_failures}")
                if self._consecutive_failures >= self.MAX_CONSECUTIVE_FAILURES:
                    return self._get_service_unavailable_message()
            else:
                self._consecutive_failures = 0

            # Track trip duration
            trip_duration = self.extractor.extract_trip_duration(user_message)
            if trip_duration:
                self.flow.trip_duration = trip_duration
                print(f"DEBUG - Stored trip duration: {trip_duration} days")

            # Update requirements with extracted data
            for field, value in extracted_data.items():
                if value is not None:
                    current = self.flow.user_requirements.get(field)
                    if current is None or str(value) != str(current):
                        self.flow.update_field(field, value)
                        self._changed_since_generation = True
                        print(f"DEBUG - Updated {field}: {current!r} → {value!r}")

            # Handle skip requests on optional fields
            next_question = self.flow.get_next_question()
            if next_question:
                current_field = self.flow.get_current_field()
                if current_field and not self.flow.is_field_required(current_field):
                    if self.extractor.is_skip_request(user_message):
                        self.flow.answered_fields.add(current_field)

            next_question = self.flow.get_next_question()

            # Generate response
            assistant_message = self.responder.generate_response(
                user_message,
                self.user_name,
                self.flow.user_requirements,
                next_question,
                len(self.chat_history),
                chat_history=self.chat_history,
            )

            self.chat_history.append({
                "role": "assistant",
                "content": assistant_message
            })

            return assistant_message

        except AIProviderError as e:
            self._consecutive_failures += 1
            print(f"Error: {str(e)}")
            if self._consecutive_failures >= self.MAX_CONSECUTIVE_FAILURES:
                return self._get_service_unavailable_message()
            error_msg = "I'm so sorry, but I ran into a technical issue! Let me try that again. Could you please repeat what you just said? 🙏"
            return error_msg
        except Exception as e:
            self._consecutive_failures += 1
            print(f"Error: {str(e)}")
            if self._consecutive_failures >= self.MAX_CONSECUTIVE_FAILURES:
                return self._get_service_unavailable_message()
            error_msg = "Oops! Something went wrong on my end. Let's try that again! 😊"
            return error_msg

    @staticmethod
    def _get_service_unavailable_message() -> str:
        return (
            "I'm really sorry, but it looks like I'm experiencing a service disruption "
            "and I'm unable to process your request right now. 😔\n\n"
            "Here's what you can do:\n"
            "• **Try again in a few minutes** — this might be a temporary issue.\n"
            "• **Contact our support team** at support@manike.ai or reach out to your system administrator for assistance.\n\n"
            "I apologize for the inconvenience! We'll get this sorted out as soon as possible. 🙏"
        )

    def extract_requirements(self) -> dict:
        return self.flow.user_requirements

    def get_conversation_summary(self) -> str:
        return "\n".join([
            f"{msg['role'].upper()}: {msg['content']}"
            for msg in self.chat_history
        ])

    def is_requirements_complete(self) -> bool:
        return self.flow.is_complete()

    def is_ready_to_generate(self) -> bool:
        """True when all required fields are filled AND no more questions to ask."""
        return self.flow.is_complete() and self.flow.get_next_question() is None

    def has_changes_since_generation(self) -> bool:
        return self._changed_since_generation

    def mark_generated(self) -> None:
        """Reset changes flag after a successful generation."""
        self._changed_since_generation = False
