"""Compatibility wrapper for the canonical RAG pipeline.

The maintained FastAPI server lives under ``backend/rag_server``.  This module
is kept for older ``app.*`` imports, but it intentionally reuses the canonical
implementation so search planning, reranking, and reference metadata do not
drift between the two backend package layouts.
"""
from __future__ import annotations

import sys
from pathlib import Path

try:
    from rag_server.core.rag_pipeline import RAGPipeline
except ModuleNotFoundError:  # pragma: no cover - supports repo-root imports
    backend_dir = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(backend_dir))
    from rag_server.core.rag_pipeline import RAGPipeline

__all__ = ["RAGPipeline"]
