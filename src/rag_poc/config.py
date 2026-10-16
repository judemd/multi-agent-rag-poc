import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

@dataclass(frozen=True)
class Config:
    root: Path = Path(os.getenv("DATA_DIR", "data"))
    project: str = os.getenv("GOOGLE_CLOUD_PROJECT", "project-d4ec743e-de8a-4ed5-b45")
    model: str = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
    location: str = os.getenv("GOOGLE_CLOUD_LOCATION", "global")
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "gemini-embedding-001")
    embedding_location: str = os.getenv("EMBEDDING_LOCATION", "us-central1")
    enabled: bool = os.getenv("ENABLE_VERTEX_CALLS", "false").lower() == "true"
    review_distance: float = float(os.getenv("REVIEW_DISTANCE", "0.45"))

    def require_live(self):
        if not self.enabled:
            raise ValueError("Vertex calls are disabled. Obtain live-test approval, then set ENABLE_VERTEX_CALLS=true.")

    def embedding_signature(self):
        return {"model": self.embedding_model, "dimensions": 768,
                "location": self.embedding_location, "version": 1}
