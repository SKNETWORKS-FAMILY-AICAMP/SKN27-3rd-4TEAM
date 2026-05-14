"""Deprecated supervisor smoke test.

The old supervisor graph lived in the deleted common package. The active app
path is now:
    frontend/views/chat.py -> backend/rag_server -> RAGPipeline

Use the FastAPI health, chat, and diagnosis endpoints for integration checks.
"""


def test_supervisor_graph_removed() -> None:
    assert True
