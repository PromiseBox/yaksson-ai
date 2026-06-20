"""
식약처 공공데이터 OpenAPI 클라이언트 (실 연동용).

[검증 완료된 엔드포인트]
- DUR 병용금기:  http://apis.data.go.kr/1471000/DURPrdlstInfoService03/getUsjntTabooInfoList03
- e약은요:       http://apis.data.go.kr/1471000/DrbEasyDrugInfoService/getDrbEasyDrugList

[역할 B 확인 필요 — Swagger UI에서 오퍼레이션명/파라미터/응답필드 최종 검증]
- 효능군중복, 노인주의, 특정연령금기, 임부금기, 용량주의, 투여기간주의 오퍼레이션명은
  DURPrdlstInfoService03 의 Swagger 명세에서 확정한 뒤 OPERATIONS 에 채운다.
- 응답 필드명(ITEM_SEQ, PROHBT_CONTENT, MIXTURE_ITEM_SEQ, NOTIFICATION_DATE 등)도
  실제 응답으로 확인 후 _to_dur_record 매핑을 보정한다.

개발계정 트래픽 한도(예: 10,000/일)가 있으므로 _cache 로 단순 캐싱한다.
운영 단계에서는 Redis 캐시로 교체.
"""
from __future__ import annotations

from typing import Any, Optional

try:
    import httpx
except ImportError:  # 데모 환경에서 httpx 미설치여도 import 자체는 통과
    httpx = None  # type: ignore

from domain.models import Drug, DurRecord, FlagType, Source

BASE = "http://apis.data.go.kr/1471000"

# 검증된 것만 실명, 나머지는 None 으로 두고 역할 B가 확정
OPERATIONS: dict[FlagType, Optional[str]] = {
    FlagType.USJNT_TABOO: f"{BASE}/DURPrdlstInfoService03/getUsjntTabooInfoList03",  # 검증됨
    FlagType.EFCY_DPLCT: None,    # TODO(B): getEfcyDplctInfoList03 등 Swagger 확인
    FlagType.ODSN_ATENT: None,    # TODO(B): getOdsnAtentInfoList03 등
    FlagType.AGE_TABOO: None,     # TODO(B): getSpcifyAgrdeTabooInfoList03 등
    FlagType.PWNM_TABOO: None,    # TODO(B): getPwnmTabooInfoList03 등
    FlagType.CPCTY_ATENT: None,   # TODO(B)
    FlagType.PD_ATENT: None,      # TODO(B)
}

EASY_DRUG_LIST = f"{BASE}/DrbEasyDrugInfoService/getDrbEasyDrugList"  # 검증됨


class MfdsDurClient:
    def __init__(self, service_key: str, timeout: float = 10.0) -> None:
        if httpx is None:
            raise RuntimeError("httpx 가 필요합니다: pip install httpx")
        self.service_key = service_key
        self._client = httpx.Client(timeout=timeout)
        self._cache: dict[str, Any] = {}

    # ---- 공통 호출 ----
    def _get(self, url: str, params: dict[str, Any]) -> dict:
        params = {
            "serviceKey": self.service_key,
            "type": "json",
            "numOfRows": 100,
            "pageNo": 1,
            **params,
        }
        cache_key = url + repr(sorted(params.items()))
        if cache_key in self._cache:
            return self._cache[cache_key]
        resp = self._client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
        self._cache[cache_key] = data
        return data

    @staticmethod
    def _rows(payload: dict) -> list[dict]:
        """data.go.kr 표준 응답에서 items 배열만 안전하게 추출."""
        try:
            items = payload["body"]["items"]
        except (KeyError, TypeError):
            try:
                items = payload["response"]["body"]["items"]
            except (KeyError, TypeError):
                return []
        if isinstance(items, dict):  # 단건이면 dict로 올 수 있음
            items = items.get("item", [])
        if isinstance(items, dict):
            items = [items]
        return items or []

    # ---- 약 해석 (약명 -> 품목기준코드) ----
    def resolve_drug(self, name_or_seq: str) -> Drug | None:
        if name_or_seq.isdigit():  # 이미 품목기준코드로 보임
            return Drug(item_seq=name_or_seq, name=name_or_seq)
        payload = self._get(EASY_DRUG_LIST, {"itemName": name_or_seq})
        rows = self._rows(payload)
        if not rows:
            return None
        r = rows[0]
        return Drug(
            item_seq=str(r.get("itemSeq") or r.get("ITEM_SEQ") or ""),
            name=r.get("itemName") or r.get("ITEM_NAME") or name_or_seq,
            entp_name=r.get("entpName") or r.get("ENTP_NAME"),
        )

    # ---- DUR 레코드 ----
    def dur_records(self, item_seq: str) -> list[DurRecord]:
        records: list[DurRecord] = []
        for flag_type, url in OPERATIONS.items():
            if not url:
                continue  # 아직 미검증 오퍼레이션은 skip
            payload = self._get(url, {"itemSeq": item_seq})
            for row in self._rows(payload):
                rec = self._to_dur_record(flag_type, item_seq, row)
                if rec:
                    records.append(rec)
        return records

    @staticmethod
    def _to_dur_record(flag_type: FlagType, item_seq: str, row: dict) -> DurRecord | None:
        """raw 응답 -> 정규화 DurRecord (실 필드명 확인 후 보정)."""
        return DurRecord(
            flag_type=flag_type,
            subject_item_seq=item_seq,
            prohibit_content=row.get("PROHBT_CONTENT") or row.get("prohbtContent") or "",
            related_item_seq=row.get("MIXTURE_ITEM_SEQ") or row.get("mixtureItemSeq"),
            class_code=row.get("CLASS_CODE") or row.get("classCode"),
            class_name=row.get("CLASS_NAME") or row.get("className"),
            source=Source(
                operation=str(OPERATIONS.get(flag_type)),
                notification_date=row.get("NOTIFICATION_DATE") or row.get("notificationDate"),
            ),
        )
