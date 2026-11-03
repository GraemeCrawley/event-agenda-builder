"""Turn a spreadsheet (saved as CSV) into sessions.json.

    python tools/csv_to_sessions.py my-agenda.csv events/my-event/sessions.json

Columns (first row = these headings; only start, end and title are required):
  start, end    times like 09:30, 14:00 or 2:00 PM
  title         session name
  room          where it is, e.g. "Level 2, Room 201" (match rooms.json if you add a map)
  description   a sentence or two
  speakers      "Name (Role, Org); Name (Org); Name"
  url           link to the session on the official agenda
  fixed         "yes" for things everyone sees and nobody picks (registration, lunch)
  lab           "yes" for hands-on sessions (gets its own colour)
See samples/example-sessions.csv.
"""
import csv
import json
import re
import sys
from pathlib import Path

YES = {"yes", "y", "true", "1", "x"}


def to24(t: str) -> str:
    t = t.strip().upper().replace(".", "")
    m = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?\s*(AM|PM)?", t)
    if not m:
        raise ValueError(f"can't read the time {t!r}; use 09:30 or 9:30 AM")
    h, mins, ap = int(m[1]), m[2] or "00", m[3]
    if ap:
        h = h % 12 + (12 if ap == "PM" else 0)
    return f"{h:02d}:{mins}"


def speakers(cell: str) -> list[dict]:
    out = []
    for part in filter(None, (p.strip() for p in (cell or "").split(";"))):
        m = re.fullmatch(r"(.+?)\s*\((.*)\)", part)
        if not m:
            out.append({"name": part, "role": "", "org": ""})
            continue
        bits = [b.strip() for b in m[2].split(",")]
        role, org = (", ".join(bits[:-1]), bits[-1]) if len(bits) > 1 else ("", bits[0])
        out.append({"name": m[1], "role": role, "org": org})
    return out


def main(src: str, dest: str) -> None:
    with open(src, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    sessions = []
    for n, r in enumerate(rows, start=2):
        r = {(k or "").strip().lower(): (v or "").strip() for k, v in r.items()}
        if not any(r.values()):
            continue
        try:
            s = {"id": f"s{len(sessions):02d}", "start": to24(r["start"]), "end": to24(r["end"]),
                 "title": r["title"], "room": r.get("room", ""), "description": r.get("description", ""),
                 "speakers": speakers(r.get("speakers", "")), "url": r.get("url", "")}
        except (KeyError, ValueError) as e:
            sys.exit(f"Row {n}: {e}")
        if not s["title"]:
            sys.exit(f"Row {n}: no title")
        if r.get("fixed", "").lower() in YES:
            s["fixed"] = True
        if r.get("lab", "").lower() in YES:
            s["lab"] = True
        sessions.append(s)
    Path(dest).parent.mkdir(parents=True, exist_ok=True)
    Path(dest).write_text(json.dumps(sessions, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(sessions)} sessions to {dest}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
