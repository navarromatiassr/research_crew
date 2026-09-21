#!/usr/bin/env python
import json
import sys
import warnings

from research_crew.crew import ResearchCrew

warnings.filterwarnings("ignore", category=SyntaxWarning, module="pysbd")

DEFAULT_INPUTS = {
    "topic": "energía solar en Argentina",
    "pregunta": "¿Qué pudiste hacer y qué no pudiste hacer en esta corrida?",
}


def run():
    """Corre el crew una vez e imprime la rendición de cuentas."""
    try:
        output = ResearchCrew().crew().kickoff(inputs=dict(DEFAULT_INPUTS))
    except Exception as e:
        raise Exception(f"An error occurred while running the crew: {e}")

    print("\n===== RENDICION DE CUENTAS =====")
    if output.pydantic is not None:
        print(json.dumps(output.pydantic.model_dump(), indent=2, ensure_ascii=False))
    else:
        print(output.raw)
    print("\n===== TOKENS =====")
    print(output.token_usage)
    return output


def train():
    """Train the crew for a given number of iterations."""
    try:
        ResearchCrew().crew().train(
            n_iterations=int(sys.argv[1]), filename=sys.argv[2], inputs=dict(DEFAULT_INPUTS)
        )
    except Exception as e:
        raise Exception(f"An error occurred while training the crew: {e}")


def replay():
    """Replay the crew execution from a specific task."""
    try:
        ResearchCrew().crew().replay(task_id=sys.argv[1])
    except Exception as e:
        raise Exception(f"An error occurred while replaying the crew: {e}")


def test():
    """Test the crew execution and returns the results."""
    try:
        ResearchCrew().crew().test(
            n_iterations=int(sys.argv[1]), eval_llm=sys.argv[2], inputs=dict(DEFAULT_INPUTS)
        )
    except Exception as e:
        raise Exception(f"An error occurred while testing the crew: {e}")


def run_with_trigger():
    """Run the crew with trigger payload."""
    if len(sys.argv) < 2:
        raise Exception("No trigger payload provided. Please provide JSON payload as argument.")

    try:
        trigger_payload = json.loads(sys.argv[1])
    except json.JSONDecodeError:
        raise Exception("Invalid JSON payload provided as argument")

    inputs = {
        "crewai_trigger_payload": trigger_payload,
        "topic": trigger_payload.get("topic", DEFAULT_INPUTS["topic"]),
        "pregunta": trigger_payload.get("pregunta", DEFAULT_INPUTS["pregunta"]),
    }

    try:
        return ResearchCrew().crew().kickoff(inputs=inputs)
    except Exception as e:
        raise Exception(f"An error occurred while running the crew with trigger: {e}")
