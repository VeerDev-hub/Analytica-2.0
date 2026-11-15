"""Phase 1 'done when': upload a CSV and browse it."""

import json

from tests.conftest import register, upload_csv

CSV = (
    "id,city,price,joined\n"
    + "\n".join(
        f'{i},{["Paris", "Rome", "Oslo"][i % 3]},"{1000 + i * 10:,}",2024-01-{(i % 28) + 1:02d}'
        for i in range(1, 121)
    )
    + "\n121,,,\n"
)


def test_auth_flow(client):
    h = register(client)
    me = client.get("/api/v1/auth/me", headers=h)
    assert me.status_code == 200 and me.json()["email"] == "ada@example.com"

    dup = client.post(
        "/api/v1/auth/register", json={"email": "ADA@example.com", "password": "another-pass"}
    )
    assert dup.status_code == 409
    assert dup.json()["error"]["code"] == "EMAIL_TAKEN"

    bad = client.post("/api/v1/auth/login", json={"email": "ada@example.com", "password": "x"})
    assert bad.status_code == 401 and bad.json()["error"]["code"] == "BAD_CREDENTIALS"

    ok = client.post(
        "/api/v1/auth/login", json={"email": "Ada@Example.com", "password": "correct-horse-1"}
    )
    assert ok.status_code == 200
    # Refresh uses the HttpOnly cookie set by login.
    ref = client.post("/api/v1/auth/refresh")
    assert ref.status_code == 200 and ref.json()["access_token"]

    assert client.get("/api/v1/projects").status_code == 401
    assert (
        client.get("/api/v1/projects", headers={"Authorization": "Bearer nonsense"}).status_code
        == 401
    )


def test_projects_are_isolated_per_user(client):
    a = register(client, "a@example.com")
    b = register(client, "b@example.com")
    p = client.post("/api/v1/projects", json={"name": "Mine"}, headers=a).json()
    assert client.get(f"/api/v1/projects/{p['id']}", headers=b).status_code == 404
    assert client.get("/api/v1/projects", headers=b).json() == []
    assert (
        client.patch(f"/api/v1/projects/{p['id']}", json={"name": "x"}, headers=b).status_code
        == 404
    )
    assert client.delete(f"/api/v1/projects/{p['id']}", headers=a).status_code == 204
    assert client.get("/api/v1/projects", headers=a).json() == []


def test_upload_profile_and_browse(client, auth):
    detail = upload_csv(client, auth, CSV)
    ds = detail["dataset"]
    v = ds["current_version"]
    assert v["version_no"] == 1 and v["row_count"] == 121 and v["column_count"] == 4
    assert detail["current_pipeline_id"]

    ov = client.get(f"/api/v1/versions/{v['id']}/overview", headers=auth).json()
    cols = {c["name"]: c for c in ov["columns"]}
    # "1,010" style text converted losslessly; empty last row has NaN price.
    assert cols["price"]["semantic_type"] == "numeric"
    assert cols["city"]["semantic_type"] == "nominal"
    assert cols["joined"]["semantic_type"] == "datetime"
    assert any("Converted 'price'" in n for n in ov["load_notes"])
    assert ov["summary"]["row_count"] == 121

    rows = client.get(
        f"/api/v1/versions/{v['id']}/rows?offset=0&limit=10&sort=price:desc", headers=auth
    ).json()
    assert rows["total"] == 121 and len(rows["rows"]) == 10
    names = [c["name"] for c in rows["columns"]]
    assert rows["rows"][0][names.index("price")] == 2200

    flt = json.dumps([{"column": "city", "op": "eq", "value": "Rome"}])
    rome = client.get(
        f"/api/v1/versions/{v['id']}/rows", params={"filter": flt}, headers=auth
    ).json()
    assert rome["total"] == 40

    bad = client.get(f"/api/v1/versions/{v['id']}/rows?sort=nope:asc", headers=auth)
    assert bad.status_code == 422

    # Column metadata + target.
    col_id = cols["city"]["id"]
    res = client.patch(
        f"/api/v1/columns/{col_id}",
        json={"description": "Customer city", "is_private": True},
        headers=auth,
    )
    assert res.json()["description"] == "Customer city" and res.json()["is_private"]
    res = client.patch(
        f"/api/v1/projects/{detail['id']}",
        json={"target_column": "city", "task_type": "classification"},
        headers=auth,
    )
    assert res.status_code == 200 and res.json()["target_column"] == "city"
    res = client.patch(
        f"/api/v1/projects/{detail['id']}", json={"target_column": "zzz"}, headers=auth
    )
    assert res.status_code == 422

    # One dataset per project in v1.
    again = client.post(
        f"/api/v1/projects/{detail['id']}/datasets",
        headers=auth,
        files={"file": ("d.csv", b"a\n1\n", "text/csv")},
    )
    assert again.status_code == 409


def test_bad_uploads(client, auth):
    p = client.post("/api/v1/projects", json={"name": "P"}, headers=auth).json()
    url = f"/api/v1/projects/{p['id']}/datasets"
    r = client.post(url, headers=auth, files={"file": ("x.exe", b"MZ", "application/x")})
    assert r.status_code == 422 and r.json()["error"]["code"] == "UNSUPPORTED_FILE"
    r = client.post(url, headers=auth, files={"file": ("x.csv", b"", "text/csv")})
    assert r.status_code == 422 and r.json()["error"]["code"] == "EMPTY_FILE"
    # Unparseable Excel: the job fails with a readable message, nothing crashes.
    r = client.post(url, headers=auth, files={"file": ("x.xlsx", b"not excel", "x")})
    assert r.status_code == 202
    job = client.get(f"/api/v1/jobs/{r.json()['job_id']}", headers=auth).json()
    assert job["status"] == "failed" and "Excel" in job["error"]
