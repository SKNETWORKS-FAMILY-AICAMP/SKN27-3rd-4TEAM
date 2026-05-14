# rag/jm/standard/run_standard.py
# standard 폴더만 따로 복사해도 실행할 수 있는 독립 CLI입니다.

from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from dotenv import load_dotenv

try:
    from .answer import answer_standard_question
except ImportError:
    from answer import answer_standard_question


def main(argv: Optional[list[str]] = None) -> int:
    """질문을 입력받아 DB/RAG 없는 표준 LLM 답변을 출력합니다."""

    load_dotenv()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(prog="run_standard")
    parser.add_argument("--question", required=True, help="사용자가 묻는 일반 전세 관련 질문")
    args = parser.parse_args(argv)

    result = answer_standard_question(args.question)
    print(
        json.dumps(
            {
                "question": result.question,
                "answer": result.answer,
                "provider": result.provider,
                "model": result.model,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

