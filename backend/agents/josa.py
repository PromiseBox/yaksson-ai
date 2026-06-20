"""한국어 조사 자동 선택 — 받침 유무로 은/는, 이/가, 을/를, 와/과, 으로/로 결정."""
from __future__ import annotations


def _has_batchim(word: str) -> bool:
    if not word:
        return False
    last = word[-1]
    if not ("가" <= last <= "힣"):
        return False  # 한글이 아니면 받침 없음 취급
    code = ord(last) - 0xAC00
    jong = code % 28
    return jong != 0


def josa(word: str, with_b: str, without_b: str) -> str:
    """word 뒤에 붙일 조사를 골라 'word+조사' 반환."""
    return word + (with_b if _has_batchim(word) else without_b)


def eun_neun(word: str) -> str:
    return josa(word, "은", "는")


def i_ga(word: str) -> str:
    return josa(word, "이", "가")


def eul_reul(word: str) -> str:
    return josa(word, "을", "를")


def wa_gwa(word: str) -> str:
    return josa(word, "과", "와")
