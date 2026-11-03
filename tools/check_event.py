"""Check an event folder and print a summary, or say exactly what's wrong.

    python tools/check_event.py events/my-event
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
from event import EventError, load_event, valid_choices  # noqa: E402

if len(sys.argv) != 2:
    sys.exit(__doc__)
try:
    d = load_event(sys.argv[1])
except EventError as e:
    sys.exit(f"Problem: {e}")

by_id = {s["id"]: s for s in d["sessions"]}
ev = d["event"]
print(f"OK: {ev['name']} ({ev.get('date') or 'no date'}, {ev['timezone']})")
print(f"{len(d['sessions'])} sessions, {len(d['slots'])} slots, {len(d['picks'])} suggestions, "
      f"{len(ev['maps'])} maps, {len(d['rooms'])} pinned rooms")
valid = valid_choices(d)
for slot in d["slots"]:
    if slot.get("fixed"):
        print(f"  {slot['label']:>8}  shown:  " + "; ".join(by_id[i]["title"] for i in slot["fixed"]))
    else:
        extra = len(valid[slot["id"]]) - len(slot["options"]) - 1
        stay = f" (+{extra} still running from earlier)" if extra else ""
        print(f"  {slot['label']:>8}  choose: {len(slot['options'])} sessions{stay}")
if d["rooms"]:
    unpinned = sorted({s["room"] for s in d["sessions"] if s["room"] and s["room"] not in d["rooms"]})
    if unpinned:
        print("Rooms with no map pin (shown without a link): " + "; ".join(unpinned))
