from mlops_server.ids import new_id
from mlops_server.models import Project
from sqlalchemy import select


def test_healthz(server):
    assert server.get("/api/v1/healthz").json() == {"status": "ok"}


def test_public_config_exposes_idp_settings(server, settings):
    body = server.get("/api/v1/config").json()
    assert body == {
        "server_url": settings.public_url,
        "oidc_issuer": settings.oidc_issuer,
        "oidc_client_id": "mlops-cli",
    }


def test_new_id_has_prefix_and_is_unique():
    a, b = new_id("exp"), new_id("exp")
    assert a.startswith("exp_") and len(a) == 20 and a != b


def test_models_roundtrip(server, app):
    with app.state.session_factory() as session:
        session.add(Project(id=new_id("prj"), slug="vision/seg", name="Seg"))
        session.commit()
        assert session.scalar(select(Project).where(Project.slug == "vision/seg")).name == "Seg"
