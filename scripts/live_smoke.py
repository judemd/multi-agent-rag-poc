"""Explicitly authorized, bounded live integration test. Never used by normal UI."""
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from reportlab.pdfgen import canvas
from rag_poc.agents import Agents
from rag_poc.config import Config
from rag_poc.embeddings import VertexEmbeddings
from rag_poc.preparation import Settings
from rag_poc.state import Store
from rag_poc.vector_store import Vectors
from rag_poc.workflow import Workflow
from rag_poc.chat import validate_citations


def main():
    # Enable this process only; leave normal application configuration unchanged.
    config = Config(root=Path("data/live-smoke"), enabled=True)
    store = Store(config.root)
    workflow = Workflow(store, config, Agents(config, store), VertexEmbeddings(config), Vectors(config.root))
    pdf_bytes = io.BytesIO()
    pdf = canvas.Canvas(pdf_bytes, invariant=1)
    pdf.drawString(50, 790, "Beacon 1 manual. Product ID P001.")
    pdf.drawString(50, 765, "Reset: hold the power button for 10 seconds.")
    pdf.save()
    files = {
        "tickets.csv": b"ticket_id,product_id,issue,resolved\nT001,P001,Reset request,true\n",
        "products.json": b'[{"product_id":"P001","name":"Beacon 1","battery_hours":9,"available":true}]',
        "policy.txt": b"Policy POL-RET: Unused Beacon products can be returned within 30 days of delivery with an order receipt.",
        "manual.pdf": pdf_bytes.getvalue(),
    }
    dataset = workflow.create(files, "Authorized minimal live integration test")
    report = {"dataset_id": dataset, "model": config.model, "embedding_model": config.embedding_model,
              "generation_location": config.location, "embedding_location": config.embedding_location,
              "checks": [], "status": "running"}
    path = config.root / "report.json"

    def checkpoint(check):
        report["checks"].append(check)
        path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(check), flush=True)

    try:
        checkpoint({"stage": "four_format_parsing", "records": len(store.get(dataset)["records"])})
        if store.get(dataset)["status"] == "uploaded":
            workflow.propose(dataset)
        d = store.get(dataset)
        checkpoint({"stage": "vertex_planning", "settings": d["settings"], "rationale": d["plan"]["rationale"]})
        # Test-harness decisions are logged explicitly; do not impersonate a human reviewer.
        if d["status"] == "review_plan":
            if d["settings"] != Settings().model_dump():
                workflow.change_settings(dataset, Settings().model_dump())
            store.log(dataset, "live_test_harness_decision", {"gate": 1, "basis": "user-authorized bounded integration test; conservative default settings"})
            workflow.approve_plan(dataset)
        if store.get(dataset)["status"] == "plan_approved":
            workflow.prepare(dataset)
        d = store.get(dataset)
        assert 1 <= len(d["chunks"]) <= 12, "Live-test chunk budget exceeded"
        checkpoint({"stage": "preparation", "chunks": len(d["chunks"])})
        if d["status"] == "review_chunks":
            store.log(dataset, "live_test_harness_decision", {"gate": 2, "basis": "user-authorized integration test; four tiny source chunks"})
            workflow.approve_chunks(dataset)
        if store.get(dataset)["status"] != "ready":
            workflow.index(dataset)
        checkpoint({"stage": "vertex_embedding_chroma_index", "status": store.get(dataset)["status"]})
        questions = [("supported", "What is the return window for unused Beacon products?"),
                     ("unsupported", "What is the CEO's private telephone number?")]
        existing = {draft["body"]["question"]: draft for draft in store.drafts(dataset)}
        for label, question in questions:
            if question not in existing:
                workflow.ask(dataset, question, always=True)
            draft = next(x for x in store.drafts(dataset) if x["body"]["question"] == question)
            body = draft["body"]
            validate_citations(body["answer"], body["evidence"], body["insufficient"])
            assert draft["status"] == "pending", "Always-review did not retain a pending draft"
            assert all(e["metadata"]["dataset_id"] == dataset for e in body["evidence"])
            if label == "supported":
                assert not body["insufficient"] and "30" in body["answer"], "Supported answer did not match expected policy"
            else:
                assert body["insufficient"], "Unsupported answer failed to abstain"
            checkpoint({"stage": label + "_question", "answer": body["answer"], "insufficient": body["insufficient"],
                        "citations": body["citations"], "review_status": draft["status"],
                        "sources": [e["metadata"]["filename"] for e in body["evidence"]]})
        report["status"] = "passed"
    except Exception as exc:
        # Provider errors can contain request metadata; report only type/status, never credentials.
        report["status"] = "failed"
        report["error"] = {"type": type(exc).__name__, "code": str(getattr(exc, "code", ""))}
        print(json.dumps({"error": report["error"]}), flush=True)
    finally:
        path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Report: {path}; result: {report['status']}", flush=True)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
