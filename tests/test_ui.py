from streamlit.testing.v1 import AppTest
from pathlib import Path

def test_page_generates_and_recovers_dataset(tmp_path, monkeypatch):
    # Config dataclass defaults are evaluated at import. Isolate the app's store explicitly.
    from rag_poc.config import Config
    monkeypatch.setattr("rag_poc.config.Config", lambda: Config(root=tmp_path, enabled=False))
    script = str(Path(__file__).resolve().parents[1] / "app.py")
    app = AppTest.from_file(script, default_timeout=30).run()
    assert not app.exception
    next(b for b in app.button if b.label == "Generate demo dataset").click().run()
    assert not app.exception
    assert len(app.selectbox) == 1
    assert app.chat_input[0].disabled
    assert next(b for b in app.button if b.label == "Create preparation plan").disabled
    saved_dataset = app.selectbox[0].value
    next(b for b in app.button if b.label == "Start over").click().run()
    assert not app.exception
    assert app.selectbox[0].value == saved_dataset
    next(b for b in app.button if b.label == "Cancel").click().run()
    assert not app.exception
    assert app.selectbox[0].value == saved_dataset
    assert not any(b.label == "Confirm start over" for b in app.button)
    next(b for b in app.button if b.label == "Start over").click().run()
    next(b for b in app.button if b.label == "Confirm start over").click().run()
    assert not app.exception
    assert app.selectbox[0].value is None
    assert any(heading.value == "Start here" for heading in app.subheader)
    assert not app.tabs
    app.run()
    assert app.selectbox[0].value is None
    app.selectbox[0].select(saved_dataset).run()
    assert not app.exception
    assert app.selectbox[0].value == saved_dataset
    assert next(b for b in app.button if b.label == "Create preparation plan").disabled
    restarted = AppTest.from_file(script, default_timeout=30).run()
    assert not restarted.exception
    assert len(restarted.selectbox) == 1

def test_page_ingestion_gates_and_pending_answer(tmp_path, monkeypatch):
    from rag_poc.config import Config
    from test_workflow import OfflineAgents, OfflineEmbeddings
    monkeypatch.setattr("rag_poc.config.Config", lambda: Config(root=tmp_path, enabled=True))
    monkeypatch.setattr("rag_poc.agents.Agents", lambda *args: OfflineAgents())
    monkeypatch.setattr("rag_poc.embeddings.VertexEmbeddings", lambda *args: OfflineEmbeddings())
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=30).run()
    def click(label):
        next(b for b in app.button if b.label == label).click().run()
        assert not app.exception
    click("Generate demo dataset")
    click("Create preparation plan")
    assert app.chat_input[0].disabled
    click("Approve plan")
    click("Create text samples")
    assert app.chat_input[0].disabled
    click("Approve samples")
    click("Build search index")
    assert not app.chat_input[0].disabled
    app.chat_input[0].set_value("What is the return window?").run()
    assert not app.exception
    assert len(app.chat_message) == 0
    assert len(app.text_area) == 1
    click("Publish answer")
    assert len(app.chat_message) == 2

def test_new_dataset_is_selected_and_next_action_is_explained(tmp_path, monkeypatch):
    from rag_poc.config import Config
    monkeypatch.setattr("rag_poc.config.Config", lambda: Config(root=tmp_path, enabled=False))
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=30).run()
    next(b for b in app.button if b.label == "Generate demo dataset").click().run()
    first = app.selectbox[0].value
    next(n for n in app.number_input if n.label == "Synthetic seed").set_value(7)
    next(b for b in app.button if b.label == "Generate demo dataset").click().run()
    assert not app.exception
    assert app.selectbox[0].value != first
    assert any("Next: ask the agents" in info.value for info in app.info)
    assert [tab.label for tab in app.tabs] == ["Walkthrough", "Files & previews", "Activity & troubleshooting"]
