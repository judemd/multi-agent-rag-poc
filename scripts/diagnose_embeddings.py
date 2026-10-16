"""One explicitly requested embedding probe; does not index or change workflow state."""
import json
import re
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from google import genai
from google.genai import types
from rag_poc.config import Config

config = Config()
print(json.dumps({"project": config.project, "model": config.embedding_model, "location": config.embedding_location}), flush=True)
try:
    with genai.Client(vertexai=True, project=config.project, location=config.embedding_location,
                      http_options=types.HttpOptions(timeout=30000, retry_options=types.HttpRetryOptions(attempts=1))) as client:
        response = client.models.embed_content(model=config.embedding_model, contents="Small embedding diagnostic.",
            config=types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT", output_dimensionality=768, auto_truncate=False))
    print(json.dumps({"ok": True, "dimensions": len(response.embeddings[0].values)}))
except Exception as exc:
    message = str(getattr(exc, "message", ""))
    message = re.sub(r"(?i)(bearer|access_token|refresh_token|api_key|client_secret)[ =:]+[^ ,;]+", "[REDACTED]", message)
    print(json.dumps({"error_type": type(exc).__name__, "code": getattr(exc, "code", None),
                      "status": getattr(exc, "status", None), "message": message[:1500]}))
    raise SystemExit(1)
