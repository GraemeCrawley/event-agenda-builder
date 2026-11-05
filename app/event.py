"""Load and check one event folder.

An event folder holds:

  event.json     required  name, date, timezone and display text
  sessions.json  required  every session (talks, breaks, labs...)
  slots.json     optional  time slots; worked out from session start times if missing
  picks.json     optional  suggested sessions: {"<session id>": "why it's suggested"}
  rooms.json     optional  map pins: {"<room>": {"map": "<map id>", "x": 0-100, "y": 0-100}}
  maps/          optional  floor-plan images named in event.json "maps"

See samples/example-event/ for a complete example and README.md for the format.
`load_event` raises EventError with a readable message on anything wrong, so
`python tools/check_event.py <folder>` can tell a person what to fix.
"""

from __future__ import annotations

import json
import re
from datetime import date as Date
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,40}$")


class EventError(ValueError):
    pass


def _read(folder: Path, name: str, default=None):
    path = folder / name
    if not path.exists():
        if default is None:
            raise EventError(f"missing {path}")
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise EventError(f"{path} is not valid JSON: line {e.lineno}, column {e.colno}: {e.msg}") from None


def fmt_time(t: str) -> str:
    """'13:30' -> '1:30 PM'."""
    h, m = map(int, t.split(":"))
    return f"{h % 12 or 12}:{m:02d} {'PM' if h >= 12 else 'AM'}"


def derive_slots(sessions: list[dict]) -> list[dict]:
    """One slot per distinct start time.

    Sessions marked "fixed": true (registration, lunch, keynote...) and start
    times with only one session become fixed slots (shown, not chosen).
    Everything else becomes a choice. Write the result to slots.json with
    tools/make_slots.py if you want to merge or rename slots by hand.
    """
    by_start: dict[str, list[dict]] = {}
    for s in sorted(sessions, key=lambda s: (s["start"], s["end"])):
        by_start.setdefault(s["start"], []).append(s)
    slots = []
    for start, group in sorted(by_start.items()):
        fixed = [s["id"] for s in group if s.get("fixed")]
        options = [s["id"] for s in group if not s.get("fixed")]
        if len(options) == 1:
            fixed, options = fixed + options, []
        hhmm = start.replace(":", "")
        if fixed:
            slots.append({"id": f"f{hhmm}", "label": fmt_time(start), "fixed": fixed})
        if options:
            slots.append({"id": f"t{hhmm}", "label": fmt_time(start), "options": options})
    return slots


def _check_session(s, n: int) -> None:
    where = f"sessions.json item {n + 1}"
    if not isinstance(s, dict):
        raise EventError(f"{where} is not an object")
    for key in ("id", "start", "end", "title"):
        if not s.get(key):
            raise EventError(f"{where} has no \"{key}\"")
    where = f"session {s['id']!r}"
    if not ID_RE.match(str(s["id"])):
        raise EventError(f"{where}: id may only use letters, digits, - and _")
    if s["id"] == "skip":
        raise EventError(f"{where}: \"skip\" is reserved")
    for key in ("start", "end"):
        if not TIME_RE.match(str(s[key])):
            raise EventError(f"{where}: {key} must be 24-hour HH:MM, e.g. \"09:30\" or \"14:00\" (got {s[key]!r})")
    if s["end"] <= s["start"]:
        raise EventError(f"{where}: ends ({s['end']}) before it starts ({s['start']})")
    s.setdefault("room", "")
    s.setdefault("description", "")
    s.setdefault("url", "")
    s.setdefault("speakers", [])
    if not isinstance(s["speakers"], list):
        raise EventError(f"{where}: speakers must be a list")
    for p in s["speakers"]:
        if not isinstance(p, dict) or not p.get("name"):
            raise EventError(f"{where}: each speaker needs a \"name\"")
        p.setdefault("role", "")
        p.setdefault("org", "")
    if s["url"] and not str(s["url"]).startswith(("https://", "http://")):
        raise EventError(f"{where}: url must start with https://")


def load_event(folder: str | Path) -> dict:
    folder = Path(folder)
    if not folder.is_dir():
        raise EventError(f"event folder not found: {folder}")
    event = _read(folder, "event.json")
    sessions = _read(folder, "sessions.json")
    slots = _read(folder, "slots.json", default=[])
    picks = _read(folder, "picks.json", default={})
    rooms = _read(folder, "rooms.json", default={})

    # event.json
    for key in ("id", "name"):
        if not event.get(key):
            raise EventError(f"event.json has no \"{key}\"")
    if not ID_RE.match(event["id"]):
        raise EventError("event.json: id may only use letters, digits, - and _ (e.g. \"my-conf-2026\")")
    if event.get("date"):
        try:
            Date.fromisoformat(event["date"])
        except ValueError:
            raise EventError(f"event.json: date must be YYYY-MM-DD (got {event['date']!r})") from None
    try:
        ZoneInfo(event.setdefault("timezone", "UTC"))
    except (ZoneInfoNotFoundError, ValueError):
        raise EventError(f"event.json: unknown timezone {event['timezone']!r}; use a name like \"America/New_York\"") from None
    event.setdefault("subtitle", "")
    event.setdefault("intro", "Pick one session per time slot, then save to get a link you can reopen or share.")
    event.setdefault("skip_note", "Free time, meetings, coffee.")
    event.setdefault("link_label", "Open on the official agenda")
    event.setdefault("maps", [])
    # links: a few related pages shown under the title, e.g. the other days of a
    # multi-day event (one instance per day). Relative URLs like "../day2/" work.
    links = event.setdefault("links", [])
    if not isinstance(links, list):
        raise EventError("event.json: links must be a list of {\"label\", \"url\"}")
    for link in links:
        if not isinstance(link, dict) or not link.get("label") or not link.get("url"):
            raise EventError(f"event.json: every link needs \"label\" and \"url\" ({link})")
        if not re.match(r"^(https?://|\.{0,2}/|[A-Za-z0-9_.-]+/?$)", str(link["url"])):
            raise EventError(f"event.json: link url must be http(s) or a relative path (got {link['url']!r})")
        link.setdefault("current", False)

    # maps: each listed image must exist; give the page a cache-busting URL.
    map_ids = set()
    for m in event["maps"]:
        for key in ("id", "name", "image", "width", "height"):
            if not m.get(key):
                raise EventError(f"event.json: every map needs \"{key}\" ({m})")
        path = folder / "maps" / m["image"]
        if not path.is_file() or path.resolve().parent != (folder / "maps").resolve():
            raise EventError(f"event.json: map image not found: {path}")
        m["id"] = str(m["id"])
        m.setdefault("short", "")
        m.setdefault("description", m["name"])
        m["src"] = f"maps/{m['image']}?v={int(path.stat().st_mtime)}"
        map_ids.add(m["id"])

    # sessions
    if not isinstance(sessions, list) or not sessions:
        raise EventError("sessions.json must be a non-empty list")
    for n, s in enumerate(sessions):
        _check_session(s, n)
    by_id = {}
    for s in sessions:
        if s["id"] in by_id:
            raise EventError(f"two sessions share the id {s['id']!r}")
        by_id[s["id"]] = s

    # slots
    if not slots:
        slots = derive_slots(sessions)
    seen_slot, placed = set(), set()
    for slot in slots:
        sid = slot.get("id")
        if not sid or not ID_RE.match(sid) or sid in seen_slot:
            raise EventError(f"slots.json: every slot needs a unique id ({slot})")
        seen_slot.add(sid)
        ids = slot.get("options", []) + slot.get("fixed", [])
        if bool(slot.get("options")) == bool(slot.get("fixed")):
            raise EventError(f"slots.json: slot {sid!r} needs either \"options\" or \"fixed\" (not both)")
        for i in ids:
            if i not in by_id:
                raise EventError(f"slots.json: slot {sid!r} lists unknown session {i!r}")
            if i in placed:
                raise EventError(f"slots.json: session {i!r} is in more than one slot")
            placed.add(i)
        slot.setdefault("label", fmt_time(min(by_id[i]["start"] for i in ids)))
    missing = set(by_id) - placed
    if missing:
        raise EventError(f"slots.json: these sessions aren't in any slot: {', '.join(sorted(missing))}")

    for i in picks:
        if i not in by_id:
            raise EventError(f"picks.json: unknown session {i!r}")
    for room, pin in rooms.items():
        if pin.get("map") is None or str(pin["map"]) not in map_ids:
            raise EventError(f"rooms.json: {room!r} points at map {pin.get('map')!r}, which isn't in event.json \"maps\"")
        pin["map"] = str(pin["map"])
        for k in ("x", "y"):
            if not isinstance(pin.get(k), (int, float)) or not 0 <= pin[k] <= 100:
                raise EventError(f"rooms.json: {room!r} {k} must be a number from 0 to 100 (percent of the image)")

    return {"event": event, "sessions": sessions, "slots": slots, "picks": picks, "rooms": rooms}


def valid_choices(data: dict) -> dict[str, set[str]]:
    """Allowed answers per choosable slot: its sessions, any session from an
    earlier slot still running when this slot starts ("stay in the lab"), or skip."""
    by_id = {s["id"]: s for s in data["sessions"]}
    out = {}
    for slot in data["slots"]:
        if not slot.get("options"):
            continue
        start = min(by_id[i]["start"] for i in slot["options"])
        running = {
            i for other in data["slots"] if other is not slot
            for i in other.get("options", [])
            if by_id[i]["start"] < start < by_id[i]["end"]
        }
        out[slot["id"]] = set(slot["options"]) | running | {"skip"}
    return out
