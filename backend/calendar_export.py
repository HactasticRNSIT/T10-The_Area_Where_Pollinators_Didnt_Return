"""
calendar_export.py — Item 5.2
Generates .ics advisory calendars from a decision_brief's intervention_plan.
Uses phenology windows to schedule events before/during the next flowering window.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta, timezone, datetime as _dt
from typing import Any

log = logging.getLogger(__name__)


def build_advisory_calendar(
    zone_id: str,
    zone_name: str,
    decision_brief: dict[str, Any],
    crops: dict[str, float],
) -> bytes:
    """
    Build an iCalendar (.ics) byte string from a decision_brief's intervention_plan.

    Each intervention_plan item becomes one VEVENT.  Timing is derived from
    phenology: interventions are scheduled 14 days before the earliest upcoming
    flowering window.  If no flowering data is available the event is placed
    one week from today.

    Returns raw .ics bytes (UTF-8).
    """
    try:
        from icalendar import Calendar, Event
    except ImportError:
        log.error("icalendar package not installed; returning empty calendar")
        return b"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nEND:VCALENDAR\r\n"

    from phenology import days_to_flowering

    cal = Calendar()
    cal.add("prodid", "-//PolyNexus//Advisory Calendar//EN")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("x-wr-calname", f"PolyNexus Advisory — {zone_name}")
    cal.add("x-wr-timezone", "Asia/Kolkata")

    today = date.today()
    intervention_plan = decision_brief.get("intervention_plan", [])

    for i, item in enumerate(intervention_plan):
        action = item.get("action", "")
        rationale = item.get("rationale", "")
        factor = item.get("factor", "unknown")
        cost_tier = item.get("cost_tier", "")
        uplift = item.get("uplift_range", "")
        timeframe = item.get("timeframe", "")

        # Determine event date: 14 days before the nearest crop's flowering window
        event_date = today + timedelta(days=7 + i * 3)  # default spacing
        for crop in crops:
            dtf = days_to_flowering(crop, zone_id)
            if dtf is not None and dtf > 14:
                candidate = today + timedelta(days=dtf - 14)
                if candidate > today:
                    event_date = candidate
                    break
            elif dtf is not None and dtf == 0:
                # Already flowering — act immediately
                event_date = today + timedelta(days=i)
                break

        ev = Event()
        ev.add("summary", f"[PolyNexus] {action[:75]}")
        ev.add("dtstart", event_date)
        ev.add("dtend", event_date + timedelta(days=1))
        ev.add("location", zone_name)
        desc_parts = [
            f"Zone: {zone_id}",
            f"Factor: {factor}",
            f"Action: {action}",
        ]
        if rationale:
            desc_parts.append(f"Rationale: {rationale}")
        if cost_tier:
            desc_parts.append(f"Cost tier: {cost_tier}")
        if uplift:
            desc_parts.append(f"Expected uplift: {uplift}")
        if timeframe:
            desc_parts.append(f"Timeframe: {timeframe}")
        ev.add("description", "\n".join(desc_parts))
        ev.add("uid", f"polynexus-{zone_id}-{i}-{today.isoformat()}@polynexus")
        ev.add(
            "dtstamp",
            _dt.now(tz=timezone.utc),
        )
        cal.add_component(ev)

    return cal.to_ical()
