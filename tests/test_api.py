import os
import tempfile

os.environ["ZEROFORG_DB"] = os.path.join(tempfile.mkdtemp(), "api.db")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


def test_endpoints_respond():
    with TestClient(app) as client:
        h = client.get("/health").json()
        assert h["status"] in ("ok", "warn", "critical")
        assert client.get("/alerts?open=true").status_code == 200
        assert client.get("/metrics?name=cpu_total&since=1h").status_code == 200
        assert client.get("/processes?sort=cpu").status_code == 200
        assert client.get("/processes?sort=bogus").status_code == 400
