import hashlib
import uuid
import re
from pathlib import Path
from .state import digest
from .parsing import parse_file, profile
from .preparation import Settings, prepare
from .chat import validate_citations, review_reasons
from functools import wraps
from .errors import error_details

def serialized(method):
    @wraps(method)
    def wrapped(self, dataset_id, *args, **kwargs):
        with self.store.lock(dataset_id):
            return method(self, dataset_id, *args, **kwargs)
    return wrapped

class Workflow:
    def __init__(self, store, config, agents, embeddings, vectors):
        self.store, self.config = store, config
        self.agents, self.embeddings, self.vectors = agents, embeddings, vectors

    def create(self, files, name="Support dataset"):
        if not 1 <= len(files) <= 20 or sum(map(len, files.values())) > 25 * 1024 * 1024:
            raise ValueError("Use 1–20 files, at most 25 MB combined")
        if any(Path(n).name != n or n in {".", ".."} or ":" in n or "\\" in n for n in files):
            raise ValueError("Unsafe source filename")
        records = []
        for filename, content in files.items():
            records.extend(parse_file(filename, content))
        if len(records) > 10000:
            raise ValueError("Dataset exceeds 10,000 records")
        manifest = {n: hashlib.sha256(b).hexdigest() for n, b in files.items()}
        fingerprint = digest(manifest)
        for existing in self.store.list():
            if existing["source_hash"] == fingerprint:
                return existing["id"]
        dataset_id = uuid.uuid4().hex
        original = self.config.root / "sources" / dataset_id
        original.mkdir(parents=True)
        for filename, content in files.items():
            (original / filename).write_bytes(content)
        dataset = {"id": dataset_id, "name": name, "manifest": manifest, "source_hash": fingerprint,
                   "records": records, "profile": profile(records), "settings": Settings().model_dump(),
                   "status": "uploaded", "plan": None, "gate1": None, "gate2": None,
                   "chunks": [], "revision": None, "active_revision": None}
        self.store.save(dataset)
        self.store.log(dataset_id, "tool_execution", {"tool": "parse_and_profile", "records": len(records)})
        return dataset_id

    def approval_key(self, dataset):
        return digest({"source": dataset["source_hash"], "settings": dataset["settings"], "pipeline": 1})

    def expected_revision(self, dataset):
        return digest({"approval": self.approval_key(dataset), "chunks": [c["id"] for c in dataset["chunks"]],
                       "embedding": self.config.embedding_signature()})

    @serialized
    def refresh_configuration(self, dataset_id):
        d = self.store.get(dataset_id)
        if d["chunks"] and d["status"] != "cancelled" and d["revision"] != self.expected_revision(d):
            d.update(revision=self.expected_revision(d), gate2=None, active_revision=None, status="review_chunks")
            self.store.save(d)
            self.store.log(dataset_id, "embedding_configuration_changed", self.config.embedding_signature())

    @serialized
    def propose(self, dataset_id):
        d = self.store.get(dataset_id)
        with self.store.operation(dataset_id + ":plan:" + d["source_hash"]):
            result = self.agents.propose(dataset_id, d["profile"])
            result["settings"] = Settings.model_validate(result["settings"]).model_dump()
            if set(result["settings"]["excluded_files"]) - set(d["manifest"]):
                raise ValueError("Agent proposed unknown files")
            d.update(plan=result, settings=result["settings"], status="review_plan")
            self.store.save(d)

    @serialized
    def change_settings(self, dataset_id, settings):
        d = self.store.get(dataset_id)
        settings = Settings.model_validate(settings).model_dump()
        if set(settings["excluded_files"]) - set(d["manifest"]):
            raise ValueError("Unknown excluded file")
        if settings != d["settings"]:
            with self.store.db() as db:
                db.execute("DELETE FROM operations WHERE key LIKE ? AND status='done' AND (key LIKE '%:prepare:%' OR key LIKE '%:index:%')", (dataset_id + ":%",))
            d.update(settings=settings, gate1=None, gate2=None, chunks=[], revision=None,
                     active_revision=None, status="review_plan")
            self.store.save(d)
            self.store.log(dataset_id, "settings_edit", settings)

    @serialized
    def approve_plan(self, dataset_id):
        d = self.store.get(dataset_id)
        if not d["plan"] or d["status"] not in {"review_plan", "plan_approved"}:
            raise ValueError("An agent preparation plan is required before approval")
        d.update(gate1=self.approval_key(d), status="plan_approved")
        self.store.save(d)
        self.store.log(dataset_id, "gate1_approved", {"key": d["gate1"], "settings": d["settings"]})

    @serialized
    def prepare(self, dataset_id):
        d = self.store.get(dataset_id)
        if d["gate1"] != self.approval_key(d) or d["status"] != "plan_approved":
            raise ValueError("Gate 1 approval is required")
        with self.store.operation(dataset_id + ":prepare:" + d["gate1"]):
            chunks, removed = prepare(dataset_id, d["records"], d["settings"])
            revision = digest({"approval": d["gate1"], "chunks": [c["id"] for c in chunks],
                               "embedding": self.config.embedding_signature()})
            d.update(chunks=chunks, revision=revision, gate2=None, status="review_chunks", active_revision=None)
            self.store.save(d)
            self.store.log(dataset_id, "tool_execution", {"tool": "prepare", "chunks": len(chunks), "removed_records": removed})

    @serialized
    def approve_chunks(self, dataset_id):
        d = self.store.get(dataset_id)
        if d["status"] != "review_chunks" or d["gate1"] != self.approval_key(d):
            raise ValueError("Prepare current approved settings before gate 2")
        d.update(gate2=d["revision"], status="index_approved")
        self.store.save(d)
        self.store.log(dataset_id, "gate2_approved", {"revision": d["revision"]})

    @serialized
    def index(self, dataset_id, on_progress=None):
        d = self.store.get(dataset_id)
        expected = digest({"approval": self.approval_key(d), "chunks": [c["id"] for c in d["chunks"]],
                           "embedding": self.config.embedding_signature()})
        if d["gate1"] != self.approval_key(d) or not d["gate2"] or d["gate2"] != expected:
            raise ValueError("Both approvals must match current source, chunks and embedding configuration")
        with self.store.operation(dataset_id + ":index:" + expected):
            try:
                saved = self.vectors.indexed_ids(expected)
                if saved - {c["id"] for c in d["chunks"]}:
                    raise ValueError("Index contains unexpected chunk IDs; refusing to activate it")
                d.update(indexed_chunks=len(saved), index_error=None, status="indexing")
                self.store.save(d)
                if on_progress:
                    on_progress(len(saved), len(d["chunks"]))
                for chunk in d["chunks"]:
                    if chunk["id"] in saved:
                        continue
                    embeddings = self.embeddings.embed([chunk["text"]])
                    # Persist immediately: a later provider failure must not discard successful requests.
                    self.vectors.upsert(expected, [chunk], embeddings)
                    saved.add(chunk["id"])
                    d["indexed_chunks"] = len(saved)
                    self.store.save(d)
                    if len(saved) == 1 or len(saved) % 8 == 0 or len(saved) == len(d["chunks"]):
                        self.store.log(dataset_id, "tool_execution", {"tool": "embed_upsert", "completed": len(saved), "total": len(d["chunks"])})
                    if on_progress:
                        on_progress(len(saved), len(d["chunks"]))
                self.vectors.verify(expected, [c["id"] for c in d["chunks"]])
                d.update(active_revision=expected, status="ready")
                self.store.save(d)
            except Exception as exc:
                d.update(active_revision=None, status="index_failed", index_error=error_details(exc))
                self.store.save(d)
                self.store.log(dataset_id, "index_failed", {"revision": expected, "completed": d.get("indexed_chunks", 0), "error": d["index_error"]})
                raise

    @serialized
    def cancel(self, dataset_id):
        d = self.store.get(dataset_id)
        d.update(status="cancelled", gate1=None, gate2=None, active_revision=None)
        self.store.save(d)
        self.store.log(dataset_id, "cancelled", {})

    @serialized
    def ask(self, dataset_id, question, always=True):
        d = self.store.get(dataset_id)
        if d["status"] != "ready" or not d["active_revision"]:
            raise ValueError("Chat requires a successfully indexed dataset")
        if d["active_revision"] != self.expected_revision(d):
            raise ValueError("Embedding configuration changed; review and index the new revision before chat")
        if not question.strip() or len(question) > 4000:
            raise ValueError("Question must contain 1–4,000 characters")
        if re.search(r"\b(total|average|sum|count|how many|percentage)\b", question, re.I):
            result = {"answer": "This demo doesn't support exact calculations across records, so I can't give you a reliable result for that question.",
                      "insufficient": True, "conflict": False, "citations": []}
            body = {**result, "question": question, "evidence": [], "reasons": ["Exact aggregation is outside this demo's scope"],
                    "published": result["answer"], "human_edited": False}
            return self.store.add_draft(dataset_id, d["active_revision"], body, True)
        def search(query):
            return self.vectors.search(d["active_revision"], dataset_id, self.embeddings.embed([query], query=True)[0])
        result, evidence = self.agents.answer(dataset_id, question, search)
        if any(e["metadata"]["dataset_id"] != dataset_id for e in evidence):
            raise ValueError("Dataset isolation violation")
        # Preserve Gemini's wording, but fail closed if it asserts an answer without evidence.
        if not evidence and not result["insufficient"]:
            raise ValueError("The agent did not acknowledge the missing evidence. No answer was published; please try the question again.")
        try:
            cited = validate_citations(result["answer"], evidence, result["insufficient"])
            if cited != set(result["citations"]):
                raise ValueError("Structured and inline citations disagree")
            reasons = review_reasons(result, evidence, always, self.config.review_distance, question)
        except ValueError:
            reasons = ["Invalid or missing citations; repair references before approval"]
        body = {**result, "question": question, "evidence": evidence, "reasons": reasons,
                "published": result["answer"], "human_edited": False}
        return self.store.add_draft(dataset_id, d["active_revision"], body, bool(reasons))
