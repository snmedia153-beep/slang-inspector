import hashlib
import json
import unicodedata
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.engine import jamo, normalize, similarity
from app.main import create_app
from app.store import Store


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    with TestClient(create_app(tmp_path_factory.mktemp("slang"))) as test_client:
        yield test_client


def analyze(client, text, **options):
    response = client.post("/api/analyze", json={"text": text, **options})
    assert response.status_code == 200, response.text
    return response.json()


def test_health_and_ui(client):
    assert client.get("/api/health").json()["kiwi"]
    assert "은어 렌즈" in client.get("/").text
    assert client.get("/static/app.js").status_code == 200


def test_dictionary_and_multiple_occurrences(client):
    result = analyze(client, "불법촬영물 관련 자료에서 불법촬영물 표현을 확인")
    assert len(result["matches"]) == 2
    assert all(m["method"] == "dictionary" for m in result["matches"])


@pytest.mark.parametrize("text", ["끄.딩.물", "끄 딩 물", "끄♡딩_물", "끄1딩2물", "끄\u200b딩물"])
def test_obfuscation_and_original_spans(client, text):
    result = analyze(client, "🧪 " + text + " 텔그 비번 교환")
    match = next(m for m in result["matches"] if m["surface"] == text)
    assert match["method"] == "normalized"
    assert result["text"][match["start"] : match["end"]] == text


def test_initials_longest_match_and_boundaries(client):
    result = analyze(client, "ㄱㄷ물 및 ㄱㄷ 그리고 ㄱㄷㄴㄹ")
    assert [m["surface"] for m in result["matches"]] == ["ㄱㄷ물", "ㄱㄷ"]


@pytest.mark.parametrize("initials,expansion", [("ㄱㄷ", "고딩"), ("ㄷㄸ", "대딸")])
def test_initial_expansion_without_context(client, initials, expansion):
    result = analyze(client, initials)
    assert result["matches"][0]["expansion"] == expansion
    assert result["matches"][0]["surface"] == initials
    assert result["matches"][0]["review_required"]


def test_derived_initials_and_ambiguous_originals(client):
    ids = []
    try:
        for word in ["감자", "과자"]:
            response = client.post(
                "/api/lexicon", json={"alias": word, "expansion": word, "canonical": "일상 단어"}
            )
            assert response.status_code == 201
            ids.append(response.json()["id"])
        item = analyze(client, "ㄱㅈ")["matches"][0]
        assert item["method"] == "initials"
        assert set(item["alternatives"]) >= {"감자", "과자"}
    finally:
        for entry_id in ids:
            client.delete(f"/api/lexicon/{entry_id}")


def test_decomposed_hangul(client):
    raw = unicodedata.normalize("NFD", "성착취물")
    result = analyze(client, raw)
    assert result["matches"][0]["surface"] == raw


def test_plain_text_and_single_context_do_not_generate_candidates(client):
    assert analyze(client, "친구와 과일을 사고 사진 촬영 수업을 들어요")["matches"] == []
    result = analyze(client, "사과 교환합니다")
    assert result["summary"]["candidates"] == 0


def test_protective_language_and_paragraph_isolation(client):
    result = analyze(client, "성착취물 신고 예방 교육")
    assert result["matches"][0]["score"] < 90
    assert any("예방" in r for r in result["matches"][0]["reasons"])
    assert analyze(client, "사과 텔그 비번 교환 신고 예방")["summary"]["candidates"] == 0
    assert analyze(client, "사과를 먹어요\n텔그 비번 교환")["summary"]["candidates"] == 0


def test_jamo_matching_is_candidate(client):
    result = analyze(client, "성착쥐물 텔그 비번 교환", threshold=0.75)
    matches = [m for m in result["matches"] if m["method"] == "jamo"]
    assert matches
    assert matches[0]["review_required"]
    assert matches[0]["similarity"] >= 0.75
    assert similarity("고딩물", "고딩물") == 1
    assert jamo("고") == "ㄱㅗ"


def test_dynamic_dictionary_add_delete(client):
    body = {
        "alias": "검증표현",
        "expansion": "검증원형",
        "canonical": "검토용 대표표현",
        "needs_context": True,
    }
    added = client.post("/api/lexicon", json=body)
    assert added.status_code == 201
    assert client.post("/api/lexicon", json=body).status_code == 409
    result = analyze(client, "검증표현")
    assert result["matches"][0]["canonical"] == body["canonical"]
    assert result["matches"][0]["expansion"] == body["expansion"]
    assert any(t["canonical"] == body["canonical"] for t in result["tokens"])
    assert client.delete(f"/api/lexicon/{added.json()['id']}").status_code == 200
    assert not analyze(client, "검증표현")["matches"]


def test_validation_and_origin(client):
    for body in [
        {"text": " "},
        {"text": "\u200b"},
        {"text": "x" * 20001},
        {"text": "안녕", "threshold": 1.1},
    ]:
        assert client.post("/api/analyze", json=body).status_code == 422
    assert client.post("/api/lexicon", json={"alias": ".*", "canonical": "검토"}).status_code == 422
    assert (
        client.post(
            "/api/analyze", json={"text": "사과"}, headers={"Origin": "https://evil.test"}
        ).status_code
        == 403
    )
    assert client.get("/").headers["content-security-policy"].startswith("default-src 'self'")


def test_discovery_review_and_deduplication(client):
    texts = ["사과 텔그 비번 교환", "사과 텔그 비번 판매"]
    response = client.post("/api/discover", json={"texts": texts + texts})
    assert response.status_code == 200
    data = response.json()
    assert data["documents"] == 2
    apple = next(c for c in data["candidates"] if c["term"] == "사과")
    assert apple["document_count"] == 2
    client.post("/api/discover", json={"texts": texts})
    saved = next(
        c for c in client.get("/api/candidates").json()["candidates"] if c["term"] == "사과"
    )
    assert saved["document_count"] == 2
    assert client.delete(f"/api/candidates/{saved['id']}").status_code == 200
    assert not any(c["term"] == "사과" for c in client.get("/api/candidates").json()["candidates"])
    assert client.post("/api/discover", json={"texts": [texts[0], texts[0]]}).status_code == 422


def test_persistence_and_seed_not_restored_after_deletion(tmp_path):
    store = Store(tmp_path)
    entry = store.entries()[0]
    store.delete(entry["id"])
    another = Store(tmp_path)
    assert not any(e["id"] == entry["id"] for e in another.entries())


def test_normalization_mapping():
    normalized, spans = normalize("Ａ\u200b불법촬영물")
    assert normalized == "a불법촬영물"
    assert spans[1][0] == 2


def test_collected_data_and_provenance(client):
    data = client.get("/api/dataset").json()
    assert data["entries"] >= 600
    assert len(data["sources"]) == 5
    assert data["initial_forms"] > 100
    assert not data["generated_variants_included"]
    assert all(
        source["license"] and source["url"].startswith("https://") for source in data["sources"]
    )
    item = analyze(client, "지인능욕")["matches"][0]
    assert item["provenance"]
    assert item["category"] == "합성·성적 괴롭힘"
    result = analyze(client, "ㅈㅇㄴㅇ")
    assert any("지인능욕" in m["alternatives"] for m in result["matches"])


def test_collected_dictionary_false_positives(client):
    result = analyze(
        client, "그 영화를 보지 못했다. 자위권 관련 뉴스를 읽었다. 고등어를 요리했어요."
    )
    assert result["matches"] == []
    assert analyze(client, "Sussex 여행을 계획합니다")["matches"] == []
    assert any(
        m["surface"] == "고등어" for m in analyze(client, "고등어 텔그 비번 교환")["matches"]
    )


def test_bundle_integrity_and_source_metadata():
    folder = Path(__file__).resolve().parents[1] / "app" / "data"
    manifest = json.loads((folder / "manifest.json").read_text("utf-8"))
    assert hashlib.sha256((folder / "lexicon.json").read_bytes()).hexdigest() == manifest["sha256"]


def test_collected_deletion_survives_restart(tmp_path):
    store = Store(tmp_path)
    item = next(e for e in store.entries() if e["alias"] == "지인능욕")
    store.delete(item["id"])
    another = Store(tmp_path)
    assert not any(e["alias"] == "지인능욕" for e in another.entries())
