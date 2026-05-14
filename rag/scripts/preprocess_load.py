"""Deprecated market preprocessing loader.

The old implementation had unresolved merge-conflict markers and is no longer
part of the active RAG/chatbot path. It is intentionally disabled to avoid
accidental execution by scripts or containers.

Use the maintained ingestion scripts under rag/ingestion/ instead.
"""


def main() -> None:
    raise SystemExit(
        "rag/scripts/preprocess_load.py is deprecated and unused. "
        "Use rag/ingestion/load_market_data.py or the relevant rag/ingestion/* "
        "script instead."
    )


if __name__ == "__main__":
    main()
