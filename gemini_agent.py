import os
import json
import yaml
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError("GEMINI_API_KEY is not set in environment variables or .env file.")

client = genai.Client(api_key=api_key)

def load_config() -> dict:
    with open("config.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def evaluate_and_draft_message(listing_text: str) -> dict:
    config = load_config()
    profile = config.get("applicant_profile", {})
    prompt_template = config.get("prompt_template", "")

    prompt = prompt_template.format(
        name=profile.get("name", ""),
        age=profile.get("age", ""),
        occupation=profile.get("occupation", ""),
        max_warm_rent=profile.get("max_warm_rent", ""),
        preferred_locations=profile.get("preferred_locations", ""),
        wg_type=profile.get("wg_type", ""),
        move_in_date=profile.get("move_in_date", ""),
        languages=profile.get("languages", ""),
        listing_text=listing_text
    )

    response = client.models.generate_content(
        model='gemini-3.7-flash',
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json"
        )
    )

    try:
        return json.loads(response.text)
    except Exception as e:
        print(f"Error parsing Gemini response: {e}")
        return {
            "is_match": False,
            "reason": "Failed to parse LLM response",
            "german_message": ""
        }
