from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response
from pydantic import ValidationError

from .fixed_width import SerializationError, safe_filename
from .parser import ParseError
from .service import agira_to_json, json_to_agira


MAX_UPLOAD_BYTES = 50 * 1024 * 1024

app = FastAPI(
    title="AGIRA RA Translator",
    version="0.2.0",
    description=(
        "Stateless translation between business JSON and AGIRA RA fixed-width "
        "files. It does not query databases, persist files, or transfer FTP files."
    ),
)


@app.get("/health", tags=["operations"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/json-to-agira", tags=["translation"])
def translate_json_to_agira(document: dict[str, Any]) -> Response:
    try:
        rendered = json_to_agira(document)
    except (ValidationError, SerializationError, UnicodeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return Response(
        content=rendered.payload,
        media_type="text/plain; charset=windows-1252",
        headers={
            "Content-Disposition": f'attachment; filename="{rendered.filename}"',
            "X-AGIRA-Document-Type": rendered.document_type,
            "X-AGIRA-Item-Count": str(rendered.item_count),
            "X-Content-SHA256": rendered.sha256,
        },
    )


@app.post("/v1/agira-to-json", tags=["translation"])
async def translate_agira_to_json(
    request: Request,
    filename: Annotated[str, Query(min_length=1, max_length=180)] = "AGIRA.TXT",
    kind: Annotated[
        Literal[
            "raw",
            "questions",
            "responses",
            "termination-requests",
            "termination-responses",
        ],
        Query(),
    ] = "raw",
) -> JSONResponse:
    try:
        source_filename = safe_filename(filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    payload = await request.body()
    if not payload:
        raise HTTPException(status_code=422, detail="request body is empty")
    if len(payload) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"request body exceeds {MAX_UPLOAD_BYTES} bytes",
        )
    try:
        translated = agira_to_json(
            payload,
            source_filename=source_filename,
            kind=kind,
        )
    except (ParseError, UnicodeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return JSONResponse(content=translated)
