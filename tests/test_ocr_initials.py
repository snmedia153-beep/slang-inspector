import json
import unicodedata

import pytest
from fastapi.testclient import TestClient

from app.contextual import ContextInterpreter
from app.main import create_app
from app.ocr import analyze_words


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    with TestClient(create_app(tmp_path_factory.mktemp("ocr-initials"))) as client:
        yield client


def analyze(client, text):
    response = client.post("/api/analyze", json={"text": text})
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize(
    "text,surface",
    [
        ("ㅇㄹㄴ", "ㅇㄹㄴ"),
        ("오줌ㄱㄲ", "ㄱㄲ"),
        ("사탕ㅈㅇ", "ㅈㅇ"),
        ("ㅇ ㄹ ㄴ", "ㅇ ㄹ ㄴ"),
        ("오줌ㄱ ㄲ", "ㄱ ㄲ"),
        ("사탕ㅈ ㅇ", "ㅈ ㅇ"),
    ],
)
def test_initials_are_visible_with_unknown_meaning_or_alternatives(client, text, surface):
    data = analyze(client, text)
    match = next(m for m in data["matches"] if m["surface"] == surface)
    assert text[match["start"] : match["end"]] == surface
    assert match["review_required"]
    if "ㅈ" in surface:
        assert match["method"] == "initials"
        assert set(match["alternatives"]) >= {"자위", "지원", "주의", "지인"}
    else:
        assert match["method"] == "unresolved_initials"
        assert match["expansion"] is None
        assert match["alternatives"] == []
        assert match["provenance"] == []
        assert match["evidence"] == "unresolved_reference"


@pytest.mark.parametrize(
    "text",
    [
        "사탕",
        "오줌",
        "ㄱㄲㄴ",
        "ㅇㄹㄴㄱ",
        "초성 ㅋㅋㅋ",
        "abcㅇㄹㄴ",
        "ㅇㄹㄴ123",
        "인스타 @ㅇㄹㄴ",
        "＠오줌ㄱㄲ",
        "https://example.com/사탕ㅈㅇ",
        "오줌ㄱㄲ@example.com",
        "채용ㅈㅇ 서류와 이력서",
        "미끄럼ㅈㅇ 안전수칙",
    ],
)
def test_normal_context_private_identifiers_and_long_initial_runs_not_flagged(client, text):
    data = analyze(client, text)
    assert data["matches"] == [], data["matches"]


def test_repeated_occurrences_and_nfd_keep_correct_original_offsets(client):
    text = "🧪 " + unicodedata.normalize("NFD", "오줌") + "ㄱㄲ / ㅇㄹㄴ / 사탕ㅈㅇ / ㅇㄹㄴ"
    data = analyze(client, text)
    assert len(data["matches"]) == 4
    assert [text[m["start"] : m["end"]] for m in data["matches"]] == [
        "ㄱㄲ",
        "ㅇㄹㄴ",
        "ㅈㅇ",
        "ㅇㄹㄴ",
    ]
    assert len({m["start"] for m in data["matches"]}) == 4


def word(text, x, line=0):
    return {
        "text": text,
        "x": x,
        "y": 10 + line * 40,
        "width": 60,
        "height": 25,
        "confidence": 90,
        "line": line,
    }


def test_exact_ocr_text_maps_three_keywords_to_original_boxes(client):
    words = [word(text, x) for text, x in [("ㅇㄹㄴ", 10), ("오줌ㄱㄲ", 100), ("사탕ㅈㅇ", 200)]]
    data = analyze_words(words, 400, 200, client.app.state.engine)
    assert [r["surface"] for r in data["regions"]] == ["ㅇㄹㄴ", "ㄱㄲ", "ㅈㅇ"]
    assert [r["word_ids"] for r in data["regions"]] == [[0], [1], [2]]
    assert [r["boxes"][0]["x"] for r in data["regions"]] == [10, 100, 200]
    assert all("미확인" in r["expansion"] for r in data["regions"][:2])
    assert "지원" in data["regions"][2]["alternatives"]


def test_split_ocr_initials_cover_each_original_word_without_crossing_lines(client):
    words = [word(text, x) for text, x in [("ㅇ", 10), ("ㄹ", 80), ("ㄴ", 150)]]
    data = analyze_words(words, 400, 200, client.app.state.engine)
    assert data["regions"][0]["word_ids"] == [0, 1, 2]
    assert len(data["regions"][0]["boxes"]) == 3
    words[1]["line"] = 1
    words[2]["line"] = 2
    assert analyze_words(words, 400, 200, client.app.state.engine)["regions"] == []


def test_reference_unknown_cannot_become_hallucinated_expansion(client, monkeypatch):
    text = "ㅇㄹㄴ, 오줌ㄱㄲ"
    fast = analyze(client, text)
    candidates = ContextInterpreter().candidates(text, fast)
    assert {c["surface"] for c in candidates} == {"ㅇㄹㄴ", "ㄱㄲ"}
    assert all(c["unresolved_reference"] for c in candidates)

    def fake(path, payload=None, timeout=3):
        if path == "/api/tags":
            return {"models": [{"name": "qwen3.5:9b", "size": 1}]}
        data = json.loads(payload["messages"][1]["content"])
        return {
            "message": {
                "content": json.dumps(
                    {
                        "items": [
                            {
                                "id": c["id"],
                                "status": "possible",
                                "choices": [
                                    {
                                        "expansion": "검증되지 않은 풀이",
                                        "rationale": "모델의 가설",
                                        "support": "",
                                    }
                                ],
                            }
                            for c in data["candidates"]
                        ]
                    },
                    ensure_ascii=False,
                )
            }
        }

    monkeypatch.setattr(client.app.state.contextual, "request", fake)
    response = client.post("/api/context/interpret", json={"text": text})
    assert response.status_code == 200
    assert len(response.json()["items"]) == 2
    assert all(i["status"] == "unresolved" and i["choices"] == [] for i in response.json()["items"])


def test_ordinary_initials_are_preserved_in_ocr_and_context_candidates(client):
    text = "채용ㅈㅇ 이력서"
    fast = analyze(client, text)
    assert not fast["matches"]
    hit = next(h for h in fast["watchlist_hits"] if h["keyword"] == "ㅈㅇ")
    assert hit["ordinary_choice"]["expansion"] == "지원"
    assert hit["assessment"] == "neutral"
    candidates = ContextInterpreter().candidates(text, fast)
    candidate = next(c for c in candidates if c["surface"] == "ㅈㅇ")
    assert candidate["ordinary_choice"]["expansion"] == "지원"
    assert analyze_words([word(text, 10)], 400, 200, client.app.state.engine)["regions"] == []
