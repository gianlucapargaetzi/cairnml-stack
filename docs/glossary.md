# Glossary

One word, one meaning. If a new feature needs a new word, add it here first.

| Term | Meaning | Example |
|---|---|---|
| **Agent** | A worker: a process on a compute machine that executes jobs. | `gpu-box-1` |
| **Project** | A list of experiments around one goal, linked to Git repositories, datasets and containers. | `vision/segmentation` |
| **Experiment** | One aspect of a project: model training, data augmentation, testing, compilation, evaluation, ... | `training` |
| **Run** | One execution of an experiment with one set of parameters: the record of code version, data versions, parameters, metrics, logs and artifacts. | `training, lr=0.1` |
| **Job** | The request to execute one run on an agent (queue, resources, status). A local run has no job; a dispatched one has exactly one. | `job_3f9a...` |
| **Dataset** | A DVC-tracked path in a Git repository, optionally described by a dataset card. The framework stores references, never data. | `data/train` |
| **Resource** | What an agent offers (CPU, memory, GPU, runtimes) and what is currently used. | `8 cpu, 2 gpu` |

Hierarchy: **project, then experiment, then run, then (if dispatched) job.**

## Where each word appears

Items marked *(planned)* are not built yet. Everything else exists today.

| Word | SDK | CLI | API | Dashboard | Database |
|---|---|---|---|---|---|
| Agent | | `mlops admin agents`, `mlops admin revoke-agent`, `mlops-agent` (the agent program) | `/api/v1/agents/*`, `/api/v1/admin/agents` | Agents tab; Resources tab *(planned)* | `agents` |
| Project | `mlops.init(project=...)` | `mlops admin project-create`, `mlops admin project-add-member`, `mlops repo init --project` | `/api/v1/projects`; `/api/v1/projects/{id}` *(planned)* | Projects tab | `projects`, `project_members` |
| Experiment | `mlops.init(experiment=...)` | `mlops experiment ls\|set` | `/api/v1/experiments/*` | project page, experiment page *(planned)* | `experiments` |
| Run | `mlops.Run`, `mlops.current_run()`, `run.use_dataset()` | `mlops ls`, `mlops logs` | `/api/v1/runs/*` | Runs tab, run page, compare page | `runs` |
| Job | | `mlops dispatch`, `mlops job show\|cancel`, `mlops job reschedule` *(planned)* | `/api/v1/jobs/*` | Jobs tab | `jobs` |
| Dataset | `run.use_dataset()`, `mlops.init(datasets=...)` | `mlops data pull\|push`; `mlops dataset ...` *(planned)* | `/api/v1/datasets/*` *(planned)* | Datasets tab *(planned)* | none (Git + DVC) |
| Resource | | | `/api/v1/resources` *(planned)* | Resources tab *(planned)* | `agents.usage` *(planned)* |

## Words we do not use as nouns

- "workspace" for a project; "worker" or "runner node" for an agent (the Python, binary and container *runners* inside an agent are executors of one job).
- "Task" for an experiment. The word is retired; a project has experiments, not tasks.
- "Experiment" for a single execution. That is a run. An experiment groups runs.
