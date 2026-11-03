"""Agenda Builder: pick one session per time slot, save, share the link.

One screen per time slot; the finished agenda is saved under a random id so it
can be reopened at /a/<id>. No login: ids are unguessable and an agenda is
just a list of session ids from the public agenda.

Storage is one small JSON file per agenda. Saved agendas never change: "edit"
makes a copy with a new id, so a shared link never changes under someone.

Settings (environment variables):
  EVENT_DIR       folder with event.json, sessions.json... (default: the sample event)
  DATA_DIR        where saved agendas go (default: ./data)
  AGENDA_METRICS  set to 1 to expose Prometheus metrics at /metrics
                  (needs `pip install prometheus-fastapi-instrumentator`)
"""

from __future__ import annotations

import json
import os
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from event import load_event, valid_choices

HERE = Path(__file__).parent
EVENT_DIR = Path(os.getenv("EVENT_DIR", HERE.parent / "samples" / "example-event"))
DATA_DIR = Path(os.getenv("DATA_DIR", HERE.parent / "data")) / "agendas"
MAX_AGENDAS = 20_000  # public write endpoint: a hard ceiling, not a quota
AGENDA_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8}$")

DATA = load_event(EVENT_DIR)  # raises EventError with a readable message
VALID = valid_choices(DATA)

app = FastAPI(title=f"agenda-builder: {DATA['event']['id']}")

if os.getenv("AGENDA_METRICS") == "1":
    from prometheus_fastapi_instrumentator import Instrumentator
    Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)


class Agenda(BaseModel):
    choices: dict[str, str]


@app.get("/health")
async def health():
    return {"status": "ok", "event": DATA["event"]["id"]}


@app.get("/api/data")
async def data():
    return DATA


@app.post("/api/agendas")
async def save(agenda: Agenda):
    if set(agenda.choices) != set(VALID):
        raise HTTPException(400, "every time slot needs a choice")
    for slot, choice in agenda.choices.items():
        if choice not in VALID[slot]:
            raise HTTPException(400, f"invalid choice for {slot}")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if sum(1 for _ in DATA_DIR.iterdir()) >= MAX_AGENDAS:
        raise HTTPException(503, "storage full")
    body = {
        "event": DATA["event"]["id"],
        "choices": agenda.choices,
        "created": datetime.now(timezone.utc).isoformat(),
    }
    while True:
        agenda_id = secrets.token_urlsafe(6)  # 8 chars, 48 bits
        try:
            with open(DATA_DIR / f"{agenda_id}.json", "x") as f:
                json.dump(body, f)
            return {"id": agenda_id}
        except FileExistsError:
            continue


@app.get("/api/agendas/{agenda_id}")
async def load(agenda_id: str):
    path = DATA_DIR / f"{agenda_id}.json"
    if not AGENDA_ID_RE.match(agenda_id) or not path.exists():
        raise HTTPException(404, "not found")
    return json.loads(path.read_text())


@app.get("/")
async def index():
    return FileResponse(HERE / "static/index.html")


@app.get("/a/{agenda_id}")
async def view(agenda_id: str):
    # Same page; it reads the id from the URL and works out its base path itself.
    return FileResponse(HERE / "static/index.html")


app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
if (EVENT_DIR / "maps").is_dir():
    app.mount("/maps", StaticFiles(directory=EVENT_DIR / "maps"), name="maps")
