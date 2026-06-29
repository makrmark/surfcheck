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
MODEL = "openai/gpt-4o-mini"


def _build_prompt(timeframes_config, all_timeframes):
    """Build system + user prompts for a single LLM call covering all timeframes."""

    system_prompt = (
        "You are an expert surfing forecaster for Sydney's Northern Beaches. "
        "Given offshore swell conditions and per-beach calculations, write ONE very "
        "brief sentence (max 20 words) per beach per timeframe. "
        "Explain the overall experience and the single key factor driving it.\n\n"
        "Factor explanations:\n"
        "- Swell size: metres face height. small <1m, moderate 1-2m, big 2-3m, huge >3m.\n"
        "- Wave period: <8s = weak windswell, 8-12s = moderate, >12s = powerful groundswell.\n"
        "- Embayment factor (0-1): how open the beach is for this swell. "
        "<0.50 = close-out risk (too narrow), 0.50-0.75 = marginal, >=0.75 = plenty of room.\n"
        "- Attack angle: swell direction vs beach face. 15-45° = ideal peeling waves.\n"
        "- Exposure: % of offshore swell reaching the beach after headland diffraction.\n"
        "- Tide factor: 1.0 = optimal (0.5-1.5m range), drops to ~0.6 at extremes.\n"
        "- Wind direction relative to beach: offshore = clean, onshore = messy, cross = neutral.\n"
        "- Overall quality is the product of: wind × attack × tide × embayment.\n\n"
        "Tone: concise, insightful, mildly colloquial — like a local surfer giving a mate "
        "the quick rundown. Do NOT restate the numbers. Focus on the experience and the "
        "primary reason for it.\n\n"
        "Respond with valid JSON only, in this exact format:\n"
        '{"timeframes": {"6-9am": {"Long Reef": "sentence", "Dee Why": "sentence", ...}, ...}}'
    )

    user_prompt = "Generate one-sentence surf reports for these timeframes:\n\n"
    for i, tf_conf in enumerate(timeframes_config):
        tf_data = all_timeframes[i]
        label = tf_conf["label"]
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
                "response_format": {"type": "json_object"},
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
            for beach_name, note in beach_dict.items():
                reports[(tf_label, beach_name)] = note.strip()

        logger.info(f"Received LLM reports for {len(reports)} beach/timeframe combos")
        return reports

    except requests.exceptions.Timeout:
        logger.warning("LLM request timed out — skipping reports")
    except requests.exceptions.RequestException as e:
        logger.warning(f"LLM request failed: {e}")
    except (json.JSONDecodeError, KeyError) as e:
        logger.warning(f"LLM response parsing failed: {e}")

    return {}