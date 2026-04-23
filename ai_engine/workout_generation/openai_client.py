from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

from .errors import OpenAIRequestException, WorkoutGenerationError
from .parsing import extract_output_text_from_responses_payload, parse_json_from_output_text


def _should_send_temperature(model_id: str) -> bool:
    """
    Some OpenAI models reject `temperature` on /v1/responses (HTTP 400).
    Set OPENAI_OMIT_TEMPERATURE=1 to never send it.
    """
    if os.environ.get("OPENAI_OMIT_TEMPERATURE", "").strip().lower() in ("1", "true", "yes"):
        return False
    m = (model_id or "").strip().lower()
    if not m:
        return True
    if m.startswith(("o1", "o3", "o4")):
        return False
    if m.startswith("gpt-5"):
        return False
    return True


def _response_rejects_temperature(body: str) -> bool:
    """Detect 400 responses like: Unsupported parameter: 'temperature' is not supported with this model."""
    b = (body or "").lower()
    return "temperature" in b and ("not supported" in b or "unsupported parameter" in b)


def openai_generate_workout_plan_with_responses_api(
    *,
    system_prompt: str,
    user_prompt: str,
    json_schema: Dict[str, Any],
    model: Optional[str] = None,
    timeout_seconds: int = 30,
    temperature: float = 0.2,
    max_output_tokens: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Call OpenAI Responses API to generate strict-JSON workout plan.

    Raises OpenAIRequestException/OpenAIResponseParseException on failures.
    """
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise OpenAIRequestException(
            WorkoutGenerationError(kind="openai_auth", message="OPENAI_API_KEY is not set.")
        )

    selected_model = (model or os.environ.get("OPENAI_MODEL") or "gpt-4o-mini").strip()

    payload: Dict[str, Any] = {
        "model": selected_model,
        "input": [
            {
                "role": "system",
                "content": [{"type": "input_text", "text": system_prompt}],
            },
            {
                "role": "user",
                "content": [{"type": "input_text", "text": user_prompt}],
            },
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "one_session_workout_plan",
                "schema": json_schema,
                "strict": True,
            }
        },
    }
    if _should_send_temperature(selected_model):
        payload["temperature"] = temperature
    if max_output_tokens is not None:
        payload["max_output_tokens"] = max_output_tokens

    def _post(payload_obj: Dict[str, Any]) -> urllib.request.Request:
        return urllib.request.Request(
            url="https://api.openai.com/v1/responses",
            data=json.dumps(payload_obj).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )

    req = _post(payload)
    attempt = 0
    try:
        while True:
            try:
                with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
                    raw = resp.read().decode("utf-8")
                    break
            except urllib.error.HTTPError as e:
                body = ""
                try:
                    body = e.read().decode("utf-8")
                except Exception:
                    body = str(e)
                code = getattr(e, "code", "unknown")
                if (
                    attempt == 0
                    and code == 400
                    and payload.get("temperature") is not None
                    and _response_rejects_temperature(body)
                ):
                    del payload["temperature"]
                    req = _post(payload)
                    attempt += 1
                    continue
                api_msg = ""
                try:
                    parsed = json.loads(body)
                    err = parsed.get("error") if isinstance(parsed, dict) else None
                    if isinstance(err, dict):
                        api_msg = str(err.get("message") or "").strip()
                except Exception:
                    pass
                if api_msg:
                    human = f"OpenAI HTTP {code}: {api_msg}"
                else:
                    human = f"OpenAI HTTP {code}: {body[:800]}"
                raise OpenAIRequestException(
                    WorkoutGenerationError(
                        kind="openai_http",
                        message=human,
                        details={"body_prefix": body[:800]},
                    )
                ) from e
    except urllib.error.URLError as e:
        raise OpenAIRequestException(
            WorkoutGenerationError(kind="openai_connection", message="OpenAI connection error.", details={"error": str(e)})
        ) from e

    try:
        response_payload = json.loads(raw)
    except json.JSONDecodeError as e:
        raise OpenAIRequestException(
            WorkoutGenerationError(
                kind="openai_http_parse",
                message="OpenAI response was not valid JSON.",
                details={"error": str(e), "prefix": raw[:200]},
            )
        ) from e

    output_text = extract_output_text_from_responses_payload(response_payload)
    if not output_text:
        raise OpenAIRequestException(
            WorkoutGenerationError(kind="openai_empty_output", message="OpenAI response did not contain output_text.")
        )

    return parse_json_from_output_text(output_text=output_text)

