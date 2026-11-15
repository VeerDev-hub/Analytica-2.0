"""Phase 2 'done when': a user cleans a dataset with no code, with undo."""

from tests.conftest import upload_csv

CITIES = [" Paris", "paris", "Rome ", "ROME", "Oslo"]
CSV = (
    "id,city,amount,signup\n"
    + "\n".join(
        f"{i},{CITIES[i % 5]},{'' if i % 7 == 0 else i * 1.5},2024-0{(i % 9) + 1}-1{i % 9}"
        for i in range(1, 201)
    )
    + "\n"
    + "\n".join("1,Paris,3.0,2024-01-11" for _ in range(2))
)


def pipeline(client, h, pid):
    return client.get(f"/api/v1/projects/{pid}/pipeline", headers=h).json()


def job_status(client, h, job_id):
    return client.get(f"/api/v1/jobs/{job_id}", headers=h).json()


def apply(client, h, pl_id, step_type, params, expect=202):
    r = client.post(
        f"/api/v1/pipeline/{pl_id}/steps",
        headers=h,
        json={"step_type": step_type, "params": params},
    )
    assert r.status_code == expect, r.text
    if expect == 202:
        job = job_status(client, h, r.json()["job_id"])
        assert job["status"] == "succeeded", job
    return r.json()


def current(client, h, pid):
    return client.get(f"/api/v1/projects/{pid}", headers=h).json()["dataset"]["current_version"]


def test_clean_with_undo_redo_and_replay(client, auth):
    h = auth
    p = upload_csv(client, h, CSV)
    pid = p["id"]
    pl = pipeline(client, h, pid)
    assert pl["steps"] == [] and not pl["can_undo"]
    v1 = current(client, h, pid)

    cat = client.get("/api/v1/steps/catalog").json()
    assert {"impute", "one_hot", "split", "smote"} <= {c["step_type"] for c in cat}

    # Preview runs on a sample and changes nothing.
    pv = client.post(
        f"/api/v1/pipeline/{pl['id']}/steps/preview",
        headers=h,
        json={"step_type": "trim_text", "params": {"columns": ["city"], "case": "title"}},
    ).json()
    assert pv["after"]["columns"] == ["city"]
    assert current(client, h, pid)["id"] == v1["id"]

    apply(client, h, pl["id"], "trim_text", {"columns": ["city"], "case": "title"})
    apply(client, h, pl["id"], "drop_duplicates", {})
    apply(client, h, pl["id"], "impute", {"columns": ["amount"], "strategy": "median"})
    v4 = current(client, h, pid)
    assert v4["version_no"] == 4 and v4["row_count"] == 201  # one duplicate removed
    ov = client.get(f"/api/v1/versions/{v4['id']}/overview", headers=h).json()
    cols = {c["name"]: c for c in ov["columns"]}
    assert cols["amount"]["missing_count"] == 0
    assert {t["value"] for t in cols["city"]["stats"]["top_values"]} == {"Paris", "Rome", "Oslo"}

    # Undo / redo move the pointer without recomputing.
    pl = client.post(f"/api/v1/pipeline/{pl['id']}/undo", headers=h).json()
    assert pl["can_redo"] and pl["steps"][-1]["status"] == "undone"
    assert current(client, h, pid)["version_no"] == 3
    pl = client.post(f"/api/v1/pipeline/{pl['id']}/redo", headers=h).json()
    assert current(client, h, pid)["id"] == v4["id"]

    # Editing an earlier step replays everything after it.
    first = pl["steps"][0]
    r = client.patch(
        f"/api/v1/steps/{first['id']}",
        headers=h,
        json={"params": {"columns": ["city"], "case": "upper"}},
    )
    assert job_status(client, h, r.json()["job_id"])["status"] == "succeeded"
    v = current(client, h, pid)
    ov = client.get(f"/api/v1/versions/{v['id']}/overview", headers=h).json()
    city = next(c for c in ov["columns"] if c["name"] == "city")
    assert {t["value"] for t in city["stats"]["top_values"]} == {"PARIS", "ROME", "OSLO"}
    assert all(s["status"] == "applied" for s in pipeline(client, h, pid)["steps"])

    # Disable a step -> replay passes data through.
    dup = pipeline(client, h, pid)["steps"][1]
    client.patch(f"/api/v1/steps/{dup['id']}", headers=h, json={"is_enabled": False})
    assert current(client, h, pid)["row_count"] == 202

    # Delete a step; reset goes back to version 1.
    client.delete(f"/api/v1/steps/{dup['id']}", headers=h)
    assert len(pipeline(client, h, pid)["steps"]) == 2
    client.post(f"/api/v1/pipeline/{pl['id']}/reset", headers=h)
    assert current(client, h, pid)["id"] == v1["id"]


def test_invalid_steps_and_leakage_guard(client, auth):
    h = auth
    p = upload_csv(client, h, CSV)
    pl = pipeline(client, h, p["id"])
    r = apply(client, h, pl["id"], "impute", {"columns": ["city"], "strategy": "mean"}, 422)
    assert r["error"]["code"] == "STEP_INVALID"
    apply(client, h, pl["id"], "nope", {}, 422)
    apply(client, h, pl["id"], "smote", {}, 422)  # needs target + split

    client.patch(
        f"/api/v1/projects/{p['id']}",
        headers=h,
        json={"target_column": "city", "task_type": "classification"},
    )
    apply(client, h, pl["id"], "scale", {"columns": ["amount"]})
    warn = pipeline(client, h, p["id"])["issues"]
    assert any("without a split" in i["message"] for i in warn)
    # Appending a split after a fitted step would leave it fitted on all rows: refused.
    r = apply(client, h, pl["id"], "split", {"method": "random"}, 422)
    assert r["error"]["code"] == "LEAKAGE_ORDER"
    # "Set split" inserts the split before the fitted step and re-fits it on train rows.
    r = client.put(f"/api/v1/pipeline/{pl['id']}/split", headers=h, json={"method": "random"})
    assert job_status(client, h, r.json()["job_id"])["status"] == "succeeded"
    steps = pipeline(client, h, p["id"])["steps"]
    assert [s["step_type"] for s in steps] == ["split", "scale"]
    assert all(s["status"] == "applied" for s in steps)
    r = client.post(
        f"/api/v1/pipeline/{pl['id']}/reorder",
        headers=h,
        json={"step_ids": [steps[1]["id"], steps[0]["id"]]},
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "LEAKAGE_ORDER"
    apply(client, h, pl["id"], "split", {"method": "random"}, 422)  # only one split

    # A failing step reports its error without breaking the pipeline.
    r = client.post(
        f"/api/v1/pipeline/{pl['id']}/steps",
        headers=h,
        json={"step_type": "pca", "params": {"columns": ["id", "amount"]}},
    )
    job = job_status(client, h, r.json()["job_id"])
    assert job["status"] == "failed" and "missing" in job["error"]
    failed = pipeline(client, h, p["id"])["steps"][-1]
    assert failed["status"] == "failed" and failed["error_message"]


def test_eda_endpoints(client, auth):
    h = auth
    p = upload_csv(client, h, CSV)
    v = p["dataset"]["current_version_id"]
    d = client.get(f"/api/v1/versions/{v}/columns/amount/detail", headers=h).json()
    assert d["semantic_type"] == "numeric" and d["histogram"]["counts"]
    specs = (
        {"kind": "histogram", "x": "amount"},
        {"kind": "bar", "x": "city"},
        {"kind": "box", "x": "city", "y": "amount"},
        {"kind": "scatter", "x": "id", "y": "amount"},
        {"kind": "heatmap"},
        {"kind": "bar", "x": "city", "y": "amount", "agg": "mean"},
        {"kind": "pie", "x": "city"},
        {"kind": "line", "x": "signup", "y": "amount", "agg": "mean"},
    )
    for spec in specs:
        r = client.post(f"/api/v1/versions/{v}/chart", headers=h, json=spec)
        assert r.status_code == 200, (spec, r.text)
        assert r.json()["data"]
    r = client.post(f"/api/v1/versions/{v}/chart", headers=h, json={"kind": "scatter", "x": "zzz"})
    assert r.status_code == 422
    c = client.get(f"/api/v1/versions/{v}/correlations", headers=h).json()
    assert "id" in c["columns"]


def test_recipes_replay_on_another_project(client, auth):
    h = auth
    p = upload_csv(client, h, CSV, project_name="A")
    pl = pipeline(client, h, p["id"])
    apply(client, h, pl["id"], "trim_text", {"columns": ["city"], "case": "lower"})
    apply(client, h, pl["id"], "drop_duplicates", {})
    rec = client.post(
        "/api/v1/recipes", headers=h, json={"project_id": p["id"], "name": "Basic clean"}
    ).json()
    assert len(rec["steps"]) == 2
    q = upload_csv(client, h, CSV, project_name="B")
    r = client.post(
        f"/api/v1/projects/{q['id']}/apply-recipe", headers=h, json={"recipe_id": rec["id"]}
    )
    assert job_status(client, h, r.json()["job_id"])["status"] == "succeeded"
    assert current(client, h, q["id"])["row_count"] == 201
    assert len(pipeline(client, h, q["id"])["steps"]) == 2
