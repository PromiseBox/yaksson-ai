# 약손(藥손) AI — 코드 스캐폴드 v2

식약처 DUR 공공데이터 기반 **다제약물 안전관리 멀티에이전트** (제14회 범정부 공공데이터·AI 창업경진대회 / 과제 트랙2).

> 이 스캐폴드는 **가치의 핵심(위험 판정)을 실제로 동작·테스트되게** 만든 골격입니다.
> 외부 API 형식과 분리된 정규화 모델 위에서 돌기 때문에, 식약처 API 세부가 달라져도
> 핵심 로직은 깨지지 않습니다.
>
> **v2 추가:** 노인 부적절약물(PIM) 우선 판정, 약사 인계용 **중재의견서 초안**,
> **QR 안전 프로필**, 재방문 **변경 위험(Delta)** 및 **What-if 시뮬레이터**, **Chainlit 대화형 데모**.
> 전부 **외부 공공 API/LLM 키 없이** Mock/골든 데이터·템플릿 모드로 동작합니다.

## 빠른 실행

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt        # 핵심 + langgraph + chainlit + qrcode

python -m pytest -q                     # 핵심+v2 로직 13개 테스트 (7 + 6)
python -m app.run_demo                  # 골든 데이터로 전체 워크플로우 CLI 데모
chainlit run ui/chainlit_app.py         # 브라우저 대화형 데모 (localhost:8000)
```

- 키 없이 동작: 기본값이 `DATA_SOURCE=mock`, `LLM_PROVIDER=template` 이므로 `.env` 없이도 실행됩니다.
- 식약처 실데이터로 돌리기: `.env` 에 `DATA_SOURCE=mfds`, `MFDS_SERVICE_KEY=...` (현재는 골격만, 호출 미사용)
- langgraph 미설치여도 데모는 순차 폴백으로 동작(`agents/graph.run`).

### Chainlit 데모 사용법

- 약 이름을 쉼표/줄바꿈으로 입력 — 예) `가나정, 다라캡슐, 벤조원정`
- 가정 시뮬레이션 — `가정: 추가 다라캡슐` 또는 `가정: 제거 가나정`
- (선택) 첫 줄에 `이름:OO 나이:NN` 형식이면 프로필에 반영

## 디렉터리

```
yaksohn-ai/
  domain/models.py        # 정규화 도메인 모델(Drug, DurRecord, Conflict, PatientProfile) — API와 분리
                          #   v2: DurRecord.pim_category, Conflict.tags 추가
  tools/
    mock_data.py          # 골든/Mock 데이터 (가상 예시; 실데이터로 교체)
                          #   v2: PIM 3종(벤조원정/자임정/하니정) 추가
    datasource.py         # DataSource 추상화 (Mock / 식약처 스위칭)
    mfds_dur_client.py    # 식약처 DUR·e약은요 실 클라이언트 (검증된 엔드포인트 + TODO 표시; 호출 금지)
  agents/
    state.py              # LangGraph 상태 (PatientState) — v2: intervention_note/qr_path/new_conflicts 등 추가
    risk.py               # ★ 위험 판정 엔진 — 병용금기/효능군중복/노인주의/연령/임부
                          #   v2: 고위험 PIM(벤조·Z-drug·1세대 항히스타민) → '상' + "치매·낙상 위험" 태그
    comm.py               # 보호자용 요약·질문지·복약표 (+ 조사 교정)
    josa.py               # 한국어 조사 자동 선택
    memory.py             # 가족별 프로필 저장 + 재방문 변경 비교 (stateful)
    handoff.py            # (v2 신규) 약사 인계용 중재의견서 초안 + QR 안전 프로필
    scenarios.py          # (v2 신규) Delta(변경 위험) + What-if 시뮬레이터 (순수 함수)
    nodes.py              # 노드 함수 (graph/pipeline 공용) + Evaluation(출처·환각 검증)
                          #   v2: handoff_node 추가, memory_node에서 Delta 계산
    graph.py              # LangGraph StateGraph 조립 + 순차 폴백
  ui/chainlit_app.py      # (v2 신규) 브라우저 대화형 데모 (위험카드/요약/질문/중재의견서/QR/변경이력 + What-if)
  app/run_demo.py         # CLI 데모 (v2 출력: 중재의견서·QR·새 위험 렌더)
  tests/
    test_risk.py          # 핵심 로직 테스트 (7)
    test_v2.py            # (v2 신규) PIM/handoff/delta/whatif 테스트 (6)
  outputs/                # (v2 신규) QR PNG 등 산출물
  config.py / .env.example / requirements.txt
```

## 워크플로우 (트랙2 매핑)

`intake → data → risk → comm → handoff → gate → eval → memory`

- **Tool Calling**: `tools/mfds_dur_client.py` (식약처 다중 오퍼레이션)
- **Stateful Memory**: `agents/memory.py` (가족별 프로필·변경 이력) + `agents/scenarios.compute_delta` (재방문 새 위험)
- **Evaluation**: `agents/nodes.eval_node` (모든 경고의 출처 인용 + 환각 약물 차단)
- **Human Gate**: `agents/nodes.gate_node` (심각도 '상' → 약사 상담 권고)
- **Handoff**: `agents/handoff.py` (약사 인계 중재의견서 초안 + QR 안전 프로필)
- **LangGraph**: `agents/graph.build_graph`

## v2 핵심 기능

- **노인 부적절약물(PIM) 우선 판정**: 고령(만 65세+) 환자에서 벤조디아제핀계·Z-drug·1세대 항히스타민으로
  분류된 약은 심각도를 '상'으로 올리고 `"치매·낙상 위험"` 태그를 부여한다(`agents/risk.HIGH_RISK_PIM`).
- **중재의견서 초안**: 발견된 약물관련문제(DRP)·출처·약사 라우팅 문구를 담은 마크다운 텍스트를 생성한다(진단 아님).
- **QR 안전 프로필**: 약물·고위험 항목 요약을 QR PNG로 생성(`qrcode` 미설치 시 텍스트 폴백).
- **변경 위험(Delta)**: 직전 방문 프로필과 비교해 **새로 생긴 위험만** 추출한다.
- **What-if 시뮬레이터**: 약 추가/제거 시 위험 변화를 사전 시뮬레이션한다(원본 프로필 불변, `copy.deepcopy`).

## 책임 경계 (= 경쟁 우위)

진단·처방을 하지 않는다. **식약처가 등재한 금기/주의를 환자의 실제 약 조합에 대입해 '해당됨'을 출처와 함께 알리고**,
최종 판단은 약사·의사로 라우팅한다. 모든 `Conflict` 에는 `Source` 가 강제되며, `eval_node` 가 출처 없는 경고를 차단한다.

## 역할별 다음 작업 (TODO)

- **역할 B (데이터/API):**
  - 공공데이터포털에서 `DUR품목정보`, `e약은요`, `낱알식별` 활용신청 → 서비스키 발급
  - `tools/mfds_dur_client.OPERATIONS` 의 미검증 오퍼레이션명을 Swagger에서 확정
  - `_to_dur_record` 의 실제 응답 필드명 보정, `mock_data` 를 실데이터 일부로 교체
  - 노인 다빈도 처방 약물로 **골든 약물셋** 확장 (PIM/효능군중복 케이스 보강)
- **역할 C (에이전트/백엔드):**
  - FastAPI 라우트(`POST /analyze` 등) + Redis 캐시 + PostgreSQL+pgvector 로 memory 교체
  - comm `refine_with_llm` 에 Claude API 연결
- **역할 D (UI/평가/테스트):**
  - Chainlit UI 고도화(결과 카드/복약표/PDF 리포트), Langfuse 트레이싱, eval 케이스 확장, 데모 영상
- **역할 A (PM):**
  - 출품 기관예선 확정(건강/복지/지자체 계열) → 시제품 완료 마감 역산
  - 발표 스토리: "정부 92만 건 데이터를 내 부모 약에 대입" 데모 1컷

## 주의

`tools/mock_data.py` 의 약품명·금기관계는 **로직 검증용 가상 예시**다. 어떤 실제 의학적 판단의 근거로도 쓰지 말 것.
모든 가상 데이터의 `prohibit_content` 에는 "(가상 예시)" 표기를 유지한다. 실 서비스는 식약처 실데이터로 교체한다.
```
