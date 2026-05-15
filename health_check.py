
import os
import sys
from pathlib import Path

# Add project root to sys.path
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.graph.graph_builder import get_driver
from backend.agents.chatbot import chat, create_session
from backend.agents.legal_agent import consult

def check_postgres():
    print("\n--- Checking Postgres (pgvector) ---")
    import psycopg2
    try:
        conn = psycopg2.connect(
            host="localhost",
            database="jeonse_risk",
            user="postgres",
            password="jeonse1234",
            port="5432"
        )
        print("✅ Postgres Connection Successful.")
        conn.close()
    except Exception as e:
        print(f"❌ Postgres Connection Failed: {e}")

def check_neo4j():
    print("--- Checking Neo4j ---")
    driver = get_driver()
    try:
        with driver.session() as session:
            result = session.run("MATCH (n) RETURN count(n) AS count").single()
            print(f"✅ Neo4j Connection Successful. Node count: {result['count']}")
    except Exception as e:
        print(f"❌ Neo4j Connection Failed: {e}")
    finally:
        driver.close()

def check_chatbot():
    print("\n--- Checking RAG Agent (Chatbot) ---")
    try:
        session = create_session()
        
        # Test 1: General
        print("Test 1: General Question")
        question1 = "전세가율이 높으면 왜 위험한가요?"
        answer1, sources1 = chat(question1, session)
        print(f"✅ General Answer: {answer1[:50]}...")
        
        # Test 2: Legal
        print("\nTest 2: Legal Question (RAG Check)")
        question2 = "보증금 대항력은 어떻게 갖추나요?"
        answer2, sources2 = chat(question2, session)
        print(f"✅ Legal Answer: {answer2[:50]}...")
        print(f"📚 Sources: {sources2}")
        
    except Exception as e:
        print(f"❌ Chatbot Test Failed: {e}")

if __name__ == "__main__":
    check_postgres()
    check_neo4j()
    check_chatbot()
