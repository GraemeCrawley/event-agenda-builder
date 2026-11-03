"""Write slots.json for an event folder, worked out from session start times.

    python tools/make_slots.py events/my-event

Without slots.json the app does the same thing on the fly, so you only need
this when you want to edit the slots by hand, e.g. to merge 1:30 and 1:45
starts into one screen, or rename a slot ("After lunch").
Rule: one slot per start time. Sessions with "fixed": true, and start times
with only one session, are shown rather than chosen.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
from event import derive_slots  # noqa: E402

if len(sys.argv) != 2:
    sys.exit(__doc__)
folder = Path(sys.argv[1])
target = folder / "slots.json"
if target.exists():
    sys.exit(f"{target} already exists; delete it first if you want to start again.")
sessions = json.loads((folder / "sessions.json").read_text(encoding="utf-8"))
slots = derive_slots(sessions)
target.write_text("[\n" + ",\n".join(" " + json.dumps(s, ensure_ascii=False) for s in slots) + "\n]\n", encoding="utf-8")
print(f"Wrote {len(slots)} slots to {target}. Check it with: python tools/check_event.py {folder}")
