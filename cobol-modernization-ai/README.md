# COBOL Modernization — Design Reference (not the active backend)

This folder contains **early design documents** from the initial architecture phase.
The **implemented backend** lives in `cobol-modernization-service/`.

## Where to look instead

| Need | Location |
|---|---|
| Active Python/FastAPI code | `../cobol-modernization-service/app/` |
| Architecture docs (aligned with code) | `../docs/architecture/` |
| Operator quickstart | `../RUN_GUIDE.md` |
| Project overview | `../README.md` |

## Files in this folder

These markdown files describe the original design intent. Some details differ from the
final implementation (e.g. LangGraph orchestration, ProLeap parser, Spring Boot target).
Treat them as historical reference only.

- `architecture.md`, `parser-layer.md`, `analysis-agent.md`, `conversion-agent.md`
- `validation.md`, `workflow.md`, `jcl-context.md`, `design-decisions.md`
- `examples/end-to-end-example.md`
