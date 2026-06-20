import chainlit as cl
from agents.graph import run
from agents import scenarios
from tools.datasource import get_default_datasource
from domain.models import PatientProfile


def build_profile(text: str, age: int = 76, alias: str = "어르신") -> PatientProfile:
    ds = get_default_datasource()
    p = PatientProfile(profile_id="demo", alias=alias, age=age)
    names = [t.strip() for t in text.replace(",", "\n").splitlines() if t.strip()]
    for n in names:
        d = ds.resolve_drug(n)
        if d:
            p.drugs.append(d)
    return p


@cl.on_chat_start
async def start():
    await cl.Message(
        content=(
            "약손 AI 데모입니다.\n"
            "약 이름을 쉼표로 입력하세요. 예) 가나정, 다라캡슐, 벤조원정\n"
            "가정 시뮬레이션: `가정: 추가 다라캡슐` 또는 `가정: 제거 가나정`\n\n"
            "※ 이 서비스는 식약처 DUR 기반 검토 보조 도구입니다. 최종 판단은 약사·의사에게 확인하세요."
        )
    ).send()


@cl.on_message
async def on_msg(msg: cl.Message):
    text = msg.content.strip()

    if text.startswith("가정:"):
        p: PatientProfile | None = cl.user_session.get("profile")
        if not p:
            await cl.Message(content="먼저 약을 입력해 주세요.").send()
            return
        ds = get_default_datasource()
        rest = text.replace("가정:", "").strip()
        add_names: list[str] = []
        rem_names: list[str] = []
        if "추가" in rest:
            parts = rest.replace("추가", "").split()
            add_names = [w for w in parts if w not in ("제거",)]
        if "제거" in rest:
            parts = rest.replace("제거", "").split()
            rem_names = [w for w in parts if w not in ("추가",)]
        r = scenarios.simulate_whatif(p, ds, add_names=add_names, remove_names=rem_names)
        new_heads = [c.headline() for c in r["newly_introduced"]]
        res_heads = [c.headline() for c in r["resolved"]]
        await cl.Message(
            content=(
                f"**가정 시뮬레이션 결과**\n"
                f"- 변경 전 위험: {len(r['before'])}건 → 변경 후: {len(r['after'])}건\n"
                f"- 새로 생김: {new_heads if new_heads else '없음'}\n"
                f"- 해소됨: {res_heads if res_heads else '없음'}"
            )
        ).send()
        return

    # 일반 약명 입력
    # 첫 줄이 "이름:OO 나이:NN" 형식이면 프로필 반영
    lines = text.splitlines()
    alias, age = "어르신", 76
    drug_text = text
    if lines and "이름:" in lines[0] and "나이:" in lines[0]:
        import re
        m_alias = re.search(r"이름:(\S+)", lines[0])
        m_age = re.search(r"나이:(\d+)", lines[0])
        if m_alias:
            alias = m_alias.group(1)
        if m_age:
            age = int(m_age.group(1))
        drug_text = "\n".join(lines[1:])

    p = build_profile(drug_text, age=age, alias=alias)
    cl.user_session.set("profile", p)

    if not p.drugs:
        await cl.Message(content="등록된 약이 없습니다. 카탈로그에 있는 약명을 입력해 주세요.").send()
        return

    out = run({"profile": p, "raw_input": ""})
    conflicts = out.get("conflicts", [])

    # 1. 요약
    summary = out.get("summary", "")
    has_high = any(c.severity.value == "상" for c in conflicts)
    summary_text = ("⚠️ **심각도 '상' 위험이 발견되었습니다.**\n\n" if has_high else "") + summary
    await cl.Message(content=summary_text).send()

    # 2. 위험 카드
    if conflicts:
        card_lines = ["**발견된 위험 목록**"]
        for c in conflicts:
            tag_str = f" ({', '.join(c.tags)})" if c.tags else ""
            card_lines.append(
                f"- [{c.severity.value}] {c.flag_type.value}{tag_str} — {' + '.join(c.drugs)}\n"
                f"  - 근거: {c.reason}\n"
                f"  - 출처: {c.source.provider}"
            )
        await cl.Message(content="\n".join(card_lines)).send()

    # 3. 약사 질문지
    questions = out.get("questions", [])
    if questions:
        q_lines = ["**[약사에게 물어볼 질문]**"]
        for i, q in enumerate(questions, 1):
            q_lines.append(f"  {i}. {q}")
        await cl.Message(content="\n".join(q_lines)).send()

    # 4. 중재의견서 초안
    note = out.get("intervention_note", "")
    if note:
        await cl.Message(content=f"**중재의견서 초안**\n```\n{note}\n```").send()

    # 5. QR
    qr_path = out.get("qr_path")
    if qr_path:
        await cl.Message(
            content="QR 안전 프로필",
            elements=[cl.Image(path=qr_path, name="qr")]
        ).send()
    else:
        qr_payload = out.get("qr_payload", {})
        if qr_payload:
            import json
            await cl.Message(content=f"QR 페이로드(텍스트):\n```json\n{json.dumps(qr_payload, ensure_ascii=False, indent=2)}\n```").send()

    # 6. 변경 이력 + 새 위험
    mem_diff = out.get("memory_diff", {})
    new_conflicts = out.get("new_conflicts", [])
    hist_lines = ["**변경 이력**"]
    if mem_diff.get("first_visit"):
        hist_lines.append("- 첫 방문 기록입니다.")
    else:
        added = mem_diff.get("added", [])
        removed = mem_diff.get("removed", [])
        if added:
            hist_lines.append(f"- 추가된 약: {', '.join(added)}")
        if removed:
            hist_lines.append(f"- 제거된 약: {', '.join(removed)}")
    if new_conflicts:
        hist_lines.append(f"- 이번에 새로 생긴 위험 {len(new_conflicts)}건: "
                          + ", ".join(c.headline() for c in new_conflicts))
    await cl.Message(content="\n".join(hist_lines)).send()
