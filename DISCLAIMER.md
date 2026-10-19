# Disclaimer

MLOps Flow is an unofficial, modified version of ClearML. It is not created, sponsored, endorsed or
supported by ClearML, Inc.

"ClearML" is a trademark of ClearML, Inc. This project uses the name only to say what the code is
based on. The source is licensed under the license in [LICENSE](LICENSE); the original copyright
notices are kept. The changes made to ClearML's code are recorded in this repository's history.

## What is changed in this copy

This copy changes several parts of ClearML. The main ones:

- **Scheduling and the managed agent** (`clearml-server`, `clearml-agent`): jobs are placed on worker machines by a
  scheduler, a managed agent daemon runs them, and job containers install the agent and the SDK from local source.
- **Server** (`clearml-server`): the sign-in integration (device sign-in, directory sync), a scheduler sweep for lost
  workers, and a reset for the end-to-end suite's test stack, which is off unless the server is configured for it.
- **SDK** (`clearml`): `Task.enqueue` checks the server's API level rather than the level the process is using.
- **Agent** (`clearml-agent`): see the scheduling item above, and the job containers' network and cache settings.
- **Web app** (`clearml-web`): the interface of this copy.
- **Tests and deployment** (`tests/e2e`, `deploy/`): the end-to-end suite, its isolated environment, and the
  deployment files.

Each submodule's history records its changes in detail.

