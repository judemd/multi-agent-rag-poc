from google import genai
from google.genai import types
from google.genai.errors import APIError
from .errors import ProviderFailure

class VertexEmbeddings:
    def __init__(self, config):
        self.config = config

    def embed(self, texts, query=False):
        self.config.require_live()
        client = genai.Client(vertexai=True, project=self.config.project, location=self.config.embedding_location,
            http_options=types.HttpOptions(timeout=60000, retry_options=types.HttpRetryOptions(
                attempts=4, initial_delay=10, max_delay=30, jitter=1,
                http_status_codes=[408, 429, 500, 502, 503, 504])))
        try:
            vectors = []
            for text in texts:
                response = client.models.embed_content(
                    model=self.config.embedding_model, contents=text,
                    config=types.EmbedContentConfig(task_type="RETRIEVAL_QUERY" if query else "RETRIEVAL_DOCUMENT",
                                                  output_dimensionality=768, auto_truncate=False))
                if not response.embeddings or len(response.embeddings[0].values) != 768:
                    raise ValueError("Unexpected embedding dimensions")
                if response.embeddings[0].statistics and response.embeddings[0].statistics.truncated:
                    raise ValueError("Embedding input was truncated")
                vectors.append(response.embeddings[0].values)
            return vectors
        except APIError as exc:
            raise ProviderFailure(exc) from None
        finally:
            client.close()
