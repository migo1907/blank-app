"""
Market calendar — session times, overlaps, holidays, open/closed status.
All times in UTC. Gold (XAUUSD) trades 24h/5d; stocks follow NYSE hours.
"""
from datetime import datetime, date, timedelta, timezone
from typing import Optional

# ── Forex / Gold sessions (UTC) ───────────────────────────────────────────────
SESSIONS = {
    "Sydney":   {"open": (21, 0), "close": (6,  0), "wrap": True},   # crosses midnight
    "Tokyo":    {"open": (0,  0), "close": (9,  0), "wrap": False},
    "London":   {"open": (8,  0), "close": (17, 0), "wrap": False},
    "New_York": {"open": (13, 0), "close": (22, 0), "wrap": False},
}

# Overlaps
OVERLAPS = {
    "Tokyo_London":   {"open": (8,  0), "close": (9,  0)},
    "London_New_York":{"open": (13, 0), "close": (17, 0)},
}

# ── NYSE stock market hours (UTC) ─────────────────────────────────────────────
NYSE_OPEN_UTC  = (14, 30)   # 9:30am ET → 14:30 UTC (EST) / 13:30 UTC (EDT)
NYSE_CLOSE_UTC = (21,  0)   # 4:00pm ET → 21:00 UTC (EST) / 20:00 UTC (EDT)

# US DST: second Sunday March → first Sunday November
def _is_us_dst(dt: datetime) -> bool:
    year = dt.year
    # Second Sunday in March
    march = date(year, 3, 1)
    sundays = [march + timedelta(days=(6 - march.weekday()) % 7 + 7 * i) for i in range(5)]
    dst_start = sundays[1]
    # First Sunday in November
    nov = date(year, 11, 1)
    dst_end = nov + timedelta(days=(6 - nov.weekday()) % 7)
    d = dt.date()
    return dst_start <= d < dst_end

def nyse_hours_utc(dt: datetime) -> tuple[int, int, int, int]:
    """Return (open_h, open_m, close_h, close_m) in UTC for given date."""
    if _is_us_dst(dt):
        return (13, 30, 20, 0)   # EDT
    return (14, 30, 21, 0)       # EST

# ── US Market holidays (NYSE) — fixed + computed ──────────────────────────────

def _nth_weekday(year: int, month: int, n: int, weekday: int) -> date:
    """Return the nth occurrence (1-based) of weekday (0=Mon…6=Sun) in month."""
    d = date(year, month, 1)
    diff = (weekday - d.weekday()) % 7
    d = d + timedelta(days=diff)
    return d + timedelta(weeks=n - 1)

def _last_weekday(year: int, month: int, weekday: int) -> date:
    d = date(year, month + 1, 1) - timedelta(days=1)
    diff = (d.weekday() - weekday) % 7
    return d - timedelta(days=diff)

def _good_friday(year: int) -> date:
    # Anonymous Gregorian algorithm for Easter
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day   = ((h + l - 7 * m + 114) % 31) + 1
    easter = date(year, month, day)
    return easter - timedelta(days=2)

def nyse_holidays(year: int) -> list[date]:
    """Return NYSE holidays for the given year (observed dates)."""
    def observe(d: date) -> date:
        """Shift to Monday if weekend."""
        if d.weekday() == 5: return d - timedelta(days=1)   # Sat → Fri
        if d.weekday() == 6: return d + timedelta(days=1)   # Sun → Mon
        return d

    holidays = [
        observe(date(year, 1, 1)),                                     # New Year's Day
        _nth_weekday(year, 1, 3, 0),                                   # MLK Day (3rd Mon Jan)
        _nth_weekday(year, 2, 3, 0),                                   # Presidents Day (3rd Mon Feb)
        _good_friday(year),                                             # Good Friday
        _last_weekday(year, 5, 0),                                     # Memorial Day (last Mon May)
        observe(date(year, 6, 19)),                                    # Juneteenth
        observe(date(year, 7, 4)),                                     # Independence Day
        _nth_weekday(year, 9, 1, 0),                                   # Labor Day (1st Mon Sep)
        _nth_weekday(year, 11, 4, 3),                                  # Thanksgiving (4th Thu Nov)
        observe(date(year, 12, 25)),                                   # Christmas
    ]
    # Unique, sorted
    return sorted(set(holidays))

def forex_holidays(year: int) -> list[date]:
    """Forex (gold) low-liquidity days — Christmas & New Year only."""
    def observe(d: date) -> date:
        if d.weekday() == 5: return d - timedelta(days=1)
        if d.weekday() == 6: return d + timedelta(days=1)
        return d
    return sorted({observe(date(year, 1, 1)), observe(date(year, 12, 25))})


# ── Core status functions ─────────────────────────────────────────────────────

def is_forex_open(dt: Optional[datetime] = None) -> bool:
    """Gold/Forex is open Mon 00:00 UTC – Fri 22:00 UTC (5d/24h)."""
    dt = dt or datetime.now(timezone.utc)
    wd = dt.weekday()   # 0=Mon … 6=Sun
    h, m = dt.hour, dt.minute
    if wd == 5: return False   # Saturday — closed all day
    if wd == 6: return False   # Sunday — closed until 22:00 UTC
    if wd == 4 and (h > 22 or (h == 22 and m > 0)): return False  # Fri after 22:00
    return True

def is_nyse_open(dt: Optional[datetime] = None) -> bool:
    """NYSE regular session open?"""
    dt = dt or datetime.now(timezone.utc)
    if dt.weekday() >= 5: return False
    if dt.date() in nyse_holidays(dt.year): return False
    oh, om, ch, cm = nyse_hours_utc(dt)
    minutes = dt.hour * 60 + dt.minute
    return (oh * 60 + om) <= minutes < (ch * 60 + cm)

def active_sessions(dt: Optional[datetime] = None) -> list[str]:
    """Return list of currently active forex sessions."""
    dt = dt or datetime.now(timezone.utc)
    if not is_forex_open(dt):
        return []
    active = []
    h, m = dt.hour, dt.minute
    t = h * 60 + m
    for name, sess in SESSIONS.items():
        oh, om = sess["open"]
        ch, cm = sess["close"]
        opens  = oh * 60 + om
        closes = ch * 60 + cm
        if sess["wrap"]:   # crosses midnight
            if t >= opens or t < closes:
                active.append(name)
        else:
            if opens <= t < closes:
                active.append(name)
    return active

def active_overlaps(dt: Optional[datetime] = None) -> list[str]:
    dt = dt or datetime.now(timezone.utc)
    if not is_forex_open(dt):
        return []
    active = []
    h, m = dt.hour, dt.minute
    t = h * 60 + m
    for name, ovl in OVERLAPS.items():
        opens  = ovl["open"][0]  * 60 + ovl["open"][1]
        closes = ovl["close"][0] * 60 + ovl["close"][1]
        if opens <= t < closes:
            active.append(name.replace("_", "/"))
    return active

def next_open(dt: Optional[datetime] = None) -> Optional[datetime]:
    """Return UTC datetime when forex next opens (if currently closed)."""
    dt = dt or datetime.now(timezone.utc)
    if is_forex_open(dt):
        return None
    # Walk forward minute by minute until open
    candidate = dt.replace(second=0, microsecond=0) + timedelta(minutes=1)
    for _ in range(10080):   # max 1 week
        if is_forex_open(candidate):
            return candidate
        candidate += timedelta(minutes=1)
    return None

def next_session_change(dt: Optional[datetime] = None) -> dict:
    """Return info about when the next session opens or closes."""
    dt = dt or datetime.now(timezone.utc)
    h, m = dt.hour, dt.minute
    t = h * 60 + m
    events = []
    for name, sess in SESSIONS.items():
        oh, om = sess["open"]
        ch, cm = sess["close"]
        opens  = oh * 60 + om
        closes = ch * 60 + cm
        if sess["wrap"]:
            # If currently open (t >= opens OR t < closes), next event is close
            if t >= opens or t < closes:
                if t >= opens:
                    mins_to = closes + 1440 - t if closes < t else closes - t
                else:
                    mins_to = closes - t
                events.append({"type": "close", "session": name, "mins": mins_to})
            else:
                mins_to = opens - t if opens > t else opens + 1440 - t
                events.append({"type": "open", "session": name, "mins": mins_to})
        else:
            if opens <= t < closes:
                events.append({"type": "close", "session": name, "mins": closes - t})
            elif t < opens:
                events.append({"type": "open", "session": name, "mins": opens - t})
            else:
                events.append({"type": "open", "session": name, "mins": opens + 1440 - t})
    if not events:
        return {}
    return min(events, key=lambda e: e["mins"])


# ── Main status payload ───────────────────────────────────────────────────────

def get_market_status(dt: Optional[datetime] = None) -> dict:
    """Full market status snapshot."""
    dt = dt or datetime.now(timezone.utc)
    wd = dt.weekday()
    weekday_name = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"][wd]
    is_weekend = wd >= 5

    forex_open = is_forex_open(dt)
    nyse_open  = is_nyse_open(dt)
    sessions   = active_sessions(dt)
    overlaps   = active_overlaps(dt)

    # Upcoming holidays
    year = dt.year
    all_nyse = nyse_holidays(year) + nyse_holidays(year + 1)
    upcoming_nyse = [str(d) for d in all_nyse if d >= dt.date()][:5]
    all_forex = forex_holidays(year) + forex_holidays(year + 1)
    upcoming_forex = [str(d) for d in all_forex if d >= dt.date()][:3]

    # Next open if closed
    n_open = next_open(dt) if not forex_open else None

    # Session schedule (UTC)
    schedule = {
        "Sydney":    "21:00 – 06:00 UTC",
        "Tokyo":     "00:00 – 09:00 UTC",
        "London":    "08:00 – 17:00 UTC",
        "New_York":  "13:00 – 22:00 UTC",
        "NYSE":      "13:30 – 20:00 UTC (EDT) / 14:30 – 21:00 UTC (EST)",
    }
    overlaps_schedule = {
        "Tokyo/London":    "08:00 – 09:00 UTC  (1h, low volatility)",
        "London/New_York": "13:00 – 17:00 UTC  (4h, HIGHEST volatility)",
    }

    oh, om, ch, cm = nyse_hours_utc(dt)
    nyse_window = f"{oh:02d}:{om:02d} – {ch:02d}:{cm:02d} UTC (today)"

    return {
        "timestamp_utc":      dt.isoformat(),
        "weekday":            weekday_name,
        "is_weekend":         is_weekend,
        "forex_gold_open":    forex_open,
        "nyse_open":          nyse_open,
        "active_sessions":    sessions,
        "active_overlaps":    overlaps if overlaps else ["none"],
        "next_open_utc":      n_open.strftime("%Y-%m-%d %H:%M UTC") if n_open else "already open",
        "nyse_hours_today":   nyse_window,
        "session_schedule":   schedule,
        "overlap_schedule":   overlaps_schedule,
        "upcoming_nyse_holidays":  upcoming_nyse,
        "upcoming_forex_holidays": upcoming_forex,
        "notes": [
            "Gold (XAUUSD) trades 24h/5d — Mon 00:00 to Fri 22:00 UTC",
            "Best gold volatility: London/NY overlap 13:00–17:00 UTC",
            "Avoid: Friday 20:00–22:00 UTC (thin liquidity), Sunday open",
            "NYSE stocks: closed weekends + 10 US holidays per year",
        ],
    }
