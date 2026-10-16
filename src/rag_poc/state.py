import hashlib
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))

def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()

class Store:
    """SQLite is authoritative; UI session state is only presentation state."""
    def __init__(self, root):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / "workflow.sqlite3"
        with self.db() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS datasets(id TEXT PRIMARY KEY, name TEXT, body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY, at TEXT, dataset TEXT, kind TEXT, body TEXT);
            CREATE TABLE IF NOT EXISTS operations(key TEXT PRIMARY KEY, status TEXT, owner TEXT);
            CREATE TABLE IF NOT EXISTS drafts(id TEXT PRIMARY KEY, dataset TEXT, revision TEXT, status TEXT, body TEXT);
            """)

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def save(self, dataset):
        with self.db() as db:
            db.execute("INSERT OR REPLACE INTO datasets VALUES (?,?,?)",
                       (dataset["id"], dataset["name"], canonical(dataset)))

    def get(self, dataset_id):
        with self.db() as db:
            row = db.execute("SELECT body FROM datasets WHERE id=?", (dataset_id,)).fetchone()
        if not row:
            raise ValueError("Unknown dataset")
        return json.loads(row[0])

    def list(self):
        with self.db() as db:
            return [json.loads(r[0]) for r in db.execute("SELECT body FROM datasets ORDER BY rowid DESC")]

    def log(self, dataset, kind, body):
        with self.db() as db:
            db.execute("INSERT INTO events(at,dataset,kind,body) VALUES (?,?,?,?)",
                       (datetime.now(timezone.utc).isoformat(), dataset, kind, canonical(body)))

    def events(self, dataset):
        with self.db() as db:
            return [dict(r) for r in db.execute("SELECT * FROM events WHERE dataset=? ORDER BY seq DESC LIMIT 100", (dataset,))]

    @contextmanager
    def operation(self, key):
        owner = uuid.uuid4().hex
        with self.db() as db:
            try:
                db.execute("INSERT INTO operations VALUES (?, 'running', ?)", (key, owner))
            except sqlite3.IntegrityError:
                row = db.execute("SELECT status FROM operations WHERE key=?", (key,)).fetchone()
                raise ValueError(f"Operation already {row[0]}; do not repeat completed work. Recover interrupted work explicitly.")
        try:
            yield
        except BaseException:
            with self.db() as db:
                db.execute("DELETE FROM operations WHERE key=? AND owner=?", (key, owner))
            raise
        else:
            with self.db() as db:
                db.execute("UPDATE operations SET status='done' WHERE key=? AND owner=?", (key, owner))

    def recover(self, dataset_id):
        # Explicit operator recovery only: automatic reclamation could race another browser.
        with self.db() as db:
            db.execute("DELETE FROM operations WHERE key LIKE ? AND status='running'", (dataset_id + ":%",))
        dataset = self.get(dataset_id)
        if dataset["status"] == "indexing":
            dataset["status"] = "index_failed"
            self.save(dataset)
        self.log(dataset_id, "recovery", {"action": "released interrupted claims"})

    @contextmanager
    def lock(self, dataset_id):
        key = dataset_id + ":lock"
        with self.db() as db:
            try:
                db.execute("INSERT INTO operations VALUES (?, 'running', '')", (key,))
            except sqlite3.IntegrityError:
                raise ValueError("This dataset has an operation in progress. Wait or explicitly recover after its process stops.")
        try:
            yield
        finally:
            with self.db() as db:
                db.execute("DELETE FROM operations WHERE key=?", (key,))

    def add_draft(self, dataset, revision, body, pending):
        draft_id = uuid.uuid4().hex
        with self.db() as db:
            db.execute("INSERT INTO drafts VALUES (?,?,?,?,?)", (draft_id, dataset, revision,
                       "pending" if pending else "approved", canonical(body)))
        return draft_id

    def drafts(self, dataset):
        with self.db() as db:
            return [dict(r, body=json.loads(r["body"])) for r in db.execute(
                "SELECT * FROM drafts WHERE dataset=? ORDER BY rowid", (dataset,))]

    def decide(self, draft_id, action, edited, active_revision):
        with self.db() as db:
            row = db.execute("SELECT dataset FROM drafts WHERE id=?", (draft_id,)).fetchone()
        if not row:
            raise ValueError("Unknown draft")
        with self.lock(row[0]):
            if self.get(row[0])["active_revision"] != active_revision:
                raise ValueError("Dataset revision changed; refresh before reviewing")
            self._decide(draft_id, action, edited, active_revision)

    def _decide(self, draft_id, action, edited, active_revision):
        if action not in {"approved", "rejected"}:
            raise ValueError("Invalid review decision")
        with self.db() as db:
            row = db.execute("SELECT * FROM drafts WHERE id=?", (draft_id,)).fetchone()
            if not row or row["status"] != "pending" or row["revision"] != active_revision:
                raise ValueError("Draft is no longer pending for the active revision")
            body = json.loads(row["body"])
            if action == "approved":
                from .chat import validate_citations
                validate_citations(edited, body["evidence"], body["insufficient"])
            body["published"] = edited
            body["human_edited"] = edited != body["answer"]
            db.execute("UPDATE drafts SET status=?,body=? WHERE id=?", (action, canonical(body), draft_id))
        self.log(row["dataset"], "answer_review", {"draft": draft_id, "decision": action, "text": edited})
