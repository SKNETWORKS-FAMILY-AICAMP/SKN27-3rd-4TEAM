"""
전세계약 위험 진단 에이전트 - rag_documents 청크 텍스트 정제 스크립트

PDF 파이프라인이 생성한 chunk_text에 섞인 노이즈를 제거하여
임베딩 품질을 높인다.

제거 대상:
  - HTML 태그      : <br>, <b>, <td> 등
  - 마크다운 기호  : ###, ##, #, **, *, ---
  - 단락 기호      : ¶ (pilcrow)
  - 표 구분자      : |---|---| 형태의 구분선
  - 과도한 공백    : 연속 공백·개행 정규화
  - 빈 셀 잔재     : Col1|Col2 형태
  - 페이지 아티팩트: 숫자만 남은 행, 단독 특수문자 행

실행: python rag/ingestion/clean_chunks.py [--dry-run]
"""

import os
import re
import sys
import argparse
import psycopg2
from dotenv import load_dotenv
from tqdm import tqdm

load_dotenv()

DB_CONFIG = {
    "host":     os.getenv("DB_HOST", "localhost"),
    "port":     int(os.getenv("DB_PORT", 5432)),
    "database": os.getenv("DB_NAME", "jeonse_risk"),
    "user":     os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", "risk1234"),
}

MIN_LENGTH = 20   # 정제 후 이 글자 수 미만이면 빈 청크로 처리


# ══════════════════════════════════════════════════════════
# 정제 함수
# ══════════════════════════════════════════════════════════

def _is_table_separator(line: str) -> bool:
    """마크다운 표 구분선 여부 판별  (|---|---| 형태)"""
    stripped = line.strip()
    if not stripped:
        return False
    # 파이프·대시·콜론·공백으로만 구성되고 대시가 2개 이상
    return bool(re.match(r"^[\|\-\:\s]+$", stripped)) and stripped.count("-") >= 2


def _clean_table_row(line) -> str:
    """
    마크다운 표 한 행 → 의미 있는 텍스트로 변환
    re.sub callable로도, 문자열 직접 호출로도 사용 가능.

    처리 순서:
      1. <br> → 공백 (셀 내 줄바꿈 복원 — 단어 파편화 방지)
      2. 파이프(|) 기준으로 셀 분리
      3. ColN 아티팩트 제거
      4. 빈 셀 제거
      5. 셀 내 연속 공백 정규화
      6. seen-set 중복 제거 (비연속 반복 포함)
      7. 셀들을 ' | ' 로 연결 → 가독성 유지
    """
    # re.sub callable로 호출될 때 Match 객체를 받음
    if hasattr(line, "group"):
        line = line.group(0)

    # 1. <br> → 공백 (파이프 분리 전에 처리해야 단어가 안 잘림)
    line = re.sub(r"<br\s*/?>", " ", line, flags=re.IGNORECASE)
    # 나머지 HTML 태그 제거
    line = re.sub(r"<[^>]+>", " ", line)

    # 2. 파이프 기준 분리
    cells = line.split("|")

    cleaned_cells = []
    for cell in cells:
        cell = cell.strip()
        # 3. ColN 아티팩트 제거
        cell = re.sub(r"\bCol\d+\b", "", cell).strip()
        # 4a. 빈 셀 제거
        if not cell:
            continue
        # 4b. 체크박스·단독 특수문자 셀 제거  (□ ■ ✓ ☑ ✗ 등 + 공백만)
        if re.match(r"^[\s□■✓✗☑☐◎○●◆◇]+$", cell):
            continue
        # 4c. 페이지 번호 셀 제거  (숫자, 숫자~숫자, 숫자-숫자)
        if re.match(r"^\d{1,3}([~\-]\d{1,3})?$", cell):
            continue
        # 4d. "페이지" 같은 테이블 헤더 단어만 있는 셀 제거
        if cell in {"페이지", "page", "비고", "note", "번호"}:
            continue
        # 4e. 단독 특수문자(공백·기호만) 제거
        if re.match(r"^[\s\W]+$", cell):
            continue
        # 5. 셀 내 연속 공백 정규화
        cell = re.sub(r"[ \t]{2,}", " ", cell)
        cleaned_cells.append(cell)

    # 6. seen-set 중복 제거 (순서 보존, 비연속 중복까지 제거)
    seen: set[str] = set()
    deduped: list[str] = []
    for cell in cleaned_cells:
        if cell not in seen:
            seen.add(cell)
            deduped.append(cell)

    # 7. 셀을 공백으로 연결 (| 구분자 제거 → 자연어 흐름, 임베딩 품질 향상)
    return " ".join(deduped)


def clean_text(text: str) -> str:
    """chunk_text 한 건을 정제하여 반환"""

    # ── PASS 1: 표 정제 (re.sub + replace 함수) ──────────────

    # A. 표 구분선 전체 제거  (|---|---| 한 방에)
    text = re.sub(r"^\s*\|[\|\-\:\s]+\|\s*$\n?", "", text, flags=re.MULTILINE)

    # B. 표 행 전체를 정규식으로 잡아 replace 함수 적용
    #    조건: 행이 |로 시작하고 내부에 | 가 1개 이상 더 있으면 표 행으로 판단
    #    (마지막 | 없이 끝나는 행도 포함)
    text = re.sub(r"^\|[^\n]*\|[^\n]*$", _clean_table_row, text, flags=re.MULTILINE)

    # C. 일반 텍스트 행의 <br> 및 HTML 태그 제거
    text = re.sub(r"<br\s*/?>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)

    # ── PASS 2: 전체 텍스트 정규화 ───────────────────────────

    # 1. 마크다운 헤더 기호 제거  (###, ##, #)
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)

    # 2. 마크다운 강조 기호 제거  (**bold**, *italic*)
    text = re.sub(r"\*{1,3}([^*\n]*)\*{1,3}", r"\1", text)

    # 3. 단락 기호(¶ § † ‡) 제거
    text = re.sub(r"[¶§†‡]", " ", text)

    # 4. ColN 잔재 제거 (표 행 밖에 남은 경우)
    text = re.sub(r"\bCol\d+\b", "", text)

    # 5. 수평선(----, ====, ____) 제거
    text = re.sub(r"^[-=_]{3,}\s*$", "", text, flags=re.MULTILINE)

    # 6. 페이지 번호만 남은 줄 제거  (숫자 1~3자리 단독 줄)
    text = re.sub(r"^\s*\d{1,3}\s*$", "", text, flags=re.MULTILINE)

    # 7. 특수문자·공백만 있는 줄 제거
    text = re.sub(r"^[\s\W]{1,5}$", "", text, flags=re.MULTILINE)

    # 8. 연속 공백 → 공백 하나
    text = re.sub(r"[ \t]{2,}", " ", text)

    # 9. 각 줄 앞뒤 공백 제거
    lines = [line.strip() for line in text.splitlines()]

    # ── PASS 3: 줄 단위 중복 제거 ────────────────────────────
    # 연속으로 동일한 줄 제거 (merged-cell 반복 행 등)
    deduped_lines: list[str] = []
    for line in lines:
        if not deduped_lines or line != deduped_lines[-1]:
            deduped_lines.append(line)

    text = "\n".join(deduped_lines)

    # 10. 3줄 이상 연속 개행 → 두 줄로 축소
    text = re.sub(r"\n{3,}", "\n\n", text)

    # 11. 표 처리 후에도 남은 | 문자 → 공백 (글머리 구분자 등)
    text = text.replace("|", " ")

    # 12. 최종 연속 공백 정리
    text = re.sub(r"[ \t]{2,}", " ", text)

    return text.strip()


def is_empty_chunk(text: str) -> bool:
    """정제 후 의미 없는 청크인지 판단"""
    # 한글·영문 글자가 MIN_LENGTH자 이상 있어야 유효
    meaningful = re.sub(r"[^가-힣a-zA-Z0-9]", "", text)
    if len(meaningful) < MIN_LENGTH:
        return True

    # 사법정보공개포털 웹 네비게이션 찌꺼기 (판례 PDF 다운로드 시 포함되는 breadcrumb)
    # 실제 법률 내용이 없는 헤더/UI 텍스트
    NOISE_PATTERNS = [
        r"사법정보공개포털",
        r"본문바로출력",
        r"판례.*?>\s*본문",
    ]
    for pattern in NOISE_PATTERNS:
        if re.search(pattern, text):
            return True

    return False


# ══════════════════════════════════════════════════════════
# DB 처리
# ══════════════════════════════════════════════════════════

def fetch_all_chunks(conn) -> list[dict]:
    """rag_documents 전체 조회 (vector_id 무관 — 텍스트 자체를 정제)"""
    cur = conn.cursor()
    cur.execute("""
        SELECT id, doc_type, title, chunk_index, chunk_text
        FROM rag_documents
        WHERE chunk_text IS NOT NULL
        ORDER BY id
    """)
    rows = cur.fetchall()
    cur.close()
    return [
        {"id": r[0], "doc_type": r[1], "title": r[2],
         "chunk_index": r[3], "chunk_text": r[4]}
        for r in rows
    ]


def apply_updates(conn, updates: list[tuple]) -> None:
    """
    updates: [(new_text, row_id), ...]
    new_text 가 None 이면 해당 청크 삭제 (빈 청크)
    """
    cur = conn.cursor()

    to_update = [(t, rid) for t, rid in updates if t is not None]
    to_delete = [rid for t, rid in updates if t is None]

    if to_update:
        cur.executemany(
            "UPDATE rag_documents SET chunk_text = %s WHERE id = %s",
            to_update,
        )

    if to_delete:
        cur.execute(
            "DELETE FROM rag_documents WHERE id = ANY(%s)",
            (to_delete,),
        )

    conn.commit()
    cur.close()


# ══════════════════════════════════════════════════════════
# 메인
# ══════════════════════════════════════════════════════════

def run(dry_run: bool = False):
    print("=== rag_documents 청크 텍스트 정제 시작 ===\n")
    if dry_run:
        print("⚠️  DRY-RUN 모드: DB를 실제로 수정하지 않습니다.\n")

    conn   = psycopg2.connect(**DB_CONFIG)
    chunks = fetch_all_chunks(conn)
    print(f"📄 총 청크 수: {len(chunks)}개\n")

    updates       = []
    deleted_count = 0
    changed_count = 0

    for chunk in tqdm(chunks, desc="정제 중"):
        original = chunk["chunk_text"]
        cleaned  = clean_text(original)

        if is_empty_chunk(cleaned):
            # 의미 없는 청크 → 삭제 대상
            updates.append((None, chunk["id"]))
            deleted_count += 1
        elif cleaned != original:
            updates.append((cleaned, chunk["id"]))
            changed_count += 1
        # 변화 없으면 업데이트 목록에 추가하지 않음

    print(f"\n📊 정제 결과:")
    print(f"   수정됨     : {changed_count}개")
    print(f"   삭제 예정  : {deleted_count}개 (빈 청크)")
    print(f"   변화 없음  : {len(chunks) - changed_count - deleted_count}개")

    if dry_run:
        # dry-run: 샘플 5건만 출력
        sample = [(t, rid) for t, rid in updates if t is not None][:5]
        print("\n[DRY-RUN 샘플 — 정제 전 → 후]")
        for cleaned_text, row_id in sample:
            orig = next(c["chunk_text"] for c in chunks if c["id"] == row_id)
            print(f"\n--- ID {row_id} ---")
            print(f"[전] {orig[:120]!r}")
            print(f"[후] {cleaned_text[:120]!r}")
    else:
        print("\nDB 반영 중...")
        apply_updates(conn, updates)
        print(f"✅ 완료! {changed_count}개 수정, {deleted_count}개 삭제")

    conn.close()

    if not dry_run:
        print("\n다음 단계: python rag/ingestion/embed_to_pg.py")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="rag_documents chunk_text 정제")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="실제 DB 수정 없이 정제 결과만 미리 확인",
    )
    args = parser.parse_args()
    run(dry_run=args.dry_run)
