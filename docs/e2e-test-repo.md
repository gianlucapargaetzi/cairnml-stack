# Test repository for `tests/e2e/test_reproduce.py`

Create a small GitHub repository (private is fine), install your GitHub App on it (read-only contents), and commit these files. Note the `owner/name` and a clone URL.

`train.py` (deterministic, no third-party packages):

```python
import argparse
import mlops

parser = argparse.ArgumentParser()
parser.add_argument("--steps", type=int, default=3)
args = parser.parse_args()

bias = float(open("bias.txt").read().strip())   # committed as 0; the e2e test edits it locally
task = mlops.init("e2e/demo", "repro")
for step in range(args.steps):
    task.log_metric("score", bias + step, step)
print(f"bias={bias} steps={args.steps}")
```

`bias.txt`: the single line `0`. `requirements.txt`: empty file.

For the dataset test in `tests/e2e/test_tabs.py` also add `data/sample.dvc` (a DVC pointer, for
example from `dvc add` on a small CSV) and `data/sample.card.md` (a dataset card). The repository is
linked with `--role data`, so the dataset is listed as `data/sample`.

Export before running the suite:

```bash
export MLOPS_E2E_GITHUB_REPO=owner/name
export MLOPS_E2E_GITHUB_REPO_URL=https://github.com/owner/name.git
```

## Other variables for the e2e suite

- `MLOPS_E2E=1` enables the suite; without it every e2e test skips.
- `MLOPS_E2E_PASSWORD_ADMIN`, `MLOPS_E2E_PASSWORD_DEV`, `MLOPS_E2E_PASSWORD_EVE`: the passwords of
  the Keycloak realm users `admin`, `dev` and `eve`. `dev` and `eve` must exist in the `mlops` realm
  (bootstrap creates only `admin`). The passwords are never stored in the repository.
- `MLOPS_E2E_SERVER` and `MLOPS_E2E_ISSUER` override the default URLs.
