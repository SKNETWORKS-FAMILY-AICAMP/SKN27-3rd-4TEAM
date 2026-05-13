# [DEPRECATED] 이 파일은 더 이상 사용하지 않습니다.
# ChromaDB 임베딩 파이프라인은 pgvector 로 완전히 대체되었습니다.
#
# 임베딩 적재는 rag/ingestion/embed_to_pg.py 를 사용하세요.
#
# 올바른 실행 순서:
#   1. python rag/scripts/pdf_pipeline.py      (PDF → PostgreSQL rag_documents)
#   2. python rag/ingestion/clean_chunks.py    (청크 텍스트 정제)
#   3. python rag/ingestion/embed_to_pg.py     (pgvector 임베딩 적재)
#   4. python rag/ingestion/build_graph.py     (Neo4j 지식 그래프 구축)

raise RuntimeError(
    "embed_to_chroma.py 는 폐기되었습니다. "
    "rag/ingestion/embed_to_pg.py 를 실행하세요."
)
python test_virtual_contract.py