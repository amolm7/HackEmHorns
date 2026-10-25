import json
import re
import ssl
import certifi
import urllib.error
import urllib.request
from ..contracts import Error, require


def provider_error(provider, exc, secrets=()):
    status = getattr(exc, "code", None)
    retryable = status in {408, 429, 500, 502, 503, 504} if status else True
    retry_after = 0
    try:
        retry_after = min(60, max(0, int(exc.headers.get("Retry-After", "0"))))
    except (AttributeError, TypeError, ValueError):
        pass
    detail = ""
    if isinstance(exc, urllib.error.HTTPError):
        # Providers explain validation failures in the response body. Keep a short, single-line
        # excerpt so a 400 is diagnosable. The response body is untrusted too.
        try:
            body = json.loads(exc.read(4000).decode("utf-8", "replace"))
            error = body[0]["error"] if isinstance(body, list) else body.get("error", body)
            detail = str(error.get("message", "") if isinstance(error, dict) else error)
        except Exception:
            detail = ""
        for secret in secrets:
            if secret:
                detail = detail.replace(secret, "[redacted]")
        detail = re.sub(r"(?i)(bearer\s+)[^\s,;]+", r"\1[redacted]", detail)
        detail = re.sub(r"\s+", " ", detail).strip()[:240]
        exc.close()
    message = (
        f"{provider} returned HTTP {status}" + (f": {detail}" if detail else ".")
        if status
        else f"{provider} could not be reached."
    )
    return Error(
        message,
        502,
        "provider_error",
        {"retryable": retryable, "retry_after": retry_after},
    )


GEMINI_SCHEMA_KEYS = {"type", "description", "properties", "required", "enum", "items", "format", "nullable"}


def gemini_schema(schema):
    """Gemini accepts an OpenAPI subset for function parameters and rejects unknown fields with HTTP 400
    (for example additionalProperties). Length limits are still enforced by the tool server."""
    if isinstance(schema, list):
        return [gemini_schema(x) for x in schema]
    if not isinstance(schema, dict):
        return schema
    out = {}
    for key, value in schema.items():
        if key == "properties" and isinstance(value, dict):
            out[key] = {name: gemini_schema(sub) for name, sub in value.items()}
        elif key in GEMINI_SCHEMA_KEYS:
            out[key] = gemini_schema(value)
    return out


def gemini_generate(config, contents, instruction, tools=None, structured=False):
    key = config.get("GEMINI_API_KEY", "")
    model = config.get("GEMINI_MODEL", "gemini-3.8-flash")
    require(
        bool(key),
        "Set GEMINI_API_KEY in .env and restart for live Gemini.",
        409,
        "model_not_configured",
    )
    require(bool(re.fullmatch(r"[a-zA-Z0-9._-]+", model)), "Invalid model setting.")
    payload = {
        "contents": contents,
        "systemInstruction": {"parts": [{"text": instruction}]},
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 4096},
    }
    if tools:
        payload["tools"] = [
            {
                "functionDeclarations": [
                    {k: t[k] for k in ["name", "description"]}
                    | {"parameters": gemini_schema(t["inputSchema"])}
                    for t in tools
                ]
            }
        ]
    if structured:
        payload["generationConfig"]["responseMimeType"] = "application/json"
    req = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "x-goog-api-key": key},
    )
    try:
        with urllib.request.urlopen(
            req, timeout=40, context=ssl.create_default_context(cafile=certifi.where())
        ) as r:
            out = json.load(r)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
        raise provider_error("Gemini", exc, (key,))
    candidates = out.get("candidates", [])
    require(
        bool(candidates and candidates[0].get("content", {}).get("parts")),
        "Gemini returned no usable content.",
        502,
        "provider_error",
    )
    return candidates[0]["content"], out.get("usageMetadata", {})


def meta_generate(config, contents, instruction, tools=None, structured=False):
    key = config.get("MODEL_API_KEY") or config.get("META_API_KEY", "")
    require(
        bool(key),
        "Set MODEL_API_KEY in .env and restart for live Meta Muse Spark.",
        409,
        "model_not_configured",
    )
    messages = [{"role": "system", "content": instruction}]
    for content in contents:
        if content.get("role") == "model" and content.get("provider_message"):
            messages.append(content["provider_message"])
            continue
        parts = content.get("parts", [])
        for part in parts:
            if "functionResponse" in part:
                f = part["functionResponse"]
                require(
                    bool(f.get("id")),
                    "Meta tool results require a matching call ID.",
                    502,
                    "provider_error",
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": f["id"],
                        "content": json.dumps(f["response"]),
                    }
                )
        text = "\n".join(p.get("text", "") for p in parts if not p.get("thought"))
        if text:
            messages.append(
                {
                    "role": "assistant" if content.get("role") == "model" else "user",
                    "content": text,
                }
            )
    payload = {
        "model": config.get("META_MODEL", "muse-spark-1.3"),
        "messages": messages,
        "max_completion_tokens": 4096,
    }
    if tools:
        payload["tools"] = [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t["inputSchema"],
                },
            }
            for t in tools
        ]
    if structured:
        properties = {
            "name": {"type": "string"},
            "job_description": {"type": "string"},
            "instructions": {"type": "string"},
            "capability_ids": {"type": "array", "items": {"type": "string"}},
            "kind": {"type": "string", "enum": ["hire", "capability"]},
        }
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": "recruiter_proposal",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": properties,
                    "required": list(properties),
                    "additionalProperties": False,
                },
            },
        }
    req = urllib.request.Request(
        "https://api.meta.ai/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + key},
    )
    try:
        with urllib.request.urlopen(
            req, timeout=45, context=ssl.create_default_context(cafile=certifi.where())
        ) as response:
            data = json.load(response)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
        raise provider_error("Meta Model API", exc, (key,))
    choices = data.get("choices", [])
    require(bool(choices), "Meta returned no usable response.", 502, "provider_error")
    native = choices[0].get("message", {})
    require(isinstance(native, dict), "Invalid Meta response.", 502, "provider_error")
    replay = {
        k: native[k]
        for k in ["role", "content", "tool_calls", "reasoning_content"]
        if k in native
    }
    replay["role"] = "assistant"
    parts = []
    if native.get("content"):
        parts.append({"text": native["content"]})
    for fn in native.get("tool_calls", []):
        require(
            fn.get("type") == "function",
            "Unsupported Meta tool call type.",
            502,
            "provider_error",
        )
        try:
            args = json.loads(fn["function"]["arguments"])
        except (ValueError, KeyError):
            raise Error("Meta returned invalid tool arguments.", 502, "provider_error")
        require(
            isinstance(args, dict) and bool(fn.get("id")),
            "Invalid Meta function call.",
            502,
            "provider_error",
        )
        parts.append(
            {
                "functionCall": {
                    "name": fn["function"]["name"],
                    "args": args,
                    "id": fn["id"],
                }
            }
        )
    require(
        bool(parts), "Meta returned no answer or function calls.", 502, "provider_error"
    )
    usage = data.get("usage", {})
    return {"role": "model", "parts": parts, "provider_message": replay}, {
        "promptTokenCount": usage.get("prompt_tokens", 0),
        "candidatesTokenCount": usage.get("completion_tokens", 0),
    }


# Keep a common internal contract so approval pauses and persisted tool history work with either provider.


def generate(
    config, contents, instruction, tools=None, structured=False, provider="gemini"
):
    if provider == "meta":
        return meta_generate(config, contents, instruction, tools, structured)
    require(provider == "gemini", "Unknown model provider.")
    return gemini_generate(config, contents, instruction, tools, structured)
