# mlops

Self-hosted MLOps framework: experiment tracking with autologging, remote job dispatch to agents, Git + DVC datasets, one identity provider.

Vocabulary: an **agent** executes jobs; a **project** is a list of **tasks**; an **experiment** is one instance of a task with one set of parameters; a **job** is the request to run an experiment on an agent.

## Layout

```
packages/
  mlops-common/   shared schemas, keys, signed-assertion auth
  mlops-server/   FastAPI control plane, scheduler, dashboard (ui/)
  mlops-agent/    worker daemon that runs jobs in containers
  mlops-client/   SDK (import mlops) and CLI
deploy/           one compose stack per machine role, bootstrap scripts
tests/            cross-package integration and end-to-end tests
docs/             glossary, runbook
```

Design: see ARCHITECTURE.md and ROADMAP.md (kept next to the implementation plans).
