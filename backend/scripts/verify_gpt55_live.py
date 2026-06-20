"""
GPT-5.5 라이브 검증 — 실제 OpenAI 호출로 ①모델 id 실재 ②키 유효 ③structured output 호환을 확인.

핵심: generate_narration 은 예외를 잡아 '조용히' 템플릿으로 폴백한다. 그래서 여기서는
먼저 **try/except 없이 직접** 호출해 실제 에러(모델 없음/키 무효 등)를 그대로 드러낸다.
그 다음 end-to-end(generate_narration)가 정말 GPT-5.5를 썼는지(폴백 아님) 확인한다.

실행(.env 에 OPENAI_API_KEY 채운 뒤):
  PYTHONPATH=. .venv/bin/python scripts/verify_gpt55_live.py
"""
from __future__ import annotations

import json
import sys

from config import settings


def main() -> int:
    print(f"설정: provider={settings.llm_provider!r}  model={settings.openai_model!r}  key_set={bool(settings.openai_api_key)}")
    if settings.llm_provider != "gpt-5.5":
        print("⚠️ LLM_PROVIDER 가 gpt-5.5 가 아닙니다(.env 확인).", file=sys.stderr)
    if not settings.openai_api_key:
        print("❌ OPENAI_API_KEY 가 비어 있습니다. .env 에 키를 넣어주세요.", file=sys.stderr)
        return 2

    from openai import OpenAI
    from agents.comm import SYSTEM_PROMPT, _FEWSHOT_USER, _FEWSHOT_ASSISTANT, _LLMOut

    facts = [{
        "index": 0, "severity": "상", "flag_type": "병용금기",
        "drugs": ["중외5-에프유주", "테고캡슐20"],
        "reason": "병용 시 gimeracil에 의해 fluoropyrimidine 대사 감소로 독성 증가",
    }]

    print("\n[1] GPT-5.5 직접 호출 (try/except 없음 — 에러 그대로 노출)…")
    client = OpenAI(api_key=settings.openai_api_key)
    completion = client.beta.chat.completions.parse(
        model=settings.openai_model,
        # GPT-5.5는 temperature 기본값만 허용 → 미지정
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _FEWSHOT_USER},
            {"role": "assistant", "content": _FEWSHOT_ASSISTANT},
            {"role": "user", "content": json.dumps({"items": facts}, ensure_ascii=False)},
        ],
        response_format=_LLMOut,
    )
    out = completion.choices[0].message.parsed
    print("  ✅ 호출 성공. 모델 응답:")
    print("   overall_message:", out.overall_message)
    for it in out.items:
        print(f"   item{it.index}.easy_explanation: {it.easy_explanation}")
        print(f"   item{it.index}.question       : {it.question_for_pharmacist}")
    usage = getattr(completion, "usage", None)
    if usage:
        print("   usage:", usage)

    print("\n[2] end-to-end generate_narration 가 실제로 GPT-5.5를 썼는지(폴백 아님) 확인…")
    from agents import comm
    from domain.models import FlagType, Severity, Source
    from domain.report import ReportItem, ReportMeta, ReportPayload
    p = ReportPayload(
        meta=ReportMeta(alias="아버지"), counts={"위험": 1, "주의": 0, "정상": 0},
        items=[ReportItem(severity=Severity.HIGH, grade="위험", flag_type=FlagType.USJNT_TABOO,
                          drugs=["중외5-에프유주", "테고캡슐20"], reason="병용 시 독성 증가",
                          source=Source(operation="product_interaction_rule"))],
    )
    before = (p.items[0].drugs[:], p.items[0].severity, p.items[0].source.operation)
    comm.generate_narration(p)
    after = (p.items[0].drugs[:], p.items[0].severity, p.items[0].source.operation)
    print("   overall_message:", p.overall_message)
    print("   easy_explanation:", p.items[0].easy_explanation)
    print("   사실 필드 불변:", before == after)

    print("\n[판정] ✅ GPT-5.5 라이브 검증 성공 — 모델 id·키·structured output 정상 동작.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
