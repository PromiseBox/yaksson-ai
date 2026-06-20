"""
약손 AI — 정규화 도메인 모델

설계 원칙:
- 식약처 DUR API의 응답 형식(필드명/구조)은 자주 바뀌고 오퍼레이션마다 다르다.
- 따라서 비즈니스 로직(위험 판정)은 외부 API 형식에 의존하지 않는 '정규화 모델' 위에서 돈다.
- API 어댑터(tools/)가 외부 응답을 아래 모델로 변환하고, 핵심 로직(agents/risk.py)은
  오직 아래 모델만 본다. -> API 세부가 달라져도 핵심 가치는 깨지지 않고 테스트 가능하다.
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class FlagType(str, Enum):
    """식약처 DUR 금기/주의 유형 (DURPrdlstInfoService03 오퍼레이션과 1:1 대응)."""
    USJNT_TABOO = "병용금기"          # getUsjntTabooInfoList03
    EFCY_DPLCT = "효능군중복"          # getEfcyDplctInfoList03
    ODSN_ATENT = "노인주의"            # getOdsnAtentInfoList03
    AGE_TABOO = "특정연령금기"         # getSpcifyAgrdeTabooInfoList03
    PWNM_TABOO = "임부금기"            # getPwnmTabooInfoList03
    CPCTY_ATENT = "용량주의"          # getCpctyAtentInfoList03
    PD_ATENT = "투여기간주의"          # getMdctnPdAtentInfoList03


class Severity(str, Enum):
    HIGH = "상"     # 즉시 약사/의사 확인 권고 (병용금기·임부금기·해당 연령금기)
    MEDIUM = "중"   # 주의 필요 (효능군중복·노인주의)
    LOW = "하"      # 참고 (용량/기간 주의)


class Source(BaseModel):
    """모든 경고에 반드시 붙는 출처. 출처 없는 경고는 Evaluation Agent가 차단한다."""
    provider: str = "식품의약품안전처 DUR(의약품안전사용서비스)"
    operation: str = ""                 # 어느 오퍼레이션에서 왔는지
    notification_date: Optional[str] = None  # 고시일자
    raw_ref: Optional[str] = None       # 추적용 원본 참조


class Drug(BaseModel):
    """환자가 복용 중인 약 1건 (정규화)."""
    item_seq: str = Field(..., description="품목기준코드 (식약처 고유 식별자)")
    name: str
    entp_name: Optional[str] = None
    ingredient_codes: list[str] = Field(default_factory=list)
    ingredient_names: list[str] = Field(default_factory=list)

    def __str__(self) -> str:
        return f"{self.name}({self.item_seq})"


class DurRecord(BaseModel):
    """특정 약(subject)에 대해 API가 알려준 DUR 플래그 1건 (정규화)."""
    flag_type: FlagType
    subject_item_seq: str               # 이 플래그가 걸린 약
    prohibit_content: str = ""          # 금기/주의 내용 (PROHBT_CONTENT)
    # 병용금기처럼 '상대 약'이 있는 경우
    related_item_seq: Optional[str] = None
    related_ingredient_code: Optional[str] = None
    # 효능군중복처럼 '분류군'으로 묶이는 경우
    class_code: Optional[str] = None
    class_name: Optional[str] = None
    # 연령금기 (개월/세)
    age_min: Optional[int] = None
    age_max: Optional[int] = None
    source: Source = Field(default_factory=Source)
    pim_category: Optional[str] = None   # 예: "벤조디아제핀계", "Z-drug", "1세대 항히스타민"


class Conflict(BaseModel):
    """위험 판정 결과 1건. 화면/리포트에 그대로 노출되는 단위."""
    flag_type: FlagType
    severity: Severity
    drugs: list[str]                    # 관련된 약 이름(들)
    reason: str                         # 식약처 근거 내용을 인용/요약
    recommendation: str                 # 행동 권고 (항상 전문가 확인으로 라우팅)
    source: Source
    tags: list[str] = Field(default_factory=list)   # 예: ["치매·낙상 위험"]

    def headline(self) -> str:
        joined = " + ".join(self.drugs)
        return f"[{self.severity.value}] {self.flag_type.value}: {joined}"


class PatientProfile(BaseModel):
    """가족 구성원 1명 (보호자가 관리하는 대상)."""
    profile_id: str
    alias: str = "어르신"               # 보호자가 붙인 별칭 (예: '아버지')
    age: Optional[int] = None
    is_pregnant: bool = False           # 고령에선 보통 무관하나 모델 일반성 위해 유지
    drugs: list[Drug] = Field(default_factory=list)

    @property
    def is_elderly(self) -> bool:
        return self.age is not None and self.age >= 65
