"""Crew para conversar con BigQuery en lenguaje natural.

Un solo agente analista con tres herramientas de solo lectura. Devuelve la
respuesta, el SQL usado y una nota de confianza, en JSON validado.

Uso local:  uv run preguntar "¿Cuántas filas tiene la tabla X?"
"""

import json
import sys
from pathlib import Path

from crewai import Agent, Crew, Process, Task
from pydantic import BaseModel, Field

from research_crew.crew import build_llm
from research_crew.tools.bigquery_tool import bigquery_tools

GLOSARIO = Path(__file__).parent / "config" / "glosario_campana.md"


class RespuestaDatos(BaseModel):
    pregunta: str
    respuesta: str = Field(description="Respuesta en español, con los números clave")
    sql: str = Field(description="La consulta final que sostiene la respuesta, o vacío si no hizo falta")
    tablas_usadas: list[str]
    supuestos: list[str] = Field(description="Interpretaciones que tuvo que hacer sobre la pregunta o los datos")
    confianza: str = Field(description="alta, media o baja, y por qué en pocas palabras")


def build_crew(contexto: str = "", glosario: bool = False) -> Crew:
    """Arma el crew analista.

    contexto: texto ya calculado por código (por ejemplo, la lista de campañas vigentes)
              que se le da al agente para que no tenga que descubrirlo consultando.
    glosario: si True, se incluye el glosario del negocio en la tarea.
    """
    analista = Agent(
        role="Analista de datos de BigQuery",
        goal="Responder preguntas de negocio consultando el dataset configurado, sin inventar datos",
        backstory=(
            "Sos un analista prolijo. Antes de consultar, mirás qué tablas hay y su esquema. "
            "Escribís SQL estándar de BigQuery con nombres de tabla completos y siempre con LIMIT. "
            "Si la pregunta es ambigua, elegís la interpretación más razonable y la declarás como supuesto. "
            "Si los datos no alcanzan para responder, lo decís."
        ),
        tools=bigquery_tools(),
        llm=build_llm(),
        max_iter=8,
        max_execution_time=240,
        verbose=True,
    )
    partes = ["Respondé esta pregunta usando las herramientas de BigQuery: {pregunta}"]
    if glosario and GLOSARIO.exists():
        partes.append("\n## Glosario del negocio (usalo para interpretar)\n" + GLOSARIO.read_text(encoding="utf-8"))
    if contexto:
        partes.append("\n## Contexto ya calculado por el sistema (no hace falta volver a consultarlo)\n" + contexto)
    partes.append("\nPasos: 1) listar tablas, 2) describir las relevantes, 3) consultar, 4) responder.")
    tarea = Task(
        description="\n".join(partes),
        expected_output="Respuesta en español con los números, el SQL usado, tablas, supuestos y confianza.",
        agent=analista,
        output_pydantic=RespuestaDatos,
    )
    return Crew(agents=[analista], tasks=[tarea], process=Process.sequential, verbose=True)


def preguntar() -> None:
    pregunta = " ".join(sys.argv[1:]) or "¿Qué tablas hay y de qué tratan?"
    salida = build_crew().kickoff(inputs={"pregunta": pregunta})
    print("\n===== RESPUESTA =====")
    print(json.dumps(salida.pydantic.model_dump(), indent=2, ensure_ascii=False) if salida.pydantic else salida.raw)
    print("\n===== TOKENS =====")
    print(salida.token_usage)
