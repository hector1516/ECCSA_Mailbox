"""
Zona horaria estándar del ecosistema ECCSA: Monterrey, Nuevo León, México.
"""
from datetime import datetime, timezone, timedelta

TZ_MX = timezone(timedelta(hours=-6))


def now_mx() -> datetime:
    return datetime.now(TZ_MX).replace(tzinfo=None)


def to_mx(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(TZ_MX).replace(tzinfo=None)
