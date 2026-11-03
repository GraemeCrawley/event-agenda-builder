import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "samples" / "example-event"
os.environ["DATA_DIR"] = tempfile.mkdtemp()
os.environ["EVENT_DIR"] = str(SAMPLE)
sys.path.insert(0, str(ROOT / "app"))

from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402
from event import EventError, derive_slots, load_event  # noqa: E402

c = TestClient(main.app)
# Sample event slots are worked out from start times (it has no slots.json).
FULL = {"t1015": "s03", "t1100": "skip", "t1300": "s12", "t1400": "s14", "t1445": "s17"}


def test_sample_slots_are_derived():
    d = c.get("/api/data").json()
    assert [s["id"] for s in d["slots"] if s.get("options")] == list(FULL)
    assert d["slots"][0] == {"id": "f0800", "label": "8:00 AM", "fixed": ["s01", "s00"]}
    slotted = {i for s in d["slots"] for i in s.get("options", []) + s.get("fixed", [])}
    assert slotted == {s["id"] for s in d["sessions"]}


def test_save_and_load_roundtrip():
    r = c.post("/api/agendas", json={"choices": FULL})
    assert r.status_code == 200
    aid = r.json()["id"]
    assert len(aid) == 8
    saved = c.get(f"/api/agendas/{aid}").json()
    assert saved["choices"] == FULL and saved["event"] == "example-summit-2026"
    assert c.get(f"/a/{aid}").status_code == 200


def test_staying_in_a_long_session_is_valid_only_where_it_overlaps():
    ok = FULL | {"t1015": "s05", "t1100": "s05"}          # 90-minute lab
    assert c.post("/api/agendas", json={"choices": ok}).status_code == 200
    ok = FULL | {"t1400": "s16", "t1445": "s16"}          # 75-minute workshop
    assert c.post("/api/agendas", json={"choices": ok}).status_code == 200
    bad = FULL | {"t1300": "s05"}
    assert c.post("/api/agendas", json={"choices": bad}).status_code == 400


def test_rejects_missing_or_unknown_choices():
    assert c.post("/api/agendas", json={"choices": {"t1015": "s03"}}).status_code == 400
    assert c.post("/api/agendas", json={"choices": FULL | {"t1015": "s17"}}).status_code == 400


def test_unknown_or_malformed_id_404():
    assert c.get("/api/agendas/AAAAAAAA").status_code == 404
    assert c.get("/api/agendas/..%2Fetc").status_code == 404


def test_maps_are_served_and_every_room_is_pinned():
    d = c.get("/api/data").json()
    assert {s["room"] for s in d["sessions"]} <= set(d["rooms"])
    for m in d["event"]["maps"]:
        assert c.get(m["src"]).status_code == 200


def test_page_has_no_event_specific_text():
    html = (ROOT / "app/static/index.html").read_text()
    assert "Example Tech Summit" not in html  # everything event-specific comes from event.json


# --- event folder checks -------------------------------------------------

def _copy_sample(tmp_path):
    dest = tmp_path / "ev"
    shutil.copytree(SAMPLE, dest)
    return dest


def _edit(folder, name, fn):
    p = folder / name
    p.write_text(json.dumps(fn(json.loads(p.read_text()))))


def test_explicit_slots_json_is_used(tmp_path):
    ev = _copy_sample(tmp_path)
    slots = derive_slots(json.loads((ev / "sessions.json").read_text()))
    slots[2]["label"] = "Morning talks"
    (ev / "slots.json").write_text(json.dumps(slots))
    assert load_event(ev)["slots"][2]["label"] == "Morning talks"


@pytest.mark.parametrize("name,fn,msg", [
    ("sessions.json", lambda s: s + [dict(s[0])], "share the id"),
    ("sessions.json", lambda s: [s[0] | {"start": "9:00"}] + s[1:], "HH:MM"),
    ("sessions.json", lambda s: [s[0] | {"end": "07:00"}] + s[1:], "before it starts"),
    ("event.json", lambda e: e | {"timezone": "Mars/Base"}, "unknown timezone"),
    ("event.json", lambda e: e | {"date": "18/06/2026"}, "YYYY-MM-DD"),
    ("picks.json", lambda p: p | {"nope": "x"}, "unknown session"),
    ("rooms.json", lambda r: r | {"X": {"map": "9", "x": 1, "y": 1}}, "isn't in event.json"),
])
def test_bad_event_folders_say_what_is_wrong(tmp_path, name, fn, msg):
    ev = _copy_sample(tmp_path)
    _edit(ev, name, fn)
    with pytest.raises(EventError, match=msg):
        load_event(ev)


def test_slot_missing_a_session_is_reported(tmp_path):
    ev = _copy_sample(tmp_path)
    slots = derive_slots(json.loads((ev / "sessions.json").read_text()))
    (ev / "slots.json").write_text(json.dumps(slots[:-1]))
    with pytest.raises(EventError, match="aren't in any slot"):
        load_event(ev)


def test_csv_import(tmp_path):
    out = tmp_path / "sessions.json"
    subprocess.run([sys.executable, ROOT / "tools/csv_to_sessions.py", ROOT / "samples/example-sessions.csv", out], check=True)
    s = json.loads(out.read_text())
    assert s[0] == {"id": "s00", "start": "08:00", "end": "09:00", "title": "Breakfast", "room": "Level 1, Hall A",
                    "description": "Coffee and pastries.", "speakers": [], "url": "", "fixed": True}
    assert s[1]["speakers"] == [{"name": "Fay Fixture", "role": "CTO", "org": "Sample Labs"},
                                {"name": "Bob Sample", "role": "", "org": "Sample Labs"}]
    assert s[4]["lab"] is True and s[4]["speakers"][0] == {"name": "Casey Demo", "role": "", "org": ""}


def test_check_event_tool_on_sample():
    r = subprocess.run([sys.executable, ROOT / "tools/check_event.py", SAMPLE], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert r.stdout.startswith("OK: Example Tech Summit")
