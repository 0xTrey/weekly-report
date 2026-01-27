"""
Ollama Client

Interfaces with local Ollama instance running Gemma 2.
Handles health checks, model verification, and LLM synthesis.
"""

import json
from pathlib import Path
from typing import Optional

import requests


def load_settings() -> dict:
    """Load settings from config file."""
    settings_path = Path(__file__).parent.parent / "config" / "settings.json"
    with open(settings_path) as f:
        return json.load(f)


def check_ollama_running(endpoint: Optional[str] = None) -> bool:
    """
    Check if Ollama is running and accessible.
    """
    settings = load_settings()
    endpoint = endpoint or settings.get("ollama_endpoint", "http://localhost:11434/api/generate")
    base_url = endpoint.rsplit("/api", 1)[0]

    try:
        response = requests.get(f"{base_url}/api/tags", timeout=5)
        return response.status_code == 200
    except requests.exceptions.RequestException:
        return False


def check_model_available(model: Optional[str] = None) -> bool:
    """
    Check if the specified model is available in Ollama.
    """
    settings = load_settings()
    model = model or settings.get("ollama_model", "gemma2:27b")
    endpoint = settings.get("ollama_endpoint", "http://localhost:11434/api/generate")
    base_url = endpoint.rsplit("/api", 1)[0]

    try:
        response = requests.get(f"{base_url}/api/tags", timeout=5)
        if response.status_code != 200:
            return False

        data = response.json()
        models = data.get("models", [])

        for m in models:
            if m.get("name", "").startswith(model.split(":")[0]):
                return True

        return False
    except requests.exceptions.RequestException:
        return False


def get_available_models() -> list[str]:
    """
    Get list of available models in Ollama.
    """
    settings = load_settings()
    endpoint = settings.get("ollama_endpoint", "http://localhost:11434/api/generate")
    base_url = endpoint.rsplit("/api", 1)[0]

    try:
        response = requests.get(f"{base_url}/api/tags", timeout=5)
        if response.status_code != 200:
            return []

        data = response.json()
        return [m.get("name", "") for m in data.get("models", [])]
    except requests.exceptions.RequestException:
        return []


SYNTHESIS_PROMPT = """You are summarizing deal/partner activity for an executive weekly report.

Be bulleted, punchy, and executive-level. No fluff. No emojis.

Structure your response as:
- Activity: What happened (meetings/emails)
- Deal Status: Pricing, Terms, Start Date if known (only if applicable)
- Risks: Blockers or concerns (only if there are any)
- Action Items: Next steps for upcoming week

Context:
{context}

Provide a concise summary following the structure above. If certain sections don't apply (e.g., no known deal status for partners), omit them."""


def synthesize(
    context: str,
    entity_name: str,
    entity_type: str = "deal",
    model: Optional[str] = None,
) -> str:
    """
    Synthesize meeting notes and emails into a summary using Ollama.

    Args:
        context: Combined email and meeting note content
        entity_name: Name of the deal/partner
        entity_type: "deal", "agency_partner", or "tech_partner"
        model: Ollama model to use (defaults to settings)

    Returns:
        Synthesized summary text
    """
    settings = load_settings()
    model = model or settings.get("ollama_model", "gemma2:27b")
    endpoint = settings.get("ollama_endpoint", "http://localhost:11434/api/generate")

    prompt = SYNTHESIS_PROMPT.format(context=context)

    # Add entity context
    prompt = f"Entity: {entity_name} ({entity_type})\n\n{prompt}"

    try:
        response = requests.post(
            endpoint,
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.3,
                    "top_p": 0.9,
                },
            },
            timeout=120,
        )

        if response.status_code != 200:
            return f"Error: Ollama returned status {response.status_code}"

        data = response.json()
        return data.get("response", "").strip()

    except requests.exceptions.Timeout:
        return "Error: Ollama request timed out"
    except requests.exceptions.RequestException as e:
        return f"Error: Could not connect to Ollama - {e}"


def verify_ollama_setup() -> tuple[bool, str]:
    """
    Verify Ollama is properly set up.

    Returns:
        (success: bool, message: str)
    """
    settings = load_settings()
    model = settings.get("ollama_model", "gemma2:27b")

    if not check_ollama_running():
        return False, (
            "Ollama is not running. Start it with:\n"
            "  ollama serve\n\n"
            "Or install Ollama from: https://ollama.ai"
        )

    available = get_available_models()

    if not available:
        return False, "Ollama is running but no models are available."

    model_base = model.split(":")[0]
    matching = [m for m in available if m.startswith(model_base)]

    if not matching:
        return False, (
            f"Model '{model}' is not available.\n"
            f"Available models: {', '.join(available)}\n\n"
            f"To install the required model, run:\n"
            f"  ollama pull {model}"
        )

    return True, f"Ollama ready with model: {matching[0]}"


if __name__ == "__main__":
    # Test the module
    print("Checking Ollama setup...")
    success, message = verify_ollama_setup()
    print(message)

    if success:
        print("\nTesting synthesis...")
        test_context = """
        Meeting on 2025-01-20: Discussed pricing options.
        They are interested in the enterprise tier.
        Need to follow up with a proposal by Friday.
        """
        result = synthesize(test_context, "Test Company", "deal")
        print(result)
