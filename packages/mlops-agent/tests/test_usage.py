import subprocess
from types import SimpleNamespace

from mlops_agent.usage import sample_usage


def _psutil():
    memory = SimpleNamespace(used=8 * 1024**3, total=32 * 1024**3)
    return SimpleNamespace(cpu_percent=lambda interval=None: 37.5, virtual_memory=lambda: memory)


def test_cpu_memory_and_gpus():
    def run(cmd, **kw):
        out = "0, 91, 20480, 40960\n1, 3, 512, 40960\n"
        return subprocess.CompletedProcess(cmd, 0, stdout=out, stderr="")

    usage = sample_usage(run=run, psutil_module=_psutil())
    assert (usage.cpu_percent, usage.mem_used_gb, usage.mem_total_gb) == (37.5, 8.0, 32.0)
    gpus = [(g.index, g.util_percent, g.mem_used_gb, g.mem_total_gb) for g in usage.gpus]
    assert gpus == [(0, 91.0, 20.0, 40.0), (1, 3.0, 0.5, 40.0)]


def test_no_gpu_tools_or_garbage_output():
    def missing(cmd, **kw):
        raise FileNotFoundError("nvidia-smi")

    assert sample_usage(run=missing, psutil_module=_psutil()).gpus == []
    def garbage(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 0, stdout="N/A, N/A\n", stderr="")

    assert sample_usage(run=garbage, psutil_module=_psutil()).gpus == []
