"""
워크플로우 조립.

build_graph(): LangGraph StateGraph 로 노드를 연결(트랙2 요구사항 충족).
run_pipeline(): langgraph 미설치 환경에서도 동일 노드를 순차 실행하는 폴백.

두 경로 모두 agents/nodes.py 의 같은 함수를 쓰므로 동작이 일치한다.
"""
from __future__ import annotations

import logging

from agents import nodes
from agents.state import PatientState

logger = logging.getLogger(__name__)


def build_graph():
    """LangGraph 그래프 컴파일. langgraph 필요: pip install langgraph"""
    from langgraph.graph import START, END, StateGraph

    g = StateGraph(PatientState)
    g.add_node("intake", nodes.intake_node)
    g.add_node("data", nodes.data_node)
    g.add_node("risk", nodes.risk_node)
    g.add_node("comm", nodes.comm_node)
    g.add_node("handoff", nodes.handoff_node)
    g.add_node("gate", nodes.gate_node)
    g.add_node("eval", nodes.eval_node)
    g.add_node("memory", nodes.memory_node)

    g.add_edge(START, "intake")
    g.add_edge("intake", "data")
    g.add_edge("data", "risk")
    g.add_edge("risk", "comm")
    g.add_edge("comm", "handoff")
    g.add_edge("handoff", "gate")
    g.add_edge("gate", "eval")
    g.add_edge("eval", "memory")
    g.add_edge("memory", END)
    return g.compile()


def run_pipeline(state: PatientState) -> PatientState:
    """순차 폴백 실행기."""
    pipeline = [
        nodes.intake_node,
        nodes.data_node,
        nodes.risk_node,
        nodes.comm_node,
        nodes.handoff_node,
        nodes.gate_node,
        nodes.eval_node,
        nodes.memory_node,
    ]
    for fn in pipeline:
        state.update(fn(state))  # type: ignore[arg-type]
    return state


def run(state: PatientState) -> PatientState:
    """langgraph 가 있으면 그래프로, 없으면 순차로 실행.

    LangGraph 실행이 실패하면 순차로 폴백하되 '조용히' 빠지지 않도록 경고를 남긴다.
    (langgraph 버전 변화 등으로 그래프가 깨졌는데 아무도 모르는 상황 방지 — 동작은 유지.)
    """
    try:
        app = build_graph()
        return app.invoke(state)  # type: ignore[return-value]
    except Exception:
        logger.warning(
            "LangGraph 실행 실패 → 순차 폴백(run_pipeline). 그래프가 깨졌을 수 있어 점검 필요.",
            exc_info=True,
        )
        return run_pipeline(state)
