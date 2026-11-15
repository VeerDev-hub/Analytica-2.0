"""Phase 4 'done when': chat answers show their query and source rows.

The model call (`stream_turn`) is replaced by a scripted fake, so these tests exercise the
tool loop, SQL sandbox, citations, step proposals and approval without an API key."""

import json
from types import SimpleNamespace

import pandas as pd
import pytest

from app.chat import orchestrator
from app.chat.sql_tool import SqlError, SqlSandbox
from tests.conftest import upload_csv

CSV = (
    "id,city,amount,secret\n"
    + "\n".join(
        f"{i},{['Paris', 'Rome', 'Oslo'][i % 3]},{i * 2},{'pw' + str(i)}" for i in range(1, 61)
    )
    + "\n"
)


def tool_use(name, inp, i="t1"):
    return SimpleNamespace(type="tool_use", id=i, name=name, input=inp)


def final(content, stop="tool_use"):
    return SimpleNamespace(
        content=content, stop_reason=stop, usage=SimpleNamespace(input_tokens=100, output_tokens=20)
    )


def scripted(turns):
    calls = {"n": 0, "systems": [], "messages": []}

    def fake(system, messages, *_args, **_kw):
        calls["systems"].append(system)
        calls["messages"].append(list(messages))
        events = turns[calls["n"]]
        calls["n"] += 1
        yield from events

    return fake, calls


def sse(res):
    return [json.loads(line[6:]) for line in res.text.splitlines() if line.startswith("data: ")]


@pytest.fixture
def chat_project(client, auth, monkeypatch):
    monkeypatch.setattr("app.api.v1.chat.get_client", lambda: None)
    monkeypatch.setattr("app.api.v1.chat.chat_enabled", lambda: True)
    p = upload_csv(client, auth, CSV)
    cols = client.get(
        f"/api/v1/versions/{p['dataset']['current_version_id']}/columns", headers=auth
    ).json()
    secret = next(c for c in cols if c["name"] == "secret")
    client.patch(f"/api/v1/columns/{secret['id']}", headers=auth, json={"is_private": True})
    s = client.post(f"/api/v1/projects/{p['id']}/chat/sessions", headers=auth).json()
    return p, s


def test_chat_disabled_without_key(client, auth):
    p = upload_csv(client, auth, CSV)
    s = client.post(f"/api/v1/projects/{p['id']}/chat/sessions", headers=auth).json()
    assert client.get("/api/v1/chat/status", headers=auth).json() == {"enabled": False}
    r = client.post(
        f"/api/v1/chat/sessions/{s['id']}/messages", headers=auth, json={"content": "hi"}
    )
    assert r.status_code == 503 and r.json()["error"]["code"] == "CHAT_DISABLED"


def test_answer_is_grounded_in_a_query(client, auth, chat_project, monkeypatch):
    p, s = chat_project
    sql = "SELECT city, avg(amount) AS avg_amount FROM data GROUP BY city ORDER BY city"
    fake, calls = scripted(
        [
            [
                ("text", "Let me check."),
                (
                    "final",
                    final([tool_use("run_sql", {"sql": sql, "purpose": "average amount by city"})]),
                ),
            ],
            [
                ("text", "Rome has the highest average amount."),
                ("final", final([SimpleNamespace(type="text", text="...")], "end_turn")),
            ],
        ]
    )
    monkeypatch.setattr(orchestrator, "stream_turn", fake)
    r = client.post(
        f"/api/v1/chat/sessions/{s['id']}/messages",
        headers=auth,
        json={"content": "Which city has the highest average amount?"},
    )
    assert r.status_code == 200
    events = sse(r)
    assert events[-1]["type"] == "done"
    done = [e for e in events if e["type"] == "tool_done"][0]
    assert done["citation"]["sql"] == sql and len(done["citation"]["rows"]) == 3

    # Private column is masked: absent from the system prompt sample and from `data`.
    system = calls["systems"][0]
    assert "secret | private" in system and "pw1" not in system
    # Tool result was sent back to the model with the real numbers.
    tool_result = calls["messages"][1][-1]["content"][0]
    assert tool_result["type"] == "tool_result" and "Rome" in tool_result["content"]

    msgs = client.get(f"/api/v1/chat/sessions/{s['id']}/messages", headers=auth).json()
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[1]["citations"][0]["sql"] == sql
    assert "highest average" in msgs[1]["content"]


def test_bad_sql_and_private_column_are_errors_for_the_model(
    client, auth, chat_project, monkeypatch
):
    p, s = chat_project
    fake, calls = scripted(
        [
            [
                (
                    "final",
                    final(
                        [
                            tool_use("run_sql", {"sql": "DROP TABLE data", "purpose": "x"}, "a"),
                            tool_use(
                                "run_sql", {"sql": "SELECT secret FROM data", "purpose": "x"}, "b"
                            ),
                        ]
                    ),
                )
            ],
            [("text", "I can't access that."), ("final", final([], "end_turn"))],
        ]
    )
    monkeypatch.setattr(orchestrator, "stream_turn", fake)
    client.post(
        f"/api/v1/chat/sessions/{s['id']}/messages", headers=auth, json={"content": "show secrets"}
    )
    results = calls["messages"][1][-1]["content"]
    assert all(r["is_error"] for r in results)
    assert "Only SELECT" in results[0]["content"]
    assert "secret" in results[1]["content"].lower()


def test_proposed_step_needs_approval(client, auth, chat_project, monkeypatch):
    p, s = chat_project
    fake, _ = scripted(
        [
            [
                (
                    "final",
                    final(
                        [
                            tool_use(
                                "propose_step",
                                {
                                    "step_type": "trim_text",
                                    "params": {"columns": ["city"], "case": "upper"},
                                    "reason": "normalise city names",
                                },
                            )
                        ]
                    ),
                )
            ],
            [("text", "I proposed a step."), ("final", final([], "end_turn"))],
        ]
    )
    monkeypatch.setattr(orchestrator, "stream_turn", fake)
    events = sse(
        client.post(
            f"/api/v1/chat/sessions/{s['id']}/messages",
            headers=auth,
            json={"content": "clean the city column"},
        )
    )
    assert events[-1]["proposed_step"]["step_type"] == "trim_text"
    before = client.get(f"/api/v1/projects/{p['id']}", headers=auth).json()
    assert before["dataset"]["current_version"]["version_no"] == 1  # nothing applied yet

    msg_id = events[-1]["message_id"]
    r = client.post(f"/api/v1/chat/messages/{msg_id}/approve", headers=auth)
    assert (
        client.get(f"/api/v1/jobs/{r.json()['job_id']}", headers=auth).json()["status"]
        == "succeeded"
    )
    after = client.get(f"/api/v1/projects/{p['id']}", headers=auth).json()
    assert after["dataset"]["current_version"]["version_no"] == 2
    again = client.post(f"/api/v1/chat/messages/{msg_id}/approve", headers=auth)
    assert again.status_code == 409


def test_sql_sandbox_blocks_file_access(tmp_path):
    path = tmp_path / "d.parquet"
    pd.DataFrame({"a": [1, 2, 3], "pii": ["x", "y", "z"]}).to_parquet(path)
    sb = SqlSandbox(str(path), private_columns={"pii"})
    assert sb.run("SELECT sum(a) AS s FROM data").rows == [[6]]
    for bad in (
        "SELECT * FROM read_csv('/etc/passwd')",
        "COPY data TO '/tmp/x.csv'",
        "SELECT 1; DROP TABLE data",
        "ATTACH 'x.db'",
        "SELECT pii FROM data",
        "SELECT * FROM '/etc/passwd'",
    ):
        with pytest.raises(SqlError):
            sb.run(bad)
    big = sb.run("SELECT * FROM range(1000)")
    assert big.truncated and big.row_count == 200
    sb.close()
