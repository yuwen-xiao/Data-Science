from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .crawler import (
    ALLOWED_HOSTS,
    DEFAULT_START_URL,
    BusyError,
    CrawlManager,
    CrawlParams,
    ValidationError,
    csv_bytes,
    json_bytes,
    log_bytes,
    validate_start_url,
)

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
DATA_DIR = BASE_DIR / "data" / "runtime"
manager = CrawlManager(DATA_DIR)

app = FastAPI(
    title="Book Crawler Console",
    description="Assignment 01 question 01: a constrained local crawler demo.",
    version="1.0.0",
)


class CreateJobRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    start_url: str = DEFAULT_START_URL
    max_pages: int = Field(default=3, ge=1, le=50)
    request_interval: float = Field(default=1.0, ge=0, le=10)
    fetch_details: bool = True

    @field_validator("start_url")
    @classmethod
    def check_start_url(cls, value: str) -> str:
        try:
            return validate_start_url(value)
        except ValidationError as exc:
            raise ValueError(str(exc)) from exc


def job_view(job: dict[str, Any]) -> dict[str, Any]:
    result = dict(job)
    result["fetch_details"] = bool(result.get("fetch_details"))
    result["progress_percent"] = (
        round(100 * result.get("pages_done", 0) / result["pages_total"], 1)
        if result.get("pages_total")
        else 0
    )
    return result


def get_job_or_404(job_id: str) -> dict[str, Any]:
    job = manager.store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在")
    return job


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "allowed_hosts": sorted(ALLOWED_HOSTS),
        "default_start_url": DEFAULT_START_URL,
        "single_worker": True,
    }


@app.get("/api/jobs")
def list_jobs() -> list[dict[str, Any]]:
    latest = manager.store.latest_job()
    return [job_view(latest)] if latest else []


@app.get("/api/jobs/latest")
def latest_job() -> dict[str, Any] | None:
    job = manager.store.latest_job()
    return job_view(job) if job else None


@app.post("/api/jobs", status_code=201)
def create_job(request: CreateJobRequest) -> dict[str, Any]:
    params = CrawlParams(
        start_url=request.start_url,
        max_pages=request.max_pages,
        request_interval=request.request_interval,
        fetch_details=request.fetch_details,
    )
    try:
        job = manager.create(params)
    except BusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return job_view(job)


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    return job_view(get_job_or_404(job_id))


@app.post("/api/jobs/{job_id}/pause")
def pause_job(job_id: str) -> dict[str, Any]:
    get_job_or_404(job_id)
    try:
        return job_view(manager.pause(job_id))
    except (ValidationError, KeyError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/jobs/{job_id}/resume")
def resume_job(job_id: str) -> dict[str, Any]:
    get_job_or_404(job_id)
    try:
        return job_view(manager.resume(job_id))
    except (ValidationError, KeyError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/jobs/{job_id}/stop")
def stop_job(job_id: str) -> dict[str, Any]:
    get_job_or_404(job_id)
    try:
        return job_view(manager.stop(job_id))
    except (ValidationError, KeyError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/jobs/{job_id}/preview")
def preview_job(
    job_id: str,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    job = get_job_or_404(job_id)
    return {
        "job_id": job_id,
        "total": job["records_count"],
        "offset": offset,
        "limit": limit,
        "items": manager.store.items(job_id, limit=limit, offset=offset),
    }


@app.get("/api/jobs/{job_id}/failures")
def failures(job_id: str) -> list[dict[str, Any]]:
    get_job_or_404(job_id)
    return manager.store.get_failures(job_id)


@app.get("/api/jobs/{job_id}/logs")
def logs(
    job_id: str,
    limit: int = Query(default=200, ge=1, le=1000),
    after_id: int = Query(default=0, ge=0),
) -> list[dict[str, Any]]:
    get_job_or_404(job_id)
    return manager.store.get_logs(job_id, limit=limit, after_id=after_id)


@app.get("/api/jobs/{job_id}/result.csv")
def download_csv(job_id: str) -> Response:
    get_job_or_404(job_id)
    return Response(
        content=csv_bytes(manager.store, job_id),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="result-{job_id}.csv"'},
    )


@app.get("/api/jobs/{job_id}/result.json")
def download_json(job_id: str) -> Response:
    get_job_or_404(job_id)
    return Response(
        content=json_bytes(manager.store, job_id),
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="result-{job_id}.json"'},
    )


@app.get("/api/jobs/{job_id}/run.log")
def download_log(job_id: str) -> Response:
    get_job_or_404(job_id)
    return Response(
        content=log_bytes(manager.store, job_id),
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="run-{job_id}.log"'},
    )


@app.exception_handler(ValidationError)
async def validation_exception_handler(_request, exc: ValidationError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
