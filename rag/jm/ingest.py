
from __future__ import annotations

import glob
import os
from dataclasses import dataclass
from typing import Iterable, List, Optional
import re

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


# 텍스트 전처리 (Cleaning)
def _clean_text(text: str) -> str:
    # 제어 문자 제거
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    
    # 이메일 및 URL 제거
    text = re.sub(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', '', text)
    text = re.sub(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', '', text)
    
    # 페이지 번호 또는 단순 숫자만 있는 줄 제거 (예: " 1 ", " - 1 - ")
    text = re.sub(r'^\s*[-]*\s*\d+\s*[-]*\s*$', '', text, flags=re.MULTILINE)
    
    # 반복적으로 나타나는 헤더/푸터 문구 제거 (필요시 리스트 추가)
    blacklist = [
        "전세사기 피해 예방을 위한 전세계약 제대로 알고 하기",
        "전세사기피해 예방을 위한 전세계약 제대로 알고 하기",
        "안내서를 이해하는 방법"
    ]
    for phrase in blacklist:
        text = text.replace(phrase, "")

    # PDF 추출 시 발생하는 CID: 형태의 불필요한 기호 제거
    text = re.sub(r'\(cid:\d+\)', '', text)
    
    # 연속된 공백 및 줄바꿈을 하나의 공백으로 통합
    text = re.sub(r'\s+', ' ', text)
    
    return text.strip()

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
        d.page_content = _clean_text(d.page_content)
        d.metadata = dict(d.metadata or {})
        d.metadata.setdefault("source", file_path)
    return docs

# 문서 적재
def ingest_paths(
    paths: Iterable[str], 
    glob_pattern: Optional[str] = None, 
    doc_type: str = "doc",
    clear: bool = False
) -> IngestResult:
    cfg = load_config()
    vs = get_vectorstore()

    # 기존 데이터 삭제 옵션 처리
    if clear:
        # 컬렉션의 모든 문서를 삭제하거나 컬렉션 자체를 초기화
        vs.delete_collection()
        # 삭제 후 다시 vectorstore 객체를 받아오거나 초기화 상태 유지
        vs = get_vectorstore()

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=cfg.chunk_size,
        chunk_overlap=cfg.chunk_overlap,
    )

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
            
            valid_chunks_count = 0
            for i, c in enumerate(chunks):
                # 전처리 후 너무 짧은 텍스트(예: 20자 미만)는 노이즈로 간주하고 제외
                clean_content = c.page_content.strip()
                if len(clean_content) < 20:
                    continue
                
                c.page_content = clean_content
                c.metadata = dict(c.metadata or {})
                c.metadata["doc_type"] = doc_type
                c.metadata["file_name"] = os.path.basename(f)
                c.metadata["chunk_index"] = i
                
                all_chunks.append(c)
                valid_chunks_count += 1
            
            file_count += 1

    if all_chunks:
        vs.add_documents(all_chunks)

    return IngestResult(files=file_count, chunks=len(all_chunks))
