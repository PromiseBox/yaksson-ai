"""
데모 실행기.

  python -m app.run_demo

골든 데이터(Mock) 기반으로 전체 워크플로우를 실행하고 결과를 보기 좋게 출력한다.
식약처 실데이터로 돌리려면: .env 에 DATA_SOURCE=mfds, MFDS_SERVICE_KEY=... 설정.
"""
from __future__ import annotations

from agents.graph import run
from agents.state import PatientState
from domain.models import PatientProfile
from tools.datasource import get_default_datasource


def sample_profile() -> PatientProfile:
    """아버지(76세) — 내과/정형외과 처방 + PIM 케이스 포함 (가상 골든 케이스)."""
    ds = get_default_datasource()
    profile = PatientProfile(profile_id="father-01", alias="아버지", age=76)
    for name in ["가나정", "다라캡슐", "마바정", "벤조원정"]:
        d = ds.resolve_drug(name)
        if d:
            profile.drugs.append(d)
    return profile


def render(state: PatientState) -> None:
    bar = "─" * 56
    print(bar)
    print("약손(藥손) AI — 다제약물 안전 점검 결과")
    print(bar)
    print(state["summary"])
    print()
    if state.get("needs_pharmacist"):
        print("⚠️  심각도 '상' 항목이 있어 약사·의사 확인이 권고됩니다.")
        print()
    print("[약사에게 물어볼 질문]")
    for i, q in enumerate(state.get("questions", []), 1):
        print(f"  {i}. {q}")
    print()
    print("[간이 복약표]")
    for slot, meds in state.get("schedule", {}).items():
        print(f"  {slot}: {', '.join(meds) if meds else '-'}")
    print()
    print("[변경 이력]", state.get("memory_diff"))
    new_c = state.get("new_conflicts", [])
    if new_c:
        print(f"[이번 방문 새 위험 {len(new_c)}건]")
        for c in new_c:
            print(f"  {c.headline()}")
    print("[품질 검증]", state.get("eval_report"))
    note = state.get("intervention_note", "")
    if note:
        print()
        print("[중재의견서 초안]")
        print(note)
    qr = state.get("qr_path")
    if qr:
        print(f"[QR 안전 프로필] {qr}")
    print(bar)


def main() -> None:
    state: PatientState = {"profile": sample_profile(), "raw_input": ""}
    result = run(state)
    render(result)


if __name__ == "__main__":
    main()
