from pydantic import BaseModel, Field, model_validator
from .state import digest

class Settings(BaseModel):
    chunk_size: int = Field(default=1800, ge=200, le=4000)
    overlap: int = Field(default=200, ge=0, le=1000)
    trim_whitespace: bool = True
    remove_duplicates: bool = False
    excluded_files: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def valid_overlap(self):
        if self.overlap >= self.chunk_size:
            raise ValueError("Overlap must be smaller than chunk size")
        return self

def prepare(dataset_id, records, settings):
    settings = Settings.model_validate(settings)
    chunks, seen, removed = [], set(), []
    for record in records:
        if record["filename"] in settings.excluded_files:
            continue
        text = record["text"].strip() if settings.trim_whitespace else record["text"]
        key = (record["filename"], text)
        if settings.remove_duplicates and key in seen:
            removed.append({"filename": record["filename"], "ref": record["ref"]})
            continue
        seen.add(key)
        offset = 0
        while offset < len(text):
            end = min(offset + settings.chunk_size, len(text))
            if end < len(text):
                boundary = text.rfind(" ", offset + settings.chunk_size // 2, end)
                if boundary > offset:
                    end = boundary
            part = text[offset:end]
            metadata = {"dataset_id": dataset_id, "filename": record["filename"],
                        "reference": record["ref"], "offset": offset}
            chunk_id = digest({"metadata": metadata, "settings": settings.model_dump(), "text": part})
            chunks.append({"id": chunk_id, "text": part, "metadata": {**metadata, "chunk_id": chunk_id}})
            if len(chunks) > 2000:
                raise ValueError("Chunk limit exceeded (2,000). Exclude files or increase chunk size.")
            if end == len(text):
                break
            offset = end - settings.overlap
    if not chunks:
        raise ValueError("Preparation produced no chunks")
    return chunks, removed
