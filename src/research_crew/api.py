"""API HTTP para desplegar el crew.

Expone los mismos endpoints que CrewAI AMP (/inputs, /kickoff, /status/{id})
para que el cliente sea intercambiable entre self-hosted y AMP, más /ask para
hacerle preguntas al relator sobre una corrida ya terminada.

Las ejecuciones corren en segundo plano porque un crew puede tardar minutos;
el cliente hace POST /kickoff, recibe un kickoff_id y consulta GET /status.
"""

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from crewai import Agent
from fastapi import BackgroundTasks, FastAPI, HTTPException
from pydantic import BaseModel, Field

from research_crew.crew import ResearchCrew, build_llm

app = FastAPI(title="Research Crew API", version="0.2.0")

# Registro en memoria. Para producción con varias réplicas reemplazar por
# Redis o una base de datos; ver README.
_jobs: dict[str, dict[str, Any]] = {}
_jobs_lock = threading.Lock()

REQUIRED_INPUTS = ["topic"]
OPTIONAL_INPUTS = {"pregunta": lambda: ""}


class KickoffRequest(BaseModel):
    inputs: dict[str, Any] = Field(default_factory=dict)


class KickoffResponse(BaseModel):
    kickoff_id: str


class TaskTrace(BaseModel):
    tarea: str
    agente: str
    salida: str


class StatusResponse(BaseModel):
    kickoff_id: str
    status: Literal["queued", "running", "completed", "failed"]
    inputs: dict[str, Any] | None = None
    started_at: str | None = None
    finished_at: str | None = None
    result: dict[str, Any] | None = None
    tasks: list[TaskTrace] | None = None
    error: str | None = None
    token_usage: dict[str, Any] | None = None


class AskRequest(BaseModel):
    pregunta: str = Field(min_length=3)


class AskResponse(BaseModel):
    kickoff_id: str
    pregunta: str
    respuesta: str


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _set(kickoff_id: str, **fields: Any) -> None:
    with _jobs_lock:
        _jobs[kickoff_id].update(fields)


def _run_crew(kickoff_id: str, inputs: dict[str, Any]) -> None:
    _set(kickoff_id, status="running", started_at=_now())
    try:
        output = ResearchCrew().crew().kickoff(inputs=inputs)
        usage = output.token_usage
        _set(
            kickoff_id,
            status="completed",
            finished_at=_now(),
            result=output.pydantic.model_dump() if output.pydantic else {"raw": output.raw},
            tasks=[
                {"tarea": t.name or "", "agente": (t.agent or "").strip(), "salida": t.raw}
                for t in output.tasks_output
            ],
            token_usage=usage.model_dump() if hasattr(usage, "model_dump") else None,
        )
    except Exception as exc:  # noqa: BLE001 - se reporta al cliente vía /status
        _set(kickoff_id, status="failed", finished_at=_now(), error=str(exc))


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "model": os.getenv("MODEL", "default")}


@app.get("/inputs")
def inputs() -> dict[str, list[str]]:
    return {"required": REQUIRED_INPUTS, "optional": list(OPTIONAL_INPUTS)}


@app.post("/kickoff", response_model=KickoffResponse, status_code=202)
def kickoff(body: KickoffRequest, background: BackgroundTasks) -> KickoffResponse:
    missing = [k for k in REQUIRED_INPUTS if not body.inputs.get(k)]
    if missing:
        raise HTTPException(status_code=422, detail=f"Faltan inputs: {missing}")

    crew_inputs = dict(body.inputs)
    for key, default in OPTIONAL_INPUTS.items():
        crew_inputs.setdefault(key, default())

    kickoff_id = str(uuid.uuid4())
    with _jobs_lock:
        _jobs[kickoff_id] = {"kickoff_id": kickoff_id, "status": "queued", "inputs": crew_inputs}
    background.add_task(_run_crew, kickoff_id, crew_inputs)
    return KickoffResponse(kickoff_id=kickoff_id)


@app.get("/status/{kickoff_id}", response_model=StatusResponse)
def status(kickoff_id: str) -> StatusResponse:
    with _jobs_lock:
        job = _jobs.get(kickoff_id)
    if job is None:
        raise HTTPException(status_code=404, detail="kickoff_id no encontrado")
    return StatusResponse(**job)


@app.post("/ask/{kickoff_id}", response_model=AskResponse)
def ask(kickoff_id: str, body: AskRequest) -> AskResponse:
    """Pregunta al relator sobre una corrida terminada, usando solo lo que quedó registrado."""
    with _jobs_lock:
        job = dict(_jobs.get(kickoff_id) or {})
    if not job:
        raise HTTPException(status_code=404, detail="kickoff_id no encontrado")
    if job["status"] != "completed":
        raise HTTPException(status_code=409, detail=f"La corrida está en estado {job['status']}")

    registro = json.dumps(
        {k: job.get(k) for k in ("inputs", "tasks", "result", "token_usage", "started_at", "finished_at")},
        ensure_ascii=False,
        indent=2,
    )
    relator = Agent(
        role="Relator de la ejecución",
        goal="Responder preguntas sobre una corrida usando únicamente su registro",
        backstory=(
            "Sos el auditor interno del equipo. Respondés en español, breve y con precisión. "
            "Si el registro no contiene la respuesta, lo decís; nunca inventás."
        ),
        llm=build_llm(),
        max_iter=3,
        verbose=False,
    )
    respuesta = relator.kickoff(
        f"Registro de la corrida {kickoff_id}:\n{registro}\n\nPregunta: {body.pregunta}"
    )
    return AskResponse(kickoff_id=kickoff_id, pregunta=body.pregunta, respuesta=respuesta.raw)


def serve() -> None:
    """Punto de entrada para `uv run serve`."""
    import uvicorn

    uvicorn.run(
        "research_crew.api:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        reload=os.getenv("RELOAD", "false").lower() == "true",
    )
