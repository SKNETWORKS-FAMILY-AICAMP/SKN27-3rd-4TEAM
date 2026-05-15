import os
import json
import sys
import io
from neo4j import GraphDatabase
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from dotenv import load_dotenv

# 인코딩 설정
sys.stdout = io.TextIOWrapper(sys.stdout.detach(), encoding='utf-8')

load_dotenv()

class LegalConsultantAgent:
    def __init__(self):
        # 1. Neo4j 접속 설정
        self.driver = GraphDatabase.driver(
            os.getenv("NEO4J_URI", "bolt://localhost:7687"),
            auth=(os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASSWORD", "test1234"))
        )
        # 2. LLM 설정 (GPT-4o-mini 사용 - 상담의 질과 속도 최적화)
        self.llm = ChatOpenAI(
            model="gpt-4o-mini",
            api_key=os.getenv("OPENAI_API_KEY"),
            temperature=0
        )

    def close(self):
        self.driver.close()

    def identify_scenario(self, query):
        """사용자의 질문에서 어떤 사기 시나리오에 해당되는지 파악합니다."""
        routing_prompt = ChatPromptTemplate.from_messages([
            ("system", "사용자의 질문을 분석하여 다음 12가지 시나리오 중 가장 관련 깊은 것을 하나 선택하세요: "
                       "대리인 계약, 선순위 근저당, 신탁등기 사기, 중개인 결격, 대항력 시차, 세금 체납, "
                       "불법/위반 건축물, 다가구 선순위 보증금, 매매·전세 동시진행, 신분증 위조 사기, "
                       "보증보험 가입 불가, 보증금 미반환. 반드시 시나리오 명칭만 답변하세요."),
            ("user", "{query}")
        ])
        chain = routing_prompt | self.llm
        return chain.invoke({"query": query}).content.strip()

    def query_legal_data(self, scenario_name):
        """Neo4j에서 해당 시나리오와 연결된 법률 조항 및 AI 설명을 가져옵니다."""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (s:Scenario {name: $s_name})-[r:APPLIES_TO]->(d:LegalChunk)
                RETURN s.description as scenario_desc, r.explanation as reason, d.text as law_text
                LIMIT 5
            """, s_name=scenario_name)
            return [record for record in result]

    def synthesize_consultation(self, query, scenario_name, legal_records):
        """수집된 법률 데이터를 바탕으로 최종 상담 답변을 생성합니다."""
        if not legal_records:
            return "죄송합니다. 해당 상황에 대한 구체적인 법률 지식을 찾지 못했습니다. 전문가와 상담을 권장합니다."

        context = "\n".join([
            f"- 법률 근거: {rec['law_text'][:500]}\n- 전문가 해석: {rec['reason']}"
            for rec in legal_records
        ])
        
        consult_prompt = ChatPromptTemplate.from_messages([
            ("system", f"당신은 전세 사기 예방 전문 법률 상담사입니다. "
                       f"현재 상황: {scenario_name}\n"
                       f"참고 법률 데이터:\n{context}\n\n"
                       "위 데이터를 바탕으로 사용자의 질문에 대해 법적 근거를 명시하며 상담 답변을 작성하세요. "
                       "반드시 '위험 진단', '법적 근거', '대응 방안' 섹션으로 나누어 답변하세요."),
            ("user", "{query}")
        ])
        chain = consult_prompt | self.llm
        return chain.invoke({"query": query}).content

    def ask(self, user_query):
        """전체 상담 프로세스 실행"""
        print(f"\n[Consultation Start] Query: {user_query}")
        
        # 1. 시나리오 파악
        scenario = self.identify_scenario(user_query)
        print(f"Scenario Identified: {scenario}")
        
        # 2. 지식 그래프 탐색
        legal_data = self.query_legal_data(scenario)
        print(f"Evidence Found: {len(legal_data)} items")
        
        # 3. 최종 상담 생성
        print("Generating Legal Consultation Answer...\n")
        answer = self.synthesize_consultation(user_query, scenario, legal_data)
        
        return answer

if __name__ == "__main__":
    agent = LegalConsultantAgent()
    try:
        print("\n==================================================")
        print("🏛️  전세 사기 예방 법률 상담소에 오신 것을 환영합니다!")
        print("   (종료하려면 '종료' 또는 'exit'를 입력하세요)")
        print("==================================================\n")
        
        while True:
            user_input = input("👤 질문을 입력하세요: ").strip()
            
            if user_input.lower() in ['종료', 'exit', 'quit', 'q']:
                print("\n상담을 종료합니다. 안전한 거래 되세요! 👋")
                break
            
            if not user_input:
                continue
                
            try:
                result = agent.ask(user_input)
                print("\n================ [법률 상담 결과] ================")
                print(result)
                print("==================================================\n")
            except Exception as e:
                print(f"❌ 상담 중 오류가 발생했습니다: {e}")
                
    finally:
        agent.close()
