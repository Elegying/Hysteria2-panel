"""Pure helpers for per-origin provider traffic budgets."""

import calendar
import datetime
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


MAX_SQLITE_INTEGER = 2**63 - 1
GIB_INPUT_PATTERN = re.compile(r"(?:0|[1-9][0-9]{0,9})(?:\.[0-9]{1,12})?")


def gib_input_to_bytes(value):
    raw = str(value or "").strip()
    if GIB_INPUT_PATTERN.fullmatch(raw) is None:
        raise ValueError("节点已用流量格式无效")
    try:
        result = (Decimal(raw) * Decimal(1024**3)).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    except InvalidOperation as exc:
        raise ValueError("节点已用流量格式无效") from exc
    if not 0 <= result <= Decimal(MAX_SQLITE_INTEGER):
        raise ValueError("节点已用流量超出允许范围")
    return int(result)


def bytes_to_gib_input(value):
    result = (Decimal(max(0, int(value or 0))) / Decimal(1024**3)).quantize(
        Decimal("0.000000000001"), rounding=ROUND_HALF_UP
    )
    return format(result, "f").rstrip("0").rstrip(".") or "0"


def _reset_at(year, month, reset_day):
    day = min(int(reset_day), calendar.monthrange(int(year), int(month))[1])
    return datetime.datetime(
        int(year), int(month), day, tzinfo=datetime.timezone.utc
    )


def budget_period(now, reset_day):
    current = datetime.datetime.fromtimestamp(int(now), tz=datetime.timezone.utc)
    this_reset = _reset_at(current.year, current.month, reset_day)
    month_index = current.year * 12 + current.month - 1
    if current >= this_reset:
        start = this_reset
        next_year, next_month_zero = divmod(month_index + 1, 12)
        end = _reset_at(next_year, next_month_zero + 1, reset_day)
    else:
        previous_year, previous_month_zero = divmod(month_index - 1, 12)
        start = _reset_at(previous_year, previous_month_zero + 1, reset_day)
        end = this_reset
    return start, end


def budget_result(origin_id, period, period_start, period_end, budget, used):
    limit_bytes = int(budget["limit_bytes"]) if budget is not None else 0
    warning_percent = (
        int(budget["warning_percent"]) if budget is not None else 80
    )
    reset_day = int(budget["reset_day"]) if budget is not None else 1
    manual_used_bytes = (
        int(budget["manual_used_bytes"]) if budget is not None else 0
    )
    used = int(used)
    if limit_bytes <= 0:
        percent = 0.0
        status = "disabled"
    else:
        percent = round(used * 100.0 / limit_bytes, 1)
        if used >= limit_bytes:
            status = "exhausted"
        elif used * 100 >= limit_bytes * warning_percent:
            status = "warning"
        else:
            status = "normal"
    return {
        "origin_id": origin_id,
        "period": period,
        "period_start": period_start.strftime("%Y-%m-%d"),
        "period_end": period_end.strftime("%Y-%m-%d"),
        "next_reset_date": period_end.strftime("%Y-%m-%d"),
        "limit_bytes": limit_bytes,
        "warning_percent": warning_percent,
        "reset_day": reset_day,
        "manual_used_bytes": manual_used_bytes,
        "baseline_at": budget["baseline_at"] if budget is not None else None,
        "used_bytes": used,
        "remaining_bytes": max(0, limit_bytes - used) if limit_bytes else None,
        "percent": percent,
        "status": status,
        "updated_by": budget["updated_by"] if budget is not None else None,
        "updated_at": budget["updated_at"] if budget is not None else None,
    }
