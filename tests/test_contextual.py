import json

import pytest
from fastapi.testclient import TestClient

from app.contextual import ContextInterpreter
from app.main import create_app

POST = (
    "xx년생,아동포르노, 나눠올리기,재업ㄴㄴ\n"
    "ദ്ദി( • ᴗ • ) 좋은 게시물에는 추천을 눌러주세요.\n인스타 @sample_07"
)


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    with TestClient(create_app(tmp_path_factory.mktemp("post-context"))) as client:
        yield client


def test_requested_post_expressions_and_signals(client):
    result = client.post("/api/analyze", json={"text": POST}).json()
    assert {m["surface"]: m["expansion"] for m in result["matches"]} == {
        "아동포르노": "아동·청소년 성착취물",
        "나눠올리기": "나누어 올리기 / 분할 업로드",
        "재업ㄴㄴ": "재업로드 금지",
    }
    assert result["summary"]["patterns"] == 3
    assert result["summary"]["signals"] == 2
    assert all(
        POST[m["start"] : m["end"]] == m["surface"] for m in result["matches"] + result["signals"]
    )
    assert {s["kind"] for s in result["signals"]} == {"birth_year", "social_account"}
    assert not any(m["surface"] in {"좋은", "추천", "sample_07"} for m in result["matches"])


@pytest.mark.parametrize(
    "text", ["나눠 올리기", "나누어올리기", "재업 ㄴㄴ", "재업로드금지", "청소년 포르노"]
)
def test_posting_expression_variants(client, text):
    result = client.post("/api/analyze", json={"text": text}).json()
    assert len(result["matches"]) == 1
    assert result["matches"][0]["method"] == "pattern"


def test_birth_year_does_not_infer_age_from_handle(client):
    result = client.post(
        "/api/analyze", json={"text": "인스타 @07_sample / 07년생 / 2007년생"}
    ).json()
    assert len(result["signals"]) == 3
    birth = [s for s in result["signals"] if s["kind"] == "birth_year"]
    assert [s["surface"] for s in birth] == ["07년생", "2007년생"]
    assert all("age" not in s for s in result["signals"])
    assert (
        client.post("/api/analyze", json={"text": "이메일 user@example.com"}).json()["signals"]
        == []
    )


def test_general_upload_is_not_exploitation_classification(client):
    result = client.post("/api/analyze", json={"text": "여행 사진 나눠올리기. 재업ㄴㄴ"}).json()
    assert all(m["category"].startswith("일반 게시글") for m in result["matches"])
    assert all(m["score"] <= 60 for m in result["matches"])


def test_local_only_configuration():
    for url in ["https://api.example.com", "http://169.254.169.254", "http://user@localhost:11434"]:
        with pytest.raises(ValueError):
            ContextInterpreter(url=url)


def test_context_model_bounded_ids_grounding_and_redaction(client, monkeypatch):
    captured = []

    def fake(path, payload=None, timeout=3):
        if path == "/api/tags":
            return {"models": [{"name": "qwen3.5:9b", "size": 1}]}
        data = json.loads(payload["messages"][1]["content"])
        captured.append(data)
        term = next(c for c in data["candidates"] if c["surface"] == "ㅈㅇ")
        return {
            "message": {
                "content": json.dumps(
                    {
                        "items": [
                            {
                                "id": term["id"],
                                "status": "possible",
                                "choices": [
                                    {
                                        "expansion": "자위",
                                        "rationale": "자료에 있는 원형 후보이나 문맥 확인 필요",
                                        "support": "존재하지 않는 문장",
                                    },
                                    {
                                        "expansion": "지원",
                                        "rationale": "다른 뜻도 가능한 초성",
                                        "support": "",
                                    },
                                ],
                            },
                            {"id": 9999, "status": "possible", "choices": []},
                        ]
                    },
                    ensure_ascii=False,
                )
            }
        }

    monkeypatch.setattr(client.app.state.contextual, "request", fake)
    result = client.post("/api/context/interpret", json={"text": "ㅈㅇ 인스타 @private_07"}).json()
    assert result["status"] == "ok"
    assert len(result["items"]) == 1
    assert result["items"][0]["choices"][0]["grounding"] == "documented_candidate"
    assert result["items"][0]["choices"][0]["support"] == ""
    assert result["items"][0]["choices"][1]["grounding"] == "model_hypothesis"
    assert "@private_07" not in json.dumps(captured, ensure_ascii=False)
    assert result["redacted_accounts"] == 1


def test_unavailable_and_invalid_output_are_not_success(client, monkeypatch):
    monkeypatch.setattr(client.app.state.contextual, "info", lambda: {"available": False})
    result = client.post("/api/context/interpret", json={"text": "ㅈㅇ"}).json()
    assert result["status"] == "unavailable"
    assert client.post("/api/analyze", json={"text": "ㄱㄷ"}).json()["matches"]
    monkeypatch.setattr(client.app.state.contextual, "info", lambda: {"available": True})
    monkeypatch.setattr(
        client.app.state.contextual,
        "request",
        lambda *args, **kwargs: {"message": {"content": "invalid"}},
    )
    assert client.post("/api/context/interpret", json={"text": "ㅈㅇ"}).json()["status"] == "failed"
    assert client.post("/api/context/interpret", json={"text": "가" * 6001}).status_code == 422


def test_missing_initials_are_unresolved(client, monkeypatch):
    monkeypatch.setattr(client.app.state.contextual, "info", lambda: {"available": True})
    monkeypatch.setattr(
        client.app.state.contextual,
        "request",
        lambda *args, **kwargs: {"message": {"content": '{"items":[]}'}},
    )
    result = client.post("/api/context/interpret", json={"text": "ㅇㄹㄴ 알몸 터미널"}).json()
    item = next(i for i in result["items"] if i["surface"] == "ㅇㄹㄴ")
    assert item["status"] == "unresolved"
    assert item["choices"] == []


def test_ordinary_initial_meaning_is_preserved(client, monkeypatch):
    monkeypatch.setattr(client.app.state.contextual, "info", lambda: {"available": True})

    def fake(path, payload, timeout):
        data = json.loads(payload["messages"][1]["content"])
        item = next(c for c in data["candidates"] if c["surface"] == "ㅅㅅ")
        assert item["clause"] == "병원에서 ㅅㅅ 예약"
        return {
            "message": {
                "content": json.dumps(
                    {
                        "items": [
                            {
                                "id": item["id"],
                                "status": "ordinary",
                                "choices": [
                                    {
                                        "expansion": "수술",
                                        "rationale": "병원·예약 문맥",
                                        "support": "병원",
                                    }
                                ],
                            }
                        ]
                    }
                )
            }
        }

    monkeypatch.setattr(client.app.state.contextual, "request", fake)
    result = client.post(
        "/api/context/interpret", json={"text": "병원에서 ㅅㅅ 예약. 다른 문장"}
    ).json()
    assert result["items"][0]["choices"][0]["expansion"] == "수술"
    assert result["items"][0]["status"] == "ordinary"
    assert result["items"][0]["reference_candidates"]


def test_documented_ordinary_word_and_particle_are_not_lost(client, monkeypatch):
    monkeypatch.setattr(client.app.state.contextual, "info", lambda: {"available": True})
    monkeypatch.setattr(
        client.app.state.contextual,
        "request",
        lambda *args, **kwargs: {"message": {"content": '{"items":[]}'}},
    )
    result = client.post(
        "/api/context/interpret", json={"text": "문구점에서 나라풀을 샀습니다."}
    ).json()
    item = next(item for item in result["items"] if item["surface"] == "나라풀을")
    assert item["reference_candidates"][0]["expansion"] == "문구용 풀의 제품명"
    assert item["status"] == "unresolved"
