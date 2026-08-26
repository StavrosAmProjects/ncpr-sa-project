# CyLaw / CyLII lookup API (unofficial)

A small, self-hosted API that lets an AI assistant locate Cypriot case law
and legislation on cylaw.org / cylii.org, since neither site publishes a
public search API.

## Run it

```bash
pip install -r requirements.txt --break-system-packages
uvicorn api:app --reload --port 8008
```

Interactive docs then appear at `http://localhost:8008/docs`.

## Deploy and connect it as a ChatGPT Action

This repository now contains a `Dockerfile` and `render.yaml`. In Render,
create a **Blueprint** from this repository and set `CYLAW_CONTACT_EMAIL` to
an address that can receive polite scraper enquiries. Render will give the
service a public URL such as `https://cylaw-api-xxxx.onrender.com`.

First verify `https://YOUR-URL/health` returns `{"status":"ok"}`. Then open
`openapi.action.yaml`, replace its one server URL placeholder with that exact
public URL, and paste the resulting YAML into the Action schema editor. The
API itself also exposes its live OpenAPI document at `https://YOUR-URL/openapi.json`.

## Endpoints

| Method | Path            | Purpose                                                        |
|--------|-----------------|-----------------------------------------------------------------|
| GET    | `/browse/cylii` | List/filter cases from a cylii.org section (`section`, `year`, `keyword`) |
| GET    | `/browse/cylaw` | List/filter cases from a cylaw.org static index page (`index_path`, `keyword`) |
| GET    | `/document`     | Fetch and return the plain text of a specific case/document URL |
| GET    | `/sections`     | A short hand-curated list of known cylii.org section paths      |

### Example

```
GET /browse/cylii?section=cy/cases/diait/aap&year=2026&keyword=POLYECO
```
```json
[
  {
    "number": "4/2026",
    "title": "POLYECO S.A. v. ΥΠΟΥΡΓΕΙΟΥ ΑΜΥΝΑΣ, Αίτηση 4/2026, 28/5/2026 (Ιεραρχική Προσφυγή)",
    "url": "https://cylii.org/document?id=/cy/cases/diait/aap/2026/ip/4-2026.htm",
    "source": "cylii"
  }
]
```

Then:
```
GET /document?url=https://cylii.org/document?id=/cy/cases/diait/aap/2026/ip/4-2026.htm
```
returns the full text of that decision.

## What this can and can't do (please read)

- **No official API exists** for either site as far as I could confirm.
  This tool works by parsing the same public HTML pages a browser loads —
  it doesn't call any private/internal endpoint.
- **cylaw.org free-text search** is a legacy Perl/Sino CGI engine. I could
  not confirm its exact request parameters from outside a browser, so this
  tool does not attempt to drive that search form. Instead it walks the
  static year/category index pages (e.g. `supreme/index_2024.html`) that
  always exist and are plain links — good for "find rulings from year X in
  court Y", less good for arbitrary keyword search across the whole archive.
- **cylii.org** has clean, guessable listing URLs per court/section/year,
  which this tool reads directly. Its on-page search icon likely calls an
  internal API not meant for external use, so this tool filters client-side
  on the listing pages instead of calling that.
- **Coverage of `/sections`** is a short starter list, not exhaustive — you
  can add more section paths as you find them by browsing cylii.org.
- **Be polite**: the client rate-limits itself (~1.5s between requests) and
  identifies itself with a User-Agent. Please put your real contact email
  in `scraper.py`'s `USER_AGENT` before running this seriously, and don't
  crank up request volume — it's a small nonprofit-run legal database, not
  a CDN.
- If you need real bulk or programmatic access, the correct move is to
  email CyLaw (info@cylaw.org) and ask — that's not something this script
  can substitute for.

## Wiring it to an AI assistant

Any assistant that can call HTTP tools can use this once it's running
locally (or deployed somewhere reachable). Give it the three GET endpoints
above as available "tools" with their query parameters, and it can chain:
`browse_cylii`/`browse_cylaw` to find candidate cases → `get_document` to
pull the full text of the one that matches.
