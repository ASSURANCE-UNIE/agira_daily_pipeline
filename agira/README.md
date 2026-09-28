# AGIRA RA translator

A small, stateless Python package that translates validated business JSON into
AGIRA RA fixed-width files and AGIRA files back into readable JSON. Database
queries, daily scheduling, history, depots, and FTP transfer intentionally live
outside this repository.

Supported outbound documents:

- questions (`AGQUES`);
- termination create/modify/delete (`AGRESC`, `AGRESM`, `AGRESS`).

Supported inbound views:

- raw/lossless parsed messages;
- questions;
- responses and rejections;
- termination requests;
- termination responses.

Files use Windows-1252, CRLF line endings, strict fixed widths, and the AGIRA
8,136-byte maximum line length.

## Install and test

```powershell
uv sync --all-extras --dev
uv run pytest
uv build
```

The core package depends only on Pydantic. The HTTP service is an optional
`api` extra.

## CLI

```powershell
uv run agira-translate to-agira examples/question-batch.json
uv run agira-translate to-json AGIRA.TXT --kind raw
uv run agira-translate to-json RESPONSE.TXT --kind responses
```

The generated AGIRA filename comes from the validated batch unless `--output`
is given. Existing outputs are protected; `--overwrite` must be explicit.

## Python library

```python
import json
from pathlib import Path

from agira_api import agira_to_json, json_to_agira

document = json.loads(Path("batch.json").read_text(encoding="utf-8"))
rendered = json_to_agira(document)
Path(rendered.filename).write_bytes(rendered.payload)

parsed = agira_to_json(
    Path(rendered.filename).read_bytes(),
    source_filename=rendered.filename,
    kind="raw",
)
```

`raw` is the safest default for inbound files. An accepted termination reply can
be identical to the request, so it cannot always be classified from bytes alone.
Use an explicit semantic `kind` when the inbound channel is known.

## Stateless HTTP API

```powershell
uv run uvicorn agira_api.main:app --host 127.0.0.1 --port 8000
```

- `GET /health`
- `POST /v1/json-to-agira` with a question or termination batch JSON body;
  returns the AGIRA TXT bytes and filename/hash headers.
- `POST /v1/agira-to-json?filename=FILE.TXT&kind=raw` with AGIRA bytes in the
  request body; returns JSON.

The API does not write uploaded or generated files. This makes it safe to embed
in a scheduler or another service without hidden inbox/outbox state.

## JSON selection and validation

The top-level key selects the outbound schema:

- `questions` → `QuestionBatch`;
- `records` → `TerminationBatch`.

Exactly one must be present. Unknown fields are rejected. Dates are ISO dates in
JSON. The question family `NOM+NAISSANCE` also supports a month/year partial date,
rendered as `00MMYYYY`, because that is the AGIRA matching form.

The authoritative model definitions are in `src/agira_api/models.py`. See
`docs/AGIRA_RA_API_AND_FLAT_FILE_SPEC.md` and the automated tests for layouts and
examples.

## Scope boundary

This repository is only the format boundary:

```text
business JSON  <->  agira-ra-translator  <->  AGIRA TXT
```

The parent `agira_daily_pipeline` repository owns SQL extraction,
35-day/yesterday date rules, daily archives, depot publication, and operational
documentation. FTP transfer remains out of scope for both projects.
