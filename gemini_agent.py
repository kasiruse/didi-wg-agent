import os
import re
import json
import time
import random
import warnings
import string
import yaml
from dotenv import load_dotenv

warnings.filterwarnings("ignore")
load_dotenv()

def load_config() -> dict:
    if os.path.exists("config.yaml"):
        with open("config.yaml", "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}

def _clean_json_output(raw_text: str) -> dict:
    raw_text = raw_text.strip()
    match = re.search(r"\{.*\}", raw_text, re.DOTALL)
    if match:
        raw_text = match.group(0)
    return json.loads(raw_text)

def _call_gemini_native(prompt: str, model_name: str) -> dict:
    from google import genai
    from google.genai import types

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not set.")

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=model_name,
        contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json")
    )
    return json.loads(response.text)

def _call_openai_compatible(prompt: str, base_url: str, model_name: str, api_key: str) -> dict:
    from openai import OpenAI

    client = OpenAI(
        base_url=base_url,
        api_key=api_key if api_key and api_key != "NONE" else "ollama"
    )

    response = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": "You must respond ONLY with a valid raw JSON object matching the requested schema. Do not include markdown codeblocks or extra text."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.2,
        response_format={"type": "json_object"}
    )
    return _clean_json_output(response.choices[0].message.content)

class SafeDict(dict):
    """Prevents KeyError if any template variable is missing."""
    def __missing__(self, key):
        return f"{{{key}}}"

def evaluate_and_draft_message(listing_text: str, max_retries: int = 4) -> dict:
    config = load_config()
    provider = config.get("active_ai_provider", "groq").lower()
    providers_cfg = config.get("ai_providers", {})
    profile = config.get("applicant_profile", {})
    prompt_template = config.get("prompt_template", "")

    format_data = SafeDict({
        "name": str(profile.get("name", "")),
        "age": str(profile.get("age", "")),
        "occupation": str(profile.get("occupation", "")),
        "max_warm_rent": str(profile.get("max_warm_rent", "")),
        "preferred_locations": str(profile.get("preferred_locations", "")),
        "wg_type": str(profile.get("wg_type", "")),
        "move_in_date": str(profile.get("move_in_date", "")),
        "languages": str(profile.get("languages", "")),
        "personal_notes": str(profile.get("personal_notes", "None specified")).strip(),
        "listing_text": str(listing_text)
    })

    # Safe format without risking KeyError crashes
    prompt = string.Formatter().vformat(prompt_template, (), format_data)

    for attempt in range(max_retries):
        try:
            if provider == "gemini":
                model = providers_cfg.get("gemini", {}).get("model", "gemini-3.7-flash")
                return _call_gemini_native(prompt, model)
            else:
                p_cfg = providers_cfg.get(provider, {})
                base_url = p_cfg.get("base_url")
                model = p_cfg.get("model")
                key_env = p_cfg.get("api_key_env", "")
                api_key = os.getenv(key_env, "NONE") if key_env != "NONE" else "NONE"

                return _call_openai_compatible(
                    prompt=prompt,
                    base_url=base_url,
                    model=model,
                    api_key=api_key
                )

        except Exception as e:
            err_str = str(e)
            is_busy = any(code in err_str for code in ["429", "503", "RESOURCE_EXHAUSTED", "rate_limit", "overloaded"])
            if is_busy and attempt < max_retries - 1:
                wait_time = (10 * (attempt + 1)) + random.uniform(1.0, 4.0)
                print(f"⚠️ Provider '{provider}' busy. Retrying {attempt+1}/{max_retries} in {wait_time:.1f}s...", flush=True)
                time.sleep(wait_time)
            else:
                print(f"❌ Error with provider '{provider}': {e}", flush=True)
                break

    return {
        "is_match": False,
        "reason": f"Evaluation failed on provider: {provider}",
        "german_message": ""
    }
