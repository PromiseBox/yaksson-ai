"""
보호자 커뮤니케이션 (Caregiver Comm).

위험 판정(Conflict)을 보호자가 알아들을 수 있는 말로 변환한다.
- 기본은 '템플릿' 생성(키 불필요, 데모 안정적).
- LLM_PROVIDER=claude 등으로 설정하면 refine_with_llm 훅에서 문장을 더 자연스럽게 다듬는다.
  (실제 LLM 호출 구현은 역할 C/D가 채움; 여기선 인터페이스만.)
"""
from __future__ import annotations

from agents.josa import eul_reul, eun_neun, i_ga, wa_gwa
from domain.models import Conflict, PatientProfile, Severity

_SEV_LABEL = {
    Severity.HIGH: "지금 약사에게 꼭 확인하세요",
    Severity.MEDIUM: "주의가 필요합니다",
    Severity.LOW: "참고하세요",
}


def build_summary(profile: PatientProfile, conflicts: list[Conflict]) -> str:
    alias = profile.alias
    if not conflicts:
        return (f"{i_ga(alias)} 복용 중인 약 {len(profile.drugs)}건을 식약처 의약품안전사용(DUR) "
                f"데이터로 점검했습니다. 등재된 병용금기·중복·연령/노인 주의는 발견되지 않았습니다. "
                f"다만 이는 최종 의학적 판단이 아니며, 새로운 증상이 있으면 약사·의사와 상의하세요.")

    high = [c for c in conflicts if c.severity == Severity.HIGH]
    lines = [f"{i_ga(alias)} 복용 중인 약을 식약처 DUR 데이터로 점검한 결과, "
             f"확인이 필요한 항목 {len(conflicts)}건이 발견되었습니다."]
    if high:
        lines.append(f"이 중 {len(high)}건은 즉시 약사·의사 확인이 권고됩니다.")
    for c in conflicts:
        lines.append(f"  · {_SEV_LABEL[c.severity]} — {c.flag_type.value}: "
                     f"{' + '.join(c.drugs)}. {c.reason}")
    lines.append("※ 약손은 식약처 공식 데이터를 전달할 뿐, 진단·처방을 하지 않습니다. "
                 "복용 중단·변경은 반드시 전문가와 상의하세요.")
    return "\n".join(lines)



def _join_wa(items: list[str]) -> str:
    """['가나정','다라캡슐'] -> '가나정과 다라캡슐'."""
    if not items:
        return ""
    out = items[0]
    for nxt in items[1:]:
        out = wa_gwa(out) + " " + nxt
    return out


def build_questions(conflicts: list[Conflict]) -> list[str]:
    qs: list[str] = []
    for c in conflicts:
        joined = _join_wa(c.drugs)
        if c.flag_type.value == "병용금기":
            qs.append(f"{eul_reul(joined)} 함께 복용해도 괜찮은가요? 대체 가능한 약이 있나요?")
        elif c.flag_type.value == "효능군중복":
            qs.append(f"{i_ga(joined)} 같은 효능군으로 중복된다는데, 하나로 줄여도 되나요?")
        elif c.flag_type.value == "노인주의":
            qs.append(f"{eun_neun(joined)} 고령자 주의 약이라는데, 용량 조절이 필요한가요?")
        else:
            qs.append(f"{joined}의 {c.flag_type.value} 항목, 제 경우 문제 없나요?")
    # 중복 제거하면서 순서 유지
    seen, out = set(), []
    for q in qs:
        if q not in seen:
            seen.add(q)
            out.append(q)
    return out[:5]  # 진료 시간 고려, 최대 5개


def build_schedule(profile: PatientProfile) -> dict[str, list[str]]:
    """간이 복약표. MVP는 약명만 시간대에 균등 배치(실제 용법은 e약은요로 보강 — 역할 B)."""
    slots = {"아침": [], "점심": [], "저녁": []}
    keys = list(slots.keys())
    for i, d in enumerate(profile.drugs):
        slots[keys[i % len(keys)]].append(d.name)
    return slots


def refine_with_llm(text: str) -> str:
    """LLM이 있으면 문장을 더 따뜻하고 쉽게 다듬는 훅. 기본은 그대로 반환."""
    from config import settings
    if settings.llm_provider == "template" or not settings.anthropic_api_key:
        return text
    # TODO(C/D): Anthropic API 호출로 톤/가독성 개선
    return text


# ============================================================
# v3: 리포트용 설명 생성 (프롬프트 → 서술 필드). [근일]
#   - 사실(약명·심각도·출처·사유)은 assemble가 채우고, 여기선 '말투'만 입힌다.
#   - GPT-5.5 structured output. 키 없으면 템플릿 폴백(데모/테스트 안정).
#   - 세 안전장치: 입력에 있는 약만, 새 위험/사유 생성 금지, 진단·처방 금지.
# ============================================================
import json

from pydantic import BaseModel

# 결측 사유(PROHBT_CONTENT) 표준문구 — 기획서 §4.5
#   노인주의 76.8% · 효능군중복 93.3% · 투여기간주의 98% 결측 → LLM이 사유 생성 금지.
STANDARD_PHRASES: dict[str, str] = {
    "노인주의": "고령자에서 주의가 필요한 약물로 등재되어 있습니다(식약처 노인주의 목록). 상세 사유는 약사·의사 확인을 권고합니다.",
    "효능군중복": "같은 효능군 약물을 2가지 이상 함께 복용 중입니다(중복 가능성). 상세는 약사 확인을 권고합니다.",
    "투여기간주의": "권장 투여기간 관련 주의 약물로 등재되어 있습니다. 상세는 약사 확인을 권고합니다.",
    "용량주의": "용량 관련 주의 약물로 등재되어 있습니다. 상세는 약사 확인을 권고합니다.",
    "병용금기": "함께 복용하면 안 되는 조합으로 등재되어 있습니다(병용금기).",
    "특정연령금기": "해당 연령에서 피해야 하는 약물로 등재되어 있습니다.",
    "임부금기": "임신 중 피해야 하는 약물로 등재되어 있습니다.",
}


def fill_reason(flag_type_value: str, prohibit_content: str) -> str:
    """사유가 비어 있으면 카테고리 표준문구로 대체. (LLM이 사유를 지어내지 못하게 함)"""
    txt = (prohibit_content or "").strip()
    if txt:
        return txt
    return STANDARD_PHRASES.get(
        flag_type_value,
        f"{flag_type_value} 항목으로 등재되어 있습니다. 약사 확인을 권고합니다.",
    )


SYSTEM_PROMPT = """너는 한국 노인 복약 안전 리포트의 '설명 작성자'다. 너는 의학적 판단을 하지 않는다.
입력으로 '이미 확정된 위험 항목 목록(index, 약 이름, 심각도, 유형, 사유)'을 받는다.

[해야 할 일]
- 각 항목을 보호자(40~60대 자녀)가 이해할 한두 문장의 쉬운 설명(easy_explanation)으로 바꾼다.
- 각 항목마다 약사에게 물어볼 질문 1개(question_for_pharmacist)를 만든다.
- 전체를 아우르는 한 단락 요약(overall_message)을 만든다. 짧고 따뜻하게.

[절대 규칙 — 위반 시 실패]
1. 입력에 있는 약 이름만 사용한다. 새 약·새 위험·새 부작용·새 사유를 절대 추가하지 않는다.
2. 사유가 비었거나 표준문구이면 사유를 지어내지 말고 "정확한 사유는 약사 확인이 필요하다"로 안내한다.
3. 진단·처방을 하지 않는다. 금지어: 중단/중지/끊으세요/증량/감량/줄이세요/늘리세요/처방/진단. 대신 "약사·의사와 상의"로 라우팅한다.
4. 심각도 '상'은 "지금 약사·의사에게 확인하세요"를 명확히 포함한다.
5. 숫자·약명·심각도·출처를 임의로 바꾸지 않는다(설명만 한다).

[톤] 쉬운 말, 공포 조장 금지, 항목당 2문장 이내. 출력은 지정된 JSON 스키마만."""

_FEWSHOT_USER = json.dumps({"items": [
    {"index": 0, "severity": "상", "flag_type": "노인주의", "drugs": ["벤조원정"],
     "reason": "장기작용 벤조디아제핀계는 고령자에서 치매·낙상 위험을 높일 수 있음"}
]}, ensure_ascii=False)

_FEWSHOT_ASSISTANT = json.dumps({
    "overall_message": "아버님 약 중 1건이 고령자에게 특히 주의가 필요한 약으로 확인됐어요. 지금 약사님께 확인해 보시길 권합니다.",
    "items": [{
        "index": 0,
        "easy_explanation": "‘벤조원정’은 어르신에게 졸림·어지럼으로 낙상이나 기억력 저하 위험을 높일 수 있는 계열의 약이에요.",
        "question_for_pharmacist": "벤조원정을 더 안전한 약으로 바꾸거나 용량을 조절할 수 있을지 여쭤봐 주세요."
    }]
}, ensure_ascii=False)


class _LLMItem(BaseModel):
    index: int
    easy_explanation: str
    question_for_pharmacist: str


class _LLMOut(BaseModel):
    overall_message: str
    items: list[_LLMItem]


def generate_narration(payload):
    """ReportPayload의 서술 필드를 채운다(in-place). GPT-5.5 또는 템플릿 폴백.

    payload.items[*] 의 사실 필드(약명·심각도·출처·사유)는 손대지 않는다.
    """
    from config import settings

    if settings.llm_provider != "gpt-5.5" or not settings.openai_api_key:
        return _template_narration(payload)

    try:
        from openai import OpenAI

        client = OpenAI(api_key=settings.openai_api_key)
        facts = [
            {"index": i, "severity": it.severity.value, "flag_type": it.flag_type.value,
             "drugs": it.drugs, "reason": it.reason}
            for i, it in enumerate(payload.items)
        ]
        completion = client.beta.chat.completions.parse(
            model=settings.openai_model,
            # NOTE: GPT-5.5는 temperature 기본값(1)만 허용(0.2 지정 시 400). 미지정으로 둔다.
            #       결정성은 구조화 출력 스키마 + assemble.audit(사실필드 불변/환각차단)로 확보.
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": _FEWSHOT_USER},
                {"role": "assistant", "content": _FEWSHOT_ASSISTANT},
                {"role": "user", "content": json.dumps({"items": facts}, ensure_ascii=False)},
            ],
            response_format=_LLMOut,
        )
        out = completion.choices[0].message.parsed
        payload.overall_message = out.overall_message
        by_idx = {m.index: m for m in out.items}
        for i, it in enumerate(payload.items):
            m = by_idx.get(i)
            if m:  # 약명·severity·source는 코드값 유지, 서술만 입력
                it.easy_explanation = m.easy_explanation
                it.question_for_pharmacist = m.question_for_pharmacist
        return payload
    except Exception:
        # 타임아웃·레이트리밋·파싱오류 → 데모 안정성 위해 템플릿 폴백
        return _template_narration(payload)


def _template_narration(payload):
    """키 없이/실패 시: 사실에서 안전한 한국어 서술을 생성(프로필 약명만 사용)."""
    items = payload.items
    if not items:
        payload.overall_message = (
            f"{payload.meta.alias} 복용 약을 식약처 DUR 데이터로 점검했어요. "
            f"지금 등재된 위험·중복·주의는 발견되지 않았습니다. "
            f"새로운 증상이 있으면 약사·의사와 상의하세요."
        )
        return payload

    high = payload.counts.get("위험", 0)
    msg = f"{payload.meta.alias} 복용 약을 점검한 결과, 확인이 필요한 항목 {len(items)}건이 발견됐어요."
    if high:
        msg += f" 이 중 {high}건은 지금 약사·의사 확인을 권합니다."
    payload.overall_message = msg

    lead_by_grade = {"위험": "지금 약사·의사에게 확인하세요", "주의": "한 번 확인해 보세요"}
    for it in items:
        joined = _join_wa(it.drugs)
        lead = lead_by_grade.get(it.grade, "참고하세요")
        it.easy_explanation = f"{joined}: {it.reason} ({lead})"
        ft = it.flag_type.value
        if ft == "병용금기":
            it.question_for_pharmacist = f"{eul_reul(joined)} 함께 복용해도 괜찮은가요? 대체 가능한 약이 있나요?"
        elif ft == "효능군중복":
            it.question_for_pharmacist = f"{i_ga(joined)} 같은 효능군으로 중복된다는데, 하나로 줄여도 되나요?"
        elif ft == "노인주의":
            it.question_for_pharmacist = f"{eun_neun(joined)} 고령자 주의 약이라는데, 용량 조절이 필요한가요?"
        else:
            it.question_for_pharmacist = f"{joined}의 {ft} 항목, 저희 경우 문제 없을까요?"
    return payload
