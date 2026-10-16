# Beacon Support RAG POC

A single-page Streamlit customer-support demo with four real Google ADK agents,
Vertex AI Gemini and embeddings, durable local approvals, and local or external Chroma.
Normal operation never substitutes fake model answers. Paid calls are disabled by default.

## PowerShell setup

Run from `C:\Users\User\multi-agent-rag-poc`. Use Python 3.11 explicitly; the system
`python` may resolve to a different version.

```powershell
# Existing .venv is supported. For a fresh checkout only:
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
Copy-Item .env.example .env
gcloud config get-value project
# Only if ADC is not already configured:
gcloud auth application-default login
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Open http://localhost:8501. Keep `.env`, ADC and `data/` out of Git. Do not copy
credential JSON into this project or container. `requirements.lock` pins all installed
dependencies, including offline test tooling. It was resolved on Windows Python 3.11;
Linux/container installation still requires validation. To regenerate after an intentional
dependency change: install the direct versions in `pyproject.toml`, run tests and
`pip check`, then write `python -m pip freeze` to the lock file using ASCII/UTF-8.

## Configuration

| Variable | Default / purpose |
|---|---|
| `GOOGLE_CLOUD_PROJECT` | `project-d4ec743e-de8a-4ed5-b45`; set to your project |
| `GEMINI_MODEL` | `gemini-3.8-flash` |
| `GOOGLE_CLOUD_LOCATION` | `global` for generation |
| `EMBEDDING_MODEL` | `gemini-embedding-001` |
| `EMBEDDING_LOCATION` | `us-central1` |
| `ENABLE_VERTEX_CALLS` | `false`; change only after approving a paid live test |
| `DATA_DIR` | `data`; SQLite, originals and local vectors |
| `REVIEW_DISTANCE` | `0.45`; heuristic cosine-distance review threshold |
| `CHROMA_HOST` | Empty means local persistence; set for external HTTP Chroma |
| `CHROMA_PORT`, `CHROMA_SSL` | `8000`, `false`; use TLS for remote connections |
| `CHROMA_AUTH_HEADER`, `CHROMA_AUTH_TOKEN` | Optional external authentication header; never commit token |

ADC, Vertex API enablement, billing, quotas, `roles/aiplatform.user` or equivalent
permissions, model availability and network access are required for live use. The code
constructs Vertex clients explicitly. Generation and embedding locations are separate;
the defaults do not promise UK/EU data residency. There is no automatic model fallback.
Model IDs are environment configurable; switching embedding models requires preparation
and indexing review again. Existing approvals are checked against the embedding signature.

## Architecture and HITL

`app.py` renders all controls. `workflow.py` owns transitions. `state.py` stores workflow
records, immutable decision events, drafts and operation claims in SQLite. `agents.py`
uses ADK Runner, sequential agents and SQLite ADK sessions. `parsing.py`,
`preparation.py`, `embeddings.py` and `vector_store.py` implement deterministic tools.

1. Upload CSV, JSON, TXT and text PDFs, or generate seeded fixtures.
2. Python parses and profiles sources. Originals remain byte-for-byte intact.
3. ADK profiling and preparation agents interpret the profile and propose settings.
4. **Gate 1:** approve, edit chunking/cleaning, exclude files, or cancel.
5. Python prepares derived chunks. Duplicate removal defaults off and logs removals.
6. **Gate 2:** inspect samples, approve indexing, request preparation changes, or cancel.
7. Vertex embeds; Chroma upserts; a complete ID manifest is verified before activation.
8. ADK retrieval and answer agents handle chat against the active dataset only.

HITL pauses are durable application checkpoints between completed ADK invocations.
Approval resumes the next bounded stage; it does not keep a model call open. This
deliberately avoids ADK tool-confirmation durability limitations. ADK session histories
are also saved locally, but application SQLite is the authority for approvals.
Development approval to build/run a paid test is separate from these in-app gates.

Streamlit reruns read SQLite; they do not automatically execute completed operations.
Atomic dataset claims serialize workflow actions across tabs. Operation keys prevent
repeat processing. Interrupted claims require explicit recovery **after the old process
stops**. Retry indexing is idempotent by stable chunk ID. Each successful embedding is
saved immediately; retries skip saved chunk IDs in the same revision. Indexing displays
live section counts and saves safe HTTP error codes with actionable guidance. Transient
HTTP 408/429/5xx responses have bounded exponential backoff (four total attempts,
10-second initial delay, capped at 30 seconds with jitter). Persistent quota/capacity
errors leave the dataset incomplete with approvals intact; there is no unbounded retry.
Do not repeatedly click Build search index while Google is rate-limiting the project.
A changed source upload becomes
a separate dataset; changed settings invalidate the current approvals and active index.
Changing back to old settings requires approval again. Old revision collections are
retained for inspection, consume disk, and are never searched as the current revision.
No automatic garbage collection is included.

Activity distinguishes agent decisions, agent tool requests and actual tool execution.
The page displays stage progress and saved batch counts. Operations run synchronously;
the initiating tab remains busy during a call. A second tab can refresh the durable event
log. Generated answer drafts are omitted from the public activity log until reviewed.
Each ADK invocation permits at most eight model calls. Retrieval performs one search per
question and passes the original evidence directly to the answer agent using ADK tool
state and skip-summarization. Duplicate tool requests reuse the saved evidence instead
of making additional embedding calls. Unsupported questions proceed to an abstention
answer rather than looping through repeated searches.

## Inputs and synthetic fixtures

Default seed `42`: 100 tickets (including an exact duplicate and unresolved records),
12 products with typed/nested JSON, three policy text files and three deterministic PDF
manuals. Product IDs link tickets, products and manuals. Policies have shared policy IDs.
Reference questions include expected answers and supporting filenames; these are displayed
separately and never indexed automatically. Do not upload the reference answer file as source.

```powershell
$env:PYTHONPATH = 'src'
.\.venv\Scripts\python.exe -m rag_poc.synthetic --seed 42 --output data/synthetic
```

Limits: 20 files, 5 MB each, 25 MB combined, 50 pages/PDF, 10,000 records/dataset,
2,000 chunks/revision. UTF-8 CSV/TXT/JSON only. JSON must be an object or array of objects;
duplicate keys, non-standard numeric constants and malformed CSV rows are rejected.
Encrypted or image-only PDF pages are rejected; OCR is excluded. PDF reading order and
table extraction are best effort. Source text is never executed. Prompt instructions
identify source content as untrusted; this is a demo boundary, not a prompt-injection proof.

CSV/JSON records, TXT paragraphs and PDF pages retain row/item/line/page provenance.
Long content splits near whitespace at 1,800 characters with 200-character overlap.
Embeddings use document/query task types, 768 dimensions and disabled auto-truncation;
oversized token inputs fail explicitly. No missing-value imputation occurs.

## Answers, citations and review

Retrieval uses five nearest chunks, a revision-specific collection and a dataset filter.
Cosine distance is a retrieval metric, not a confidence probability. The answer agent
must cite source IDs inline, for example `[S1]`. IDs are validated against actual tool
results; source excerpts, filename, dataset/chunk IDs and page/row references are expandable.
Citation existence checks cannot prove semantic entailment of each statement.

Always-review defaults on. With it off, no close retrieval match, insufficient evidence,
reported conflicts, malformed citations and aggregation requests still require review.
The distance threshold is an explainable heuristic, not a calibrated quality estimate.
When evidence is absent or insufficient, Gemini drafts a brief, considerate response in
its own words, tied to what is missing from the selected files. Python preserves that
wording and requires review; it does not replace the response with a fixed phrase. If
Gemini asserts an answer despite having no evidence, processing stops without publishing
or automatically retrying. Common exact-aggregation wording
is blocked deterministically; free-form language detection is incomplete.

Pending answers appear only in the reviewer panel. Approve, edit and publish, or reject.
Edits retain the original answer and immutable evidence mapping. Bad citation references
block publication; human edits are not automatically fact-checked. A draft from an old
revision cannot be published into the current chat. Rejection never retries automatically.
This is single-user workflow separation, not role-based reviewer authorization.

## Validation

Verified locally on October 16, 2026: **34 tests passed**, `pip check` passed, Python
compilation passed, synthetic CLI generation succeeded, and Streamlit health/page HTTP
checks returned 200. Tests include a complete UI gate-to-answer-review flow with offline
doubles. Docker image building was skipped because the daemon was unavailable. Live
Vertex calls were deferred during the offline build. Following separate user approval,
the minimal live test also passed on October 16, 2026: real Gemini planning, four Vertex
document embeddings, local Chroma indexing, a cited 30-day return answer, and abstention
for an unsupported private-phone-number question. Both answers remained pending review.
External Chroma, Docker building and Cloud Run remain unverified. No deployment or cloud
resource creation occurred.

The full 118-section manual demo subsequently reproduced a Vertex HTTP 429
(`RESOURCE_EXHAUSTED`). After adding per-section checkpointing, safe error reporting,
visible progress and bounded backoff, the resume reused saved sections and completed
all 118 sections. The active manifest was verified and the dataset became ready for chat.

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pip check
```

Tests exercise real local Chroma, SQLite, parsing, synthetic PDFs and Streamlit AppTest.
Explicit deterministic doubles replace Vertex inference/embeddings in tests only. The ADK
integration test uses real Runner, sequential orchestration, tool calls and SQLite sessions
with an offline model double. No network/paid inference is required. Test artifacts go under
ignored `data/`; pytest only clears its designated temporary test directory.

The pinned ADK currently emits a deprecation warning for `SequentialAgent` and an
experimental function-schema warning. Its sequential API remains functional in this pin;
future ADK upgrades require migration testing.

## Manual demo

The page has a five-step progress strip and a next-action message. Use the sidebar to
create or select datasets. **Walkthrough** contains the current action and review cards;
**Files & previews** contains readable source samples; **Activity & troubleshooting**
contains execution logs and recovery tools. Live AI status explains when a step is blocked.
New datasets are selected automatically. Pending answer reviews appear below the
published conversation, directly above the question box.

1. Launch with paid calls disabled; generate data and inspect previews/original downloads.
2. After separate live-test approval, set `ENABLE_VERTEX_CALLS=true` and restart.
3. Choose **Create preparation plan**, then **Approve plan**.
4. Choose **Create text samples**, inspect the source text, then **Approve samples**.
5. Choose **Build search index**. Ask the return-window question and inspect citations in the reviewer card.
6. Edit/approve the answer; verify it appears in chat. Reject another draft; verify no retry.
7. Restart the app and verify saved decisions. Change chunk size; verify approvals/chat reset.
8. Select a second dataset and check its chat retrieves only its own sources.

## Minimal live test — requires separate approval

The initial minimal test has now been separately authorized and passed. Its isolated,
ignored artifacts and result are under `data/live-smoke/`, including `report.json`.
`scripts/live_smoke.py` enables paid calls only for its own process and logs its gate
decisions as test-harness actions, rather than claiming human review. It leaves answer
drafts pending. The normal app's `ENABLE_VERTEX_CALLS` setting remains unchanged.
Future reruns need authorization for any additional billable work; do not run this script
as part of automated offline validation.

Use four tiny sources (one ticket CSV, one product JSON, one policy TXT and one text PDF),
at most 12 chunks. Run one planning invocation, exercise both human gates, index once,
then ask one supported and one unsupported question. Check Vertex auth, structured agent
output, real embeddings, tool retrieval, citations and insufficient evidence. This incurs
billable calls: two planning agent generations, at most 12 document embedding requests,
and two chat workflows (each bounded to eight generations and one query embedding).
Do not interpret the offline tests as proof of live model access or answer quality.

## Docker and future Cloud Run deployment

```powershell
# Docker Desktop must be running in Linux-container mode.
docker build -t beacon-rag-poc .
docker run --rm -p 8080:8080 --env-file .env beacon-rag-poc
```

The container binds port 8080. The example intentionally does not bake in credentials.
For local live container use, mount ADC read-only and pass `GOOGLE_APPLICATION_CREDENTIALS`;
for Cloud Run use its service identity with the required Vertex permissions. Mount a local
data directory if you want local container approvals to survive container deletion.

No cloud deployment or new resources have been performed. The following is a future,
ephemeral demo deployment recipe, requiring separate approval, an existing Artifact Registry
repository, service account and externally reachable Chroma endpoint:

```powershell
$projectId = gcloud config get-value project
$region = 'us-central1'
$image = "$region-docker.pkg.dev/$projectId/EXISTING_REPOSITORY/beacon-rag-poc:demo"
gcloud auth configure-docker "$region-docker.pkg.dev"
docker build -t $image .
docker push $image
gcloud run deploy beacon-rag-poc --image $image --project $projectId --region $region `
  --port 8080 --memory 2Gi --cpu 1 --max-instances 1 --timeout 3600 `
  --session-affinity --no-allow-unauthenticated `
  --service-account "EXISTING_SERVICE_ACCOUNT@$projectId.iam.gserviceaccount.com" `
  --set-env-vars "GOOGLE_CLOUD_PROJECT=$projectId,GOOGLE_CLOUD_LOCATION=global,ENABLE_VERTEX_CALLS=false,CHROMA_HOST=EXTERNAL_HOST,CHROMA_PORT=443,CHROMA_SSL=true"
# For an authorized local viewer:
gcloud run services proxy beacon-rag-poc --project $projectId --region $region --port 8080
```

Provide any Chroma secret through an approved secret integration rather than command-line
plaintext. Ensure network routing/TLS/auth and client/server version compatibility. External
Chroma is not launched by this application. The HTTP mode targets an ordinary Chroma server;
vendor-specific managed-cloud tenancy/auth may require another adapter.

Cloud Run's writable filesystem is ephemeral and memory-backed. SQLite approvals, ADK
sessions, originals and chat history can disappear when the instance is replaced, even with
external Chroma and max-instances=1. Session affinity is best effort and WebSockets can
reconnect. This recipe does **not** meet the local durable-approval guarantee across container
replacement. Durable hosted operation needs an approved external transactional state/source
storage design; do not put SQLite on object-storage mounts. Production durability, identity,
multi-user isolation, exact analytics, hybrid search and Graph RAG remain outside this POC.

Official references: [ADK resumability](https://adk.dev/runtime/resume/),
[ADK confirmation limitations](https://adk.dev/tools-custom/confirmation/),
[Vertex models](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/learn/model-versions),
[embeddings](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/embeddings/get-text-embeddings),
[Streamlit execution](https://docs.streamlit.io/develop/api-reference/execution-flow),
[Chroma](https://docs.trychroma.com/reference/python),
[Cloud Run container contract](https://docs.cloud.google.com/run/docs/container-contract),
[WebSockets](https://docs.cloud.google.com/run/docs/triggering/websockets), and
[deployment](https://docs.cloud.google.com/run/docs/deploying).
