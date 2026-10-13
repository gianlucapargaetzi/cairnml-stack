"""Runs a user-supplied image with an optional entrypoint and command."""

from __future__ import annotations

import docker.errors

from mlops_agent.config import AgentSettings
from mlops_agent.executors.base import BaseExecutor, RunContext
from mlops_agent.executors.docker_run import container_dir, run_container


class ImageExecutor(BaseExecutor):
    def __init__(self, client, settings: AgentSettings | None = None) -> None:
        super().__init__()
        self._client = client
        # The Docker Hub token is used only for this login; it never reaches the container.
        if settings and settings.dockerhub_user and settings.dockerhub_token:
            client.login(username=settings.dockerhub_user, password=settings.dockerhub_token)

    def _ensure_image(self, image: str) -> None:
        try:
            self._client.images.get(image)
        except docker.errors.ImageNotFound:
            self._client.images.pull(image)

    def run(self, ctx: RunContext) -> int:
        runtime = ctx.spec.runtime
        self._ensure_image(runtime.image)
        volumes = {}
        working_dir = None
        if ctx.spec.code is not None:
            volumes = {str(ctx.root): {"bind": "/work", "mode": "rw"}}
            working_dir = container_dir(ctx)
        return run_container(
            self._client,
            runtime.image,
            runtime.command,
            ctx=ctx,
            volumes=volumes,
            environment=dict(ctx.env),
            executor=self,
            entrypoint=runtime.entrypoint,
            working_dir=working_dir,
            network=ctx.settings.job_network,
        )
