"""Calls an OpenAI-compatible chat endpoint, trying Groq then Gemini.

Model names are never hard-coded: they come from settings.GROQ_MODEL /
settings.GEMINI_MODEL. On a rate-limit or server error, a provider gets one
retry with a short backoff before moving to the next provider. A response
that fails schema validation gets one retry (same provider, with the
validation error appended) before moving on. If every provider fails,
raises AIUnavailableError with a message the UI shows as-is.
"""

import hashlib
import json
import time
from dataclasses import dataclass

from openai import APIStatusError, OpenAI, RateLimitError
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from app.config import settings
from app.models.ai_outputs import AIOutput

RETRY_BACKOFF_SECONDS = 1.5


class AIUnavailableError(Exception):
    """Raised when no configured provider could produce a valid response."""


@dataclass
class AICallResult:
    output: BaseModel
    provider: str
    model: str
    cached: bool


def _providers() -> list[tuple[str, str, str, str]]:
    """(name, base_url, api_key, model) for each provider with a key set, in priority order."""
    providers = []
    if settings.GROQ_API_KEY:
        providers.append(("groq", "https://api.groq.com/openai/v1", settings.GROQ_API_KEY, settings.GROQ_MODEL))
    if settings.GEMINI_API_KEY:
        providers.append(
            ("gemini", "https://generativelanguage.googleapis.com/v1beta/openai/", settings.GEMINI_API_KEY, settings.GEMINI_MODEL)
        )
    return providers


def _chat(base_url: str, api_key: str, model: str, system_prompt: str, user_prompt: str) -> str:
    client = OpenAI(base_url=base_url, api_key=api_key)
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
        response_format={"type": "json_object"},
    )
    return response.choices[0].message.content


def _is_retryable(exc: Exception) -> bool:
    if isinstance(exc, RateLimitError):
        return True
    return isinstance(exc, APIStatusError) and exc.status_code >= 500


def _chat_with_backoff(base_url: str, api_key: str, model: str, system_prompt: str, user_prompt: str) -> str:
    try:
        return _chat(base_url, api_key, model, system_prompt, user_prompt)
    except Exception as exc:
        if not _is_retryable(exc):
            raise
        time.sleep(RETRY_BACKOFF_SECONDS)
        return _chat(base_url, api_key, model, system_prompt, user_prompt)


def _call_provider(
    name: str, base_url: str, api_key: str, model: str, system_prompt: str, user_prompt: str, schema: type[BaseModel]
) -> BaseModel:
    raw = _chat_with_backoff(base_url, api_key, model, system_prompt, user_prompt)
    try:
        return schema.model_validate_json(raw)
    except ValidationError as validation_error:
        retry_prompt = (
            f"{user_prompt}\n\nYour previous response did not match the required schema "
            f"({validation_error}). Return valid JSON matching the schema exactly."
        )
        raw_retry = _chat(base_url, api_key, model, system_prompt, retry_prompt)
        return schema.model_validate_json(raw_retry)


def call_llm(system_prompt: str, user_prompt: str, schema: type[BaseModel]) -> tuple[BaseModel, str, str]:
    """Returns (parsed_output, provider_name, model). Raises AIUnavailableError on total failure."""
    providers = _providers()
    if not providers:
        raise AIUnavailableError("AI is unavailable right now. Please continue manually.")

    last_error: Exception | None = None
    for name, base_url, api_key, model in providers:
        try:
            output = _call_provider(name, base_url, api_key, model, system_prompt, user_prompt, schema)
            return output, name, model
        except Exception as exc:  # any provider failure falls through to the next provider
            last_error = exc
            continue

    raise AIUnavailableError("AI is unavailable right now. Please continue manually.") from last_error


def compute_input_hash(input_data: dict) -> str:
    normalized = json.dumps(input_data, sort_keys=True, default=str)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def peek_cache(db: Session, task: str, input_data: dict, prompt_version: str, schema: type[BaseModel]) -> BaseModel | None:
    """Read-only cache lookup for display purposes. Never calls the LLM."""
    input_hash = compute_input_hash({**input_data, "prompt_version": prompt_version})
    cached = db.query(AIOutput).filter(AIOutput.task == task, AIOutput.input_hash == input_hash).first()
    return schema.model_validate(cached.output) if cached is not None else None


def call_llm_cached(
    db: Session,
    task: str,
    input_data: dict,
    prompt_version: str,
    system_prompt: str,
    user_prompt: str,
    schema: type[BaseModel],
    force: bool = False,
) -> AICallResult:
    """Looks up a cached AIOutput by (task, sha256(normalised input)) before calling the LLM.

    `force=True` skips the cache lookup and always makes a fresh call -- this is
    what "Regenerate" means. The input (and so the cache key) hasn't changed, so
    without this the LLM is never actually called again: a plain cache-first
    lookup would just keep handing back the same stored row forever, which
    makes a "Regenerate" button silently do nothing new. The fresh result
    still overwrites the same cache row, so the next page load (a plain,
    non-forced peek) sees the regenerated version, not the original.
    """
    input_hash = compute_input_hash({**input_data, "prompt_version": prompt_version})

    cached = db.query(AIOutput).filter(AIOutput.task == task, AIOutput.input_hash == input_hash).first()
    if cached is not None and not force:
        return AICallResult(output=schema.model_validate(cached.output), provider=cached.provider, model=cached.model, cached=True)

    output, provider, model = call_llm(system_prompt, user_prompt, schema)

    if cached is not None:
        cached.provider = provider
        cached.model = model
        cached.output = output.model_dump()
    else:
        db.add(
            AIOutput(
                task=task,
                input_hash=input_hash,
                provider=provider,
                model=model,
                prompt_version=prompt_version,
                output=output.model_dump(),
            )
        )
    db.flush()
    return AICallResult(output=output, provider=provider, model=model, cached=False)
