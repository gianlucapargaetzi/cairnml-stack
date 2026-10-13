import threading

import docker.errors


class FakeContainer:
    def __init__(self, exit_code=0, stdout=(), stderr=(), block: threading.Event | None = None):
        self.exit_code, self._out, self._err, self.block = (
            exit_code,
            list(stdout),
            list(stderr),
            block,
        )
        self.removed = self.killed = False

    def logs(self, stream=False, follow=False, stdout=True, stderr=True):
        lines = (
            self._out
            if (stdout and not stderr)
            else self._err
            if (stderr and not stdout)
            else self._out + self._err
        )
        return iter([line.encode() for line in lines])

    def wait(self, timeout=None):
        if self.block is not None:
            self.block.wait(5)
        return {"StatusCode": 137 if self.killed else self.exit_code}

    def kill(self):
        self.killed = True
        if self.block is not None:
            self.block.set()

    def remove(self, force=False):
        self.removed = True


class FakeContainers:
    def __init__(self, containers):
        self._queue, self.runs = list(containers), []

    def run(self, **kwargs):
        self.runs.append(kwargs)
        return self._queue.pop(0)


class FakeImages:
    def __init__(self, present=True):
        self.present, self.pulled = present, []

    def get(self, name):
        if not self.present:
            raise docker.errors.ImageNotFound(name)

    def pull(self, name):
        self.pulled.append(name)


class FakeDocker:
    def __init__(self, containers=(), images_present=True):
        self.containers = FakeContainers(containers)
        self.images = FakeImages(images_present)
        self.logins = []

    def login(self, **kwargs):
        self.logins.append(kwargs)
