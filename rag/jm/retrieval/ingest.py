# rag/jm/retrieval/ingest.py
# 문서를 읽고 정제한 뒤 chunk 단위로 나누어 PGVector에 적재합니다.

from __future__ import annotations

import glob
import os
import re
import time
from dataclasses import dataclass
from typing import Iterable, List, Optional

from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from ..core.config import load_config
from ..core.index import get_vectorstore


@dataclass(frozen=True)
class IngestResult:
    files: int
    chunks: int


def _iter_files(path: str, pattern: Optional[str]) -> List[str]:
    if os.path.isfile(path):
        return [path]
    if not os.path.isdir(path):
        raise FileNotFoundError(path)

    return sorted(glob.glob(os.path.join(path, "**", pattern or "*"), recursive=True))


def _clean_text(text: str) -> str:
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\u200b\u200c\u200d\ufeff]", "", text)
    text = re.sub(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", "", text)
    text = re.sub(r"https?://[^\s]+", "", text)
    text = re.sub(r"^\s*[-_]*\s*\d+\s*[-_]*\s*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"(?<![a-zA-Z])[pP]\.?\s*\d+(?![a-zA-Z])", "", text)
    text = re.sub(r"[Pp]age\s*\d+", "", text)
    text = re.sub(r"(?<![a-zA-Z])\d+\s*[pP](?![a-zA-Z])", "", text)
    text = re.sub(r"\(cid:\d+\)", "", text)
    text = re.sub(r"[-=~_]{3,}", " ", text)
    text = re.sub(r"[\.]{2,}", " ", text)
    text = re.sub(r"(?<=\d)\s(?=\d)|(?<=\d)\s(?=,)|(?<=,)\s(?=\d)", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _load_documents(file_path: str) -> List[Document]:
    ext = os.path.splitext(file_path)[1].lower()
    loader = PyPDFLoader(file_path) if ext == ".pdf" else TextLoader(file_path, encoding="utf-8")
    docs = loader.load()

    for doc in docs:
        doc.page_content = _clean_text(doc.page_content)
        doc.metadata = dict(doc.metadata or {})
        doc.metadata.setdefault("source", file_path)
    return docs


def ingest_paths(
    paths: Iterable[str],
    glob_pattern: Optional[str] = None,
    doc_type: str = "doc",
    clear: bool = False,
) -> IngestResult:
    cfg = load_config()
    vs = get_vectorstore()

    if clear:
        vs.delete_collection()
        vs = get_vectorstore()

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=cfg.chunk_size,
        chunk_overlap=cfg.chunk_overlap,
    )

    all_chunks: List[Document] = []
    file_count = 0

    for path in paths:
        for file_path in _iter_files(path, glob_pattern):
            if not os.path.isfile(file_path) or os.path.basename(file_path).startswith("."):
                continue

            docs = _load_documents(file_path)
            chunks = splitter.split_documents(docs)

            for chunk_index, chunk in enumerate(chunks):
                content = chunk.page_content.strip()
                if len(content) < 20:
                    continue

                chunk.page_content = content
                chunk.metadata = dict(chunk.metadata or {})
                chunk.metadata["doc_type"] = doc_type
                chunk.metadata["file_name"] = os.path.basename(file_path)
                chunk.metadata["chunk_index"] = chunk_index
                all_chunks.append(chunk)

            file_count += 1

    if all_chunks:
        batch_size = 20
        for i in range(0, len(all_chunks), batch_size):
            vs.add_documents(all_chunks[i : i + batch_size])
            if cfg.embedding_provider == "openai":
                time.sleep(2)

    return IngestResult(files=file_count, chunks=len(all_chunks))
