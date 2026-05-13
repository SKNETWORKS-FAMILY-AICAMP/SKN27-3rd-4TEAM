"""
전세계약 위험 진단 에이전트
PDF 텍스트 추출 + 청크 분할 + rag_documents 적재  (개선판 v2)

변경사항 (v2):
  - 관련성 필터: 전세/임대차 핵심 키워드가 없는 판례 자동 스킵
  - 청크 크기 상향: 판례 1000→1200자 / 법령 800→1000자 / 사례집 800→1000자
  - 오버랩 확대: 80-100자 → 150자 (법률 문장의 문맥 보존)
  - 법령 separator 정교화: "\n제" → "\n제\d+조" (오분할 방지)
  - 메타데이터 강화: 법원명, 선고일, 사건번호, 핵심키워드 추출 후 저장
  - 텍스트 클렌징 강화: 페이지 번호/머리글/바닥글 제거, 인코딩 오류 정리

파일 유형별 로더:
  - 판례 (대법원, 헌재)    → PyPDFLoader       (텍스트 중심, 빠름)
  - 법령 조문, 서식        → PDFPlumberLoader  (레이아웃/표 보존)
  - 사례집, 안내서         → PyMuPDFLoader     (LangChain 0.3 호환)

실행: python rag/scripts/pdf_pipeline.py
"""

from __future__ import annotations

import json
import os
import re
import glob
import psycopg2
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

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
# 관련성 필터 설정
# =============================================
# 핵심 키워드: 하나라도 있어야 전세/임대차 관련 문서로 인정
CORE_KEYWORDS = [
    "전세", "임대차", "임차인", "보증금 반환", "주택임대차",
    "전세사기", "대항력", "우선변제", "임차권",
]
# 잡음 키워드: 2개 이상이면서 핵심 키워드가 1개 이하이면 제거
NOISE_KEYWORDS = [
    "폭행", "횡령", "사기죄", "강도", "절도", "마약", "업무방해", "배임",
    "성폭력", "강간", "살인", "음주운전", "도박", "병역",
    "가사", "이혼", "친권", "상속", "군사",
]
# 판례 유지 섹션
KEEP_SECTIONS = ["이유", "주문", "참조조문", "참조판례"]

# =============================================
# 파일 유형별 분류
# =============================================
JUDGEMENT_KEYWORDS = ["판결", "결정", "헌법재판소"]
LAW_KEYWORDS       = ["법률", "시행령", "표준계약서", "중개대상물", "확인ㆍ설명서"]


def classify_pdf(filename: str) -> str:
    name = os.path.basename(filename)
    if any(k in name for k in JUDGEMENT_KEYWORDS):
        return "judgement"
    if any(k in name for k in LAW_KEYWORDS):
        return "law"
    return "case"


def get_doc_type(filename: str) -> str:
    name = os.path.basename(filename)
    if any(k in name for k in JUDGEMENT_KEYWORDS):
        return "판례"
    if "법률" in name or "시행령" in name or "민법" in name:
        return "법령"
    if "계약서" in name or "확인" in name:
        return "서식"
    return "사례집"


# =============================================
# 관련성 필터 (v2 신규)
# =============================================
def is_relevant(text: str) -> bool:
    """전세/임대차 관련 판례인지 텍스트로 판별."""
    core_hits  = sum(1 for kw in CORE_KEYWORDS  if kw in text)
    noise_hits = sum(1 for kw in NOISE_KEYWORDS if kw in text)
    if core_hits == 0:
        return False
    if noise_hits >= 2 and core_hits <= 1:
        return False
    return True


# =============================================
# 텍스트 클렌징 (v2 강화)
# =============================================
def clean_text(text: str) -> str:
    """페이지 번호·머리글·바닥글·인코딩 오류 제거."""
    # 인코딩 깨진 문자 제거
    text = text.replace("�", "").replace("\xa0", " ")
    # 단독 줄의 숫자(페이지 번호) 제거: 줄 전체가 숫자+공백인 경우
    text = re.sub(r"(?m)^\s*\d{1,4}\s*$", "", text)
    # "- N -" 형태 페이지 마커 제거
    text = re.sub(r"-\s*\d+\s*-", "", text)
    # 연속 공백·줄바꿈 정리
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" {2,}", " ", text)
    return text.strip()


# =============================================
# 판례 전처리 - 불필요 섹션 제거
# =============================================
def preprocess_judgement(text: str) -> str:
    """【섹션명】 기준으로 분리 → KEEP_SECTIONS만 유지."""
    parts  = re.split(r"【([^】]+)】", text)
    result = []
    i = 1
    while i < len(parts) - 1:
        section_name    = parts[i].strip()
        section_content = parts[i + 1].strip() if i + 1 < len(parts) else ""
        if any(k in section_name for k in KEEP_SECTIONS):
            result.append(f"【{section_name}】\n{section_content}")
        i += 2

    # 섹션 분리 실패(섹션 태그 없는 판례)시 전체 텍스트 사용
    cleaned = "\n\n".join(result) if result else text
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = re.sub(r" {2,}", " ", cleaned)
    return cleaned.strip()


# =============================================
# 메타데이터 추출 (v2 신규)
# =============================================
def extract_judgement_meta(filename: str, text: str) -> dict:
    """파일명 + 텍스트에서 법원명, 선고일, 사건번호, 키워드 추출."""
    name = os.path.basename(filename).replace(".pdf", "")

    # 법원명: 파일명 앞부분
    court = re.match(r"([가-힣]+(?:법원|법|재판소)[^\s]*)", name)
    court_name = court.group(1) if court else ""

    # 선고일: "YYYY. MM. DD." 패턴
    date_m = re.search(r"(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})", name)
    decision_date = (
        f"{date_m.group(1)}-{date_m.group(2).zfill(2)}-{date_m.group(3).zfill(2)}"
        if date_m else ""
    )

    # 사건번호: 연도+사건유형+번호
    case_m = re.search(r"(\d{4}[가나다라마바사아도두누구무루수부주스][가-힣\d]+)", name)
    case_no = case_m.group(1) if case_m else ""

    # 핵심 키워드 태깅
    all_kw = ["전세사기", "보증금 반환", "임차권등기", "대항력", "우선변제",
              "근저당", "전세가율", "임대차 종료", "계약갱신", "묵시갱신"]
    found_kw = [kw for kw in all_kw if kw in text]

    return {
        "court": court_name,
        "decision_date": decision_date,
        "case_no": case_no,
        "keywords": found_kw,
    }


def extract_law_meta(filename: str, text: str) -> dict:
    """법령 파일에서 시행일, 법령명, 키워드 추출."""
    name = os.path.basename(filename).replace(".pdf", "")
    # 법령명: 괄호 앞 부분
    law_name = re.split(r"[\(\（]", name)[0].strip()
    # 핵심 조문 번호들
    articles = re.findall(r"제\d+조(?:의\d+)?", text[:3000])
    unique_articles = list(dict.fromkeys(articles))[:10]
    return {"law_name": law_name, "key_articles": unique_articles}


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
        return loader.load()
    except Exception as e:
        print(f"  ⚠️  로드 실패 ({os.path.basename(filepath)}): {e}")
        return []


# =============================================
# 청크 분할 (v2: 크기·오버랩·separator 개선)
# =============================================
def split_docs(docs: list, pdf_type: str, extra_meta: dict | None = None) -> list:
    extra_meta = extra_meta or {}

    if pdf_type == "judgement":
        full_text = "\n\n".join(d.page_content for d in docs)
        full_text = clean_text(full_text)
        cleaned   = preprocess_judgement(full_text)

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=1200,     # 1000 → 1200 (판례 단락이 길어 문맥 보존)
            chunk_overlap=150,   # 100  → 150  (법률 논리 연결 보존)
            separators=["【", "\n\n", "\n", ". ", " "],
        )
        chunks = splitter.create_documents([cleaned])
        # 메타데이터 주입
        for chunk in chunks:
            chunk.metadata.update(extra_meta)

    elif pdf_type == "law":
        # 법령 텍스트 클렌징
        for doc in docs:
            doc.page_content = clean_text(doc.page_content)

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,     # 800 → 1000 (조문 1개가 800자 넘는 경우 다수)
            chunk_overlap=150,   # 80  → 150
            separators=[
                r"\n제\d+조",    # 조문 경계 (정규식): "제1조", "제10조" 등
                "\n\n", "\n", ". ", " ",
            ],
            is_separator_regex=True,   # separator를 정규식으로 해석
        )
        chunks = splitter.split_documents(docs)
        for chunk in chunks:
            chunk.metadata.update(extra_meta)

    else:  # case (사례집/안내서)
        for doc in docs:
            doc.page_content = clean_text(doc.page_content)

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,     # 800 → 1000
            chunk_overlap=150,   # 80  → 150
            separators=["\n\n", "\n", ". ", " "],
        )
        chunks = splitter.split_documents(docs)
        for chunk in chunks:
            chunk.metadata.update(extra_meta)

    # 너무 짧은 청크 제거 (50자 미만)
    chunks = [c for c in chunks if len(c.page_content.strip()) >= 50]
    return chunks


# =============================================
# DB 적재
# =============================================
def load_to_db(chunks: list, filepath: str, extra_meta: dict | None = None) -> int:
    extra_meta = extra_meta or {}
    conn = psycopg2.connect(**DB_CONFIG)
    cur  = conn.cursor()

    filename = os.path.basename(filepath)
    doc_type = get_doc_type(filepath)
    title    = filename.replace(".pdf", "")
    # source_law: 판례의 참조조문, 법령의 법령명
    source_law = extra_meta.get("key_articles", extra_meta.get("keywords"))
    source_law_str = json.dumps(source_law, ensure_ascii=False) if source_law else None

    rows = [
        (doc_type, title, filename, i, chunk.page_content, None, source_law_str)
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
                doc_type   = EXCLUDED.doc_type,
                source_law = EXCLUDED.source_law
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

    print(f"=== PDF 파이프라인 v2 시작: 총 {len(pdf_files)}개 파일 ===\n")

    # 기존 데이터 삭제 후 재적재
    conn = psycopg2.connect(**DB_CONFIG)
    cur  = conn.cursor()
    cur.execute("DELETE FROM rag_documents")
    conn.commit()
    cur.close()
    conn.close()
    print("기존 rag_documents 데이터 삭제 완료\n")

    total_chunks  = 0
    skipped_files = 0
    pbar = tqdm(sorted(pdf_files), desc="PDF 파이프라인 v2")

    for filepath in pbar:
        filename = os.path.basename(filepath)
        pdf_type = classify_pdf(filepath)
        pbar.set_postfix_str(f"{filename[:25]}...")

        docs = load_pdf(filepath)
        if not docs:
            continue

        full_text = "\n\n".join(d.page_content for d in docs[:3])

        # ── 관련성 필터: 판례만 적용 ──────────────────────
        if pdf_type == "judgement" and not is_relevant(full_text):
            skipped_files += 1
            tqdm.write(f"  ⏭  관련성 없음 스킵: {filename[:55]}")
            continue

        # ── 메타데이터 추출 ────────────────────────────────
        if pdf_type == "judgement":
            extra_meta = extract_judgement_meta(filepath, full_text)
        elif pdf_type == "law":
            extra_meta = extract_law_meta(filepath, full_text)
        else:
            extra_meta = {}

        chunks = split_docs(docs, pdf_type, extra_meta)
        count  = load_to_db(chunks, filepath, extra_meta)
        total_chunks += count

    print(f"\n=== 완료! ===")
    print(f"  총 청크 적재: {total_chunks}개")
    print(f"  관련성 없음 스킵: {skipped_files}개")


if __name__ == "__main__":
    PDF_DIR = "docs/pdf"
    run(PDF_DIR)
