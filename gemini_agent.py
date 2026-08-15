import os
import json
import time
import random
import warnings
import yaml
from dotenv import load_dotenv
from google import genai
from google.genai import types
from google.genai.errors import ClientError, APIError

warnings.filterwarnings("ignore")
load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError("GEMINI_API_KEY is not set in environment variables or .env file.")

client = genai.Client(api_key=api_key)

def load_config() -> dict:
    with open("config.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def evaluate_and_draft_message(listing_text: str, max_retries: int = 4) -> dict:
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

        except (ClientError, APIError, Exception) as e:
            err_str = str(e)
            is_overloaded = "503" in err_str or "UNAVAILABLE" in err_str or "high demand" in err_str
            is_rate_limit = "429" in err_str or "RESOURCE_EXHAUSTED" in err_str

            if (is_overloaded or is_rate_limit) and attempt < max_retries - 1:
                # Exponential backoff with jitter
                wait_time = (15 * (attempt + 1)) + random.uniform(2.0, 5.0)
                print(f"⚠️ Google API busy ({'503 High Demand' if is_overloaded else '429 Rate Limit'}). Retrying attempt {attempt+1}/{max_retries} after {wait_time:.1f}s...", flush=True)
                time.sleep(wait_time)
                continue
            else:
                print(f"❌ Failed to evaluate with Gemini: {e}", flush=True)
                break

    return {
        "is_match": False,
        "reason": "Evaluation failed due to temporary server load",
        "german_message": ""
    }
