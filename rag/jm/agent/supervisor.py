from __future__ import annotations

import operator
from typing import Annotated, List, Union, TypedDict

from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode

from ..core.config import load_config
from .tools import search_documents

# 에이전트 상태 정의
class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], operator.add]
    next: str

# Supervisor 노드 정의
def create_supervisor(llm: ChatOpenAI, tools: list):
    tool_names = [t.name for t in tools]
    options = ["FINISH"] + tool_names
    
    system_prompt = (
        "당신은 사용자의 질문을 해결하기 위해 적절한 도구를 선택하는 관리자입니다.\n"
        "제공된 도구들을 사용하여 질문에 답하거나, 충분한 정보가 모였다면 FINISH를 선택하세요.\n"
        f"선택 가능한 다음 단계: {options}"
    )

    def supervisor_node(state: AgentState):
        messages = [
            {"role": "system", "content": system_prompt}
        ] + state["messages"]
        
        # LLM이 다음 단계를 결정하도록 강제 (함수 호출 방식 사용 가능)
        # 여기서는 단순화를 위해 결정 로직을 포함
        response = llm.bind_tools(tools).invoke(messages)
        
        # 도구 호출이 있으면 도구 노드로, 없으면 종료 혹은 직접 답변
        if response.tool_calls:
            return {"next": response.tool_calls[0]["name"]}
        return {"next": "FINISH"}

    return supervisor_node

# 그래프 구축
def get_agent_graph():
    cfg = load_config()
    llm = ChatOpenAI(model=cfg.llm_model, temperature=0)
    tools = [search_documents]
    
    workflow = StateGraph(AgentState)
    
    # 노드 추가
    workflow.add_node("supervisor", create_supervisor(llm, tools))
    workflow.add_node("tools", ToolNode(tools))
    
    # 에지 정의
    workflow.add_edge("tools", "supervisor")
    
    # 조건부 에지 (Supervisor의 결정에 따라)
    workflow.add_conditional_edges(
        "supervisor",
        lambda x: x["next"],
        {
            "search_documents": "tools",
            "FINISH": END
        }
    )
    
    workflow.set_entry_point("supervisor")
    return workflow.compile()

# 실행 함수
def run_agent(query: str):
    graph = get_agent_graph()
    inputs = {"messages": [HumanMessage(content=query)]}
    
    # 최종 답변을 추출하기 위해 스트리밍 혹은 전체 결과 반환
    final_state = graph.invoke(inputs)
    return final_state["messages"][-1].content
