import time
from django.conf import settings
from google import genai
from google.genai import types
from pydantic import BaseModel
from typing import Literal

import logging

logger = logging.getLogger(__name__)


class ComplaintClassification(BaseModel):
    category: Literal["BILLING", "TECHNICAL", "ACCOUNT", "OTHER"]
    priority: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    sentiment: Literal["POSITIVE", "NEUTRAL", "NEGATIVE"]
    summary: str


def classify_complaint(subject, description):

    if not settings.GEMINI_API_KEY:
        raise ValueError("Gemini API key is missing.")

    client = genai.Client(
        api_key=settings.GEMINI_API_KEY,
        http_options=types.HttpOptions(
            retry_options=types.HttpRetryOptions(
                attempts=3,
                initial_delay=1,
                max_delay=4,
                exp_base=2,
                jitter=0.5,
                http_status_codes=[429, 500, 502, 503, 504]
            )
        )
    )

    prompt = f"""
    You are an AI assistant for a customer support ticket system.

    Analyse this customer complaint.

    Subject: {subject}
    Description: {description}

    Return:
    1. Category: BILLING, TECHNICAL, ACCOUNT, or OTHER.
    2. Priority: LOW, MEDIUM, HIGH, or CRITICAL.
    3. Sentiment: POSITIVE, NEUTRAL, or NEGATIVE.
    4. A short summary.

    Choose priority based on urgency and business impact.
    Do not invent facts.
    """

    start_time = time.perf_counter()

    interaction = client.interactions.create(
        model="gemini-3.5-flash-lite",
        input=prompt,
        response_format={
            "type": "text",
            "mime_type": "application/json",
            "schema": ComplaintClassification.model_json_schema(),
        },
        generation_config={
            "max_output_tokens": 1024,
            "thinking_level": "low",
        },
    )

    end_time = time.perf_counter()
    print(f"Gemini API response time: {end_time - start_time:.2f} seconds")

    if not interaction.output_text:
        raise ValueError("Gemini returned an empty response.")

    result = ComplaintClassification.model_validate_json(
        interaction.output_text
    )

    return result.model_dump()
