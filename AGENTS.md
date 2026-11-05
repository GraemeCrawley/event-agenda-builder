# AGENTS.md: setting up Agenda Builder for a user

You are helping a human build a schedule picker for one event: usually by turning
that event's published agenda into an event folder, then running the app.
Read README.md for the user-facing version. Here are the essentials.

## What it is

One Docker Compose service, `app` (FastAPI + one static HTML page, no build step),
on `${BIND:-127.0.0.1}:${PORT:-8000}`. It reads one **event folder**, mounted
read-only at `/event` from `${EVENT_FOLDER:-./samples/example-event}` (set in
`.env`, template `.env.example`). Saved agendas are one JSON file each in the
named volume `agendas` (`/data/agendas/<8-char id>.json`). The event is loaded
once at startup: restart after editing it.

Code: `app/event.py` (loads and validates an event folder: the source of truth
for the format), `app/main.py` (API), `app/static/index.html` (whole UI),
`tools/` (`check_event.py`, `csv_to_sessions.py`, `make_slots.py`), `tests/`.

## Event folder format

Put the user's folder in `events/<slug>/` (gitignored). Copy
`samples/example-event/` as a starting point.

- `event.json` (required): `id` (slug), `name`; optional `subtitle`, `date`
  (`YYYY-MM-DD`, enables now/up-next on that day), `timezone` (IANA, default
  UTC), `venue`, `intro`, `skip_note`, `link_label` (tooltip on each session's
  ↗ link), `maps` (list of `{id, name, short, description, image, width, height}`,
  images in `maps/`), `map_source` (`{label, url}`), `links` (list of
  `{label, url, current?}` shown as buttons under the title; for a multi-day
  event use relative URLs like `../day2/` and mark this day `"current": true`).
- `sessions.json` (required): list of `{id, start, end, title, room, description,
  speakers: [{name, role, org}], url}`. Times are 24-hour `HH:MM` in the event's
  timezone. Ids unique, any `[A-Za-z0-9_-]`; `s00`, `s01`... in agenda order is
  the convention. Optional `"fixed": true` (shown, never chosen: registration,
  meals, single-track keynotes) and `"lab": true` (hands-on colour; titles
  matching Lab/Workshop get it anyway).
- `slots.json` (optional): `[{id, label, options: [...]} | {id, label, fixed: [...]}]`.
  Every session in exactly one slot. Without it, slots are derived: one per
  distinct start time; single-session starts and `fixed` sessions become fixed
  slots. Write it out with `make_slots.py` only when you need to merge
  near-identical starts (e.g. 13:30 and 13:45 parallel tracks) or relabel.
  A session that runs past later slot starts (a lab) is offered as "Stay" in
  those slots automatically; don't list it there.
- `picks.json` (optional): `{"<session id>": "why it's suggested"}`. Only add
  picks if the human asks and tells you their criteria; don't invent opinions.
- `rooms.json` (optional): `{"<room string exactly as in sessions>": {"map": "<map id>", "x": 0-100, "y": 0-100}}`,
  percent of the image from left/top.

The format is one day per event folder. For a multi-day event, make one
folder per day (each with its own `id` and `date`) and run one instance per day
(different `PORT` and compose project name, e.g. `docker compose -p day2 up -d`), or ask the human which day matters.
Behind a reverse proxy, serve the days as sibling paths (`/<event>/day1/`, `/<event>/day2/`)
and add `links` to each `event.json` so people can switch days.

## Turning an agenda into sessions.json

1. Ask the human for the agenda URL (and which day, if it's multi-day).
2. Fetch it. Many event sites (Sessionize, Sched, Bizzabo, Cvent, Swapcard...)
   render the agenda with JavaScript, so a plain fetch sees an empty shell.
   Then: look for an embedded iframe or a JSON/API request the page makes
   (often the cleanest source), or use a headless browser (Playwright) and read
   the rendered text. Sessionize and Sched also offer public JSON/iCal feeds
   for many events.
3. Keep scraped material in `raw/` (gitignored); write a throwaway parser
   outside the repo or in `raw/`. Don't commit site-specific scrapers.
4. Convert times to 24-hour in the event's local timezone. Keep the official
   per-session URL in `url` when the site has one.
5. Use the room string the agenda uses, minus repeated venue boilerplate
   (e.g. strip the building name if every room has it).
6. Alternatively build a CSV and run `tools/csv_to_sessions.py` (format in its docstring).

Floor plans: venues often publish PDFs. Render a page to PNG (e.g.
`pdftoppm -r 150 -png`), crop to the useful area, and record the PNG size in
`event.json`. For pins, `pdftotext -bbox` gives label coordinates you can
convert to percentages of the crop. Only use maps the human is happy to
redistribute if their event folder will be shared.

## Steps

```bash
cp .env.example .env          # set EVENT_FOLDER=./events/<slug>
docker compose run --rm app python /srv/tools/check_event.py /event   # must print "OK: ..."
docker compose up -d --build
```

Tools that write files need the folder mounted read-write (the container runs as uid 1000):

```bash
docker compose run --rm -v ./events/<slug>:/work app python /srv/tools/csv_to_sessions.py /work/agenda.csv /work/sessions.json
docker compose run --rm -v ./events/<slug>:/work app python /srv/tools/make_slots.py /work
```

Without Docker: `python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt`,
then `EVENT_DIR=events/<slug> .venv/bin/uvicorn --app-dir app main:app --port 8000`.

## Verify

```bash
docker compose ps                                       # app "Up ... (healthy)"
curl -fsS http://localhost:${PORT:-8000}/health         # {"status":"ok","event":"<id>"}
docker compose logs --tail=50 app                       # EventError here = fix the folder
```

Then open the page, build and save an agenda, and open the saved link with
`?now=HH:MM` (a time during the event) to check the now/up-next markers and
map pins. Compare a few sessions against the official agenda (times, rooms,
speakers): scraping mistakes are the most likely bug.

Tests (need the venv above): `.venv/bin/python -m pytest`. They run against the sample event.

## Rules

- **Never commit `.env`, `events/*`, `raw/`, `data/` or scraped files.** `.gitignore` covers these; don't override it with `git add -f`.
- **Sample data must stay obviously fictional** (example.com links, made-up names). Don't copy a real event into `samples/`.
- **Don't put personal notes or opinions in `picks.json`** unless the human wrote or approved them: they're visible to everyone who opens the page.
- **The app has no authentication by design.** Agenda ids are 48-bit random; saved agendas only hold session ids. The optional agenda name stays in the browser's localStorage. Don't add fields to saved agendas that would make them personal data. If the human exposes it to the internet, recommend HTTPS via a reverse proxy; keep `MAX_AGENDAS` in place.
- **Never run `docker compose down -v`** on a real install without explicit confirmation: it deletes every saved agenda.
- Saved agendas never change; "Edit a copy" makes a new id. Keep it that way so shared links stay stable.
- Keep `index.html` free of event-specific text: everything comes from the event folder (a test checks this).
- Optional extras stay optional: `AGENDA_METRICS=1` exposes Prometheus metrics at `/metrics` only if `prometheus-fastapi-instrumentator` is installed.
