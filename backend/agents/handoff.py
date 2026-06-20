from __future__ import annotations
import json, hashlib
from pathlib import Path
from domain.models import Conflict, PatientProfile, Severity

OUT_DIR = Path(__file__).resolve().parent.parent / "outputs"


def build_intervention_note(profile: PatientProfile, conflicts: list[Conflict]) -> str:
    """방문약사·자문약사용 약물 중재의견서 초안(마크다운 텍스트). 진단 아님."""
    lines = ["# 약물 중재 의견서 (초안)",
             f"- 대상자: {profile.alias} / 연령: {profile.age or '미상'}세",
             f"- 복용 약물({len(profile.drugs)}건): " + ", ".join(d.name for d in profile.drugs),
             "", "## 발견된 약물관련문제(DRP)"]
    if not conflicts:
        lines.append("- 등재 기준상 발견된 병용금기·중복·부적절약물 없음.")
    for i, c in enumerate(conflicts, 1):
        tag = f" [{', '.join(c.tags)}]" if c.tags else ""
        lines.append(f"{i}. ({c.severity.value}) {c.flag_type.value}{tag} — {' + '.join(c.drugs)}")
        lines.append(f"   - 근거: {c.reason}")
        lines.append(f"   - 출처: {c.source.provider}"
                     + (f" / {c.source.operation}" if c.source.operation else ""))
    lines += ["", "## 약사 의견(권고)",
              "- 위 항목은 식약처·심평원 등재 정보에 기반한 검토 보조 결과이며 최종 판단이 아닙니다.",
              "- 처방의·담당약사 확인 후 필요 시 중복·부적절약물 조정 상담을 권고합니다.",
              "", "## 메모", "- (자문약사 자유 기재)"]
    return "\n".join(lines)


def safety_profile_payload(profile: PatientProfile, conflicts: list[Conflict]) -> dict:
    return {
        "alias": profile.alias, "age": profile.age,
        "drugs": [d.name for d in profile.drugs],
        "high_risk": [f"{c.flag_type.value}:{'+'.join(c.drugs)}"
                      for c in conflicts if c.severity == Severity.HIGH],
        "note": "식약처 DUR 기반 검토 보조 / 최종 판단은 약사·의사",
    }


def generate_qr(payload: dict, name_hint: str = "profile") -> str | None:
    """QR PNG 생성. qrcode 미설치 시 None 반환(데모는 텍스트로 폴백)."""
    try:
        import qrcode
    except Exception:
        return None
    OUT_DIR.mkdir(exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False)
    fid = hashlib.md5(text.encode("utf-8")).hexdigest()[:8]
    path = OUT_DIR / f"qr_{name_hint}_{fid}.png"
    qrcode.make(text).save(path)
    return str(path)


def handoff_node(state: dict) -> dict:
    profile, conflicts = state["profile"], state.get("conflicts", [])
    payload = safety_profile_payload(profile, conflicts)
    return {
        "intervention_note": build_intervention_note(profile, conflicts),
        "qr_payload": payload,
        "qr_path": generate_qr(payload, profile.profile_id),
    }
