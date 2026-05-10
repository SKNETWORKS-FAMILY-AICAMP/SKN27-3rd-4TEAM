from __future__ import annotations

import argparse
import json
from typing import List, Optional

from dotenv import load_dotenv

from .ingest import ingest_paths
from .search import search

# 문서 적재
def _cmd_ingest(args: argparse.Namespace) -> int:
    res = ingest_paths(paths=args.path, glob_pattern=args.glob, doc_type=args.doc_type)
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


def main(argv: Optional[List[str]] = None) -> int:
    load_dotenv()

    p = argparse.ArgumentParser(prog="rag.jm")
    sub = p.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("ingest", help="Ingest documents into PGVector")
    pi.add_argument("--path", action="append", required=True, help="File or directory path (repeatable)")
    pi.add_argument("--glob", default=None, help='Glob pattern when path is a directory, e.g. "*.pdf"')
    pi.add_argument("--doc-type", default="doc", help="Metadata: doc_type")
    pi.set_defaults(func=_cmd_ingest)

    ps = sub.add_parser("search", help="Search similar chunks from PGVector")
    ps.add_argument("--query", required=True)
    ps.add_argument("--k", type=int, default=5)
    ps.add_argument("--where", default=None, help='JSON filter for metadata, e.g. {"doc_type":"law"}')
    ps.set_defaults(func=_cmd_search)

    args = p.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
