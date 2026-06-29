"""
LLM-powered per-beach surf report generator.

Uses OpenRouter API to generate concise, insightful one-sentence reports
for each beach at each timeframe, based on the computed numerical data.
"""

import os
import json
import requests
import logging

logger = logging.getLogger(__name__)

API_KEY_ENV = "OPENROUTER_API_KEY"
API_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "meta-llama/llama-3.3-70b-instruct:free"


def _build_prompt(timeframes_config, all_timeframes):
    """Build system + user prompts for a single LLM call covering all timeframes."""

    system_prompt = (
        "You are an expert surfing forecaster for Sydney's Northern Beaches. "
        "Given offshore swell conditions and per-beach calculations, write ONE very "
        "brief sentence (max 20 words) per beach per timeframe. "
        "Explain the overall experience and the key FACTORS driving it.\n\n"
        "IMPORTANT: The numerical values (height, exposure %, wind label, tide height, "
        "rating) are already displayed on the card. Do NOT restate them. Instead, talk about "
        "the underlying factors that explain WHY the surf is big/small and good/bad.\n\n"
        "Factors driving SURF SIZE:\n"
        "- Headland shadowing / exposure: is the beach in the direct swell window? Big waves "
        "wrap around headlands when the swell direction is favourable.\n"
        "- Wave period energy: long-period groundswell (>12s) has more push and amplifies "
        "more via shoaling. Short-period windswell (<8s) is weak regardless of height.\n"
        "- Diffraction: waves bend around headlands, reducing energy in the lee.\n\n"
        "Factors driving SURF QUALITY:\n"
        "- Embayment: a narrow/closed beach (like Freshwater) can't spread big swell energy \u2014 "
        "it closes out. A wide beach (Long Reef) gives room to breathe. Match this to the "
        "swell size.\n"
        "- Attack angle: the swell angle relative to the beach face. Use outcome language: "
        "'closes out' (straight-on, 0-10\u00b0), 'peels down the line' (ideal, 15-45\u00b0), "
        "'mushy / weak from refracting' (extreme angle, 60\u00b0+).\n"
        "- Wind: offshore holds up the face; onshore chops it up; cross is neutral.\n"
        "- Tide: the rising/falling cycle affects whether banks are working or fat.\n"
        "- Quality is a product: one bad factor (e.g. onshore gale) ruins the session "
        "regardless of wave height.\n\n"
        "Tone: concise, insightful, mildly colloquial \u2014 like a local surfer giving a mate "
        "the quick rundown. Use phrases like 'wraps around', 'sheltered from', 'the long period "
        "gives it punch', 'too narrow to handle', 'clean offshore holds up the face'.\n\n"
        "Respond with valid JSON only, in this exact format:\n"
        '{"timeframes": {"6-9am": {"Long Reef": "sentence", "Dee Why": "sentence", ...}, ...}}'
    )

    user_prompt = "Provide forecasts for these timeframes (focus on WHY the conditions are what they are):\n\n"
    for i, tf_conf in enumerate(timeframes_config):
        tf_data = all_timeframes[i]
        label = tf_conf["label"]
        # Replace en-dash with hyphen so the LLM doesn't have to reproduce Unicode
        label = _normalise_label(label)
        user_prompt += f"--- {label} ---\n"
        user_prompt += (
            f"Offshore: {tf_data['wave_height']:.1f}m @ {tf_data['wave_period']:.0f}s "
            f"from {tf_data['wave_direction']:.0f}° ({tf_data['wave_compass']})\n"
        )
        user_prompt += (
            f"Wind: {tf_data['wind_speed']:.0f} km/h from {tf_data['wind_direction']:.0f}° "
            f"({tf_data['wind_compass']})\n"
        )
        user_prompt += f"Tide: {tf_data['display_tide']:.1f}m ({tf_data['tide_trend']})\n\n"
        user_prompt += "Beaches:\n"
        for bc in tf_data["beach_conditions"]:
            user_prompt += (
                f"  {bc['name']}: {bc['effective_height']:.1f}m, "
                f"exposure {bc['exposure']:.0f}%, "
                f"embayment {bc['embayment_factor']:.0%}, "
                f"attack {bc['attack_angle']:.0f}° (factor {bc['attack_factor']:.0%}), "
                f"wind {bc['wind_label']} (quality {bc['wind_quality']:.0%}), "
                f"tide factor {bc['tide_factor_value']:.0%}, "
                f"overall quality {bc['wave_quality']:.0%}, "
                f"rating {bc['rating']}★\n"
            )
        user_prompt += "\n"

    return system_prompt, user_prompt


def _normalise_label(label):
    """Normalise unicode dashes to regular hyphens for matching."""
    return label.replace('\u2013', '-').replace('\u2014', '-')


def _load_env_file():
    """Try to load ~/.surforecast/env.sh as a fallback for API keys."""
    env_file = os.path.expanduser("~/.surforecast/env.sh")
    if os.path.isfile(env_file):
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line.startswith("export ") and "=" in line:
                    parts = line[7:].split("=", 1)
                    key, val = parts[0], parts[1].strip('"').strip("'")
                    os.environ.setdefault(key, val)


def generate_reports(timeframes_config, all_timeframes):
    """
    Call OpenRouter to generate per-beach surf reports for all timeframes.

    Args:
        timeframes_config: list of {"label": ..., "hour": ..., "emoji": ...}
        all_timeframes: list of dicts from compute_timeframe_conditions()

    Returns:
        dict mapping (timeframe_label, beach_name) -> str report sentence.
        Empty dict if API key is not set or call fails.
    """
    # Try env var first, then fall back to ~/.surforecast/env.sh
    _load_env_file()
    api_key = os.environ.get(API_KEY_ENV)
    if not api_key:
        logger.info("OPENROUTER_API_KEY not set — skipping LLM reports")
        return {}

    system_prompt, user_prompt = _build_prompt(timeframes_config, all_timeframes)
    logger.info(f"Sending LLM request ({len(all_timeframes)} timeframes, "
                f"{len(all_timeframes[0]['beach_conditions'])} beaches each)")

    try:
        response = requests.post(
            API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "max_tokens": 2000,
                "temperature": 0.3,
            },
            timeout=30,
        )
        response.raise_for_status()
        result = response.json()
        content = json.loads(result["choices"][0]["message"]["content"])

        reports = {}
        for tf_label, beach_dict in content.get("timeframes", {}).items():
            # Normalise LLM label to match timeframes_config (handles dash variations)
            norm_label = _normalise_label(tf_label)
            matched_label = None
            for tf_conf in timeframes_config:
                if _normalise_label(tf_conf["label"]) == norm_label:
                    matched_label = tf_conf["label"]
                    break
            if not matched_label:
                logger.warning(f"LLM returned unknown timeframe label: {tf_label!r}")
                continue
            for beach_name, note in beach_dict.items():
                reports[(matched_label, beach_name)] = note.strip()

        logger.info(f"Received LLM reports for {len(reports)} beach/timeframe combos")
        return reports

    except requests.exceptions.Timeout:
        logger.warning("LLM request timed out — skipping reports")
    except requests.exceptions.RequestException as e:
        logger.warning(f"LLM request failed: {e}")
    except (json.JSONDecodeError, KeyError) as e:
        logger.warning(f"LLM response parsing failed: {e}")

    return {}