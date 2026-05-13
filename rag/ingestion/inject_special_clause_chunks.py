"""
전세계약 특약(特約) 키워드 임베딩 보강 스크립트
================================================
목적: QA005 특약 항목의 키워드 커버리지(수리비·임차인·특약·원상복구)를
      높이기 위해 합성 청크를 rag_documents 테이블에 INSERT하고 임베딩합니다.

실행:
  python rag/ingestion/inject_special_clause_chunks.py          # 주입 + 임베딩
  python rag/ingestion/inject_special_clause_chunks.py --dry-run  # 주입만 (임베딩 skip)
"""

from __future__ import annotations

import argparse
import os
import sys
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import psycopg2
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langchain_postgres import PGVector

# ── 설정 ──────────────────────────────────────────────────────
DB_CONFIG = {
    "host":     os.getenv("DB_HOST", "localhost"),
    "port":     int(os.getenv("DB_PORT", 5432)),
    "database": os.getenv("DB_NAME", "jeonse_risk"),
    "user":     os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", "risk1234"),
}
CONNECTION_STRING = (
    f"postgresql+psycopg2://{DB_CONFIG['user']}:{DB_CONFIG['password']}"
    f"@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}"
)
OPENAI_API_KEY  = os.getenv("OPENAI_API_KEY", "")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-large")
COLLECTION_NAME = os.getenv("PG_VECTOR_COLLECTION", "jeonse_docs")

INJECT_SOURCE = "synthetic_special_clause_augment"
INJECT_PREFIX = INJECT_SOURCE  # DELETE 시 LIKE 패턴용

# ── 합성 청크 데이터 ──────────────────────────────────────────
# 키워드: 수리비, 임차인, 특약, 원상복구 (QA005 실패 원인)
# file_name에 doc_type을 포함시켜 (file_name, chunk_index) 유니크 제약 회피
SPECIAL_CLAUSE_CHUNKS: list[dict] = [
    {
        "doc_type": "사례집",
        "title": "전세계약 특약 위험 유형별 분석",
        "file_name": f"{INJECT_SOURCE}_사례집_1",
        "chunk_index": 0,
        "chunk_text": (
            "전세계약서의 특약사항은 임대인과 임차인이 별도로 합의한 조항으로, "
            "표준 계약 조항과 달리 당사자 의사에 따라 임차인에게 불리하게 작성될 수 있습니다. "
            "대표적인 위험 특약 유형으로는 ① 수리비 전액 임차인 부담 특약, "
            "② 원상복구 범위를 과도하게 확대한 특약, "
            "③ 보증금 반환 시점을 다음 임차인 입주 이후로 미루는 특약, "
            "④ 임대인의 담보권 추가 설정을 제한하지 않은 특약이 있습니다."
        ),
    },
    {
        "doc_type": "사례집",
        "title": "전세계약 특약 위험 유형별 분석",
        "file_name": f"{INJECT_SOURCE}_사례집_2",
        "chunk_index": 0,
        "chunk_text": (
            "수리비 관련 특약: 민법 제623조에 따라 임대인은 목적물을 사용·수익에 필요한 상태로 "
            "유지할 의무를 부담합니다. 따라서 '모든 수리비는 임차인이 부담한다'는 특약은 "
            "임차인의 통상적 사용으로 인한 손모(소모)까지 임차인에게 전가하는 것으로, "
            "법적으로 임대인의 수선 의무를 과도하게 배제한 약정이 될 수 있습니다. "
            "계약 전 수리비 부담 범위를 '임차인의 고의·과실로 인한 파손에 한정'하도록 "
            "특약 문구를 수정 요청하는 것이 바람직합니다."
        ),
    },
    {
        "doc_type": "사례집",
        "title": "전세계약 특약 위험 유형별 분석",
        "file_name": f"{INJECT_SOURCE}_사례집_3",
        "chunk_index": 0,
        "chunk_text": (
            "원상복구 관련 특약: '임차인은 퇴거 시 원상복구 의무를 진다'는 특약은 일반적이지만, "
            "'도배·장판·전등·에어컨 설치물 일체를 원상복구한다'처럼 구체적 목록을 나열하거나 "
            "신규 도배·장판을 의무화하는 경우 임차인에게 과도한 비용 부담이 발생합니다. "
            "원상복구 의무는 임차인의 고의·과실로 인한 손상에 한정되며, "
            "통상적인 사용으로 인한 자연 소모·노후는 원상복구 대상이 아닙니다. "
            "특약에 '통상 사용으로 인한 자연 소모는 제외'라는 문구를 삽입하도록 협의하세요."
        ),
    },
    {
        "doc_type": "법령",
        "title": "특약 관련 주요 법령 — 민법·주택임대차보호법",
        "file_name": f"{INJECT_SOURCE}_법령_1",
        "chunk_index": 0,
        "chunk_text": (
            "주택임대차보호법 제10조(강행규정): 이 법의 규정에 위반된 약정으로서 임차인에게 "
            "불리한 것은 효력이 없습니다. 따라서 임차인의 법적 권리(대항력, 우선변제권, "
            "보증금 반환청구권)를 약화시키는 특약 조항은 무효입니다. "
            "민법 제623조: 임대인은 목적물을 임차인이 약정한 방법으로 사용·수익할 수 있게 할 의무를 부담하며, "
            "수리·보수 의무는 원칙적으로 임대인에게 귀속됩니다. "
            "임차인이 특약으로 수리비 전부를 부담하기로 한 경우에도, "
            "임대인의 수선 의무를 전부 면제하는 특약은 신의칙 위반으로 일부 무효가 될 수 있습니다."
        ),
    },
    {
        "doc_type": "법령",
        "title": "특약 관련 주요 법령 — 민법·주택임대차보호법",
        "file_name": f"{INJECT_SOURCE}_법령_2",
        "chunk_index": 0,
        "chunk_text": (
            "계약서 특약사항 작성 시 임차인 보호를 위한 필수 방어 특약:\n"
            "1. 잔금 지급 전후 임대인은 추가 근저당권·담보 설정을 하지 않는다.\n"
            "2. 원상복구는 임차인의 고의·과실로 인한 훼손에 한하며, 통상 사용·노후로 인한 자연 소모는 제외한다.\n"
            "3. 수리비 부담은 임차인의 고의·과실로 인한 파손에만 적용하며, 임대인 귀책 하자는 임대인이 부담한다.\n"
            "4. 계약 종료 즉시 보증금을 반환하며, 다음 임차인 입주를 조건으로 반환을 지체하지 않는다.\n"
            "5. 임차인은 입주 즉시 전입신고 및 확정일자를 취득할 권리를 갖는다."
        ),
    },
    {
        "doc_type": "판례",
        "title": "특약 관련 판례 — 수리비·원상복구 분쟁",
        "file_name": f"{INJECT_SOURCE}_판례_1",
        "chunk_index": 0,
        "chunk_text": (
            "대법원 판례에 따르면 임차인이 임대차 종료 후 목적물을 반환할 때 원상복구 의무는 "
            "임차인이 계약 당시 상태로 복구하는 것을 의미하며, "
            "임차인의 통상적인 사용으로 인한 손모·노후는 원상복구 대상에 포함되지 않습니다. "
            "특약으로 원상복구 범위를 확대하더라도 통상 손모까지 포함하는 특약은 "
            "임차인에게 불리한 약정으로 주택임대차보호법 제10조에 따라 무효입니다. "
            "수리비 전액 임차인 부담 특약의 경우, 임대인의 수선 의무를 전부 면제하는 내용은 "
            "강행규정에 반해 무효로 볼 수 있습니다."
        ),
    },
    {
        "doc_type": "서식",
        "title": "전세계약 특약사항 표준 체크리스트",
        "file_name": f"{INJECT_SOURCE}_서식_1",
        "chunk_index": 0,
        "chunk_text": (
            "[전세계약 특약 체크리스트]\n"
            "□ 수리비: 임차인 고의·과실 파손만 부담 (임대인 귀책 하자는 임대인 부담) 문구 확인\n"
            "□ 원상복구: 통상 사용으로 인한 자연 소모·노후는 제외 문구 확인\n"
            "□ 보증금 반환: 계약 종료 즉시 반환 (다음 임차인 조건 없음) 문구 확인\n"
            "□ 담보 추가: 잔금일 이후 임대인의 추가 담보권 설정 금지 문구 확인\n"
            "□ 전입신고·확정일자: 임차인의 즉시 취득 권리 보장 문구 확인\n"
            "□ 하자 통보: 임차인이 발견한 하자 임대인 통보 후 임대인 책임 수리 문구 확인\n"
            "위 항목 중 임차인에게 불리하거나 누락된 항목이 있으면 계약 전 수정·추가를 요청하세요."
        ),
    },
]


# ── DB 삽입 ────────────────────────────────────────────────────

def insert_chunks(conn, chunks: list[dict]) -> list[int]:
    """rag_documents 테이블에 합성 청크 INSERT. 중복 방지를 위해 file_name 기준 삭제 후 삽입."""
    cur = conn.cursor()

    # 기존 합성 데이터 제거 (재실행 안전) — LIKE 패턴으로 모든 합성 청크 삭제
    cur.execute("DELETE FROM rag_documents WHERE file_name LIKE %s", (f"{INJECT_PREFIX}%",))
    deleted = cur.rowcount
    if deleted:
        print(f"  ♻️  기존 합성 청크 {deleted}개 삭제")

    inserted_ids: list[int] = []
    for chunk in chunks:
        cur.execute(
            """
            INSERT INTO rag_documents (doc_type, title, file_name, chunk_index, chunk_text, vector_id)
            VALUES (%s, %s, %s, %s, %s, NULL)
            RETURNING id
            """,
            (chunk["doc_type"], chunk["title"], chunk["file_name"],
             chunk["chunk_index"], chunk["chunk_text"]),
        )
        row = cur.fetchone()
        if row:
            inserted_ids.append(row[0])

    conn.commit()
    cur.close()
    print(f"  ✅ 합성 청크 {len(inserted_ids)}개 INSERT 완료")
    return inserted_ids


# ── 임베딩 ────────────────────────────────────────────────────

def embed_chunks(conn, inserted_ids: list[int]) -> None:
    """삽입된 청크를 임베딩하여 pgvector에 저장."""
    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY가 설정되지 않았습니다.")

    # 방금 삽입한 청크 조회
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, doc_type, title, file_name, chunk_index, chunk_text
        FROM rag_documents
        WHERE id = ANY(%s) AND vector_id IS NULL
        ORDER BY id
        """,
        (inserted_ids,),
    )
    rows = cur.fetchall()
    cur.close()

    chunks = [
        {"id": r[0], "doc_type": r[1], "title": r[2],
         "file_name": r[3], "chunk_index": r[4], "chunk_text": r[5]}
        for r in rows
    ]

    print(f"  📦 임베딩 모델: {EMBEDDING_MODEL}")
    embeddings = OpenAIEmbeddings(model=EMBEDDING_MODEL, openai_api_key=OPENAI_API_KEY)
    vector_store = PGVector(
        collection_name=COLLECTION_NAME,
        connection=CONNECTION_STRING,
        embeddings=embeddings,
        use_jsonb=True,
        pre_delete_collection=False,
    )

    documents = [
        Document(
            page_content=c["chunk_text"],
            metadata={
                "doc_type":    c["doc_type"],
                "title":       c["title"],
                "file_name":   c["file_name"],
                "chunk_index": c["chunk_index"],
                "row_id":      c["id"],
            },
        )
        for c in chunks
    ]
    ids = [f"chunk_{c['id']}" for c in chunks]
    vector_store.add_documents(documents=documents, ids=ids)

    # vector_id 업데이트
    cur = conn.cursor()
    cur.executemany(
        "UPDATE rag_documents SET vector_id = %s WHERE id = %s",
        [(f"chunk_{c['id']}", c["id"]) for c in chunks],
    )
    conn.commit()
    cur.close()
    print(f"  ✅ {len(chunks)}개 청크 pgvector 임베딩 완료")


# ── 메인 ─────────────────────────────────────────────────────

def run(dry_run: bool = False) -> None:
    print("=" * 55)
    print("  특약 키워드 임베딩 보강 시작")
    print("=" * 55)
    print(f"  대상 청크: {len(SPECIAL_CLAUSE_CHUNKS)}개")
    print(f"  doc_type: 사례집 {sum(1 for c in SPECIAL_CLAUSE_CHUNKS if c['doc_type']=='사례집')}개 | "
          f"법령 {sum(1 for c in SPECIAL_CLAUSE_CHUNKS if c['doc_type']=='법령')}개 | "
          f"판례 {sum(1 for c in SPECIAL_CLAUSE_CHUNKS if c['doc_type']=='판례')}개 | "
          f"서식 {sum(1 for c in SPECIAL_CLAUSE_CHUNKS if c['doc_type']=='서식')}개\n")

    conn = psycopg2.connect(**DB_CONFIG)

    print("[1/2] DB 삽입...")
    inserted_ids = insert_chunks(conn, SPECIAL_CLAUSE_CHUNKS)

    if dry_run:
        print("\n  --dry-run 모드: 임베딩 단계 스킵 (DB INSERT만 완료)")
        conn.close()
        return

    print("\n[2/2] pgvector 임베딩...")
    embed_chunks(conn, inserted_ids)

    conn.close()
    print("\n" + "=" * 55)
    print("  완료! 특약 관련 합성 청크 임베딩 보강 완료")
    print("  재검증: python test_rag_accuracy.py --verbose")
    print("=" * 55)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="특약 키워드 임베딩 보강")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="DB INSERT만 실행하고 임베딩은 skip합니다.",
    )
    args = parser.parse_args()
    run(dry_run=args.dry_run)
