import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from app.engine import normalize
from app.main import create_app
from app.post_rules import posting_signals
from app.watchlist import Watchlist
from scripts.import_watchlist import parse_rows


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    with TestClient(create_app(tmp_path_factory.mktemp("watchlist"))) as client:
        yield client


def analyze(client, text, **options):
    response = client.post("/api/analyze", json={"text": text, **options})
    assert response.status_code == 200, response.text
    return response.json()


def test_admin_parser_does_not_confuse_action_with_state():
    text = "키워드\t타입\t상태\t등록일\t관리\n"
    text += "몸사\t은어\t활성\t2026-09-21 13:14:08\t\n이동\n비활성\n\n"
    text += "포즈\t일반\t비활성\t2026-09-21 13:13:00\t\n이동\n활성\n"
    assert parse_rows(text) == [
        {"keyword": "몸사", "type": "은어", "status": "활성"},
        {"keyword": "포즈", "type": "일반", "status": "비활성"},
    ]
    with pytest.raises(ValueError):
        parse_rows("몸사\t은어\t잘못된상태\t2026-09-21 13:14:08")
    with pytest.raises(ValueError):
        parse_rows(text + "몸사\t은어\t활성\t2026-09-21 13:14:08")


def test_attached_200_rows_preserve_exact_spellings_types_and_states(client):
    data = client.get("/api/watchlist").json()
    assert data["total"] == data["active"] == 200
    assert data["types"] == {"은어": 126, "일반": 35, "유인문구": 39}
    rows = [{k: e[k] for k in ("keyword", "type", "status")} for e in data["entries"]]
    # Checksum calculated independently from the parsed attachment, before annotation.
    assert hashlib.sha256(
        json.dumps(rows, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest() == ("ac4fe938d86d90c32f7791d77fb4212b7cb701f5bdcccbf3952131b2f9a35587")
    assert len({e["keyword"] for e in data["entries"]}) == 200
    assert all(e["occurrence_sources"][0] == "attached-watchlist" for e in data["entries"])


def test_all_listed_terms_are_recognized_as_complete_expressions():
    watchlist = Watchlist()
    for entry in watchlist.bundle["entries"]:
        text = "🧪 " + entry["keyword"]
        normalized, spans = normalize(text)
        hits, _ = watchlist.scan(normalized, spans, text, posting_signals(normalized, spans, text))
        assert any(entry["keyword"] in h["keywords"] for h in hits), entry["keyword"]
        assert all(text[h["start"] : h["end"]] == h["surface"] for h in hits)


def test_photo_reward_context_and_original_offsets(client):
    text = "🧪 서울에서 몸사를 보내면 용돈 줄게. 라인 연락"
    data = analyze(client, text)
    hits = {h["surface"]: h for h in data["watchlist_hits"]}
    assert {"서울", "몸사", "용돈", "라인"} <= hits.keys()
    assert hits["몸사"]["meaning"] == "몸 사진"
    assert hits["몸사"]["evidence"] == "documented"
    context = next(c for c in data["watchlist_contexts"] if c["kind"] == "reward_media_request")
    assert "라인" not in context["clause"]
    assert all(text[h["start"] : h["end"]] == h["surface"] for h in data["watchlist_hits"])


def test_fused_tags_spacing_particles_and_longest_match(client):
    data = analyze(client, "#몸사판매 #교복 업스 #맘눌뎀으로 #중딩 ㄱㅇ")
    hits = data["watchlist_hits"]
    assert {"몸사", "판매", "교복 업스", "맘눌뎀", "중딩 ㄱㅇ"} <= {h["surface"] for h in hits}
    up = next(h for h in hits if h["surface"] == "교복 업스")
    assert set(up["keywords"]) == {"교복업스", "교복 업스"}
    assert not any(h["surface"] == "교복" for h in hits)
    assert any(c["kind"] == "media_trade" for c in data["watchlist_contexts"])


@pytest.mark.parametrize(
    "text",
    [
        "서울 학생 용돈 관리 교육. 강아지 발 사진 수업. 라인 노선표",
        "게이 08게이 중딩게이 10비떱 교복 스타일",
        "부산에서 고등학생 수학여행 포즈 연습",
    ],
)
def test_general_identity_and_clothing_are_not_sexual_findings(client, text):
    data = analyze(client, text)
    assert not data["matches"]
    assert not data["watchlist_contexts"]
    assert data["watchlist_hits"]
    assert not any(h["detect"] for h in data["watchlist_hits"])


def test_ordinary_watchlist_words_are_not_automatic_new_slang(client):
    data = analyze(client, "게이 서울 학생 발 텔그 비번 교환")
    assert not any(m["surface"] in {"게이", "서울", "학생", "발"} for m in data["matches"])


def test_substrings_dates_accounts_urls_and_phone_numbers_are_excluded(client):
    text = (
        "서울대 학생회 발표 정지선 라인업 2026-10-29 [11] 010-1234-1008 "
        "08:11 10.11 인스타 @08게이 https://example.com/몸사"
    )
    data = analyze(client, text)
    assert not data["watchlist_hits"]
    data = analyze(client, "08, 10, 11년생 09게이 18세")
    assert {h["surface"] for h in data["watchlist_hits"]} >= {
        "08",
        "10",
        "11년생",
        "09게이",
        "18세",
    }
    assert all("age" not in h for h in data["watchlist_hits"])


def test_rules_stay_inside_post_boundaries_and_mark_prevention(client):
    data = analyze(client, "용돈 제공\n몸사 요청\n2026-10-29 학생 [3] 2026-10-29 섹스")
    assert not data["watchlist_contexts"]
    data = analyze(client, "몸사 판매 피해 예방 교육")
    assert data["watchlist_contexts"]
    assert all(c["protective"] for c in data["watchlist_contexts"])
    assert all("예방" in c["note"] for c in data["watchlist_contexts"])


def test_sexual_school_and_proxy_purchase_are_distinct(client):
    data = analyze(client, "고딩 섹스 판매\n담배댈구 문의")
    assert {c["kind"] for c in data["watchlist_contexts"]} >= {
        "age_sexual",
        "media_trade",
        "proxy_purchase",
    }
    assert any(m["surface"] == "고딩" for m in data["watchlist_hits"])
    assert not any(m["method"] == "watchlist" and m["surface"] == "고딩" for m in data["matches"])


def test_unclear_listed_terms_never_become_confirmed_definitions(client, monkeypatch):
    captured = []

    def fake(path, payload=None, timeout=3):
        if path == "/api/tags":
            return {"models": [{"name": "qwen3.5:9b", "size": 1}]}
        data = json.loads(payload["messages"][1]["content"])
        captured.append(data)
        target = next(c for c in data["candidates"] if c["surface"] == "야상극")
        return {
            "message": {
                "content": json.dumps(
                    {
                        "items": [
                            {
                                "id": target["id"],
                                "status": "possible",
                                "choices": [
                                    {
                                        "expansion": "꾸며낸 원형",
                                        "rationale": "허구의 풀이",
                                        "support": "야상극",
                                    }
                                ],
                            }
                        ]
                    },
                    ensure_ascii=False,
                )
            }
        }

    monkeypatch.setattr(client.app.state.contextual, "request", fake)
    result = client.post("/api/context/interpret", json={"text": "야상극 맘눌피"}).json()
    assert result["status"] == "ok"
    item = next(i for i in result["items"] if i["surface"] == "야상극")
    assert item["status"] == "unresolved" and item["choices"] == []
    assert next(c for c in captured[0]["candidates"] if c["surface"] == "맘눌피")["knowledge"]
    omitted = next(i for i in result["items"] if i["surface"] == "맘눌피")
    assert omitted["reference_candidates"][0]["sources"][0]["id"] == "tacteen-monitoring-2023"


def test_occurrence_is_not_definition_evidence():
    data = Watchlist().bundle
    ids = {s["id"] for s in data["sources"]}
    assert len(ids) == len(data["sources"])
    for entry in data["entries"]:
        assert set(entry["occurrence_sources"]) <= ids
        for candidate in entry["candidates"]:
            assert set(candidate["sources"]) <= ids
            assert "attached-watchlist" not in candidate["sources"]
            assert candidate["evidence"] != "documented" or candidate["sources"]
    unknown = next(e for e in data["entries"] if e["keyword"] == "라관")
    assert unknown["candidates"][0]["evidence"] == "hypothesis"
    assert unknown["candidates"][0]["sources"] == []


def test_oral_variant_and_ordinary_initial_meanings(client, monkeypatch):
    data = analyze(client, "ㅇㄹ")
    item = next(m for m in data["matches"] if m["surface"] == "ㅇㄹ")
    assert "오랄" in item["expansion"]
    assert any("오럴" in option for option in item["alternatives"])
    hit = data["watchlist_hits"][0]
    assert hit["candidates"][0]["sources"] == []
    assert hit["candidates"][1]["evidence"] == "documented"

    def fake(path, payload=None, timeout=3):
        if path == "/api/tags":
            return {"models": [{"name": "qwen3.5:9b", "size": 1}]}
        payload_data = json.loads(payload["messages"][1]["content"])
        candidate = next(c for c in payload_data["candidates"] if c["surface"] == "ㅇㄹ")
        assert any(
            c["expansion"] == "요리" for e in candidate["knowledge"] for c in e["candidates"]
        )
        return {
            "message": {
                "content": json.dumps(
                    {
                        "items": [
                            {
                                "id": candidate["id"],
                                "status": "possible",
                                "choices": [
                                    {
                                        "expansion": "오랄",
                                        "rationale": "일상 문맥을 무시한 모델의 잘못된 가설",
                                        "support": "",
                                    }
                                ],
                            }
                        ]
                    },
                    ensure_ascii=False,
                )
            }
        }

    monkeypatch.setattr(client.app.state.contextual, "request", fake)
    result = client.post("/api/context/interpret", json={"text": "오늘 ㅇㄹ 레시피"}).json()
    interpreted = next(i for i in result["items"] if i["surface"] == "ㅇㄹ")
    assert interpreted["status"] == "ordinary"
    assert interpreted["choices"][0]["expansion"] == "요리"
    assert interpreted["choices"][0]["grounding"] == "context_rule"
    fast = analyze(client, "학생 ㅇㄹ 레시피")
    assert not fast["matches"]
    assert not fast["watchlist_contexts"]
    assert (
        next(h for h in fast["watchlist_hits"] if h["surface"] == "ㅇㄹ")["assessment"] == "neutral"
    )


def test_conflicting_ordinary_and_sexual_hints_stay_ambiguous(client):
    fast = analyze(client, "ㅇㄹ 레시피 푸시")
    assert not fast["watchlist_hits"][0].get("ordinary_choice")
    fast = analyze(client, "ㅇㄹ 레시피 섹스")
    assert not fast["watchlist_hits"][0].get("ordinary_choice")
