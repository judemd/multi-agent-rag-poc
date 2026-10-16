"""Safe provider diagnostics: never render raw requests, headers or credentials."""
from google.genai.errors import APIError

def error_details(exc):
    if isinstance(exc, ProviderFailure):
        return exc.details
    if not isinstance(exc, APIError):
        return {"type": type(exc).__name__, "message": "Processing stopped. Saved chunks can be reused on retry."}
    code = exc.code
    guidance = {
        400: "Vertex rejected the embedding input or request settings. Check the model and input size.",
        401: "Google credentials could not authenticate. Refresh Application Default Credentials and restart the app.",
        403: "Vertex access was denied. Check API enablement, billing and the account's Vertex permissions.",
        404: "The configured model or endpoint was not found. Check the model ID and region.",
        429: "Vertex rate, quota or capacity limit reached. Wait before retrying; saved chunks will be reused.",
    }.get(code, "Vertex is temporarily unavailable. Retry later; saved chunks will be reused." if code >= 500
          else "Vertex rejected the request. Check the configured model and Google Cloud access.")
    # Status comes from our HTTP-code map, never from an arbitrary provider response.
    status = {400: "INVALID_ARGUMENT", 401: "UNAUTHENTICATED", 403: "PERMISSION_DENIED",
              404: "NOT_FOUND", 429: "RESOURCE_EXHAUSTED"}.get(code, "API_ERROR")
    return {"type": type(exc).__name__, "http_code": code, "status": status,
            "message": f"Vertex request failed (HTTP {code}, {status}). {guidance}"}

class ProviderFailure(ValueError):
    def __init__(self, exc):
        self.details = error_details(exc)
        super().__init__(self.details["message"])
