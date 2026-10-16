"""Offline integration tests: deterministic doubles explicitly replace Vertex only."""
from dataclasses import replace
import pytest
from rag_poc.config import Config
from rag_poc.state import Store
from rag_poc.workflow import Workflow
from rag_poc.preparation import Settings
from rag_poc.synthetic import generate
from rag_poc.parsing import parse_file
from rag_poc.vector_store import Vectors
from rag_poc.chat import validate_citations

class OfflineEmbeddings:
    fail = False
    calls = 0
    def embed(self, texts, query=False):
        self.calls += 1
        if self.fail:
            raise RuntimeError("Injected offline failure")
        return [[1.0, 0.0, 0.0] for _ in texts]

class OfflineAgents:
    empty = False
    invalid = False
    def propose(self, dataset, report):
        return {"rationale": "Offline deterministic test plan", "settings": Settings().model_dump()}
    def answer(self, dataset, question, search):
        evidence = [] if self.empty else search(question)
        if self.empty:
            return {"answer": "I couldn't find details about that in these files, so I can't answer reliably.",
                    "insufficient": True, "conflict": False, "citations": []}, evidence
        return {"answer": "Return within 30 days [S99]" if self.invalid else "Return within 30 days [S1]",
                "insufficient": False, "conflict": False, "citations": ["S99" if self.invalid else "S1"]}, evidence

@pytest.fixture
def app(tmp_path):
    config = Config(root=tmp_path)
    store = Store(tmp_path)
    w = Workflow(store, config, OfflineAgents(), OfflineEmbeddings(), Vectors(tmp_path))
    dataset = w.create({"policy.txt": b"Unused products may be returned within 30 days."})
    return w, dataset

def ready(w, dataset):
    w.propose(dataset)
    w.approve_plan(dataset)
    w.prepare(dataset)
    w.approve_chunks(dataset)
    w.index(dataset)

def test_gates_restart_and_duplicate_prevention(app):
    w, dataset = app
    with pytest.raises(ValueError, match="Gate 1"):
        w.prepare(dataset)
    with pytest.raises(ValueError, match="Both approvals"):
        w.index(dataset)
    with pytest.raises(ValueError, match="successfully indexed"):
        w.ask(dataset, "returns?")
    w.propose(dataset)
    w.approve_plan(dataset)
    w.store = Store(w.config.root)  # Simulated process restart
    w.prepare(dataset)
    with pytest.raises(ValueError):
        w.index(dataset)
    w.approve_chunks(dataset)
    w.store = Store(w.config.root)
    w.index(dataset)
    calls = w.embeddings.calls
    with pytest.raises(ValueError, match="already done"):
        w.index(dataset)
    assert w.embeddings.calls == calls
    assert w.vectors.collection(w.store.get(dataset)["active_revision"]).count() == 1

def test_settings_invalidate_and_stale_chunks(app):
    w, dataset = app
    ready(w, dataset)
    old = w.store.get(dataset)["active_revision"]
    settings = Settings(chunk_size=250, overlap=20).model_dump()
    w.change_settings(dataset, settings)
    d = w.store.get(dataset)
    assert d["gate1"] is None and d["gate2"] is None and d["active_revision"] is None
    with pytest.raises(ValueError):
        w.index(dataset)
    w.approve_plan(dataset)
    w.prepare(dataset)
    w.approve_chunks(dataset)
    w.index(dataset)
    assert w.store.get(dataset)["active_revision"] != old
    assert w.vectors.collection(w.store.get(dataset)["active_revision"]).count() == 1

def test_failure_and_retry(app):
    w, dataset = app
    w.propose(dataset); w.approve_plan(dataset); w.prepare(dataset); w.approve_chunks(dataset)
    w.embeddings.fail = True
    with pytest.raises(RuntimeError):
        w.index(dataset)
    assert w.store.get(dataset)["status"] == "index_failed"
    assert w.store.get(dataset)["active_revision"] is None
    w.embeddings.fail = False
    w.index(dataset)
    assert w.store.get(dataset)["status"] == "ready"

def test_dataset_isolation_and_answer_review(app):
    w, dataset = app
    ready(w, dataset)
    other = w.create({"secret.txt": b"Other dataset secret"})
    ready(w, other)
    draft_id = w.ask(dataset, "return policy", always=True)
    draft = w.store.drafts(dataset)[0]
    assert draft["status"] == "pending"
    assert all(e["metadata"]["dataset_id"] == dataset for e in draft["body"]["evidence"])
    revision = w.store.get(dataset)["active_revision"]
    with pytest.raises(ValueError, match="unknown citation"):
        w.store.decide(draft_id, "approved", "Edited [S999]", revision)
    w.store.decide(draft_id, "approved", "Human edited: 30 days [S1]", revision)
    assert w.store.drafts(dataset)[0]["body"]["human_edited"]
    second = w.ask(dataset, "return policy")
    w.store.decide(second, "rejected", "Rejected", revision)
    assert len(w.store.drafts(dataset)) == 2  # no automatic retry

def test_insufficient_and_invalid_citations(app):
    w, dataset = app
    ready(w, dataset)
    w.agents.empty = True
    w.ask(dataset, "unknown", always=False)
    body = w.store.drafts(dataset)[0]["body"]
    assert body["insufficient"] and body["answer"] == "I couldn't find details about that in these files, so I can't answer reliably."
    w.agents.empty = False
    w.agents.invalid = True
    w.ask(dataset, "returns", always=False)
    assert w.store.drafts(dataset)[-1]["status"] == "pending"

def test_no_evidence_asserted_answer_is_blocked(app):
    w, dataset = app
    ready(w, dataset)
    w.agents.answer = lambda *args: ({"answer": "Invented answer", "insufficient": False,
                                     "conflict": False, "citations": []}, [])
    with pytest.raises(ValueError, match="missing evidence"):
        w.ask(dataset, "unknown")
    assert not w.store.drafts(dataset)

def test_input_hash_and_original_preservation(app):
    w, dataset = app
    content = b"Unused products may be returned within 30 days."
    assert w.create({"policy.txt": content}) == dataset
    other = w.create({"policy.txt": content + b" Changed."})
    assert other != dataset and w.store.get(other)["gate1"] is None
    assert (w.config.root / "sources" / dataset / "policy.txt").read_bytes() == content

def test_synthetic_formats_and_reproducibility():
    first, references = generate()
    second, _ = generate()
    assert first == second
    records = [r for name, content in first.items() for r in parse_file(name, content)]
    assert len(records) == 118
    assert len(references) == 5
    assert any("page" in r["ref"] for r in records)
    assert any(r["values"] and "specs" in r["values"] for r in records)

@pytest.mark.parametrize("name,content", [("x.exe", b"hello"), ("x.json", b'{"a":1,"a":2}'),
    ("x.csv", b"a,b\n1,2,3"), ("x.txt", b"\xff"), ("x.pdf", b"invalid"), ("x.json", b"[1,2]")])
def test_malformed(name, content):
    with pytest.raises(ValueError):
        parse_file(name, content)

def test_interrupted_claim_and_recovery(app):
    w, dataset = app
    with w.store.db() as db:
        db.execute("INSERT INTO operations VALUES (?, 'running', 'dead-process')", (dataset + ":lock",))
    with pytest.raises(ValueError, match="operation in progress"):
        w.propose(dataset)
    w.store.recover(dataset)
    w.propose(dataset)
    assert w.store.get(dataset)["plan"]

def test_live_guard(app):
    from rag_poc.embeddings import VertexEmbeddings
    w, _ = app
    with pytest.raises(ValueError, match="disabled"):
        VertexEmbeddings(replace(w.config, enabled=False)).embed(["no paid call"])

def test_aggregation_review(app):
    w, dataset = app
    ready(w, dataset)
    w.ask(dataset, "What is the total?", always=False)
    assert any("aggregation" in reason for reason in w.store.drafts(dataset)[0]["body"]["reasons"])

def test_embedding_configuration_invalidates_index_approval(app):
    w, dataset = app
    w.propose(dataset); w.approve_plan(dataset); w.prepare(dataset); w.approve_chunks(dataset)
    w.config = replace(w.config, embedding_model="different-model")
    with pytest.raises(ValueError, match="Both approvals"):
        w.index(dataset)
    assert w.embeddings.calls == 0

def test_partial_index_never_becomes_active(app):
    w, _ = app
    dataset = w.create({"long.txt": ("A useful support policy paragraph. " * 1200).encode()})
    w.propose(dataset); w.approve_plan(dataset); w.prepare(dataset); w.approve_chunks(dataset)
    embed = w.embeddings.embed
    batches = 0
    def fail_second(texts, query=False):
        nonlocal batches
        batches += 1
        if batches == 2:
            raise RuntimeError("Injected second-batch failure")
        return embed(texts, query)
    w.embeddings.embed = fail_second
    with pytest.raises(RuntimeError):
        w.index(dataset)
    d = w.store.get(dataset)
    assert w.vectors.collection(d["revision"]).count() == 1
    assert d["active_revision"] is None
    w.store = Store(w.config.root)
    w.embeddings.embed = embed
    w.index(dataset)
    d = w.store.get(dataset)
    assert w.vectors.collection(d["revision"]).count() == len(d["chunks"])
    assert w.embeddings.calls == len(d["chunks"])  # Already-saved chunk was not embedded again.

def test_old_draft_cannot_publish_after_settings_change(app):
    w, dataset = app
    ready(w, dataset)
    draft = w.ask(dataset, "returns?")
    old = w.store.get(dataset)["active_revision"]
    w.change_settings(dataset, Settings(chunk_size=500).model_dump())
    with pytest.raises(ValueError, match="revision changed"):
        w.store.decide(draft, "approved", "30 days [S1]", old)

def test_cancel_blocks_remaining_stages(app):
    w, dataset = app
    w.propose(dataset); w.approve_plan(dataset)
    w.cancel(dataset)
    with pytest.raises(ValueError):
        w.prepare(dataset)
    with pytest.raises(ValueError):
        w.approve_chunks(dataset)

def test_embedding_change_blocks_existing_chat_and_resets_gate2(app):
    w, dataset = app
    ready(w, dataset)
    w.config = replace(w.config, embedding_model="new-embedding-model")
    with pytest.raises(ValueError, match="configuration changed"):
        w.ask(dataset, "returns?")
    w.refresh_configuration(dataset)
    d = w.store.get(dataset)
    assert d["status"] == "review_chunks" and d["gate2"] is None
    assert d["gate1"] and not d["active_revision"]

def test_index_error_is_saved_safely_with_resume_progress(app):
    from google.genai.errors import ClientError
    from rag_poc.errors import ProviderFailure
    w, dataset = app
    w.propose(dataset); w.approve_plan(dataset); w.prepare(dataset); w.approve_chunks(dataset)
    def fail(texts, query=False):
        raise ProviderFailure(ClientError(429, {"error": {"message": "secret provider detail"}}))
    w.embeddings.embed = fail
    with pytest.raises(ProviderFailure):
        w.index(dataset)
    d = w.store.get(dataset)
    assert d["status"] == "index_failed" and d["index_error"]["http_code"] == 429
    assert "secret" not in str(d["index_error"])
    assert d["gate1"] and d["gate2"] and not d["active_revision"]

def test_indexing_status_progress_and_interruption_recovery(app):
    w, dataset = app
    w.propose(dataset); w.approve_plan(dataset); w.prepare(dataset); w.approve_chunks(dataset)
    observed = []
    w.index(dataset, on_progress=lambda done, total: observed.append((done, total, w.store.get(dataset)["status"])))
    assert observed[0] == (0, 1, "indexing")
    assert observed[-1] == (1, 1, "indexing")
    assert w.store.get(dataset)["status"] == "ready"
    d = w.store.get(dataset)
    d.update(status="indexing", active_revision=None)
    w.store.save(d)
    w.store.recover(dataset)
    assert w.store.get(dataset)["status"] == "index_failed"
