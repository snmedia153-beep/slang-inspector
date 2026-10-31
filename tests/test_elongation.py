import unicodedata

import pytest
from fastapi.testclient import TestClient

from app.contextual import ContextInterpreter
from app.elongation import ElongationNormalizer
from app.engine import normalize
from app.main import create_app
from app.ocr import analyze_words
from app.watchlist import PRIVATE as WATCH_PRIVATE
from app.watchlist import SUFFIX


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    with TestClient(create_app(tmp_path_factory.mktemp("elongation"))) as client:
        yield client


def analyze(client, text):
    response = client.post("/api/analyze", json={"text": text})
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize(
    "raw,restored",
    [
        ("간다아아아아아안", "간단"),
        ("고오오딩", "고딩"),
        ("고디이잉", "고딩"),
        ("몸사사사사", "몸사"),
        ("마아아안나아암", "만남"),
        ("ㄱㄱㄱㄷㄷㄷ", "ㄱㄷ"),
        ("간다아아안입니다", "간단입니다"),
        ("몸사아아판매", "몸사판매"),
    ],
)
def test_dictionary_gated_folding_preserves_full_original_span(raw, restored):
    folder = ElongationNormalizer(["간단", "고딩", "몸사", "만남", "ㄱㄷ", "판매"], SUFFIX)
    source = "🧪 " + raw + "!"
    text, spans = normalize(source)
    folded, mapped, events = folder.fold(text, spans, source)
    assert folded == "🧪 " + restored + "!"
    assert len(folded) == len(mapped)
    assert events == [
        {
            "start": 2,
            "end": 2 + len(raw),
            "surface": raw,
            "restored": restored,
            "normalized_start": 2,
            "normalized_end": 2 + len(restored),
            "kind": "elongation",
            "review_required": True,
        }
    ]
    assert source[mapped[2][0] : mapped[1 + len(restored)][1]] == raw


def test_multiple_events_coda_mapping_and_nfd_unicode():
    raw = unicodedata.normalize("NFD", "간다아아안")
    source = "🧪 " + raw + " 몸사사사!"
    text, spans = normalize(source)
    folder = ElongationNormalizer(["간단", "몸사"], SUFFIX)
    folded, mapped, events = folder.fold(text, spans, source)
    assert folded == "🧪 간단 몸사!"
    assert len(mapped) == len(folded)
    assert source[mapped[3][0] : mapped[3][1]] == unicodedata.normalize("NFD", "다아아안")
    assert [e["surface"] for e in events] == [raw, "몸사사사"]
    assert all(source[e["start"] : e["end"]] == e["surface"] for e in events)


@pytest.mark.parametrize(
    "source",
    [
        "간단한 설명입니다",
        "아아아 좋아요 ㅋㅋㅋㅋ",
        "가가가가나나나",
        "고오오딩친구",
        "고오오\n딩",
        "abc고오오딩",
        "https://example.com/고오오딩",
        "@고오오딩",
        "인스타 ＠고오오딩",
        "test@고오오딩.example",
        "노모",
        "간단",
    ],
)
def test_no_arbitrary_word_deletion_private_identifier_or_cross_line_folding(source):
    folder = ElongationNormalizer(["간단", "고딩", "노모"], SUFFIX)
    text, spans = normalize(source)
    folded, mapped, events = folder.fold(text, spans, source)
    assert folded == text and mapped == spans and events == []


def test_registered_repeated_spelling_is_preserved():
    source = "가가가나"
    folder = ElongationNormalizer([source, "가나"], SUFFIX)
    text, spans = normalize(source)
    assert folder.fold(text, spans, source) == (text, spans, [])


@pytest.mark.parametrize(
    "address",
    [
        "first.last+tag@example.co.kr",
        "name-1@example.com",
        "고오오딩@example.com",
    ],
)
def test_private_address_boundaries_keep_entire_address(address):
    text = f"연락 <{address}>, 검토"
    assert [m.group() for m in WATCH_PRIVATE.finditer(text)] == [address]
    folder = ElongationNormalizer(["고딩"], SUFFIX)
    normalized, spans = normalize(text)
    assert folder.fold(normalized, spans, text)[2] == []


def test_user_example_is_reviewable_without_inventing_high_school_meaning(client):
    raw = "간다아아아아아안"
    data = analyze(client, raw)
    assert data["normalized"] == "간단"
    assert data["normalizations"][0]["restored"] == "간단"
    assert data["matches"] == []
    hit = next(h for h in data["watchlist_hits"] if h["keyword"] == "간단")
    assert hit["surface"] == raw and not hit["detect"]
    assert "고딩" not in str(data["matches"])
    assert analyze(client, "간단한 설명과 식사입니다")["matches"] == []


def test_folded_watchlist_context_and_match_coordinates(client):
    raw = "간다아아아아아안"
    source = "🧪 " + raw + " 몸사 판매 만남"
    data = analyze(client, source)
    match = next(m for m in data["matches"] if m["surface"] == raw)
    assert match["method"] == "watchlist"
    assert match["term"] == "간단"
    assert source[match["start"] : match["end"]] == raw
    assert any("늘임·반복 복원" in r for r in match["reasons"])
    assert all(source[m["start"] : m["end"]] == m["surface"] for m in data["matches"])


def test_ordinary_negation_account_and_post_boundaries_still_apply(client):
    assert analyze(client, "보오오지 못했다")["matches"] == []
    assert analyze(client, "인스타 @고오오딩")["normalizations"] == []
    data = analyze(client, "간다아아안\n몸사 판매 만남")
    hit = next(h for h in data["watchlist_hits"] if h["keyword"] == "간단")
    assert not hit["detect"]
    data = analyze(client, "간다아아안 몸사 판매 예방 교육")
    assert all(c["protective"] for c in data["watchlist_contexts"])


def test_context_model_receives_restored_keyword_but_original_surface(client):
    raw = "간다아아아아아안"
    source = raw + " 몸사 판매 만남"
    data = analyze(client, source)
    candidates = ContextInterpreter().candidates(source, data)
    candidate = next(c for c in candidates if c["surface"] == raw)
    assert candidate["normalized_surface"] == "간단"
    assert source[candidate["start"] : candidate["end"]] == raw
    assert any(k["term"] == "간단" for k in candidate["knowledge"])


def test_ocr_keeps_all_original_word_boxes_and_neutral_folds_are_not_red(client):
    raw = "간다아아아아아안"
    words = [
        {"text": raw, "x": 10, "y": 10, "width": 100, "height": 25, "confidence": 90, "line": 0}
    ]
    neutral = analyze_words(words, 500, 200, client.app.state.engine)
    assert neutral["regions"] == []
    assert neutral["analysis"]["normalizations"][0]["restored"] == "간단"
    words += [
        {"text": text, "x": x, "y": 10, "width": 50, "height": 25, "confidence": 90, "line": 0}
        for text, x in [("몸사", 150), ("판매", 220), ("만남", 290)]
    ]
    data = analyze_words(words, 500, 200, client.app.state.engine)
    region = next(r for r in data["regions"] if r["surface"] == raw)
    assert region["word_ids"] == [0]
    assert region["boxes"] == [{"x": 10, "y": 10, "width": 100, "height": 25}]


def test_long_repetition_is_linear_and_does_not_truncate_original_offsets(client):
    raw = "간다" + "아" * 15000 + "안"
    data = analyze(client, raw)
    assert data["normalized"] == "간단"
    assert data["normalizations"][0]["end"] == len(raw)
    assert len(data["tokens"]) <= 2


def test_user_dictionary_reload_and_deletion_update_restoration_forms(client):
    raw = "검즈으응표현"
    assert analyze(client, raw)["normalizations"] == []
    response = client.post(
        "/api/lexicon",
        json={
            "alias": "검증표현",
            "expansion": "검증원형",
            "canonical": "검토용 대표표현",
        },
    )
    assert response.status_code == 201
    try:
        data = analyze(client, raw)
        assert data["normalizations"][0]["restored"] == "검증표현"
        assert data["matches"][0]["expansion"] == "검증원형"
        assert data["matches"][0]["score"] <= 70
    finally:
        assert client.delete(f"/api/lexicon/{response.json()['id']}").status_code == 200
    assert analyze(client, raw)["normalizations"] == []
