# research_crew

Crew de CrewAI definido en código Python (`@CrewBase` + YAML) y listo para desplegar
de dos formas: self-hosted como API HTTP en Docker, o en CrewAI AMP.

## Estructura

```
research_crew/
├── src/research_crew/
│   ├── crew.py            # Agentes, tareas y crew (decoradores @agent/@task/@crew)
│   ├── api.py             # API FastAPI: /inputs, /kickoff, /status/{id}
│   ├── main.py            # Entradas CLI: run, train, replay, test
│   └── config/
│       ├── agents.yaml    # role / goal / backstory de cada agente
│       └── tasks.yaml     # description / expected_output / agent de cada tarea
├── Dockerfile
├── docker-compose.yml
├── .env.example
└── pyproject.toml
```

## Configuración

```bash
cp .env.example .env
```

Editá `.env` y completá la clave del proveedor. El modelo se elige con `MODEL`
en formato `<proveedor>/<modelo>`:

| MODEL                        | Clave necesaria     |
| ---------------------------- | ------------------- |
| `anthropic/claude-opus-5`    | `ANTHROPIC_API_KEY` |
| `openai/gpt-4o`              | `OPENAI_API_KEY`    |

## Ejecución local

```bash
crewai install
```

```bash
crewai run
```

El reporte queda en `output/report.md`.

## API HTTP (self-hosted)

```bash
uv run serve
```

Documentación interactiva en `http://localhost:8000/docs`.

| Método | Ruta                  | Descripción                                         |
| ------ | --------------------- | --------------------------------------------------- |
| GET    | `/health`             | Estado del servicio y modelo configurado            |
| GET    | `/inputs`             | Inputs requeridos y opcionales                      |
| POST   | `/kickoff`            | Lanza una ejecución, devuelve `kickoff_id` (202)    |
| GET    | `/status/{kickoff_id}`| Estado, resultado o error de la ejecución           |

Ejemplo:

```bash
curl -X POST http://localhost:8000/kickoff -H "content-type: application/json" -d "{\"inputs\": {\"topic\": \"Agentes de IA\"}}"
```

```bash
curl http://localhost:8000/status/<kickoff_id>
```

Los endpoints replican los de CrewAI AMP, así que un cliente escrito contra
esta API funciona igual contra un despliegue en AMP.

### Docker

```bash
docker compose up --build
```

La imagen instala dependencias con `uv` a partir de `uv.lock`, corre como usuario
sin privilegios y expone el puerto 8000. El reporte se monta en `./output`.

### Consideraciones para producción

- El registro de ejecuciones vive en memoria. Con más de una réplica, o si
  necesitás persistencia, reemplazá `_jobs` en `api.py` por Redis o una base de datos.
- Las ejecuciones corren en el threadpool del servidor. Para alto volumen usá
  una cola de trabajos (Celery, RQ, Arq) y dejá la API solo como frontend.
- Agregá autenticación (API key en header, OAuth) antes de exponer el servicio.

## Despliegue en CrewAI AMP

El proyecto mantiene la estructura estándar de `crewai create crew --classic`,
por lo que se puede desplegar sin cambios. Requiere que el código esté en GitHub.

```bash
crewai login
```

```bash
crewai deploy create
```

```bash
crewai deploy status
```

```bash
crewai deploy push
```

`crewai deploy create` lee las variables de `.env` y las transfiere a la
plataforma. Una vez desplegado, AMP expone `/inputs`, `/kickoff` y `/status/{id}`.

## Personalización

- Cambiá los agentes en `src/research_crew/config/agents.yaml`.
- Cambiá las tareas en `src/research_crew/config/tasks.yaml`.
- Agregá herramientas en `src/research_crew/tools/` y pasalas en `crew.py`.
- Los placeholders `{topic}` y `{current_year}` se completan con los inputs.
