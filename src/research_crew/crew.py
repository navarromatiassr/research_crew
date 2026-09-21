import json
import os
from typing import Literal

from crewai import LLM, Agent, Crew, Process, Task
from crewai.agents.agent_builder.base_agent import BaseAgent
from crewai.project import CrewBase, after_kickoff, agent, crew, task
from pydantic import BaseModel, Field

# El modelo se configura por entorno para poder cambiarlo sin tocar código.
# Formato "<proveedor>/<modelo>", por ejemplo:
#   anthropic/claude-opus-5   (requiere ANTHROPIC_API_KEY)
#   openai/gpt-5.6-terra      (requiere OPENAI_API_KEY)
DEFAULT_MODEL = "anthropic/claude-opus-5"


def human_review_enabled() -> bool:
    return os.getenv("HUMAN_REVIEW", "false").strip().lower() == "true"


def build_llm() -> LLM:
    # Algunos modelos (por ejemplo los de razonamiento de OpenAI) solo aceptan
    # la temperatura por defecto, así que solo se envía si está configurada.
    kwargs: dict = {"model": os.getenv("MODEL", DEFAULT_MODEL)}
    if os.getenv("MODEL_TEMPERATURE"):
        kwargs["temperature"] = float(os.environ["MODEL_TEMPERATURE"])
    return LLM(**kwargs)


class PasoEjecutado(BaseModel):
    paso: str = Field(description="Nombre de la tarea ejecutada")
    agente: str = Field(description="Rol del agente que la ejecutó")
    que_hizo: str = Field(description="Qué hizo, en una oración")
    resultado: str = Field(description="Resultado resumido en una o dos oraciones")


class RendicionDeCuentas(BaseModel):
    """Salida final del crew: qué se hizo, qué no, y con qué confianza."""

    tema: str
    resumen: str = Field(description="El resumen final producido por el redactor")
    pasos: list[PasoEjecutado]
    limitaciones: list[str] = Field(description="Qué no pudo hacer o verificar el equipo")
    confianza: Literal["alta", "media", "baja"]
    respuesta_a_pregunta: str = Field(description="Respuesta a la pregunta del usuario")
    revision_humana_activada: bool | None = Field(
        default=None,
        description="No completar. Lo fija el sistema según la configuración del entorno.",
    )


@CrewBase
class ResearchCrew:
    """Crew de prueba end-to-end: investiga, resume y rinde cuentas."""

    agents: list[BaseAgent]
    tasks: list[Task]

    def _agent(self, name: str) -> Agent:
        return Agent(
            config=self.agents_config[name],  # type: ignore[index]
            llm=build_llm(),
            max_iter=5,
            max_execution_time=120,
            verbose=True,
        )

    @agent
    def researcher(self) -> Agent:
        return self._agent("researcher")

    @agent
    def reporting_analyst(self) -> Agent:
        return self._agent("reporting_analyst")

    @agent
    def relator(self) -> Agent:
        return self._agent("relator")

    @task
    def research_task(self) -> Task:
        return Task(config=self.tasks_config["research_task"])  # type: ignore[index]

    @task
    def reporting_task(self) -> Task:
        # Human in the loop: con HUMAN_REVIEW=true la ejecución se pausa al terminar
        # el resumen para que una persona lo apruebe o pida cambios. En local la
        # pausa es por consola; en AMP queda en "Pending Human Input" y se reanuda
        # con POST /resume. Apagado por defecto para no bloquear corridas automáticas.
        return Task(
            config=self.tasks_config["reporting_task"],  # type: ignore[index]
            output_file="output/resumen.md",
            human_input=human_review_enabled(),
        )

    @task
    def accountability_task(self) -> Task:
        return Task(
            config=self.tasks_config["accountability_task"],  # type: ignore[index]
            output_pydantic=RendicionDeCuentas,
        )

    @after_kickoff
    def stamp_environment(self, output):
        """Agrega a la salida datos que fija el sistema, no el modelo."""
        enabled = human_review_enabled()
        if output.pydantic is not None:
            output.pydantic.revision_humana_activada = enabled
            output.raw = json.dumps(output.pydantic.model_dump(), ensure_ascii=False)
        return output

    @crew
    def crew(self) -> Crew:
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=True,
        )
