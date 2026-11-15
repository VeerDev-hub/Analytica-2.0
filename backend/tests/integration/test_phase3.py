"""Phase 3 'done when': exported data trains a model; leakage guard blocks bad order."""

import io
import json
import random
import subprocess
import sys
import zipfile

import numpy as np
import pandas as pd

from tests.conftest import upload_csv

random.seed(3)
ROWS = ["PassengerId,Survived,Pclass,Sex,Age,Fare,Embarked"]
for i in range(1, 601):
    sex = random.choice(["male", "female"])
    pclass = random.choice([1, 2, 3])
    survived = int(
        random.random() < (0.7 if sex == "female" else 0.2) + (0.1 if pclass == 1 else 0)
    )
    age = "" if random.random() < 0.2 else random.randint(1, 80)
    fare = round(random.lognormvariate(3, 1) * (4 - pclass), 2)
    emb = random.choice(["S", "S", "C", "Q", ""])
    ROWS.append(f"{i},{survived},{pclass},{sex},{age},{fare},{emb}")
CSV = "\n".join(ROWS) + "\n"


def run(client, h, method, url, **kw):
    r = client.request(method, url, headers=h, **kw)
    assert r.status_code < 300, r.text
    body = r.json()
    if body and body.get("job_id"):
        job = client.get(f"/api/v1/jobs/{body['job_id']}", headers=h).json()
        assert job["status"] == "succeeded", job
        body["job"] = job
    return body


def test_ml_ready_flow_exports_and_baseline(client, auth, tmp_path):
    h = auth
    p = upload_csv(client, h, CSV, name="titanic.csv")
    pid = p["id"]
    run(
        client,
        h,
        "PATCH",
        f"/api/v1/projects/{pid}",
        json={"target_column": "Survived", "task_type": "classification"},
    )
    pl = client.get(f"/api/v1/projects/{pid}/pipeline", headers=h).json()["id"]

    rd = client.get(f"/api/v1/projects/{pid}/readiness", headers=h).json()
    assert not rd["ready"]
    failing = {c["id"] for c in rd["checks"] if c["status"] == "fail"}
    assert {"split", "no_missing", "numeric_only"} <= failing

    steps = [
        ("drop_columns", {"columns": ["PassengerId"]}),
        ("split", {"method": "stratified", "ratios": [0.7, 0.15, 0.15], "seed": 1}),
        ("impute", {"columns": ["Age"], "strategy": "median"}),
        ("impute", {"columns": ["Embarked"], "strategy": "most_frequent"}),
        ("one_hot", {"columns": ["Sex", "Embarked"]}),
        ("scale", {"columns": ["@numeric"], "method": "standard"}),
        ("smote", {}),
    ]
    for st, params in steps:
        run(
            client,
            h,
            "POST",
            f"/api/v1/pipeline/{pl}/steps",
            json={"step_type": st, "params": params},
        )

    rd = client.get(f"/api/v1/projects/{pid}/readiness", headers=h).json()
    assert rd["ready"], rd
    assert not any(c["status"] == "fail" for c in rd["checks"])

    # Leakage guard: a fitted step cannot be moved before the split.
    st = client.get(f"/api/v1/projects/{pid}/pipeline", headers=h).json()["steps"]
    ids = [s["id"] for s in st]
    bad = [ids[0], ids[2], ids[1], *ids[3:]]
    r = client.post(f"/api/v1/pipeline/{pl}/reorder", headers=h, json={"step_ids": bad})
    assert r.status_code == 422 and r.json()["error"]["code"] == "LEAKAGE_ORDER"

    base = run(client, h, "POST", f"/api/v1/projects/{pid}/baseline")
    res = base["job"]["result"]
    assert res["task"] == "classification" and res["evaluated_on"] == "validation"
    gb = next(r for r in res["results"] if r["model"] == "Gradient boosting")
    dummy = next(r for r in res["results"] if r["model"] == "Most frequent class")
    assert gb["balanced_accuracy"] > dummy["balanced_accuracy"]

    def export(kind, fmt=None):
        out = run(
            client, h, "POST", f"/api/v1/projects/{pid}/exports", json={"kind": kind, "format": fmt}
        )
        d = client.get(f"/api/v1/exports/{out['export']['id']}/download", headers=h)
        assert d.status_code == 200, d.text
        return d.content, d.headers["content-disposition"]

    data, _ = export("dataset", "csv")
    z = zipfile.ZipFile(io.BytesIO(data))
    assert {"train.csv", "val.csv", "test.csv", "README.txt"} <= set(z.namelist())
    train = pd.read_csv(z.open("train.csv"))
    test = pd.read_csv(z.open("test.csv"))
    assert "__split__" not in train.columns and train["Survived"].value_counts().nunique() == 1

    # The exported data trains a model.
    from sklearn.linear_model import LogisticRegression

    X, y = train.drop(columns="Survived"), train["Survived"]
    model = LogisticRegression(max_iter=500).fit(X, y)
    assert model.score(test.drop(columns="Survived"), test["Survived"]) > 0.6

    data, _ = export("dataset", "npy")
    z = zipfile.ZipFile(io.BytesIO(data))
    assert np.load(io.BytesIO(z.read("X_train.npy"))).shape[1] == X.shape[1]

    script, _ = export("script")
    src = tmp_path / "titanic.csv"
    src.write_text(CSV)
    path = tmp_path / "pipeline.py"
    path.write_bytes(script)
    proc = subprocess.run(
        [sys.executable, str(path), str(src)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    produced = pd.read_csv(tmp_path / "prepared.csv")
    # Same columns as the UI result (row count differs only by SMOTE's synthetic rows).
    assert set(produced.columns) == set(train.columns)

    nb, _ = export("notebook")
    assert json.loads(nb)["nbformat"] == 4
    pj, _ = export("pipeline")
    doc = json.loads(pj)
    assert [s["step_type"] for s in doc["steps"]][:2] == ["drop_columns", "split"]
    assert doc["steps"][2]["learned"]["fills"]["Age"] is not None
    for kind in ("pytorch", "tensorflow"):
        data, _ = export(kind)
        names = zipfile.ZipFile(io.BytesIO(data)).namelist()
        assert f"train_{kind}.py" in names and "train.parquet" in names
    html, _ = export("report")
    assert b"ML readiness" in html

    lst = client.get(f"/api/v1/projects/{pid}/exports", headers=h).json()
    assert len(lst) == 8 and all(e["status"] == "ready" for e in lst)
