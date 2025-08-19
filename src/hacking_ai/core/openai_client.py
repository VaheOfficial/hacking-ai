import os
import requests
from typing import Optional


def summarize_with_openai(prompt: str, text: str, max_tokens: int = 256) -> Optional[str]:
	api_key = os.environ.get("OPENAI_API_KEY")
	if not api_key:
		return None
	base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
	model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
	try:
		resp = requests.post(
			f"{base_url}/chat/completions",
			headers={
				"Authorization": f"Bearer {api_key}",
				"Content-Type": "application/json",
			},
			json={
				"model": model,
				"messages": [
					{"role": "system", "content": "You are a concise security research assistant."},
					{"role": "user", "content": f"Summarize the following focusing on actionable steps and indicators.\n\n{text}"},
				],
				"temperature": 0.2,
				"max_tokens": max_tokens,
			},
			timeout=30,
		)
		resp.raise_for_status()
		data = resp.json()
		return data["choices"][0]["message"]["content"].strip()
	except Exception:
		return None