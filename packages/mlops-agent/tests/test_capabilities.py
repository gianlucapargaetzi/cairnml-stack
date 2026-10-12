import subprocess

from mlops_agent.capabilities import detect


def _run(outputs):
    def run(cmd, **kwargs):
        key = " ".join(cmd[:2])
        if key not in outputs:
            raise FileNotFoundError(cmd[0])
        code, out = outputs[key]
        return subprocess.CompletedProcess(cmd, code, stdout=out, stderr="")

    return run


def _detect(outputs, docker=True, labels=()):
    return detect(labels, run=_run(outputs), docker_ok=lambda: docker, cpu_count=lambda: 12,
                  mem_bytes=lambda: 32 * 1024**3)


def test_full_machine():
    caps = _detect({"nvidia-smi --query-gpu=name": (0, "NVIDIA A100\nNVIDIA A100\n"),
                    "docker compose": (0, "v2")}, labels=["a100"])
    assert (caps.cpu, caps.memory_gb, caps.gpus) == (12, 32.0, 2)
    assert caps.gpu_models == ["NVIDIA A100", "NVIDIA A100"] and caps.labels == ["a100"]
    assert caps.runtimes == ["python", "image", "compose"] and caps.docker is True


def test_no_gpu_no_compose():
    caps = _detect({"docker compose": (1, "")})
    assert caps.gpus == 0 and caps.gpu_models == [] and caps.docker is True
    assert caps.runtimes == ["python", "image"]


def test_no_docker_means_no_runtimes():
    caps = _detect({}, docker=False)
    assert caps.docker is False and caps.runtimes == []


def test_nvidia_smi_nonzero_exit_gives_no_gpus():
    caps = _detect({"nvidia-smi --query-gpu=name": (9, "driver error")})
    assert caps.gpus == 0 and caps.gpu_models == []


def test_permission_error_from_nvidia_smi_gives_no_gpus():
    def run(cmd, **kwargs):
        if cmd[0] == "nvidia-smi":
            raise PermissionError(cmd[0])
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="")

    caps = detect((), run=run, docker_ok=lambda: True, cpu_count=lambda: 4,
                  mem_bytes=lambda: 8 * 1024**3)
    assert caps.gpus == 0 and caps.runtimes == ["python", "image"]


def test_gpus_present_but_docker_down():
    caps = _detect({"nvidia-smi --query-gpu=name": (0, "NVIDIA A100\n"),
                    "docker compose": (0, "v2")}, docker=False)
    assert caps.gpus == 1 and caps.runtimes == [] and caps.docker is False
