import io
import os
import tempfile

import docker

from scoring.base import ScoreResult

BASE_IMAGE = "python:3.11-slim"
# python:3.11-slim has no pytest, and the sandboxed run has networking disabled
# (network_disabled=True) so it can't pip install at execution time. Build a
# derived image with pytest baked in once, ahead of time; the build step uses
# network but is not part of the untrusted code's sandboxed execution.
DOCKER_IMAGE = "eval-harness-scorer:py311-pytest"
TIMEOUT_SECONDS = 10

_DOCKERFILE = f"""\
FROM {BASE_IMAGE}
RUN pip install --no-cache-dir pytest
"""


def _ensure_image(client: docker.DockerClient) -> None:
    try:
        client.images.get(DOCKER_IMAGE)
    except docker.errors.ImageNotFound:
        client.images.build(
            fileobj=io.BytesIO(_DOCKERFILE.encode("utf-8")),
            tag=DOCKER_IMAGE,
            rm=True,
        )


def score_codegen(generated_code: str, test_code: str) -> ScoreResult:
    client = docker.from_env()
    _ensure_image(client)
    with tempfile.TemporaryDirectory() as tmpdir:
        with open(os.path.join(tmpdir, "solution.py"), "w") as f:
            f.write(generated_code)
        with open(os.path.join(tmpdir, "test_solution.py"), "w") as f:
            f.write(test_code)

        container = client.containers.run(
            DOCKER_IMAGE,
            command=["python", "-m", "pytest", "test_solution.py", "-v", "-p", "no:cacheprovider"],
            volumes={tmpdir: {"bind": "/work", "mode": "rw"}},
            working_dir="/work",
            detach=True,
            mem_limit="256m",
            network_disabled=True,
        )
        try:
            result = container.wait(timeout=TIMEOUT_SECONDS)
            logs = container.logs().decode("utf-8", errors="replace")
            exit_code = result["StatusCode"]
        except Exception as exc:
            container.kill()
            logs = container.logs().decode("utf-8", errors="replace")
            return ScoreResult(score=0.0, pass_fail="fail", raw_output=logs, error=f"timeout_or_error: {exc}")
        finally:
            container.remove(force=True)

        if exit_code == 0:
            return ScoreResult(score=1.0, pass_fail="pass", raw_output=logs)
        return ScoreResult(score=0.0, pass_fail="fail", raw_output=logs)
