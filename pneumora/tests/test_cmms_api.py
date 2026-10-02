from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["PNEUMORA_DB"] = str(Path(__file__).resolve().parents[1] / "data" / "test-cmms.sqlite")

from fastapi.testclient import TestClient

from server.main import app


def test_product_serves_honest_status_and_a_working_cmms() -> None:
    client = TestClient(app)
    bootstrap = client.get("/api/bootstrap")
    assert bootstrap.status_code == 200
    assert bootstrap.json()["model_status"] == "NO_PROMOTION"

    now = client.get("/api/now", params={"at": "2020-06-06T20:30:00"})
    assert now.status_code == 200
    body = now.json()
    assert body["series"]
    assert body["estimate"]

    created = client.post(
        "/api/work-orders",
        json={
            "problem": "Test leak check",
            "action": "Inspect the dryer drain",
            "technician": "Inês Carvalho",
            "part": "Seal kit",
            "priority": "urgent",
        },
    )
    assert created.status_code == 200
    order_id = created.json()["id"]
    updated = client.patch(f"/api/work-orders/{order_id}", json={"status": "progress"})
    assert updated.json()["status"] == "progress"

    training = client.get("/api/training")
    assert training.status_code == 200
    assert training.json()["decision"]["status"] == "NO_PROMOTION"
    assert training.json()["trained_rows"]["calibration_synthetic_rows"] == 0

    copilot = bootstrap.json()["copilot"]
    prediction = json.loads((ROOT / "autoresearch" / "prediction_study.json").read_text(encoding="utf-8"))
    assert copilot["status"] == prediction["status"]
    during_leak = client.get("/api/now", params={"at": "2020-06-05T12:00:00"}).json()
    assert during_leak["copilot"]["active"] is True
    assert during_leak["title"] in {"Possible air leak", "Air may run low soon"}
    quiet = client.get("/api/now", params={"at": "2020-05-02T12:00:00"}).json()
    assert quiet["copilot"]["active"] is False
    drafts = [o for o in client.get("/api/maintenance").json()["orders"] if o["id"].startswith("PN-CO-")]
    assert drafts and all("cross-validation" in o["note"] for o in drafts)

    evidence = client.get("/api/evidence").json()
    external = evidence["external_validation"]
    if external is not None:
        assert external["status"] in {"PROMOTED", "NO_PROMOTION"}
        assert external["status"] == ("PROMOTED" if all(external["gates"].values()) else "NO_PROMOTION")
        assert len(external["rows"]) == 4

    for moment in ("2020-06-05T12:00:00", "2020-05-02T12:00:00", "2020-06-06T20:30:00"):
        status = client.get("/api/now", params={"at": moment}).json()
        fired = [reason for reason in status["reasons"] if reason["triggered"]]
        if status["state"] == "ok":
            assert not fired and status["decided_by"] == "Every check is inside its normal range"
        else:
            assert fired and status["decided_by"] == fired[0]["check"]

    marks = bootstrap.json()["marks"]
    assert {mark["kind"] for mark in marks} == {"failure", "copilot"}
    assert all(mark["start"] <= mark["end"] for mark in marks)

    track = client.get("/api/copilot").json()
    assert track["tally"]["failures"] == 4
    assert all(row["cleared_at"] >= row["raised_at"] for row in track["copilot"] + track["low_pressure_alarm"])
    assert all(f["series"] for f in track["failures"])
    caught = {r["failure_id"] for r in track["copilot"] if r["outcome"] == "caught_in_time"}
    assert track["tally"]["copilot"]["caught_in_time"] == len(caught)

    page = client.get("/")
    assert page.status_code == 200
    assert "PNEUMORA" in page.text
    assert "/assets/pneumora-icon.svg" in page.text
