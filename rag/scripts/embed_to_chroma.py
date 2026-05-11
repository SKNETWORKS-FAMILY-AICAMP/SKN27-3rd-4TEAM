"""
전세계약 위험 진단 에이전트 - ChromaDB 임베딩 적재 스크립트
역할: PostgreSQL rag_documents 테이블의 청크를 임베딩하여 ChromaDB에 저장

실행 순서:
  1. python rag/scripts/pdf_pipeline.py   (PDF → PostgreSQL)
  2. python rag/scripts/embed_to_chroma.py  ← 이 스크립트
  3. python rag/scripts/build_graph.py    (Neo4j 그래프 구축)

실행: python rag/scripts/embed_to_chroma.py
"""

import os
import sys
import psycopg2
import chromadb
from chromadb.config import Settings as ChromaSettings
from dotenv import load_dotenv
from tqdm import tqdm

load_dotenv()

# 경로 설정
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from langchain_openai import OpenAIEmbeddings

# ── 설정 ─────────────────────────────────────────────────

DB_CONFIG = {
    "host":     os.getenv("DB_HOST", "localhost"),
    "port":     int(os.getenv("DB_PORT", 5432)),
    "database": os.getenv("DB_NAME", "jeonse_risk"),
    "user":     os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", "password"),
}

CHROMA_HOST       = os.getenv("CHROMA_HOST", "localhost")
CHROMA_PORT       = int(os.getenv("CHROMA_PORT", 8000))
CHROMA_COLLECTION = os.getenv("CHROMA_COLLECTION", "jeonse_docs")
OPENAI_API_KEY    = os.getenv("OPENAI_API_KEY", "")
EMBEDDING_MODEL   = "text-embedding-3-small"
BATCH_SIZE        = 50   # 한 번에 임베딩할 청크 수 (API 비용 최적화)


# ── ChromaDB 클라이언트 ───────────────────────────────────

def get_chroma_client() -> chromadb.HttpClient:
    return chromadb.HttpClient(
        host=CHROMA_HOST,
        port=CHROMA_PORT,
        settings=ChromaSettings(anonymized_telemetry=False),
    )


# ── PostgreSQL에서 미적재 청크 조회 ──────────────────────

def fetch_unembedded_chunks(conn) -> list[dict]:
    """
    vector_id가 NULL인 청크만 조회.
    (이미 임베딩된 청크는 재처리하지 않음 → 중복/비용 방지)
    """
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


def update_vector_ids(conn, id_vector_pairs: list[tuple[str, int]]) -> None:
    """임베딩 완료된 청크의 vector_id를 업데이트"""
    cur = conn.cursor()
    cur.executemany(
        "UPDATE rag_documents SET vector_id = %s WHERE id = %s",
        id_vector_pairs,  # (vector_id, row_id)
    )
    conn.commit()
    cur.close()


# ── 임베딩 + ChromaDB 적재 ────────────────────────────────

def embed_and_store(chunks: list[dict], collection, embeddings_model) -> list[tuple[str, int]]:
    """
    청크 배치를 임베딩하여 ChromaDB에 저장.

    Returns:
        [(vector_id, db_row_id), ...] - DB 업데이트용
    """
    texts     = [c["chunk_text"] for c in chunks]
    ids       = [f"chunk_{c['id']}" for c in chunks]
    metadatas = [
        {
            "doc_type":    c["doc_type"],
            "title":       c["title"],
            "file_name":   c["file_name"],
            "chunk_index": c["chunk_index"],
        }
        for c in chunks
    ]

    # 임베딩 생성
    vectors = embeddings_model.embed_documents(texts)

    # ChromaDB에 upsert
    collection.upsert(
        ids=ids,
        embeddings=vectors,
        documents=texts,
        metadatas=metadatas,
    )

    # (vector_id, db_row_id) 반환
    return [(f"chunk_{c['id']}", c["id"]) for c in chunks]


# ── 메인 실행 ─────────────────────────────────────────────

def run():
    print("=== ChromaDB 임베딩 적재 시작 ===\n")

    # 1. PostgreSQL 연결
    conn = psycopg2.connect(**DB_CONFIG)
    chunks = fetch_unembedded_chunks(conn)

    if not chunks:
        print("✅ 적재할 새 청크가 없습니다. (모두 임베딩 완료)")
        conn.close()
        return

    print(f"📄 임베딩 대상 청크: {len(chunks)}개\n")

    # 2. ChromaDB 컬렉션 준비
    chroma = get_chroma_client()
    try:
        collection = chroma.get_or_create_collection(
            name=CHROMA_COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )
    except Exception as e:
        print(f"❌ ChromaDB 연결 실패: {e}")
        conn.close()
        return

    # 3. OpenAI 임베딩 모델
    embeddings_model = OpenAIEmbeddings(
        model=EMBEDDING_MODEL,
        openai_api_key=OPENAI_API_KEY,
    )

    # 4. 배치 처리
    id_vector_pairs = []
    pbar = tqdm(range(0, len(chunks), BATCH_SIZE), desc="임베딩 배치")

    for i in pbar:
        batch = chunks[i: i + BATCH_SIZE]
        pbar.set_postfix_str(f"배치 {i//BATCH_SIZE + 1} ({len(batch)}개)")

        try:
            pairs = embed_and_store(batch, collection, embeddings_model)
            id_vector_pairs.extend(pairs)

            # 배치마다 DB 업데이트 (중간 실패 시 진행 상황 보존)
            update_vector_ids(conn, pairs)

        except Exception as e:
            print(f"\n⚠️  배치 {i//BATCH_SIZE + 1} 실패: {e}")
            continue

    conn.close()

    print(f"\n✅ 완료! {len(id_vector_pairs)}개 청크 ChromaDB 적재")
    print(f"   컬렉션: {CHROMA_COLLECTION}")
    print(f"   총 문서 수: {collection.count()}")


if __name__ == "__main__":
    run()
