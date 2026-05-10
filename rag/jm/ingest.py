
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
    
    # 페이지 번호 및 표기 제거 (한국어 조사 '23p에서' 등이 붙는 경우 고려하여 \b 대신 더 정교한 패턴 사용)
    text = re.sub(r'^\s*[-]*\s*\d+\s*[-]*\s*$', '', text, flags=re.MULTILINE) # 숫자만 있는 줄
    text = re.sub(r'(?<![a-zA-Z])[pP]\.?\s*\d+(?![a-zA-Z])', '', text) # p74, p. 74 등 (영어 알파벳과 겹치지 않게)
    text = re.sub(r'[Pp]age\s?\d+', '', text)    # Page 74 등
    text = re.sub(r'(?<![a-zA-Z])\d+\s*[pP](?![a-zA-Z])', '', text)   # 23p, 23 p 등 (23p에서 처럼 조사가 붙어도 지워짐)
    text = re.sub(r'\d+\s*(?:페이지|쪽)', '', text) # 23페이지, 23쪽 등
    
    # 띄어쓰기 사이에 혼자 둥둥 떠다니는 무의미한 숫자 패턴 제거 (예: " 27-2 ", " 1-1 ")
    # 단, 123-45번지 처럼 뒤에 글자가 붙거나, 2024-05-10 처럼 긴 날짜 형식은 보호됨
    text = re.sub(r'(?<!\S)\d{1,3}-\d{1,3}(?!\S)', '', text)
    
    # 목차 기호 및 단독 로마자 제거 (예: "I.", "II.", "IV.")
    # 단, 영어 단어 I와 헷갈리지 않게 문장 부호가 같이 있는 경우나 단독으로 쓰인 경우만 처리
    text = re.sub(r'\b(?:I{1,3}|IV|V|VI{1,3}|IX|X)\.\s', ' ', text)
    
    # 반복적으로 나타나는 헤더/푸터 문구 제거
    blacklist = [
        "전세사기 피해 예방을 위한 전세계약 제대로 알고 하기",
        "전세사기피해 예방을 위한 전세계약 제대로 알고 하기",
        "안내서를 이해하는 방법"
    ]
    for phrase in blacklist:
        text = text.replace(phrase, "")
    
    # 의미 없는 단일 기호나 짧은 노이즈 제거 (예: " _ ", " . ")
    text = re.sub(r'\s+[\._-]\s+', ' ', text)

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
