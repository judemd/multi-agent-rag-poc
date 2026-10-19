import sys
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "src"))
import streamlit as st
from rag_poc.config import Config
from rag_poc.state import Store
from rag_poc.workflow import Workflow
from rag_poc.agents import Agents
from rag_poc.embeddings import VertexEmbeddings
from rag_poc.vector_store import Vectors
from rag_poc.synthetic import generate
from rag_poc.errors import error_details
from google.genai.errors import APIError

st.set_page_config(page_title="Beacon Support RAG", layout="wide")
config = Config()
store = Store(config.root)

def workflow():
    return Workflow(store, config, Agents(config, store), VertexEmbeddings(config), Vectors(config.root))

def action(label, function, *args):
    try:
        with st.spinner(label):
            function(*args)
        st.rerun()
    except Exception as exc:
        if isinstance(exc, APIError):
            st.error(error_details(exc)["message"])
        elif isinstance(exc, ValueError):
            st.error(str(exc))
        else:
            st.error(f"Operation failed ({type(exc).__name__}). Check configuration and connectivity. Your progress is saved.")

def create_dataset(files, name):
    selected = workflow().create(files, name)
    st.session_state["next_dataset"] = selected

def start_over():
    for key in list(st.session_state):
        del st.session_state[key]
    st.session_state["show_landing"] = True

def request_start_over():
    st.session_state["confirm_start_over"] = True

def cancel_start_over():
    st.session_state.pop("confirm_start_over", None)

def evidence_panel(body, key):
    cited = set(body.get("citations", []))
    with st.expander("Check the source evidence", expanded=False):
        st.caption("Cited sources are marked below. Distance measures retrieval similarity; it is not a confidence probability.")
        for e in body["evidence"]:
            meta = e["metadata"]
            st.markdown(f"**[{e['citation']}] {meta['filename']}** — {meta['reference']}" + (" · Cited" if e["citation"] in cited else ""))
            st.text(e["text"])
            st.caption(f"Cosine distance: {e['distance']:.3f} · Chunk: {meta['chunk_id'][:12]} · Dataset: {meta['dataset_id'][:8]}")

heading, navigation = st.columns([5, 1])
with heading:
    st.title("Beacon Support")
with navigation:
    st.button("Start over", on_click=request_start_over, width="stretch")
if st.session_state.get("confirm_start_over"):
    with st.container(border=True):
        st.write("Return to the landing page? Current inputs will be cleared. Saved datasets and progress will remain available.")
        confirm, cancel = st.columns(2)
        confirm.button("Confirm start over", type="primary", on_click=start_over, width="stretch")
        cancel.button("Cancel", on_click=cancel_start_over, width="stretch")
st.write("Turn support files into answers you can check and approve.")

datasets = store.list()
if "next_dataset" in st.session_state:
    st.session_state["selected_dataset"] = st.session_state.pop("next_dataset")
    st.session_state["show_landing"] = False
selected = None
with st.sidebar:
    st.header("Your datasets")
    if datasets:
        ids = [d["id"] for d in datasets]
        if st.session_state.get("selected_dataset") not in ids and not st.session_state.get("show_landing"):
            st.session_state["selected_dataset"] = ids[0]
        selected = st.selectbox("Working dataset", ids, key="selected_dataset",
            index=None, placeholder="Choose a saved dataset",
            format_func=lambda value: next(d["name"] for d in datasets if d["id"] == value))
    st.divider()
    st.subheader("Start a new dataset")
    st.caption("For your first walkthrough, choose Generate demo dataset.")
    name = st.text_input("Dataset name", "Beacon support demo")
    with st.expander("Demo options"):
        seed = st.number_input("Synthetic seed", value=42, min_value=0, step=1)
    if st.button("Generate demo dataset", type="primary" if not datasets else "secondary", width="stretch"):
        files, _ = generate(seed)
        action("Creating your demo dataset", create_dataset, files, name)
    with st.expander("Upload your own files"):
        uploads = st.file_uploader("CSV, JSON, TXT or text PDF", type=["csv", "json", "txt", "pdf"], accept_multiple_files=True)
        st.caption("Up to 20 files · 5 MB each · 25 MB total. Scanned PDFs are unsupported.")
        if st.button("Import uploads", disabled=not uploads):
            if len({f.name for f in uploads}) != len(uploads):
                st.error("Each file needs a unique filename.")
            else:
                action("Checking your files", create_dataset, {f.name: f.getvalue() for f in uploads}, name)
    st.divider()
    st.caption("Live AI: enabled" if config.enabled else "Live AI: paused · no paid calls")

if selected is None:
    st.subheader("Start here")
    st.info("Choose **Generate demo dataset** in the left sidebar. It creates linked tickets, products, policies and manuals on your laptop.")
    st.markdown("1. **Add files** — inspect what you uploaded.\n2. **Review the plan** — approve how files will be prepared.\n3. **Review text samples** — approve what the AI will search.\n4. **Build the search index** — create searchable embeddings.\n5. **Ask and review** — check sources before publishing an answer.")
    st.caption("Your progress and approvals are saved automatically between visits.")
    st.stop()

try:
    workflow().refresh_configuration(selected)
except ValueError:
    pass
d = store.get(selected)
drafts = store.drafts(selected)
pending = [x for x in drafts if x["status"] == "pending" and x["revision"] == d["active_revision"]]
approved = [x for x in drafts if x["status"] == "approved" and x["revision"] == d["active_revision"]]
stage = {"uploaded": 1, "review_plan": 2, "plan_approved": 2, "review_chunks": 3,
         "index_approved": 4, "index_failed": 4, "indexing": 4, "ready": 5}.get(d["status"], 1)
st.subheader(d["name"])
for i, (column, label) in enumerate(zip(st.columns(5), ["Add files", "Review plan", "Review samples", "Build index", "Ask & review"]), 1):
    with column:
        st.markdown(f"{'✓' if i < stage else '→' if i == stage else '○'} **{i}. {label}**")
st.progress((stage - 1) / 4)

titles = {
    "uploaded": ("Next: ask the agents for a preparation plan", "First inspect your files below. The agents will suggest settings; nothing is indexed until you approve both reviews."),
    "review_plan": ("Your review: approve the preparation plan", "Check the proposal below. Keep the recommended settings for a first walkthrough, or open Change settings."),
    "plan_approved": ("Next: create text samples", "Your plan is approved. Prepare the files to see exactly what will become searchable."),
    "review_chunks": ("Your review: inspect the text samples", "Check that the extracted text and source references look correct. Approval allows these samples to be indexed."),
    "index_approved": ("Next: build your searchable index", "Both reviews are complete. This step uses Vertex embeddings and may incur charges."),
    "index_failed": ("Indexing needs another attempt", "The dataset is not ready for chat. Your approvals are saved; retry after checking the connection and configuration."),
    "indexing": ("Building your search index", "Each completed section is saved immediately. Wait for indexing to finish; refresh to see the saved count."),
    "ready": (f"Your review: {len(pending)} answer{'s' if len(pending) != 1 else ''} waiting" if pending else "Ready: ask a question", "Review the waiting answers below. Approve to publish them in the conversation, edit them first, or reject." if pending else "Ask a question about this dataset. Answers with review enabled wait for your approval before appearing in the conversation."),
    "cancelled": ("This workflow was cancelled", "Choose another dataset or start a new one from the sidebar."),
}
title, description = titles[d["status"]]
st.info(f"**{title}**\n\n{description}")
if not config.enabled:
    if d["status"] == "ready":
        st.caption("Live AI is paused. You can inspect sources and approve or reject existing answers without making new paid calls.")
    else:
        st.warning("Live AI is paused. You can inspect files and saved reviews. Agent planning and indexing need live AI enabled before you can finish this walkthrough.")
    with st.expander("How to enable live AI"):
        st.write("After authorizing paid use, restart the app from PowerShell with:")
        st.code("$env:ENABLE_VERTEX_CALLS='true'\n.\\.venv\\Scripts\\python.exe -m streamlit run app.py", language="powershell")
        st.caption("This setting permits billable Vertex calls. Existing review cards work while it is off.")

work, sources, activity = st.tabs(["Walkthrough", "Files & previews", "Activity & troubleshooting"])
with work:
    if d["status"] == "uploaded":
        st.subheader("1. Your files are loaded")
        a, b, c = st.columns(3)
        a.metric("Files", len(d["manifest"]))
        b.metric("Records / text sections", d["profile"]["records"])
        c.metric("Duplicate records", d["profile"]["duplicate_records"])
        st.write("Open **Files & previews** to inspect the content, then request the agents’ proposal.")
        if st.button("Create preparation plan", type="primary", disabled=not config.enabled):
            action("Agents are examining your files and proposing a plan", workflow().propose, selected)

    if d["plan"] and d["status"] != "cancelled":
        with st.expander("2. Preparation plan" + (" · approved" if d["gate1"] else " · needs your review"), expanded=stage == 2):
            st.write(d["plan"]["rationale"])
            s = d["settings"]
            st.write(f"Split long text into sections of about **{s['chunk_size']:,} characters**, with **{s['overlap']} characters** repeated between sections to preserve context.")
            st.write("Duplicate records: **remove and log**" if s["remove_duplicates"] else "Duplicate records: **keep**. Missing values are preserved.")
            st.caption("Original files are always kept intact. Settings affect derived text only.")
            with st.expander("Change settings or exclude files"):
                st.warning("Saving different settings resets affected approvals and turns off chat until the new version is indexed.")
                with st.form("settings_" + selected):
                    size = st.number_input("Text section size (characters)", 200, 4000, s["chunk_size"])
                    overlap = st.number_input("Repeated context between sections (characters)", 0, 1000, s["overlap"])
                    trim = st.checkbox("Trim whitespace in derived text", s["trim_whitespace"])
                    dedup = st.checkbox("Remove duplicate derived records and log removals", s["remove_duplicates"])
                    excluded = st.multiselect("Exclude files", list(d["manifest"]), default=s["excluded_files"])
                    if st.form_submit_button("Save settings and return to plan review"):
                        action("Saving your changes", workflow().change_settings, selected,
                            dict(chunk_size=size, overlap=overlap, trim_whitespace=trim, remove_duplicates=dedup, excluded_files=excluded))
            if d["status"] == "review_plan" and st.button("Approve plan", type="primary"):
                action("Saving your approval", workflow().approve_plan, selected)
            if d["status"] == "plan_approved" and st.button("Create text samples", type="primary"):
                action("Creating text samples from your approved plan", workflow().prepare, selected)

    if d["chunks"]:
        with st.expander("3. Text samples" + (" · approved" if d["gate2"] else " · needs your review"), expanded=stage == 3):
            st.write(f"**{len(d['chunks'])} searchable text sections** created. Check a few sections and their source locations before approving.")
            for chunk in d["chunks"][:5]:
                with st.container(border=True):
                    st.markdown(f"**{chunk['metadata']['filename']}** · {chunk['metadata']['reference']}")
                    st.text(chunk["text"])
            st.caption("Showing up to five samples. To change how text is split, reopen Preparation plan → Change settings.")
            if d["status"] == "review_chunks" and st.button("Approve samples", type="primary"):
                action("Saving your approval of the text samples", workflow().approve_chunks, selected)
    if d["status"] in {"index_approved", "index_failed", "indexing"}:
        st.subheader("4. Build the search index")
        if d.get("index_error"):
            st.error(d["index_error"]["message"])
        if d.get("indexed_chunks"):
            st.caption(f"{d['indexed_chunks']} of {len(d['chunks'])} sections are already saved. Retry resumes the remaining sections.")
        st.write(f"Create embeddings for {len(d['chunks'])} approved sections and save them in Chroma. Chat unlocks only after the complete index is verified.")
        if st.button("Build search index", type="primary", disabled=not config.enabled or d["status"] == "indexing"):
            progress = st.progress(0, text="Checking saved progress…")
            def index_selected():
                workflow().index(selected, on_progress=lambda done, total: progress.progress(done / total,
                    text=f"Saved {done} of {total} searchable sections"))
            action("Building and verifying your search index", index_selected)

    if d["status"] == "ready":
        st.subheader("5. Ask about your dataset")
        st.caption("Try: What is the return window for unused Beacon products? Or: How do I reset Beacon 1?")
        always = st.checkbox("Always review answers", value=True, help="New answers wait just above the question box for approval. Turning this off still keeps answers with review triggers pending.")
        if not approved:
            st.write("No published answers yet. After you approve a draft, the question and answer will appear here.")
        for draft in approved:
            body = draft["body"]
            with st.chat_message("user"):
                st.text(body["question"])
            with st.chat_message("assistant"):
                st.text(body["published"])
                if body["human_edited"]:
                    st.caption("Edited by reviewer. Sources retained; edits are not automatically fact-checked.")
                evidence_panel(body, draft["id"])
        if pending:
            st.subheader("Review answers before publishing")
            for draft in pending:
                body = draft["body"]
                with st.container(border=True):
                    st.markdown("**Question**")
                    st.text(body["question"])
                    st.caption("Waiting for your decision · " + "; ".join(body["reasons"]))
                    edited = st.text_area("Answer — edit here if needed", body["answer"], key=draft["id"])
                    evidence_panel(body, draft["id"])
                    left, right = st.columns(2)
                    if left.button("Publish answer", key="approve_" + draft["id"], type="primary"):
                        action("Publishing your reviewed answer", store.decide, draft["id"], "approved", edited, d["active_revision"])
                    if right.button("Reject answer", key="reject_" + draft["id"]):
                        action("Rejecting this draft without retrying", store.decide, draft["id"], "rejected", edited, d["active_revision"])
    else:
        always = True
    question = st.chat_input("Ask a question about these files", disabled=d["status"] != "ready" or not config.enabled)
    if question:
        action("Searching your files and drafting an answer", workflow().ask, selected, question, always)
    if d["status"] not in {"cancelled", "ready"}:
        with st.expander("Cancel this workflow"):
            st.caption("Cancelling clears approvals. Your original files remain saved.")
            if st.button("Cancel ingestion"):
                action("Cancelling this workflow", workflow().cancel, selected)

with sources:
    st.subheader("Files in this dataset")
    st.dataframe([{"File": filename, "Records / sections": sum(r["filename"] == filename for r in d["records"]),
                   "Included": filename not in d["settings"]["excluded_files"]} for filename in d["manifest"]], hide_index=True, width="stretch")
    for filename in d["manifest"]:
        with st.expander(filename):
            for record in [r for r in d["records"] if r["filename"] == filename][:3]:
                st.caption(record["ref"])
                st.text(record["text"][:3000])
            source = config.root / "sources" / selected / filename
            st.download_button("Download original", source.read_bytes(), file_name=filename, key="download_" + filename)
    with st.expander("Detailed data profile"):
        st.json(d["profile"])
    with st.expander("Demo reference questions"):
        st.caption("These are expectations for the generated demo, not evidence added to your search index. Uploaded datasets may have different answers.")
        for reference in generate(seed)[1]:
            st.write("**" + reference["question"] + "**")
            st.caption("Expected: " + reference["expected"] + " · Sources: " + (", ".join(reference["sources"]) or "none"))

with activity:
    st.subheader("What actually ran")
    st.caption("Agent decisions and deterministic Python operations are recorded separately. During a long operation, refresh this tab in another browser window to see saved progress.")
    events = store.events(selected)
    for event in events[:25]:
        details = json.loads(event["body"])
        with st.expander(event["kind"].replace("_", " ").capitalize() + " · " + event["at"][11:19]):
            st.json(details)
    if st.button("Refresh activity"):
        st.rerun()
    with st.expander("Advanced: recover interrupted work"):
        st.warning("Only use this after the previous process has stopped. Releasing an active operation can allow duplicate work.")
        if st.button("Recover interrupted operation"):
            action("Releasing interrupted claims", store.recover, selected)
