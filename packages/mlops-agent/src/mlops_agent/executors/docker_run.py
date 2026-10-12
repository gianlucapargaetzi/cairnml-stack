"""Shared container runner: limits, log streaming, cancellation, cleanup."""

from __future__ import annotations

import threading

from mlops_agent.executors.base import BaseExecutor, LogSink, RunContext


def _pump(container, stdout: bool, sink: LogSink) -> None:
    buffer = ""
    for chunk in container.logs(stream=True, follow=True, stdout=stdout, stderr=not stdout):
        buffer += chunk.decode(errors="replace")
        while "\n" in buffer:
            line, buffer = buffer.split("\n", 1)
            sink(line.rstrip("\r"))
    if buffer:
        sink(buffer)


def _limits(ctx: RunContext) -> dict:
    resources = ctx.spec.resources
    limits = {
        "nano_cpus": int(resources.cpu * 1_000_000_000),
        "mem_limit": f"{int(resources.memory_gb * 1024)}m",
    }
    if resources.gpu:
        from docker.types import DeviceRequest

        limits["device_requests"] = [DeviceRequest(count=resources.gpu, capabilities=[["gpu"]])]
    return limits


def run_container(
    client,
    image: str,
    command,
    *,
    ctx: RunContext,
    volumes: dict,
    environment: dict,
    executor: BaseExecutor,
    entrypoint=None,
    working_dir: str | None = None,
    network: str | None = None,
    limits: bool = True,
) -> int:
    kwargs = dict(
        image=image,
        command=command,
        detach=True,
        volumes=volumes,
        environment=environment,
        labels={"mlops.job": ctx.job_id},
    )
    if entrypoint is not None:
        kwargs["entrypoint"] = entrypoint
    if working_dir:
        kwargs["working_dir"] = working_dir
    if network:
        kwargs["network"] = network
    if limits:
        kwargs.update(_limits(ctx))

    container = client.containers.run(**kwargs)
    executor._container = container
    threads = [
        threading.Thread(target=_pump, args=(container, True, ctx.stdout), daemon=True),
        threading.Thread(target=_pump, args=(container, False, ctx.stderr), daemon=True),
    ]
    for thread in threads:
        thread.start()
    try:
        code = int(container.wait()["StatusCode"])
        for thread in threads:
            thread.join(timeout=10)
        return code
    finally:
        try:
            container.remove(force=True)
        finally:
            executor._container = None
