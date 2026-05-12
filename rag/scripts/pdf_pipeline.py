"""
전세계약 위험 진단 에이전트
PDF 텍스트 추출 + 청크 분할 + rag_documents 적재

파일 유형별 로더 선택:
- 판례 (대법원, 헌재)     → PyPDFLoader       (텍스트 중심, 빠름)
- 법령 조문, 서식         → PDFPlumberLoader  (레이아웃/표 보존)
- 사례집, 안내서          → PyMuPDFLoader     (텍스트 중심, LangChain 0.3 호환)

실행: python pdf_pipeline.py
"""

import os
import re
import glob
import psycopg2
import sys
import io

# Windows 터미널 인코딩 문제 해결
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

print("파이프라인 준비 중...")
from psycopg2.extras import execute_values
from dotenv import load_dotenv
from tqdm import tqdm

from langchain_community.document_loaders import PyMuPDFLoader, PyPDFLoader, PDFPlumberLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

load_dotenv()

DB_CONFIG = {
    "host":     os.getenv("DB_HOST", "db"),
    "port":     int(os.getenv("DB_PORT", 5432)),
    "database": os.getenv("DB_NAME", "jeonse_risk"),
    "user":     os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD"),
}

# =============================================
# 판례 필요 섹션 / 불필요 섹션
# =============================================
KEEP_SECTIONS    = ["이유", "주문", "참조조문", "참조판례"]
DISCARD_SECTIONS = ["전문", "피고인", "상고인", "피고인들", "변호인",
                    "대상판결", "원심판결", "상고이유", "주심"]


# =============================================
# 파일 유형별 분류
# =============================================
JUDGEMENT_KEYWORDS = ["판결", "결정", "헌법재판소"]
LAW_KEYWORDS       = ["법률", "시행령", "표준계약서", "중개대상물", "확인ㆍ설명서"]

def classify_pdf(filename: str) -> str:
    name = os.path.basename(filename)
    if any(k in name for k in JUDGEMENT_KEYWORDS):
        return "judgement"
    elif any(k in name for k in LAW_KEYWORDS):
        return "law"
    else:
        return "case"

def get_doc_type(filename: str) -> str:
    name = os.path.basename(filename)
    if any(k in name for k in JUDGEMENT_KEYWORDS):
        return "판례"
    elif "법률" in name or "시행령" in name or "민법" in name:
        return "법령"
    elif "계약서" in name or "확인" in name:
        return "서식"
    else:
        return "사례집"


# =============================================
# 판례 전처리 - 불필요 섹션 제거
# =============================================
def preprocess_judgement(text: str) -> str:
    """
    【섹션명】 기준으로 분리 후
    KEEP_SECTIONS에 해당하는 섹션만 유지
    """
    # 섹션 분리: 【...】 패턴 기준
    pattern = r'【([^】]+)】'
    parts   = re.split(pattern, text)

    # parts = [before_first, section1_name, section1_content, section2_name, ...]
    result = []
    i = 1
    while i < len(parts) - 1:
        section_name    = parts[i].strip()
        section_content = parts[i + 1].strip() if i + 1 < len(parts) else ""

        # KEEP_SECTIONS에 포함되면 유지
        if any(k in section_name for k in KEEP_SECTIONS):
            result.append(f"【{section_name}】\n{section_content}")

        i += 2

    cleaned = "\n\n".join(result)

    # 공백 정리
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    cleaned = re.sub(r' {2,}', ' ', cleaned)

    return cleaned.strip()


# =============================================
# PDF 로드
# =============================================
def load_pdf(filepath: str) -> list:
    pdf_type = classify_pdf(filepath)
    try:
        if pdf_type == "judgement":
            loader = PyPDFLoader(filepath)
        elif pdf_type == "law":
            loader = PDFPlumberLoader(filepath)
        else:
            loader = PyMuPDFLoader(filepath)

        docs = loader.load()
        return docs

    except Exception as e:
        print(f"  ⚠️  로드 실패 ({os.path.basename(filepath)}): {e}")
        return []


# =============================================
# 청크 분할 (유형별)
# =============================================
def split_docs(docs: list, pdf_type: str) -> list:

    if pdf_type == "judgement":
        # 판례: 전체 텍스트 합치고 → 전처리 → 섹션+1000자 분할
        full_text = "\n\n".join([d.page_content for d in docs])
        cleaned   = preprocess_judgement(full_text)

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=100,
            separators=["【", "\n\n", "\n", ". ", " "],
        )
        chunks = splitter.create_documents([cleaned])

    elif pdf_type == "law":
        # 법령: 조문 단위 + 최대 800자
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=800,
            chunk_overlap=80,
            separators=["\n제", "\n\n", "\n", ". ", " "],
        )
        chunks = splitter.split_documents(docs)

    else:
        # 사례집/안내서: 문단 단위 + 최대 800자
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=800,
            chunk_overlap=80,
            separators=["\n\n", "\n", ". ", " "],
        )
        chunks = splitter.split_documents(docs)

    return chunks


# =============================================
# DB 적재
# =============================================
def load_to_db(chunks: list, filepath: str) -> int:
    conn = psycopg2.connect(**DB_CONFIG)
    cur  = conn.cursor()

    filename = os.path.basename(filepath)
    doc_type = get_doc_type(filepath)
    title    = filename.replace(".pdf", "")

    rows = [
        (doc_type, title, filename, i, chunk.page_content, None, None)
        for i, chunk in enumerate(chunks)
        if chunk.page_content.strip()
    ]

    if not rows:
        print(f"  ⚠️  유효한 청크 없음: {filename}")
        cur.close()
        conn.close()
        return 0

    try:
        conn.autocommit = False
        execute_values(cur, """
            INSERT INTO rag_documents
            (doc_type, title, file_name, chunk_index, chunk_text, vector_id, source_law)
            VALUES %s
            ON CONFLICT (file_name, chunk_index)
            DO UPDATE SET
                chunk_text = EXCLUDED.chunk_text,
                doc_type   = EXCLUDED.doc_type
        """, rows)
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"  ❌ 적재 실패 - 롤백: {e}")
        return 0
    finally:
        cur.close()
        conn.close()
    return len(rows)


# =============================================
# 전체 실행
# =============================================
def run(pdf_dir: str = "docs/pdf"):
    pdf_files  = glob.glob(os.path.join(pdf_dir, "**/*.pdf"), recursive=True)
    pdf_files += glob.glob(os.path.join(pdf_dir, "*.pdf"))
    pdf_files  = list(set(pdf_files))

    if not pdf_files:
        print(f"❌ PDF 파일 없음: {pdf_dir}")
        return

    print(f"=== PDF 파이프라인 시작: 총 {len(pdf_files)}개 ===\n")

    # 기존 데이터 삭제 후 재적재
    conn = psycopg2.connect(**DB_CONFIG)
    cur  = conn.cursor()
    cur.execute("DELETE FROM rag_documents")
    conn.commit()
    cur.close()
    conn.close()
    print("기존 rag_documents 데이터 삭제 완료\n")

    total_chunks = 0
    pbar = tqdm(sorted(pdf_files), desc="PDF 파이프라인")

    for filepath in pbar:
        filename = os.path.basename(filepath)
        pdf_type = classify_pdf(filepath)
        pbar.set_postfix_str(f"파일: {filename[:20]}...")

        docs   = load_pdf(filepath)
        if not docs:
            continue

        chunks = split_docs(docs, pdf_type)
        count  = load_to_db(chunks, filepath)
        total_chunks += count

    print(f"=== 완료! 총 {total_chunks}개 청크 적재 ===")


if __name__ == "__main__":
    PDF_DIR = "docs/pdf"
    run(PDF_DIR)
