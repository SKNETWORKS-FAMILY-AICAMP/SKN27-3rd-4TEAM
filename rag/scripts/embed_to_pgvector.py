"""
전세계약 위험 진단 에이전트 - pgvector 임베딩 적재 스크립트  (신규 v2)

embed_to_chroma.py를 대체합니다.
기존: PostgreSQL rag_documents → ChromaDB
변경: PostgreSQL rag_documents → pgvector (LangChain PGVector)
     → rag_pipeline.py의 VectorStore.similarity_search()와 직접 연결

실행 순서:
  1. python rag/scripts/pdf_pipeline.py       (PDF → rag_documents)
  2. python rag/scripts/embed_to_pgvector.py  ← 이 스크립트
  3. python rag/scripts/build_graph.py        (Neo4j 그래프 구축)

실행: python rag/scripts/embed_to_pgvector.py
"""

from __future__ import annotations

import os
import sys
import json
import time
import psycopg2
from dotenv import load_dotenv
from tqdm import tqdm

load_dotenv()

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

# ── 설정 ─────────────────────────────────────────────────

DB_CONFIG = {
    "host":     os.getenv("DB_HOST", "localhost"),
    "port":     int(os.getenv("DB_PORT", 5432)),
    "database": os.getenv("DB_NAME", "jeonse_risk"),
    "user":     os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", "risk1234"),
}

OPENAI_API_KEY    = os.getenv("OPENAI_API_KEY", "")
EMBEDDING_MODEL   = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
PG_COLLECTION     = os.getenv("PG_VECTOR_COLLECTION", "jeonse_docs")
BATCH_SIZE        = 50    # 한 번에 임베딩할 청크 수 (API 비용/속도 균형)
MIN_TEXT_LEN      = 30    # 이 미만이면 임베딩 스킵

# ── PostgreSQL 연결 문자열 ────────────────────────────────

def _pg_url() -> str:
    cfg = DB_CONFIG
    return (
        f"postgresql+psycopg2://{cfg['user']}:{cfg['password']}"
        f"@{cfg['host']}:{cfg['port']}/{cfg['database']}"
    )


# ── 미임베딩 청크 조회 ───────────────────────────────────

def fetch_unembedded(conn) -> list[dict]:
    """
    vector_id IS NULL인 청크만 조회.
    이미 임베딩된 청크는 재처리하지 않아 API 비용 중복을 방지.
    """
    cur = conn.cursor()
    cur.execute("""
        SELECT id, doc_type, title, file_name, chunk_index, chunk_text, source_law
        FROM rag_documents
        WHERE vector_id IS NULL
          AND chunk_text IS NOT NULL
          AND LENGTH(TRIM(chunk_text)) >= %s
        ORDER BY id
    """, (MIN_TEXT_LEN,))
    rows = cur.fetchall()
    cur.close()
    return [
        {
            "id":          r[0],
            "doc_type":    r[1],
            "title":       r[2],
            "file_name":   r[3],
            "chunk_index": r[4],
            "chunk_text":  r[5],
            "source_law":  r[6],
        }
        for r in rows
    ]


# ── vector_id 업데이트 ───────────────────────────────────

def mark_embedded(conn, chunk_ids: list[int], vector_ids: list[str]) -> None:
    """임베딩 완료된 청크에 vector_id를 기록."""
    cur = conn.cursor()
    cur.executemany(
        "UPDATE rag_documents SET vector_id = %s WHERE id = %s",
        [(vid, cid) for cid, vid in zip(chunk_ids, vector_ids)],
    )
    conn.commit()
    cur.close()


# ── LangChain PGVector에 배치 적재 ──────────────────────

def embed_and_store(chunks: list[dict]) -> list[str]:
    """
    청크 목록을 OpenAI로 임베딩 후 PGVector에 저장.
    저장된 document id 목록 반환.
    """
    from langchain_core.documents import Document
    from langchain_openai import OpenAIEmbeddings
    from langchain_postgres import PGVector

    embeddings = OpenAIEmbeddings(
        model=EMBEDDING_MODEL,
        openai_api_key=OPENAI_API_KEY,
    )

    store = PGVector(
        embeddings=embeddings,
        collection_name=PG_COLLECTION,
        connection=_pg_url(),
        use_jsonb=True,
    )

    docs = []
    for c in chunks:
        # source_law JSON 파싱
        source_law = None
        if c["source_law"]:
            try:
                source_law = json.loads(c["source_law"])
            except Exception:
                source_law = c["source_law"]

        docs.append(Document(
            page_content=c["chunk_text"],
            metadata={
                "rag_doc_id":  c["id"],
                "doc_type":    c["doc_type"],
                "title":       c["title"],
                "file_name":   c["file_name"],
                "chunk_index": c["chunk_index"],
                "source_law":  source_law,
            },
        ))

    ids = store.add_documents(docs)
    return ids


# ── 전체 실행 ────────────────────────────────────────────

def run() -> None:
    if not OPENAI_API_KEY:
        print("❌ OPENAI_API_KEY가 설정되지 않았습니다. .env 파일을 확인하세요.")
        sys.exit(1)

    conn = psycopg2.connect(**DB_CONFIG)
    chunks = fetch_unembedded(conn)
    conn.close()

    total = len(chunks)
    if total == 0:
        print("✅ 임베딩할 청크가 없습니다 (모두 완료됨).")
        return

    print(f"=== pgvector 임베딩 적재 시작: {total}개 청크 ===")
    print(f"    모델: {EMBEDDING_MODEL}  /  컬렉션: {PG_COLLECTION}  /  배치: {BATCH_SIZE}\n")

    processed = 0
    errors    = 0

    for start in tqdm(range(0, total, BATCH_SIZE), desc="임베딩 배치"):
        batch = chunks[start : start + BATCH_SIZE]
        try:
            ids = embed_and_store(batch)
            # vector_id 업데이트
            conn = psycopg2.connect(**DB_CONFIG)
            mark_embedded(conn, [c["id"] for c in batch], ids)
            conn.close()
            processed += len(batch)
        except Exception as e:
            errors += len(batch)
            print(f"\n  ❌ 배치 오류 (start={start}): {e}")
            # 일시적 API 오류 대비 잠시 대기 후 계속
            time.sleep(2)

    print(f"\n=== 완료 ===")
    print(f"  임베딩 성공: {processed}개")
    print(f"  오류:        {errors}개")
    if errors:
        print(f"  → 오류 청크는 vector_id=NULL 상태로 남아 있습니다.")
        print(f"    재실행하면 자동으로 재시도합니다.")


if __name__ == "__main__":
    run()
