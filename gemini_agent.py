import os
import json
import time
import random
import yaml
from dotenv import load_dotenv
from google import genai
from google.genai import types
from google.genai.errors import ClientError

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError("GEMINI_API_KEY is not set in environment variables or .env file.")

client = genai.Client(api_key=api_key)

def load_config() -> dict:
    with open("config.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def evaluate_and_draft_message(listing_text: str, max_retries: int = 5) -> dict:
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

    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model='gemini-3.7-flash',
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"
                )
            )
            return json.loads(response.text)

        except ClientError as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                jitter = random.uniform(2.0, 5.0)
                wait_time = (20 * (attempt + 1)) + jitter
                print(f"⏳ Rate limit on Gemini 3.7. Backing off for {wait_time:.1f}s...")
                time.sleep(wait_time)
            else:
                print(f"API Client Error: {e}")
                break
        except Exception as e:
            print(f"Error executing Gemini request: {e}")
            break

    return {
        "is_match": False,
        "reason": "Failed to evaluate listing via Gemini 3.7",
        "german_message": ""
    }
