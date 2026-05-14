"""Deprecated Chroma embedding entrypoint.

This project now uses PostgreSQL pgvector for RAG embeddings. Keep this file as
an explicit no-op/deprecation guard so accidental execution does not run stale
Chroma code.

Use:
    python rag/ingestion/embed_to_pg.py
"""


def main() -> None:
    raise SystemExit(
        "rag/scripts/embed_to_chroma.py is deprecated and unused. "
        "Run rag/ingestion/embed_to_pg.py instead."
    )


if __name__ == "__main__":
    main()
