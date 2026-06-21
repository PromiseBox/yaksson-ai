"""
LangGraph(run(), 8노드 StateGraph)를 실제 yaksok_db(DATA_SOURCE=pg)로 끝까지 구동 검증.

'랭그래프로 한 게 맞나' + 'LangGraph가 실DB로 도나' 를 한 번에 확인한다.
조용한 폴백(except → 순차)을 우회/감시해 진짜 그래프 경로임을 증명한다.

실행(프록시 55432 떠 있을 때):
  DATA_SOURCE=pg YAKSOK_DB_PASSWORD='***' PYTHONPATH=. .venv/bin/python scripts/run_graph_on_yaksok_db.py
"""
from __future__ import annotations

import sys

from config import settings

print(f"DATA_SOURCE={settings.data_source}  db={settings.db_host}:{settings.db_port}/{settings.db_name}  "
      f"user={settings.db_user}  pw_set={bool(settings.db_password)}")
if settings.data_source != "pg" or not settings.db_password:
    print("❌ DATA_SOURCE=pg 와 YAKSOK_DB_PASSWORD 가 필요합니다.", file=sys.stderr)
    raise SystemExit(2)

import agents.graph as G
from agents.assemble import build_report
from domain.models import PatientProfile


def drugs_of(state):
    return [d.name for d in state["profile"].drugs]


print("\n[1] build_graph().invoke() 직접 — LangGraph가 실DB로 8노드 실행(try/except 없이)")
app = G.build_graph()
print("    compiled:", type(app).__module__ + "." + type(app).__name__)
out = app.invoke({
    "profile": PatientProfile(profile_id="graph-pg", alias="아버지", age=68),
    "raw_input": "중외5-에프유주(플루오로우라실), 테고캡슐20",
})
print("  ✅ invoke OK · 해석된 약(실DB):", drugs_of(out))
print("  conflicts:", len(out.get("conflicts") or []))
for c in out.get("conflicts") or []:
    print(f"    [{c.severity.value}] {c.flag_type.value}: {' + '.join(c.drugs)} | 출처={c.source.operation}")

print("\n[2] run() 이 진짜 LangGraph 경로인지(순차 폴백 감시)")
hit = {"fallback": False}
orig = G.run_pipeline
def spy(s):
    hit["fallback"] = True
    return orig(s)
G.run_pipeline = spy
out2 = G.run({
    "profile": PatientProfile(profile_id="graph-pg2", alias="아버지", age=76),
    "raw_input": "빅손정1밀리그람(에틸로플라제페이트)",
})
G.run_pipeline = orig
print("  순차 폴백 탔나:", hit["fallback"], "→",
      "❌ LangGraph 아님(폴백)" if hit["fallback"] else "✅ 진짜 LangGraph(StateGraph)로 실행")
print("  conflicts:", len(out2.get("conflicts") or []),
      [c.flag_type.value for c in out2.get("conflicts") or []])

print("\n[3] 그래프 출력 → 리포트 아웃풋 포맷(build_report)")
rep = build_report(out)
audit = rep.eval_report.get("report_audit", {})
print("  counts:", rep.counts, "· needs_pharmacist:", rep.needs_pharmacist, "· audit_passed:", audit.get("passed"))

ok = (not hit["fallback"]) and (len(out.get("conflicts") or []) > 0)
print("\n[판정]", "✅ LangGraph(8노드) × yaksok_db 실데이터 end-to-end 동작" if ok else "❌ 확인 필요")
