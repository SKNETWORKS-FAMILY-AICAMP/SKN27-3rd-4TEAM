import os
import sys
import io
from neo4j import GraphDatabase
from dotenv import load_dotenv

# 인코딩 설정 (윈도우 한글 깨짐 방지)
sys.stdout = io.TextIOWrapper(sys.stdout.detach(), encoding='utf-8')

load_dotenv()

def audit_graph():
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "test1234")
    
    driver = GraphDatabase.driver(uri, auth=(user, password))
    
    with driver.session() as session:
        # 1. 관계 수 확인
        rel_count = session.run("MATCH ()-[r:APPLIES_TO]->() RETURN count(r) as count").single()["count"]
        # 2. 시나리오 수 확인
        scenario_count = session.run("MATCH (s:Scenario) RETURN count(s) as count").single()["count"]
        # 3. 법률 조항 수 확인
        chunk_count = session.run("MATCH (l:LegalChunk) RETURN count(l) as count").single()["count"]
        
        print("\n--- [📊 지식 그래프 복구 현황 보고서] ---")
        print(f"✅ 현재 복구된 관계: {rel_count}건")
        print(f"✅ 활성화된 시나리오: {scenario_count}개")
        print(f"✅ 매핑된 법률 조항: {chunk_count}건")
        print("------------------------------------------\n")
        
    driver.close()

if __name__ == "__main__":
    audit_graph()
