
from __future__ import annotations

import glob
import time
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
    # 제어 문자 및 보이지 않는 유니코드 문자(Zero-width space 등) 제거
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\u200b\u200c\u200d\ufeff]', '', text)
    
    # 이메일 제거
    text = re.sub(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', '', text)
    # URL 제거
    text = re.sub(r'https?://[^\s]+', '', text)
    
    # 페이지 번호 및 표기 제거
    # 단독 숫자만 있는 줄 (예: - 23 - , _23_ 등)
    text = re.sub(r'^\s*[-_]*\s*\d+\s*[-_]*\s*$', '', text, flags=re.MULTILINE)
    # p.74, p 74 등 (영어 알파벳과 겹치지 않게)
    text = re.sub(r'(?<![a-zA-Z])[pP]\.?\s*\d+(?![a-zA-Z])', '', text)
    # Page 74 등
    text = re.sub(r'[Pp]age\s*\d+', '', text)
    # 23p, 23 p 등 (뒤에 '에서' 같은 조사가 붙는 경우도 고려)
    text = re.sub(r'(?<![a-zA-Z])\d+\s*[pP](?![a-zA-Z])', '', text)
    # 23페이지, 23쪽 등
    text = re.sub(r'\d+\s*(?:페이지|쪽)', '', text)
    
    # 띄어쓰기 사이에 혼자 둥둥 떠다니는 무의미한 숫자 패턴 제거 (예: " 27-2 ", " 1-1 ")
    text = re.sub(r'(?<!\S)\d{1,3}-\d{1,3}(?!\S)', '', text)
    
    # 목차 기호 및 단독 로마자 제거 (예: "I.", "II.", "IV." 및 특수문자 "Ⅰ", "Ⅱ")
    # 알파벳 형태와 유니코드 특수문자 형태 모두 대응
    text = re.sub(r'\b(?:I{1,3}|IV|V|VI{1,3}|IX|X)\b\.?\s?|[Ⅰ-Ⅻ]\.?\s?', ' ', text)
    
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
    
    # 불필요한 특수문자 반복 제거 (예: ----, ~~~~ 등)
    text = re.sub(r'[-=~_]{3,}', ' ', text)

    # 중점(⋅), 불렛(•) 등 특수 기호 제거
    text = re.sub(r'[⋅•]', ' ', text)

    # 목차에 사용되는 연속된 점선(······ 또는 ......) 제거
    text = re.sub(r'[·\.]{2,}', ' ', text)

    # 대량의 번호 나열 노이즈 제거 (예: 3660, 3661, 3663~3669, 3671~3673 ...)
    text = re.sub(r'(?:\d{1,5}(?:~\d{1,5})?,\s*){3,}\d{1,5}(?:~\d{1,5})?', ' ', text)


    # 흩어져서 추출된 숫자/콤마 사이의 공백 제거 (예: "5 , 3 7 5" -> "5,375")
    text = re.sub(r'(?<=\d)\s(?=\d)|(?<=\d)\s(?=,)|(?<=,)\s(?=\d)', '', text)

    # 문장 시작이나 공백 뒤에 나오는 '숫자 + 한두 글자' 파편 제거 (예: "10 다면", "23 에서")
    text = re.sub(r'(?:^|\s)\d+\s[\w]{1,2}(?=\s)', ' ', text)

    # 문장 중간에 뜬금없이 나타나는 단독 숫자(페이지 번호 등) 제거
    text = re.sub(r'\s\d{1,3}\s', ' ', text)

    # 페이지 번호와 별표(*)가 결합된 노이즈 (예: "72 * ") 제거
    text = re.sub(r'(?:^|\s)\d+\s*\*\s*', ' ', text)

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
        # OpenAI Rate Limit(특히 TPM 한도) 방지를 위해 배치 사이즈를 20으로 대폭 줄이고 딜레이 추가
        batch_size = 20
        for i in range(0, len(all_chunks), batch_size):
            vs.add_documents(all_chunks[i:i + batch_size])
            time.sleep(2)  # API 한도 방지를 위해 2초 대기

    return IngestResult(files=file_count, chunks=len(all_chunks))
