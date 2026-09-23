"""Flow: conversar sobre el estado de las campañas de Daniel.

Tres pasos, en este orden:

1. contexto   (código)  consulta la versión vigente de cada campaña en ops_campanas
                        y la deja en el estado del Flow. El agente arranca sabiendo
                        qué campañas existen y cómo están, sin gastar tokens en descubrirlo.
2. responder  (crew)    el analista responde la pregunta con SQL propio, acotado a las
                        tablas permitidas y con columnas sensibles ocultas.
3. trazar     (código)  guarda la traza de la corrida: pregunta, SQL, respuesta, tokens,
                        duración. En local va a output/trazas.jsonl; si BQ_TRACE_TABLE está
                        definida, también se inserta en esa tabla de BigQuery.

Uso local:  uv run estado "¿Cuántos handoffs hubo ayer por campaña?"
"""

import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from crewai.flow.flow import Flow, listen, start
from google.cloud import bigquery
from pydantic import BaseModel, Field

from research_crew.datos_crew import build_crew

TABLAS_OPERACION = "ops_campanas,ops_calls,ops_measurements,gtr_events,alertas_recupero,alertas_resueltas"
COLUMNAS_OCULTAS = "telefono,numero,transcript,recording_url,diagnostico,detalle,evidencia,msg_cliente,msg_vendedor,comentario"


class EstadoCampana(BaseModel):
    run_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    pregunta: str = ""
    campaign_id: str = ""
    contexto: str = ""
    campanas: list[dict] = Field(default_factory=list)
    respuesta: dict = Field(default_factory=dict)
    tokens: dict = Field(default_factory=dict)
    inicio: float = Field(default_factory=time.time)
    traza_path: str = ""


def _dataset() -> str:
    return os.environ["BQ_DATASET"]


class EstadoCampanaFlow(Flow[EstadoCampana]):

    @start()
    def contexto(self) -> None:
        """Paso determinista: campañas vigentes. Sin LLM."""
        os.environ.setdefault("BQ_TABLES", TABLAS_OPERACION)
        os.environ.setdefault("BQ_HIDDEN_COLUMNS", COLUMNAS_OCULTAS)
        client = bigquery.Client()
        filtro = "AND campaign_id = @cid" if self.state.campaign_id else ""
        sql = f"""
        WITH ult AS (
          SELECT *, ROW_NUMBER() OVER (PARTITION BY campaign_id ORDER BY version_ts DESC) AS rn
          FROM `{_dataset()}.ops_campanas`
          WHERE TRUE {filtro}
        )
        SELECT campaign_id, name, region, status, dialing_state, fuego_objetivo, fuego_max,
               objetivo_voz_viva_dia, objetivo_handoff, budget_dia_usd, contactos_total,
               franjas, FORMAT_TIMESTAMP('%Y-%m-%d %H:%M', version_ts) AS ultima_version
        FROM ult WHERE rn = 1
        ORDER BY (status = 'active') DESC, version_ts DESC
        LIMIT 30
        """
        cfg = bigquery.QueryJobConfig(
            maximum_bytes_billed=200 * 1024**2,
            query_parameters=[bigquery.ScalarQueryParameter("cid", "STRING", self.state.campaign_id)],
        )
        self.state.campanas = [dict(r) for r in client.query(sql, job_config=cfg).result()]
        hoy = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        lineas = [f"Fecha de hoy (UTC): {hoy}", f"Dataset: {_dataset()}", "Campañas (versión vigente):"]
        for c in self.state.campanas:
            lineas.append(
                f"- {c['campaign_id']} | {c['name']} | {c['region']} | status={c['status']} "
                f"dialing={c['dialing_state']} | fuego={c['fuego_objetivo']}/{c['fuego_max']} "
                f"| obj_voz_viva={c['objetivo_voz_viva_dia']} obj_handoff={c['objetivo_handoff']} "
                f"| budget_dia={c['budget_dia_usd']} | contactos={c['contactos_total']} | v={c['ultima_version']}"
            )
        self.state.contexto = "\n".join(lineas)

    @listen(contexto)
    def responder(self) -> None:
        """Paso con crew: el analista responde con SQL propio."""
        salida = build_crew(contexto=self.state.contexto, glosario=True).kickoff(
            inputs={"pregunta": self.state.pregunta}
        )
        self.state.respuesta = salida.pydantic.model_dump() if salida.pydantic else {"raw": salida.raw}
        usage = salida.token_usage
        self.state.tokens = usage.model_dump() if hasattr(usage, "model_dump") else {}

    @listen(responder)
    def trazar(self) -> dict:
        """Paso determinista: traza auditable de la corrida."""
        traza = {
            "run_id": self.state.run_id,
            "ts": datetime.now(timezone.utc).isoformat(),
            "flow": "estado_campana",
            "pregunta": self.state.pregunta,
            "campaign_id": self.state.campaign_id or None,
            "campanas_en_contexto": len(self.state.campanas),
            "sql": self.state.respuesta.get("sql"),
            "tablas_usadas": self.state.respuesta.get("tablas_usadas"),
            "respuesta": self.state.respuesta.get("respuesta"),
            "supuestos": self.state.respuesta.get("supuestos"),
            "confianza": self.state.respuesta.get("confianza"),
            "modelo": os.getenv("MODEL"),
            "tokens_total": self.state.tokens.get("total_tokens"),
            "duracion_seg": round(time.time() - self.state.inicio, 1),
        }
        out = Path("output"); out.mkdir(exist_ok=True)
        path = out / "trazas.jsonl"
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(traza, ensure_ascii=False) + "\n")
        self.state.traza_path = str(path)
        tabla = os.getenv("BQ_TRACE_TABLE")
        if tabla:
            errores = bigquery.Client().insert_rows_json(tabla, [{**traza, "tablas_usadas": json.dumps(traza["tablas_usadas"]), "supuestos": json.dumps(traza["supuestos"], ensure_ascii=False)}])
            if errores:
                traza["traza_bq_error"] = str(errores)[:300]
        return {"respuesta": self.state.respuesta, "traza": traza}


def estado() -> None:
    args = sys.argv[1:]
    campaign_id = ""
    if args and args[0].startswith("--campaign="):
        campaign_id = args.pop(0).split("=", 1)[1]
    pregunta = " ".join(args) or "¿Qué campañas están activas y cómo vienen hoy?"
    resultado = EstadoCampanaFlow().kickoff(inputs={"pregunta": pregunta, "campaign_id": campaign_id})
    print("\n===== RESPUESTA =====")
    print(json.dumps(resultado["respuesta"], indent=2, ensure_ascii=False))
    print("\n===== TRAZA =====")
    print(json.dumps(resultado["traza"], indent=2, ensure_ascii=False))


def plot() -> None:
    EstadoCampanaFlow().plot("estado_campana")
