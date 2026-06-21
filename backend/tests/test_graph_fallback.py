"""run() 폴백 관측성 — LangGraph가 깨지면 순차로 폴백하되 '조용히' 빠지지 않고 경고를 남긴다."""
from __future__ import annotations

import logging

import agents.graph as G
from domain.models import PatientProfile


def _boom():
    raise RuntimeError("graph compile boom")


def test_run_falls_back_and_warns(monkeypatch, caplog):
    # LangGraph 컴파일이 깨진 상황 강제
    monkeypatch.setattr(G, "build_graph", _boom)
    state = {
        "profile": PatientProfile(profile_id="t", alias="아버지", age=76),
        "raw_input": "가나정, 다라캡슐",
    }
    with caplog.at_level(logging.WARNING):
        out = G.run(state)

    # 1) 폴백해도 결과는 정상 산출(동작 유지)
    assert "conflicts" in out
    # 2) 조용히 빠지지 않고 경고 1건 이상 남긴다
    assert any("폴백" in r.message for r in caplog.records), "폴백 경고 로그가 없음"


def test_run_uses_graph_when_ok(monkeypatch, caplog):
    # 정상 경로에서는 폴백 경고가 없어야 한다
    with caplog.at_level(logging.WARNING):
        out = G.run({
            "profile": PatientProfile(profile_id="t2", alias="아버지", age=76),
            "raw_input": "가나정, 다라캡슐",
        })
    assert "conflicts" in out
    assert not any("폴백" in r.message for r in caplog.records)
