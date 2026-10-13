import httpx
import pytest

pytestmark = pytest.mark.e2e


def _spec(directory) -> str:
    path = directory / "lifecycle.yaml"
    path.write_text("name: lifecycle\nproject: e2e/demo\nqueue: nobody-serves-this\n"
                    "runtime:\n  type: image\n  image: alpine:3.20\n  command: [echo, hi]\n")
    return str(path)


def test_disabling_a_user_in_the_idp_revokes_keys_and_cancels_queued_jobs(
    make_cli, admin, project, keycloak_admin
):
    carol = make_cli("carol")
    admin.run("admin", "project-add-member", "e2e/demo", "carol")
    assert carol.run("whoami").stdout.startswith("client cli_")
    out = carol.run("dispatch", "--file", _spec(carol.directory)).stdout
    # no agent serves this queue, so the job stays queued
    job_id = next(word for word in out.split() if word.startswith("job_"))

    keycloak_admin.set_enabled("carol", False)
    try:
        assert "disabled 1" in admin.run("admin", "sync-users").stdout
        # the enrolled key stopped working
        assert carol.run("whoami", check=False).returncode != 0
        # her queued job was cancelled
        assert admin.api().get_job(job_id)["status"] == "cancelled"
        # the IdP refuses her login now
        with pytest.raises(httpx.HTTPStatusError):
            carol.enroll()
    finally:
        keycloak_admin.set_enabled("carol", True)
        admin.run("admin", "sync-users")
    # re-enabled: she can enroll a new key
    fresh = make_cli("carol")
    assert fresh.run("whoami").stdout.startswith("client cli_")
    # while the old key stays revoked
    assert carol.run("whoami", check=False).returncode != 0
