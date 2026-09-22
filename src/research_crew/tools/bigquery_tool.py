"""Herramientas de BigQuery de solo lectura para agentes.

Protecciones:
- Solo consultas SELECT / WITH; cualquier sentencia de escritura o DDL se rechaza.
- Dry run previo con tope de bytes a facturar (BQ_MAX_BYTES, por defecto 1 GB).
- Límite de filas devueltas (BQ_MAX_ROWS, por defecto 200) para no inflar el contexto.
- Alcance acotado a un dataset (BQ_DATASET) para que el agente no explore todo el proyecto.

Autenticación: credenciales por defecto de Google (ADC) o GOOGLE_APPLICATION_CREDENTIALS.
"""

import json
import os
import re
from typing import Type

from crewai.tools import BaseTool
from google.cloud import bigquery
from pydantic import BaseModel, Field

FORBIDDEN = re.compile(
    r"\b(insert|update|delete|merge|drop|create|alter|truncate|grant|revoke|call|export|load)\b",
    re.IGNORECASE,
)


def _client() -> bigquery.Client:
    return bigquery.Client(project=os.getenv("BQ_PROJECT") or None)


def _dataset() -> str:
    ds = os.getenv("BQ_DATASET")
    if not ds:
        raise ValueError("Falta BQ_DATASET en el entorno (formato proyecto.dataset o dataset).")
    return ds


def _max_bytes() -> int:
    return int(os.getenv("BQ_MAX_BYTES", str(1 * 1024**3)))


def _max_rows() -> int:
    return int(os.getenv("BQ_MAX_ROWS", "200"))


class ListarTablasInput(BaseModel):
    pass


class ListarTablasTool(BaseTool):
    name: str = "listar_tablas"
    description: str = "Lista las tablas disponibles en el dataset configurado, con filas y tamaño."
    args_schema: Type[BaseModel] = ListarTablasInput

    def _run(self) -> str:
        client = _client()
        out = []
        for t in client.list_tables(_dataset()):
            full = client.get_table(t.reference)
            out.append(
                {
                    "tabla": f"{full.project}.{full.dataset_id}.{full.table_id}",
                    "filas": full.num_rows,
                    "mb": round((full.num_bytes or 0) / 1024**2, 1),
                    "descripcion": full.description or "",
                }
            )
        return json.dumps(out, ensure_ascii=False, indent=2)


class DescribirTablaInput(BaseModel):
    tabla: str = Field(description="Nombre de la tabla, con o sin dataset, por ejemplo 'ventas' o 'proyecto.dataset.ventas'")


class DescribirTablaTool(BaseTool):
    name: str = "describir_tabla"
    description: str = "Devuelve las columnas, tipos y descripciones de una tabla, y 3 filas de ejemplo."
    args_schema: Type[BaseModel] = DescribirTablaInput

    def _run(self, tabla: str) -> str:
        client = _client()
        ref = tabla if tabla.count(".") == 2 else f"{_dataset()}.{tabla.split('.')[-1]}"
        table = client.get_table(ref)
        cols = [{"columna": f.name, "tipo": f.field_type, "modo": f.mode, "descripcion": f.description or ""} for f in table.schema]
        muestra = [dict(r) for r in client.list_rows(table, max_results=3)]
        return json.dumps({"tabla": ref, "columnas": cols, "ejemplo": muestra}, ensure_ascii=False, indent=2, default=str)


class ConsultarInput(BaseModel):
    sql: str = Field(description="Consulta SQL estándar de BigQuery, solo SELECT. Usá nombres de tabla completos.")


class ConsultarTool(BaseTool):
    name: str = "consultar_bigquery"
    description: str = (
        "Ejecuta una consulta SELECT en BigQuery y devuelve las filas en JSON. "
        "Rechaza escrituras y consultas que superen el tope de bytes. Agregá LIMIT."
    )
    args_schema: Type[BaseModel] = ConsultarInput

    def _run(self, sql: str) -> str:
        limpio = sql.strip().rstrip(";")
        if not re.match(r"^\s*(select|with)\b", limpio, re.IGNORECASE) or FORBIDDEN.search(limpio):
            return "RECHAZADA: solo se permiten consultas SELECT de lectura."
        client = _client()
        dry = client.query(limpio, job_config=bigquery.QueryJobConfig(dry_run=True, use_query_cache=False))
        if dry.total_bytes_processed > _max_bytes():
            return (
                f"RECHAZADA: procesaría {dry.total_bytes_processed/1024**3:.2f} GB y el tope es "
                f"{_max_bytes()/1024**3:.2f} GB. Filtrá por fecha o partición."
            )
        job = client.query(limpio, job_config=bigquery.QueryJobConfig(maximum_bytes_billed=_max_bytes()))
        rows = [dict(r) for r in job.result(max_results=_max_rows())]
        return json.dumps(
            {
                "filas": rows,
                "filas_devueltas": len(rows),
                "truncado_a": _max_rows() if len(rows) >= _max_rows() else None,
                "bytes_procesados": job.total_bytes_processed,
                "sql": limpio,
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        )


def bigquery_tools() -> list[BaseTool]:
    return [ListarTablasTool(), DescribirTablaTool(), ConsultarTool()]
