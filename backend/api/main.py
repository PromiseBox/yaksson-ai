"""
약손 AI — FastAPI 진입점 (GCP Cloud Run에서 실행). [근일]

- 프론트(Next.js/Vercel)는 이 엔드포인트만 호출한다.
- LLM/DB 키는 서버(여기)에만 둔다(Secret Manager 주입). 프론트 노출 금지.
- 판정은 graph(규칙엔진+DataSource)가 하고, 이 계층은 입력→실행→리포트 조립만.

실행: uvicorn api.main:app --reload
"""
from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel, Field

from agents.assemble import build_report
from agents.graph import run
from domain.models import PatientProfile
from domain.report import ReportPayload

app = FastAPI(title="약손 AI API", version="1.0")


class AnalyzeRequest(BaseModel):
    alias: str = "어르신"
    age: int | None = None
    is_pregnant: bool = False
    drug_names: list[str] = Field(default_factory=list)  # 구조화 입력
    raw_input: str = ""  # 또는 자유 텍스트(약명 나열)
    profile_id: str = "adhoc"


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/analyze", response_model=ReportPayload)
def analyze(req: AnalyzeRequest) -> ReportPayload:
    profile = PatientProfile(
        profile_id=req.profile_id,
        alias=req.alias,
        age=req.age,
        is_pregnant=req.is_pregnant,
    )
    raw = req.raw_input or "\n".join(req.drug_names)
    out = run({"profile": profile, "raw_input": raw})  # 8노드(폴백 포함)
    return build_report(out)
