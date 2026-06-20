"""
노드 함수들 — LangGraph/순차 파이프라인 양쪽에서 공유.

각 노드: (PatientState) -> dict(부분 업데이트)
프레임워크에 의존하지 않으므로 단위 테스트가 쉽고, graph.py(LangGraph)와
pipeline.py(순차 실행) 모두에서 그대로 재사용된다.
"""
from __future__ import annotations

from typing import Any

from agents import comm, handoff, memory, risk, scenarios
from agents.state import PatientState
from domain.models import Conflict, Drug, PatientProfile, Severity
from tools.datasource import DataSource, get_default_datasource


def intake_node(state: PatientState, ds: DataSource | None = None) -> dict[str, Any]:
    """원문 약명 나열 -> 정규화된 Drug 목록으로 프로필 보강.
    이미 profile.drugs 가 채워져 있으면 그대로 사용(테스트/구조화 입력 경로)."""
    ds = ds or get_default_datasource()
    profile = state["profile"]
    if profile.drugs:
        return {"profile": profile}
    names = [t.strip() for t in state.get("raw_input", "").replace(",", "\n").splitlines() if t.strip()]
    drugs: list[Drug] = []
    for n in names:
        d = ds.resolve_drug(n)
        if d:
            drugs.append(d)
    profile.drugs = drugs
    return {"profile": profile}


def data_node(state: PatientState, ds: DataSource | None = None) -> dict[str, Any]:
    ds = ds or get_default_datasource()
    records = risk.collect_records(state["profile"], ds)
    return {"records_by_drug": records}


def risk_node(state: PatientState) -> dict[str, Any]:
    conflicts = risk.detect_conflicts(state["profile"], state["records_by_drug"])
    return {"conflicts": conflicts}


def comm_node(state: PatientState) -> dict[str, Any]:
    profile, conflicts = state["profile"], state["conflicts"]
    summary = comm.refine_with_llm(comm.build_summary(profile, conflicts))
    return {
        "summary": summary,
        "questions": comm.build_questions(conflicts),
        "schedule": comm.build_schedule(profile),
    }


def gate_node(state: PatientState) -> dict[str, Any]:
    needs = any(c.severity == Severity.HIGH for c in state.get("conflicts", []))
    return {"needs_pharmacist": needs}


def eval_node(state: PatientState) -> dict[str, Any]:
    """Evaluation Agent (간이): 모든 경고가 (1) 출처를 갖고 (2) 프로필에 실제 존재하는
    약만 참조하는지 검증. 위반 시 보고 -> 환각/근거없는 단정 차단."""
    conflicts: list[Conflict] = state.get("conflicts", [])
    present = {d.name for d in state["profile"].drugs}
    missing_source, hallucinated = [], []
    for c in conflicts:
        if not (c.source and c.source.provider):
            missing_source.append(c.headline())
        for name in c.drugs:
            if name not in present:
                hallucinated.append(name)
    report = {
        "total_conflicts": len(conflicts),
        "all_cited": len(missing_source) == 0,
        "missing_source": missing_source,
        "hallucinated_drugs": sorted(set(hallucinated)),
        "passed": len(missing_source) == 0 and not hallucinated,
    }
    return {"eval_report": report}


def handoff_node(state: PatientState) -> dict[str, Any]:
    return handoff.handoff_node(state)


def memory_node(state: PatientState, ds: DataSource | None = None) -> dict[str, Any]:
    ds = ds or get_default_datasource()
    profile = state["profile"]
    prev = memory.load_previous(profile.profile_id)
    delta = scenarios.compute_delta(prev, profile, ds)
    memory.save_profile(profile)
    return {"memory_diff": {"first_visit": delta["first_visit"],
                            "added": delta["added_drugs"], "removed": delta["removed_drugs"]},
            "new_conflicts": delta["new_conflicts"]}
