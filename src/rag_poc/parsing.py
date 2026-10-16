import csv
import io
import json
import re
from pathlib import Path
from pypdf import PdfReader

MAX_FILE = 5 * 1024 * 1024

def parse_file(name, content):
    if len(content) > MAX_FILE:
        raise ValueError(f"{name}: exceeds 5 MB")
    ext = Path(name).suffix.lower()
    records = []
    try:
        if ext == ".pdf":
            reader = PdfReader(io.BytesIO(content), strict=True)
            if reader.is_encrypted or len(reader.pages) > 50:
                raise ValueError("encrypted PDF or more than 50 pages")
            for page, item in enumerate(reader.pages, 1):
                text = item.extract_text() or ""
                if not text.strip():
                    raise ValueError(f"page {page} has no extractable text; OCR is unsupported")
                records.append({"text": text, "ref": f"page {page}", "values": None})
        elif ext in {".csv", ".json", ".txt"}:
            text = content.decode("utf-8-sig")
            if "\x00" in text:
                raise ValueError("binary content is unsupported")
            if ext == ".csv":
                reader = csv.DictReader(io.StringIO(text), strict=True)
                if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames):
                    raise ValueError("missing or duplicate CSV headers")
                for row in reader:
                    if None in row or any(v is None for v in row.values()):
                        raise ValueError(f"malformed CSV at line {reader.line_num}")
                    records.append({"text": json.dumps(row, ensure_ascii=False),
                                    "ref": f"row {len(records)+1} (line end {reader.line_num})", "values": row})
            elif ext == ".json":
                def reject_constant(value):
                    raise ValueError(f"invalid JSON constant {value}")
                def unique_pairs(pairs):
                    result = {}
                    for key, value in pairs:
                        if key in result:
                            raise ValueError(f"duplicate JSON key {key}")
                        result[key] = value
                    return result
                data = json.loads(text, parse_constant=reject_constant, object_pairs_hook=unique_pairs)
                items = data if isinstance(data, list) else [data]
                if not all(isinstance(x, dict) for x in items):
                    raise ValueError("JSON must be an object or array of objects")
                records = [{"text": json.dumps(x, ensure_ascii=False, sort_keys=True),
                            "ref": f"JSON item {i}", "values": x} for i, x in enumerate(items, 1)]
            else:
                # Blank lines delimit paragraphs; preserve exact source line boundaries.
                start, lines = 1, []
                for n, line in enumerate(text.splitlines() + [""], 1):
                    if line.strip():
                        if not lines:
                            start = n
                        lines.append(line)
                    elif lines:
                        records.append({"text": "\n".join(lines), "ref": f"lines {start}-{n-1}", "values": None})
                        lines = []
        else:
            raise ValueError("supported formats: CSV, JSON, TXT, text PDF")
        if not records or not any(r["text"].strip() for r in records):
            raise ValueError("file contains no records")
        if len(records) > 10000:
            raise ValueError("more than 10,000 records")
        return [{**r, "filename": name} for r in records]
    except Exception as exc:
        raise ValueError(f"{name}: {exc}") from exc

def profile(records):
    types = {}
    def inspect(value, path=""):
        if isinstance(value, dict):
            for key, item in value.items():
                inspect(item, f"{path}.{key}" if path else key)
            return
        if isinstance(value, list):
            types.setdefault(path, set()).add("array")
            for item in value:
                inspect(item, path + "[]")
            return
        kind = type(value).__name__
        if isinstance(value, str):
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                kind = "date-like string"
            elif value.lower() in {"true", "false"}:
                kind = "boolean-like string"
            elif re.fullmatch(r"-?\d+(\.\d+)?", value):
                kind = "numeric-like string"
        types.setdefault(path, set()).add(kind)
    for record in records:
        if record["values"] is not None:
            inspect(record["values"], record["filename"])
    def missing(value):
        if isinstance(value, dict):
            return sum(missing(v) for v in value.values())
        if isinstance(value, list):
            return sum(missing(v) for v in value)
        return int(value is None or value == "")
    return {"records": len(records), "files": sorted({r["filename"] for r in records}),
            "field_types_observed": {key: sorted(value) for key, value in types.items()},
            "missing_values": sum(missing(r["values"]) for r in records if r["values"] is not None),
            "duplicate_records": len(records) - len({(r["filename"], r["text"]) for r in records}),
            "samples": [{"filename": r["filename"], "ref": r["ref"], "text": r["text"][:2000]} for r in records[:8]]}
