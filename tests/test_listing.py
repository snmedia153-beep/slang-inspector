import json

import pytest
from fastapi.testclient import TestClient

from app.contextual import clause_for
from app.main import create_app

LISTING = "2026-10-29 ㅌㅌ 가상인물 꼭노 [3] 2026-10-29 취향)개한테 임신시켜달라는 ㄱㄹㄴ"


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    with TestClient(create_app(tmp_path_factory.mktemp("listing"))) as client:
        yield client


def test_listing_is_found_without_model(client):
    result = client.post("/api/analyze", json={"text": LISTING}).json()
    assert len(result["matches"]) == 4
    assert {m["surface"] for m in result["matches"]} == {
        "ㅌㅌ",
        "꼭노",
        "개한테 임신시켜달라는",
        "ㄱㄹㄴ",
    }
    exposure = next(m for m in result["matches"] if m["surface"] == "꼭노")
    assert exposure["evidence"] == "inferred_alias"
    assert "추정" in exposure["expansion"]
    tiktok = next(m for m in result["matches"] if m["surface"] == "ㅌㅌ")
    assert set(tiktok["alternatives"]) == {"틱톡", "튀어튀어"}
    assert tiktok["category"] == "플랫폼·일상 초성 후보"
    derogatory = next(m for m in result["matches"] if m["surface"] == "ㄱㄹㄴ")
    assert derogatory["provenance"]
    assert "미확인" in derogatory["note"]
    assert result["summary"]["patterns"] == 2
    assert result["summary"]["candidates"] == 2
    assert all(LISTING[m["start"] : m["end"]] == m["surface"] for m in result["matches"])


def test_metadata_is_not_slang(client):
    result = client.post("/api/analyze", json={"text": LISTING}).json()
    assert [s["kind"] for s in result["signals"]].count("post_date") == 2
    assert [s["kind"] for s in result["signals"]].count("comment_count") == 1
    assert (
        next(s for s in result["signals"] if s["kind"] == "person_label")["surface"] == "가상인물"
    )
    assert not any(m["surface"] == "가상인물" for m in result["matches"])
    for signal in result["signals"]:
        assert LISTING[signal["start"] : signal["end"]] == signal["surface"]


@pytest.mark.parametrize(
    "text",
    [
        "개가 임신했어요",
        "강아지 임신 검사 예약",
        "수의사가 개에게 임신시키는 방법을 연구합니다",
        "개한테 밥 시켜달라",
        "2026-10-29 반려견 건강 [3]",
        "그림에 꼭 노란색을 써주세요",
    ],
)
def test_nearby_ordinary_examples_do_not_trigger_animal_or_exposure(client, text):
    result = client.post("/api/analyze", json={"text": text}).json()
    assert not any(
        m.get("rule_id") in {"animal_pregnancy_request", "exposure_abbreviation"}
        for m in result["matches"]
    )


def test_row_boundaries_and_person_redaction(client, monkeypatch):
    positions = [LISTING.index("꼭노"), LISTING.index("ㄱㄹㄴ")]
    assert "ㄱㄹㄴ" not in clause_for(LISTING, positions[0], positions[0] + 2)
    assert "꼭노" not in clause_for(LISTING, positions[1], positions[1] + 3)
    monkeypatch.setattr(client.app.state.contextual, "info", lambda: {"available": True})
    captured = []

    def fake(path, payload, timeout):
        captured.append(json.loads(payload["messages"][1]["content"]))
        return {"message": {"content": '{"items":[]}'}}

    monkeypatch.setattr(client.app.state.contextual, "request", fake)
    result = client.post("/api/context/interpret", json={"text": LISTING}).json()
    assert result["status"] == "ok"
    assert result["redacted_person_labels"] == 1
    assert "가상인물" not in json.dumps(captured, ensure_ascii=False)
    assert any(i["surface"] == "ㄱㄹㄴ" for i in result["items"])


def test_invalid_date_is_not_accepted(client):
    result = client.post("/api/analyze", json={"text": "2026-99-99 [3]"}).json()
    assert not any(s["kind"] == "post_date" for s in result["signals"])
