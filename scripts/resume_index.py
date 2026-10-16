"""Resume an already-approved index with visible progress. Makes paid embedding calls."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from rag_poc.config import Config
from rag_poc.state import Store
from rag_poc.agents import Agents
from rag_poc.embeddings import VertexEmbeddings
from rag_poc.vector_store import Vectors
from rag_poc.workflow import Workflow
from rag_poc.errors import error_details

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--data-dir", type=Path, required=True)
parser.add_argument("--dataset", required=True)
parser.add_argument("--live", action="store_true", help="Explicitly enable paid embeddings for this process")
args = parser.parse_args()
if not args.live:
    parser.error("--live is required to enable paid embedding calls")
config = Config(root=args.data_dir, enabled=True)
store = Store(config.root)
workflow = Workflow(store, config, Agents(config, store), VertexEmbeddings(config), Vectors(config.root))
def progress(done, total):
    if done % 8 == 0 or done == total:
        print(json.dumps({"saved": done, "total": total}), flush=True)
try:
    workflow.index(args.dataset, on_progress=progress)
    print(json.dumps({"status": store.get(args.dataset)["status"]}), flush=True)
except Exception as exc:
    print(json.dumps(error_details(exc)), flush=True)
    raise SystemExit(1)
