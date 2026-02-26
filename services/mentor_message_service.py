"""Orchestrates the mentor-message response (deterministic, no I/O)."""


class MentorMessageService:

    def handle(self, *, body, request_id: str, status_fetcher) -> dict:
        return {
            "request_id": request_id,
            "received": {
                "student_id": body.student_id,
                "channel": body.channel if isinstance(body.channel, str) else body.channel.value,
                "message": body.message,
            },
            "student_status": status_fetcher.fetch_status(body.student_id),
            "delivery": {
                "channel": body.channel if isinstance(body.channel, str) else body.channel.value,
                "constraints": {
                    "max_length": 1000,
                },
            },
            "response_message": {
                "text": "Your message has been received and logged. A mentor will follow up shortly.",
            },
            "engagement_log": {
                "logged": True,
                "event_type": "incoming_message",
            },
        }
