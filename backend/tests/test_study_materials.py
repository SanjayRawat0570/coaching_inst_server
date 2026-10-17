"""Teacher study material: upload -> Storage + RAG_SERVER, list/refresh, re-index,
delete, and the lecture-transcript CLI. RAG_SERVER and Supabase are faked."""

import asyncio

import httpx
import pytest
from fastapi.testclient import TestClient

import main
from auth.supabase_auth import get_current_user
from rag import rag_config, rag_server_client, study_materials as sm

INST = "33333333-3333-3333-3333-333333333333"
MID = "44444444-4444-4444-4444-444444444444"


def user(role):
    return lambda: {"id": "auth-teacher", "email": "t@x.com", "role": role, "institute_id": INST}


@pytest.fixture
def env(monkeypatch, fake_sb):
    rec = {"uploads": [], "status_calls": [], "status": {}, "upload_result": None,
           "institute": INST}

    async def fake_upload(content, filename, **kw):
        rec["uploads"].append({"content": content, "filename": filename, **kw})
        return rec["upload_result"] or {"execution_id": f"ex-{len(rec['uploads'])}", "status": "running"}

    async def fake_status(execution_id, **kw):
        rec["status_calls"].append((execution_id, kw))
        result = rec["status"].get(execution_id, {"status": "running", "progress": 0.4})
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(sm, "_supabase", lambda: fake_sb)
    monkeypatch.setattr(rag_config, "get_rag_config", lambda iid: ("inst-a", "sk-a"))
    monkeypatch.setattr(rag_server_client, "upload_document", fake_upload)
    monkeypatch.setattr(rag_server_client, "upload_status", fake_status)
    monkeypatch.setattr(main, "_caller_institute_id", lambda u: rec["institute"])
    fake_sb.results[("study_materials", "insert")] = lambda q: [q.payload]
    main.app.dependency_overrides[get_current_user] = user("teacher")
    rec["client"], rec["sb"] = TestClient(main.app), fake_sb
    yield rec
    main.app.dependency_overrides.clear()


def upload(env, name="ch 5 (final).PDF", content=b"%PDF-1.7 newton", **form):
    data = {"subject": "Physics", "chapter": "Laws of Motion", "class_level": "11",
            "exam": "jee", "material_type": "notes", **form}
    return env["client"].post("/teacher/materials/upload", data=data,
                              files={"file": (name, content, "application/pdf")})


# ── Naming / validation ───────────────────────────────────────────────────────

def test_citation_filename():
    assert sm.citation_filename("ch 5 (final).PDF", "Physics", "Laws of Motion", "notes") \
        == "Physics_Laws_of_Motion_notes_ch_5_final.pdf"
    assert sm.citation_filename("../../etc/passwd.txt", None, "", "pyq") == "pyq_passwd.txt"
    assert sm.citation_filename("नोट्स.pdf", "Chemistry", None, "notes") == "Chemistry_notes_file.pdf"


# ── Upload ────────────────────────────────────────────────────────────────────

def test_upload_stores_original_and_starts_indexing(env):
    r = upload(env)
    assert r.status_code == 200, r.text
    row = r.json()
    name = "Physics_Laws_of_Motion_notes_ch_5_final.pdf"
    assert row["filename"] == name and row["status"] == "running" and row["execution_id"] == "ex-1"
    assert (row["institute_id"], row["uploaded_by"], row["exam"]) == (INST, "auth-teacher", "JEE")
    assert row["storage_path"] == f"{INST}/{row['id']}/{name}"

    assert env["sb"].storage.files[row["storage_path"]] == b"%PDF-1.7 newton"
    assert env["sb"].storage.calls[0][0] == "study-materials"
    sent = env["uploads"][0]
    assert (sent["filename"], sent["tenant"], sent["api_key"], sent["wait"]) == (name, "inst-a", "sk-a", False)
    assert sent["content"] == b"%PDF-1.7 newton"


@pytest.mark.parametrize("name,size,form,status", [
    ("virus.exe", 2, {}, 400),
    ("empty.pdf", 0, {}, 400),
    ("notes.pdf", 1, {"material_type": "homework"}, 400),
    ("notes.pdf", 1, {"exam": "GATE"}, 400),
    ("big.pdf", 50 * 1024 * 1024 + 1, {}, 413),
], ids=["extension", "empty", "material_type", "exam", "over-50MB"])
def test_upload_validation(env, name, size, form, status):
    r = upload(env, name=name, content=b"x" * size, **form)
    assert r.status_code == status
    assert env["uploads"] == [] and env["sb"].storage.files == {}


def test_upload_503_when_rag_not_configured(env, monkeypatch):
    monkeypatch.setattr(rag_config, "get_rag_config", lambda iid: ("inst-a", ""))
    monkeypatch.delenv("RAG_SERVER_API_KEY")
    r = upload(env)
    assert r.status_code == 503 and "not configured" in r.json()["detail"]
    assert env["sb"].storage.files == {}


def test_upload_storage_failure_is_502_and_not_indexed(env):
    env["sb"].storage.fail["upload"] = RuntimeError("Bucket not found")
    r = upload(env)
    assert r.status_code == 502 and "study-materials" in r.json()["detail"]
    assert env["uploads"] == []


def test_upload_rag_failure_saves_failed_row(env):
    env["upload_result"] = {"status": "failed", "message": "Unsupported PDF"}
    row = upload(env).json()
    assert (row["status"], row["message"], row["execution_id"]) == ("failed", "Unsupported PDF", None)


def test_upload_row_insert_failure_cleans_storage(env):
    env["sb"].results[("study_materials", "insert")] = RuntimeError("relation does not exist")
    r = upload(env)
    assert r.status_code == 500 and "migrations" in r.json()["detail"]
    assert env["sb"].storage.files == {}


def test_students_cannot_upload(env):
    main.app.dependency_overrides[get_current_user] = user("student")
    assert upload(env).status_code == 403
    assert env["client"].get("/teacher/materials").status_code == 403


def test_admin_can_upload(env):
    main.app.dependency_overrides[get_current_user] = user("admin")
    assert upload(env).status_code == 200


def test_no_institute_uses_shared_path(env):
    env["institute"] = None
    row = upload(env).json()
    assert row["institute_id"] is None and row["storage_path"].startswith("shared/")


# ── List + refresh ────────────────────────────────────────────────────────────

ROWS = [
    {"id": "m1", "status": "running", "execution_id": "ex-done", "filename": "a.pdf"},
    {"id": "m2", "status": "running", "execution_id": "ex-busy", "filename": "b.pdf"},
    {"id": "m3", "status": "running", "execution_id": "ex-gone", "filename": "c.pdf"},
    {"id": "m4", "status": "running", "execution_id": "ex-flaky", "filename": "d.pdf"},
    {"id": "m5", "status": "completed", "execution_id": "ex-old", "chunks_indexed": 9, "filename": "e.pdf"},
]


def test_list_refreshes_running_rows(env):
    env["sb"].results[("study_materials", "select")] = [dict(r) for r in ROWS]
    gone = httpx.HTTPStatusError("404", request=httpx.Request("GET", "http://x"),
                                 response=httpx.Response(404))
    env["status"].update({
        "ex-done": {"status": "completed", "message": "ok", "chunks_indexed": 21},
        "ex-gone": gone,
        "ex-flaky": httpx.ConnectError("down"),
    })
    out = {m["id"]: m for m in env["client"].get("/teacher/materials").json()["materials"]}

    assert (out["m1"]["status"], out["m1"]["chunks_indexed"]) == ("completed", 21)
    assert out["m2"]["status"] == "running" and out["m2"]["progress"] == 0.4
    assert out["m3"]["status"] == "failed" and "re-index" in out["m3"]["message"]
    assert out["m4"]["status"] == "running"
    assert out["m5"]["chunks_indexed"] == 9
    assert {c[0] for c in env["status_calls"]} == {"ex-done", "ex-busy", "ex-gone", "ex-flaky"}
    assert all(c[1] == {"api_key": "sk-a"} for c in env["status_calls"])
    updated = {c.filters[0][2]: c.payload for c in env["sb"].ops("study_materials", "update")}
    assert set(updated) == {"m1", "m3"}  # only finished rows are written back


def test_list_is_scoped_to_institute(env):
    env["client"].get("/teacher/materials")
    assert ("eq", "institute_id", INST) in env["sb"].ops("study_materials", "select")[0].filters
    env["institute"] = None
    env["client"].get("/teacher/materials")
    assert ("is", "institute_id", "null") in env["sb"].ops("study_materials", "select")[1].filters


# ── Re-index / delete ─────────────────────────────────────────────────────────

def _stored(env, **over):
    row = {"id": MID, "institute_id": INST, "filename": "Physics_notes_a.pdf",
           "storage_path": f"{INST}/{MID}/Physics_notes_a.pdf", "status": "failed",
           "execution_id": None, **over}
    env["sb"].storage.files[row["storage_path"]] = b"%PDF original"
    env["sb"].results[("study_materials", "select")] = \
        lambda q: [row] if ("eq", "id", MID) in q.filters else []
    return row


def test_reindex_resends_stored_original(env):
    _stored(env)
    r = env["client"].post(f"/teacher/materials/{MID}/reindex")
    assert r.status_code == 200
    assert (r.json()["status"], r.json()["execution_id"]) == ("running", "ex-1")
    assert env["uploads"][0]["content"] == b"%PDF original"
    assert env["uploads"][0]["filename"] == "Physics_notes_a.pdf"
    update = env["sb"].ops("study_materials", "update")[0]
    assert update.payload["execution_id"] == "ex-1" and update.payload["status"] == "running"


def test_reindex_unknown_or_other_institute_is_404(env):
    _stored(env)
    other = "55555555-5555-5555-5555-555555555555"
    assert env["client"].post(f"/teacher/materials/{other}/reindex").status_code == 404
    assert env["client"].post("/teacher/materials/not-a-uuid/reindex").status_code == 404
    assert ("eq", "institute_id", INST) in env["sb"].ops("study_materials", "select")[0].filters


def test_reindex_missing_original_is_502(env):
    row = _stored(env)
    env["sb"].storage.files.pop(row["storage_path"])
    assert env["client"].post(f"/teacher/materials/{MID}/reindex").status_code == 502
    assert env["uploads"] == []


def test_delete_removes_row_and_file_only(env):
    row = _stored(env)
    r = env["client"].delete(f"/teacher/materials/{MID}")
    assert r.status_code == 200 and "stay" in r.json()["note"]
    assert row["storage_path"] not in env["sb"].storage.files
    assert env["sb"].ops("study_materials", "delete")[0].filters == [("eq", "id", MID)]
    assert env["uploads"] == []  # nothing sent to RAG_SERVER


def test_delete_storage_failure_keeps_row(env):
    _stored(env)
    env["sb"].storage.fail["remove"] = RuntimeError("timeout")
    assert env["client"].delete(f"/teacher/materials/{MID}").status_code == 502
    assert env["sb"].ops("study_materials", "delete") == []


# ── Lecture transcripts ───────────────────────────────────────────────────────

def test_transcribe_uploads_timestamped_txt_as_lecture(monkeypatch):
    from rag import transcribe
    calls = []

    async def fake_create(content, name, **kw):
        calls.append((content, name, kw))
        return {"filename": "Physics_Rotation_lecture_rot.txt", "status": "running"}

    class FakeModel:
        def transcribe(self, path, **kw):
            return {"segments": [{"start": 0, "text": " Torque is "},
                                 {"start": 3725.4, "text": "r cross F."}]}

    monkeypatch.setattr(transcribe, "_get_model", lambda: FakeModel())
    monkeypatch.setattr(sm, "create_material", fake_create)
    row = transcribe.transcribe_and_upload("lectures/rot.mp4", subject="Physics",
                                           chapter="Rotation", institute_id=INST)
    content, name, kw = calls[0]
    assert name == "rot.txt" and row["status"] == "running"
    assert kw["material_type"] == "lecture" and kw["institute_id"] == INST
    assert kw["uploaded_by"] == sm.CLI_UPLOADER
    text = content.decode()
    assert "[00:00:00] Torque is\n[01:02:05] r cross F." in text
    assert "Source recording: rot.mp4" in text


def test_create_material_direct_call(env):
    """The CLI path calls create_material directly (no HTTP layer)."""
    row = asyncio.run(sm.create_material(b"[00:00:00] hi", "rot.txt", institute_id=INST,
                                         uploaded_by=sm.CLI_UPLOADER, material_type="lecture"))
    assert row["filename"] == "lecture_rot.txt" and row["status"] == "running"
