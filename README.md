# MLOps Flow

Self-hosted MLOps: experiment tracking with autologging, remote jobs on your own agents, Git and DVC for datasets, and one identity provider for people. Each machine has its own key, and the server issues short-lived tokens for it.

- **Track** a training script with a few lines of Python. Metrics, parameters, logs, artifacts and the code state are recorded on the server.
- **Explore** runs in the web UI: charts, parameters, images, comparisons, experiments and resources.
- **Dispatch** a run to an agent, from the command line or from the UI.
- **Version** datasets with Git and DVC, and link them to the runs that used them.

The server and agent setup is in [docs/server-setup.md](docs/server-setup.md). The architecture and the security model are in ARCHITECTURE.md, which is kept with the design documents outside this repository.

## Contents

1. [Install the client](#1-install-the-client)
2. [Your first run](#2-your-first-run)
3. [Dispatch a job to an agent](#3-dispatch-a-job-to-an-agent)
4. [Generate a dataset](#4-generate-a-dataset)
5. [Use a dataset in a run](#5-use-a-dataset-in-a-run)
6. [Tests](#tests)
7. [Documentation](#documentation)

## 1. Install the client

You need a running server (see [server setup](docs/server-setup.md)) and [uv](https://docs.astral.sh/uv/). From a checkout of this repository:

```bash
uv tool install --editable ./packages/mlops-client --with-editable ./packages/mlops-common
```

This installs the `mlops` command for your user. Check it:

```bash
mlops --help
```

To install into a project's `.venv` with pip, straight from Git (the repository is not on PyPI). Install both packages from their subdirectories in one command. Add `@<branch>` before `#subdirectory=` to install a branch other than the default one:

```bash
cd my-project
python3 -m venv .venv
source .venv/bin/activate
pip install \
  "git+ssh://git@github.com/gianlucapargaetzi/mlops-framework.git#subdirectory=packages/mlops-common" \
  "git+ssh://git@github.com/gianlucapargaetzi/mlops-framework.git#subdirectory=packages/mlops-client"
mlops --help
```

To use the client in a script, add `mlops-client` to that project's dependencies, or install it with `uv pip install -e packages/mlops-client`.

Enroll this machine once. A browser opens for the login:

```bash
mlops enroll --server http://mlops-server:8000
mlops whoami
```

`whoami` prints the client it is enrolled as. It uses the key and needs no login.

> *GIF: enrollment*

## 2. Your first run

Save this as `first_run.py` in any folder:

```python
import mlops

exp = mlops.init(project="vision/seg", name="first-run", config={"lr": 0.1})
for step in range(3):
    exp.log_metric("loss", 1.0 / (step + 1), step=step)
print("first run finished")

with open("model.txt", "w") as f:
    f.write("weights")
exp.upload_artifact("model.txt", path="model.txt")
exp.close()
```

Run it with plain Python:

```bash
python first_run.py
mlops ls --project vision/seg
```

The run is recorded on the server. `mlops ls` lists the recent runs with their IDs, and `mlops logs <id>` prints its output. Add `-f` to follow a run that is still going.

### Explore it in the UI

Open **http://mlops-server:8000/ui-next/** and sign in with your account.

> *GIF: first run in the UI*

| Page | What you see |
|---|---|
| **Runs** | All runs of the projects you belong to. Filter them with the search bar, and open one to see its detail. |
| **Metrics** | Metric charts of the selected runs, one line per run. |
| **Params** | Parameters of the runs, as a table you can sort and group. |
| **Scatters** | Two parameters or metrics against each other. |
| **Images** | Images the runs logged, with sliders for steps and indices. |
| **Projects** | Each project's experiments, its best result, its linked repositories (with the commit graph) and its datasets. |
| **Experiment** | One experiment: its settings, its best run and its runs. Select runs and compare them. |
| **Compare** | Two to ten runs side by side: metrics, parameters, code and data. |
| **Datasets** | Dataset cards and their versions. |
| **Jobs** | Scheduled, running and finished jobs. Cancel a job, or copy and reschedule it. |
| **Resources** | Agents and queues, with their allocated and actual load. |
| **Tags** | Tags of a project. Attach them to runs from the run's side bar. |

A **run detail** page has the overview (command line, environment, packages, git state, datasets and artifacts), the metrics, the images, and a **Run on an agent** form.

## 3. Dispatch a job to an agent

A job runs a recorded run on an agent, on a queue the agent serves. Resource requests are `--cpu`, `--memory-gb`, `--gpu` and `--label`.

### From the command line

Dispatching a recorded run needs the code it ran from on GitHub, because the agent clones it. Commit and push, then:

```bash
git push
mlops dispatch <run id> --queue default
```

A job can also come from a spec file. This one runs an image, so it needs no repository:

```yaml
# job.yaml
name: hello
project: vision/seg
queue: default
resources: {cpu: 1, memory_gb: 0.5}
runtime:
  type: image
  image: alpine:3.20
  entrypoint: [/bin/sh, -c]
  command: ['echo hello from the agent']
```

```bash
mlops dispatch --file job.yaml        # prints the job ID
mlops job show <job id>
```

Dispatching needs the server. When it is unreachable, the client refuses to dispatch.

### From the UI (reschedule a run)

1. Open the run in the UI.
2. Click **Run on an agent**.
3. Pick the queue and the resources, and submit. The run is queued as a job.

To run the same job again with a change, open it in **Jobs**, choose **Copy and reschedule**, and change the queue, the resources or the parameters. Only the fields you change are sent.

> *GIF: dispatch from the UI*

## 4. Generate a dataset

Datasets are DVC-tracked folders in a Git repository. The framework stores references only. Inside a clone of the project's code repository (with at least one commit, and DVC installed with `pip install 'mlops-client[dvc]'`):

```bash
mlops repo init --project vision/seg
dvc add data/train
git add .mlops data/train.dvc data/.gitignore .dvc
git commit -m "add training data"
git push
mlops data push data/train
```

`repo init` links the repository to the project. `data push` uploads the data with temporary storage credentials from the server, so no credentials are kept in the repository. Commit the `.dvc` file and `.mlops/project.yaml`, never the data.

To describe the dataset in the UI, add a card (`mlops dataset card init data/train`). The card appears on the **Datasets** page.

## 5. Use a dataset in a run

In your script, name the dataset. The path is relative to the working directory, and it must be DVC-tracked in the Git repository:

```python
import mlops

exp = mlops.init(project="vision/seg", name="train-on-dataset", config={"lr": 0.1})
exp.use_dataset("data/train")
# ... train ...
exp.close()
```

The run's detail page lists the dataset with its version (the DVC hash of the data). `mlops dataset show data/train --project vision/seg` lists the runs that used the dataset.

Pull the data on another machine with `mlops data pull data/train` before you reproduce a run there.

## Tests

```bash
uv run pytest                        # unit and integration tests, no Docker needed
uv run pytest -m docker              # tests that need a local Docker daemon
MLOPS_E2E=1 uv run pytest tests/e2e  # end-to-end tests against the running compose stack
```

The end-to-end suite needs the stack from the server setup and the settings in [docs/e2e-test-repo.md](docs/e2e-test-repo.md).

## Documentation

- [docs/server-setup.md](docs/server-setup.md): server and agent setup, from an empty machine.
- [docs/runbook.md](docs/runbook.md): the full workflow, moving roles to their own machines, and troubleshooting.
- [docs/glossary.md](docs/glossary.md): the terms used in the code, the CLI, the web UI and the documentation.
- [docs/plans/finished/AIM_IMPLEMENTATION_SUMMARY.md](docs/plans/finished/AIM_IMPLEMENTATION_SUMMARY.md): how the web UI was built, and what is still open.
