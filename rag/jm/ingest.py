
from __future__ import annotations

import glob
import os
from dataclasses import dataclass
from typing import Iterable, List, Optional

from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from .config import load_config
from .index import get_vectorstore


@dataclass(frozen=True)
class IngestResult:
    files: int
    chunks: int

# 파일 경로 순회
def _iter_files(path: str, pattern: Optional[str]) -> List[str]:
    if os.path.isfile(path):
        return [path]
    if not os.path.isdir(path):
        raise FileNotFoundError(path)

    pat = pattern or "*"
    return sorted(glob.glob(os.path.join(path, "**", pat), recursive=True))

# 문서 로드
def _load_documents(file_path: str) -> List[Document]:
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".pdf":
        loader = PyPDFLoader(file_path)
        docs = loader.load()
    else:
        loader = TextLoader(file_path, encoding="utf-8")
        docs = loader.load()

    for d in docs:
        d.metadata = dict(d.metadata or {})
        d.metadata.setdefault("source", file_path)
    return docs

# 문서 적재
def ingest_paths(paths: Iterable[str], glob_pattern: Optional[str] = None, doc_type: str = "doc") -> IngestResult:
    cfg = load_config()
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=cfg.chunk_size,
        chunk_overlap=cfg.chunk_overlap,
    )
    vs = get_vectorstore()

    all_chunks: List[Document] = []
    file_count = 0

    for p in paths:
        files = _iter_files(p, glob_pattern)
        for f in files:
            if not os.path.isfile(f):
                continue
            if os.path.basename(f).startswith("."):
                continue

            docs = _load_documents(f)
            chunks = splitter.split_documents(docs)
            for i, c in enumerate(chunks):
                c.metadata = dict(c.metadata or {})
                c.metadata["doc_type"] = doc_type
                c.metadata["file_name"] = os.path.basename(f)
                c.metadata["chunk_index"] = i

            all_chunks.extend(chunks)
            file_count += 1

    if all_chunks:
        vs.add_documents(all_chunks)

    return IngestResult(files=file_count, chunks=len(all_chunks))
