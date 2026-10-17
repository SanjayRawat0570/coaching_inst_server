"""Phase 5: long-term memory on pgvector, the Qdrant -> RAG_SERVER migration
script, and proof that nothing imports the old RAG any more."""

import pathlib
import re
from types import SimpleNamespace

import pytest

from memory import long_term
from scripts import migrate_to_rag_server as mig

BACKEND = pathlib.Path(__file__).resolve().parents[1]


# ── Long-term memory (Supabase pgvector) ──────────────────────────────────────

@pytest.fixture
def mem(monkeypatch, fake_sb):
    monkeypatch.setattr(long_term, "_supabase", lambda: fake_sb)
    monkeypatch.setattr(long_term, "_embed", lambda text: [0.5, -0.25, 1.0])
    return fake_sb


def test_add_memory_inserts_row_with_vector(mem):
    assert long_term.add_memory("stu-1", "What is torque?", "r x F") is True
    row = mem.ops("student_memories", "insert")[0].payload
    assert row == {"student_id": "stu-1", "memory": "What is torque?\nr x F",
                   "embedding": "[0.5,-0.25,1.0]"}


def test_get_memories_uses_rpc(mem):
    mem.results[("match_student_memories", "rpc")] = [{"memory": "m1", "similarity": 0.9},
                                                      {"memory": "m2", "similarity": 0.7}]
    assert long_term.get_memories("stu-1", "torque", limit=2) == "m1\nm2"
    call = mem.ops("match_student_memories", "rpc")[0]
    assert call.payload == {"p_student_id": "stu-1", "query_embedding": "[0.5,-0.25,1.0]",
                            "match_count": 2}


def test_memory_fails_soft(mem):
    mem.results[("student_memories", "insert")] = RuntimeError('relation "student_memories" does not exist')
    mem.results[("match_student_memories", "rpc")] = RuntimeError("function does not exist")
    assert long_term.add_memory("stu-1", "q") is False
    assert long_term.get_memories("stu-1", "q") == ""
    assert long_term.add_memory("stu-1", "") is False and long_term.get_memories("", "q") == ""


# ── Rebuilding documents from old chunks ──────────────────────────────────────

def _chunks(n_words):
    """Chunk a document of n_words words exactly like the old rag/ingest.py did."""
    words = [f"w{i}" for i in range(n_words)]
    out, i = [], 0
    while i < len(words):
        out.append(" ".join(words[i:i + mig.CHUNK_WORDS]))
        i += mig.CHUNK_WORDS - mig.OVERLAP_WORDS
    return words, out


def test_order_chunks_restores_reading_order_without_overlap():
    words, chunks = _chunks(2500)
    shuffled = [chunks[2], chunks[0], chunks[3], chunks[1]]
    assert mig.order_chunks(shuffled) == " ".join(words)


def test_order_chunks_keeps_unrelated_documents_apart():
    words, chunks = _chunks(1500)
    assert len(chunks) == 3
    text = mig.order_chunks([chunks[1], "a separate short note", chunks[2], chunks[0]])
    assert " ".join(words) in text and "a separate short note" in text
    assert text.count("\n\n") == 1


def _point(**payload):
    return SimpleNamespace(payload=payload)


def test_group_points_and_markdown():
    points = [_point(content="Newton one", source="ncert", subject="Physics", chapter="Laws", level=1),
              _point(content="Newton two", source="ncert", subject="Physics", chapter="", level=1),
              _point(content="cutoff row", source="nta_cutoff", subject=None, level=1),
              _point(content="summary", source="ncert", subject="Physics", level=3),
              _point(content="  ", source="pyq", subject="Physics")]
    groups = mig.group_points(points)
    assert set(groups) == {("ncert", "Physics")}
    md = mig.build_markdown("ncert", "Physics", groups[("ncert", "Physics")])
    assert md.startswith("# Physics — NCERT")
    assert md.index("## Laws") < md.index("## General")  # named chapters first
    assert "Newton one" in md and "Newton two" in md


class FakeQdrant:
    def __init__(self, collections):
        self.collections = collections

    def get_collections(self):
        return SimpleNamespace(collections=[SimpleNamespace(name=n) for n in self.collections])

    def scroll(self, name, limit, offset, with_payload, with_vectors):
        return self.collections[name], None


INST = "77777777-7777-7777-7777-777777777777"


def test_plan_qdrant_targets():
    client = FakeQdrant({
        "rag_shared": [_point(content="ncert text", source="ncert", subject="Physics", chapter="Laws")],
        f"rag_{INST}": [_point(content="notes", source="institute_notes", subject="Chemistry")],
        "rag_not-a-uuid": [_point(content="x", source="ncert")],
        "longterm_memories": [_point(memory="m", student_id="s")],
    })
    other = "88888888-8888-8888-8888-888888888888"
    plan = mig.plan_qdrant(client, shared_to=[INST, other])
    targets = sorted((u["collection"], u["institute_id"], u["material_type"]) for u in plan)
    assert targets == [(f"rag_{INST}", INST, "notes"),
                       ("rag_shared", INST, "ncert"), ("rag_shared", other, "ncert")]
    assert b"## Laws" in next(u for u in plan if u["collection"] == "rag_shared")["content"]


def test_dry_run_writes_nothing(monkeypatch, tmp_path, capsys):
    (tmp_path / "ch5.pdf").write_bytes(b"%PDF")
    (tmp_path / "video.mp4").write_bytes(b"x")
    monkeypatch.setattr(mig, "run_uploads", lambda u: pytest.fail("uploaded during dry run"))
    assert mig.main(["--files", str(tmp_path), "--material-type", "ncert",
                     "--subject", "Physics", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "would upload Physics_ncert_ch5.pdf -> default tenant" in out
    assert "skipping" in out and "video.mp4" in out
    assert "Dry run: 1 uploads planned, nothing written." in out


def test_cli_requires_a_mode():
    with pytest.raises(SystemExit):
        mig.main(["--dry-run"])


# ── Nothing references the old RAG ────────────────────────────────────────────

OLD = re.compile(r"rag\.retriever|rag\.qdrant_client|full_rag_pipeline|search_qdrant|"
                 r"qdrant_client|CrossEncoder|tavily|hyde_search|crag_check|raptor_search",
                 re.IGNORECASE)


def test_no_code_imports_the_old_rag():
    allowed = {BACKEND / "scripts" / "migrate_to_rag_server.py",  # one-off Qdrant reader
               pathlib.Path(__file__).resolve()}
    hits = [f"{p.relative_to(BACKEND)}:{n}"
            for p in BACKEND.rglob("*.py") if p not in allowed and ".venv" not in p.parts
            for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
            if OLD.search(line)]
    assert hits == []
    assert not (BACKEND / "rag" / "retriever.py").exists()
    assert not (BACKEND / "rag" / "qdrant_client.py").exists()


def test_requirements_dropped_old_rag_stack():
    reqs = (BACKEND / "requirements.txt").read_text(encoding="utf-8").lower()
    pinned = {line.split("==")[0].strip() for line in reqs.splitlines()
              if line and not line.startswith("#")}
    assert not pinned & {"qdrant-client", "mem0ai", "langchain-community", "pymupdf", "tavily-python"}
    assert {"httpx", "scikit-learn", "sentence-transformers"} <= pinned
