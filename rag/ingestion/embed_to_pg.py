"""
전세계약 위험 진단 에이전트 - pgvector 임베딩 적재 스크립트
역할: PostgreSQL rag_documents 테이블의 청크를 임베딩하여
      langchain_pg_embedding 테이블에 저장

실행: python rag/ingestion/embed_to_pg.py
"""

import os
import sys
import psycopg2
from dotenv import load_dotenv
from tqdm import tqdm

load_dotenv()
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from langchain_openai import OpenAIEmbeddings
from langchain_postgres import PGVector
from langchain_core.documents import Document

# ── 설정 ─────────────────────────────────────────────────────

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
EMBEDDING_MODEL = "text-embedding-3-small"
COLLECTION_NAME = "jeonse_docs"
BATCH_SIZE      = 50


# ── 미임베딩 청크 조회 ────────────────────────────────────────

def fetch_unembedded_chunks(conn) -> list[dict]:
    """vector_id가 NULL인 청크만 조회 (재처리 방지)"""
    cur = conn.cursor()
    cur.execute("""
        SELECT id, doc_type, title, file_name, chunk_index, chunk_text
        FROM rag_documents
        WHERE vector_id IS NULL
          AND chunk_text IS NOT NULL
          AND LENGTH(TRIM(chunk_text)) > 10
        ORDER BY id
    """)
    rows = cur.fetchall()
    cur.close()
    return [
        {
            "id": r[0], "doc_type": r[1], "title": r[2],
            "file_name": r[3], "chunk_index": r[4], "chunk_text": r[5],
        }
        for r in rows
    ]


def update_vector_ids(conn, id_pairs: list[tuple]) -> None:
    """임베딩 완료된 청크의 vector_id 업데이트"""
    cur = conn.cursor()
    cur.executemany(
        "UPDATE rag_documents SET vector_id = %s WHERE id = %s",
        id_pairs,
    )
    conn.commit()
    cur.close()


# ── 임베딩 + pgvector 적재 ────────────────────────────────────

def embed_and_store(chunks: list[dict], vector_store: PGVector) -> list[tuple]:
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
    return [(f"chunk_{c['id']}", c["id"]) for c in chunks]


# ── 메인 실행 ─────────────────────────────────────────────────

def run():
    print("=== pgvector 임베딩 적재 시작 ===\n")

    conn   = psycopg2.connect(**DB_CONFIG)
    chunks = fetch_unembedded_chunks(conn)

    if not chunks:
        print("✅ 적재할 새 청크가 없습니다. (모두 임베딩 완료)")
        conn.close()
        return

    print(f"📄 임베딩 대상 청크: {len(chunks)}개\n")

    embeddings = OpenAIEmbeddings(
        model=EMBEDDING_MODEL,
        openai_api_key=OPENAI_API_KEY,
    )

    vector_store = PGVector(
        collection_name=COLLECTION_NAME,
        connection=CONNECTION_STRING,
        embeddings=embeddings,
        use_jsonb=True,
        pre_delete_collection=False,
    )

    id_pairs: list[tuple] = []
    pbar = tqdm(range(0, len(chunks), BATCH_SIZE), desc="임베딩 배치")

    for i in pbar:
        batch = chunks[i: i + BATCH_SIZE]
        pbar.set_postfix_str(f"배치 {i // BATCH_SIZE + 1} ({len(batch)}개)")
        try:
            pairs = embed_and_store(batch, vector_store)
            id_pairs.extend(pairs)
            update_vector_ids(conn, pairs)
        except Exception as e:
            print(f"\n⚠️  배치 {i // BATCH_SIZE + 1} 실패: {e}")
            continue

    conn.close()
    print(f"\n✅ 완료! {len(id_pairs)}개 청크 pgvector 적재")
    print(f"   컬렉션: {COLLECTION_NAME}")


if __name__ == "__main__":
    run()
