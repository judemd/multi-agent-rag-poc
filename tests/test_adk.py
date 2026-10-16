"""Exercise real ADK Runner, sequential orchestration, SQLite sessions and tools.
Only model inference is replaced with a named deterministic offline double.
"""
import json
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.genai import types
from rag_poc.agents import Agents
from rag_poc.config import Config
from rag_poc.state import Store
from rag_poc.preparation import Settings

class OfflineModel(BaseLlm):
    model: str = "offline-test-double"
    async def generate_content_async(self, llm_request, stream=False):
        schema = llm_request.config.response_schema
        name = getattr(schema, "__name__", "")
        if name == "Plan":
            text = json.dumps({"rationale": "Preserve missing values", "settings": Settings().model_dump()})
        elif name == "Answer":
            text = json.dumps({"answer": "30 days [S1]", "insufficient": False, "conflict": False, "citations": ["S1"]})
        elif llm_request.tools_dict:
            tool_results = [p for c in llm_request.contents for p in c.parts or [] if p.function_response]
            if not tool_results:
                yield LlmResponse(content=types.Content(role="model", parts=[types.Part(
                    function_call=types.FunctionCall(name="retrieve_evidence", args={"query": "return policy"}))]))
                return
            text = "Evidence: return within 30 days [S1]"
        else:
            text = "One policy record; no missing values."
        yield LlmResponse(content=types.Content(role="model", parts=[types.Part(text=text)]))

def test_actual_adk_planning_and_retrieval(tmp_path, monkeypatch):
    config = Config(root=tmp_path, enabled=True)
    store = Store(tmp_path)
    agents = Agents(config, store)
    monkeypatch.setattr(Agents, "model", lambda self: OfflineModel())
    result = agents.propose("dataset", {"records": 1})
    assert result["settings"]["remove_duplicates"] is False
    searched = []
    evidence = [{"citation": "S1", "text": "30 days", "distance": 0.1,
                 "metadata": {"dataset_id": "dataset", "filename": "policy.txt", "reference": "lines 1-1", "chunk_id": "abc"}}]
    def search(query):
        searched.append(query)
        return evidence
    answer, actual = agents.answer("dataset", "What is the return window?", search)
    assert searched and actual == evidence
    assert answer["answer"] == "30 days [S1]"
    assert (tmp_path / "adk.sqlite3").exists()
    kinds = {e["kind"] for e in store.events("dataset")}
    assert {"agent_decision", "agent_tool_request", "tool_execution", "tool_result"} <= kinds

class RepeatingRetrievalModel(OfflineModel):
    """Reproduce a model requesting more tools than the old two-call budget."""
    retrieval_turns: int = 0
    async def generate_content_async(self, llm_request, stream=False):
        if llm_request.tools_dict:
            self.retrieval_turns += 1
            assert self.retrieval_turns == 1, "Retrieval loop did not terminate after the tool"
            yield LlmResponse(content=types.Content(role="model", parts=[types.Part(
                function_call=types.FunctionCall(name="retrieve_evidence", args={"query": query}))
                for query in ["returns", "return deadline", "refund policy"]]))
            return
        # Verify the answer agent sees the actual evidence stored by Python.
        assert "Original policy evidence" in str(llm_request.config.system_instruction)
        async for response in super().generate_content_async(llm_request, stream):
            yield response

def test_repeated_retrieval_requests_reuse_evidence_and_advance(tmp_path, monkeypatch):
    config = Config(root=tmp_path, enabled=True)
    agents = Agents(config, Store(tmp_path))
    model = RepeatingRetrievalModel()
    monkeypatch.setattr(Agents, "model", lambda self: model)
    searches = []
    evidence = [{"citation": "S1", "text": "Original policy evidence: return within 30 days.",
                 "distance": 0.1, "metadata": {"dataset_id": "dataset"}}]
    def search(query):
        searches.append(query)
        return evidence
    answer, actual = agents.answer("dataset", "What is the return window?", search)
    assert len(searches) == 1
    assert model.retrieval_turns == 1
    assert actual == evidence and answer["citations"] == ["S1"]
