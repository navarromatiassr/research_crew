import os

from crewai import LLM, Agent, Crew, Process, Task
from crewai.agents.agent_builder.base_agent import BaseAgent
from crewai.project import CrewBase, agent, crew, task

# El modelo se configura por entorno para poder cambiarlo sin tocar código.
# Formato "<proveedor>/<modelo>", por ejemplo:
#   anthropic/claude-opus-5   (requiere ANTHROPIC_API_KEY)
#   openai/gpt-4o             (requiere OPENAI_API_KEY)
DEFAULT_MODEL = "anthropic/claude-opus-5"


def build_llm() -> LLM:
    # Algunos modelos (por ejemplo los de razonamiento de OpenAI) solo aceptan
    # la temperatura por defecto, así que solo se envía si está configurada.
    kwargs: dict = {"model": os.getenv("MODEL", DEFAULT_MODEL)}
    if os.getenv("MODEL_TEMPERATURE"):
        kwargs["temperature"] = float(os.environ["MODEL_TEMPERATURE"])
    return LLM(**kwargs)


@CrewBase
class ResearchCrew:
    """Crew de investigación: un investigador y un analista de reportes."""

    agents: list[BaseAgent]
    tasks: list[Task]

    @agent
    def researcher(self) -> Agent:
        return Agent(
            config=self.agents_config["researcher"],  # type: ignore[index]
            llm=build_llm(),
            verbose=True,
        )

    @agent
    def reporting_analyst(self) -> Agent:
        return Agent(
            config=self.agents_config["reporting_analyst"],  # type: ignore[index]
            llm=build_llm(),
            verbose=True,
        )

    @task
    def research_task(self) -> Task:
        return Task(
            config=self.tasks_config["research_task"],  # type: ignore[index]
        )

    @task
    def reporting_task(self) -> Task:
        return Task(
            config=self.tasks_config["reporting_task"],  # type: ignore[index]
            output_file="output/report.md",
        )

    @crew
    def crew(self) -> Crew:
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=True,
        )
