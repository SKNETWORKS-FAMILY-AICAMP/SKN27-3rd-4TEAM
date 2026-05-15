import os
import sys
import io
from neo4j import GraphDatabase
from dotenv import load_dotenv

# 인코딩 설정 (윈도우 한글 깨짐 방지)
sys.stdout = io.TextIOWrapper(sys.stdout.detach(), encoding='utf-8')

load_dotenv()

def restore_from_cypher(file_path):
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "test1234")
    
    driver = GraphDatabase.driver(uri, auth=(user, password))
    
    if not os.path.exists(file_path):
        print(f"❌ Error: {file_path} 파일을 찾을 수 없습니다.")
        return

    print(f"📂 백업 파일 읽는 중: {file_path}")
    with open(file_path, "r", encoding="utf-8") as f:
        # 각 사이퍼 구문은 세미콜론(;)으로 구분되어 있음
        cypher_queries = f.read().split(";")

    with driver.session() as session:
        print("🧹 기존 지식 그래프 초기화 중 (Scenario, LegalChunk 관련)...")
        # 안전을 위해 관련 노드들만 삭제 (다른 데이터가 있을 수 있으므로)
        session.run("MATCH (s:Scenario) DETACH DELETE s")
        session.run("MATCH (l:LegalChunk) DETACH DELETE l")
        
        print(f"🚀 {len(cypher_queries)}개의 지식 조각 복구 시작...")
        count = 0
        for query in cypher_queries:
            clean_query = query.strip()
            if clean_query:
                try:
                    session.run(clean_query)
                    count += 1
                    if count % 100 == 0:
                        print(f"✅ {count}개 복구 완료...")
                except Exception as e:
                    print(f"⚠️ 오류 발생 (일부 구문): {e}")

    driver.close()
    print(f"\n✨ 복구 대성공! 총 {count}개의 지식 노드 및 관계가 복구되었습니다.")
    print("이제 'legal_agent_engine.py'를 실행하여 상담을 시작하실 수 있습니다!")

if __name__ == "__main__":
    restore_from_cypher("scenario_graph_backup.cypher")
