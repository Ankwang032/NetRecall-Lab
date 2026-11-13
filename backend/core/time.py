"""API 응답 시각의 시간대 (develop-memo D7)."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

# 한국은 일광 절약 시간이 없어 고정 오프셋으로 충분하다 (Windows에 tzdata가 없어도 동작)
KST = timezone(timedelta(hours=9), "KST")


def to_kst(value: datetime) -> datetime:
    # DB에는 UTC로 저장한다. SQLite에서 읽은 값은 시간대가 없으므로 UTC로 보고 KST로 바꾼다.
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(KST)
