"""
판례 PDF 85개 → LLM 엔티티 추출 → Neo4j 그래프 빌드

실행: python -m scripts.build_graph
사전 조건: docker compose up neo4j -d
"""

import sys
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8")

from backend.graph.extract_entities import extract_all
from backend.graph.graph_builder import build_graph

print("=== 1단계: 판례 엔티티 추출 (LLM) ===\n")
entities = extract_all("docs/pdf/판례")

print(f"\n추출 완료: {len(entities)}개 판례")
print(f"  법조문 보유: {sum(1 for e in entities if e.cited_laws)}개")
print(f"  쟁점 보유: {sum(1 for e in entities if e.issues)}개")

print(f"\n=== 2단계: Neo4j 그래프 빌드 ===\n")
build_graph(entities)

print("\n=== 완료! ===")
