from __future__ import annotations

import argparse
import json
from typing import List, Optional

from dotenv import load_dotenv

from .generate import generate_answer
from .ingest import ingest_paths
from .search import search

# 문서 적재
def _cmd_ingest(args: argparse.Namespace) -> int:
    res = ingest_paths(
        paths=args.path, 
        glob_pattern=args.glob, 
        doc_type=args.doc_type,
        clear=args.clear
    )
    print(json.dumps({"files": res.files, "chunks": res.chunks}, ensure_ascii=False))
    return 0

# 검색
def _cmd_search(args: argparse.Namespace) -> int:
    where = json.loads(args.where) if args.where else None
    hits = search(query=args.query, k=args.k, where=where)
    payload = [
        {
            "score": h.score,
            "metadata": h.metadata,
            "content": h.content,
        }
        for h in hits
    ]
    print(json.dumps(payload, ensure_ascii=False))
    return 0

# 최종 답변 생성
def _cmd_generate(args: argparse.Namespace) -> int:
    where = json.loads(args.where) if args.where else None
    result = generate_answer(query=args.query, k=args.k, where=where)
    
    payload = {
        "answer": result.answer,
        "hits": [
            {
                "score": h.score,
                "metadata": h.metadata,
                "content": h.content,
            }
            for h in result.hits
        ]
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    load_dotenv()

    p = argparse.ArgumentParser(prog="rag.jm")
    sub = p.add_subparsers(dest="cmd", required=True)
    
    # 문서 적재 옵션 설명
    # --path: 문서가 있는 경로
    # --glob: glob 패턴
    # --doc-type: 문서 유형
    # --clear: 기존 데이터 삭제
    pi = sub.add_parser("ingest", help="Ingest documents into PGVector")
    pi.add_argument("--path", action="append", required=True, help="File or directory path (repeatable)")
    pi.add_argument("--glob", default=None, help='Glob pattern when path is a directory, e.g. "*.pdf"')
    pi.add_argument("--doc-type", default="doc", help="Metadata: doc_type")
    pi.add_argument("--clear", action="store_true", help="Clear existing data before ingestion")
    pi.set_defaults(func=_cmd_ingest)

    # 검색 옵션
    # --query: 검색어
    # --k: 검색 결과 수
    # --where: 메타데이터 필터
    ps = sub.add_parser("search", help="Search similar chunks from PGVector")
    ps.add_argument("--query", required=True)
    ps.add_argument("--k", type=int, default=5)
    ps.add_argument("--where", default=None, help='JSON filter for metadata, e.g. {"doc_type":"law"}')
    ps.set_defaults(func=_cmd_search)

    # 답변 생성 옵션
    # --query: 검색어
    # --k: 검색 결과 수
    # --where: 메타데이터 필터
    pg = sub.add_parser("generate", help="Generate answer using LLM based on searched chunks")
    pg.add_argument("--query", required=True)
    pg.add_argument("--k", type=int, default=5)
    pg.add_argument("--where", default=None, help='JSON filter for metadata, e.g. {"doc_type":"law"}')
    pg.set_defaults(func=_cmd_generate)

    args = p.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
