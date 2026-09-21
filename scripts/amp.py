"""Cliente mínimo para operar el despliegue de AMP por API.

Toma la URL pública y el token del despliegue desde la sesión de la CLI
(`crewai login`), así que no hay credenciales en archivos ni en el código.

Uso, con el Python de la CLI de CrewAI:

    PY="$APPDATA/uv/tools/crewai/Scripts/python.exe"
    $PY scripts/amp.py inputs
    $PY scripts/amp.py kickoff "yerba mate" "¿Qué fue verificado?"
    $PY scripts/amp.py status <kickoff_id>
    $PY scripts/amp.py run "yerba mate" "¿Qué fue verificado?"      # kickoff + espera
    $PY scripts/amp.py resume <kickoff_id> <task_id> aprobar
    $PY scripts/amp.py resume <kickoff_id> <task_id> rechazar "Hacelo más corto"
"""

import json
import sys
import time
import warnings

import httpx

warnings.filterwarnings("ignore", category=DeprecationWarning)

from crewai.cli.authentication.token import get_auth_token  # noqa: E402
from crewai.cli.plus_api import PlusAPI  # noqa: E402

DEPLOYMENT_UUID = "fe9e2ecd-4413-48cf-89ae-33fea9d47b8e"
FINAL_STATES = {"SUCCESS", "FAILED", "FAILURE", "ERROR", "COMPLETED"}


def client() -> httpx.Client:
    info = PlusAPI(api_key=get_auth_token()).crew_status_by_uuid(DEPLOYMENT_UUID).json()
    return httpx.Client(
        base_url=info["public_url"],
        headers={"Authorization": f"Bearer {info['token']}"},
        timeout=60,
    )


def show(data) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False))


def parsed_status(c: httpx.Client, kickoff_id: str) -> dict:
    s = c.get(f"/status/{kickoff_id}").json()
    if isinstance(s.get("result"), str):
        try:
            s["result"] = json.loads(s["result"])
        except json.JSONDecodeError:
            pass
    s.pop("result_json", None)
    return s


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    cmd, args = sys.argv[1], sys.argv[2:]
    c = client()

    if cmd == "inputs":
        show(c.get("/inputs").json())
    elif cmd in ("kickoff", "run"):
        inputs = {"topic": args[0], "pregunta": args[1] if len(args) > 1 else ""}
        kickoff_id = c.post("/kickoff", json={"inputs": inputs}).json()["kickoff_id"]
        print("kickoff_id:", kickoff_id)
        if cmd == "run":
            start = time.time()
            while True:
                s = parsed_status(c, kickoff_id)
                state = (s.get("state") or "").upper()
                print(f"  {int(time.time() - start):>3}s  {state}  ultima tarea: {s.get('last_executed_task')}")
                if state in FINAL_STATES or "HUMAN" in state or time.time() - start > 600:
                    break
                time.sleep(8)
            show(s)
    elif cmd == "status":
        show(parsed_status(c, args[0]))
    elif cmd == "resume":
        # La API real exige camelCase (executionId, taskId), distinto de lo que
        # muestra la documentación. Devuelve un kickoff_id nuevo: la corrida
        # reanudada continúa bajo ese id. El taskId real llega por el webhook.
        body = {
            "executionId": args[0],
            "taskId": args[1],
            "isApprove": args[2].lower().startswith("aprob"),
            "humanFeedback": args[3] if len(args) > 3 else "Aprobado",
        }
        r = c.post("/resume", json=body)
        print(r.status_code)
        show(r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text)
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
