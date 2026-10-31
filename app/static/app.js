"use strict";
const $ = (id) => document.getElementById(id);
const samples = {
  initials: "ㄱㄷ ㄷㄸ",
  posting: "xx년생, 아동포르노, 나눠올리기, 재업ㄴㄴ\nദ്ദി( • ᴗ • ) 좋은 게시물에는 추천을 눌러주세요.\n인스타 @sample_07",
  obfuscated: "레전드 끄.딩.물 및 ㄱㄷ 공유방 입갤. 텔그에서 비번 확인 후 교환",
  context: "병원에서 ㅅㅅ 예약을 확인했습니다. 채용 ㅈㅇ 서류를 제출했습니다.",
  normal: "오늘은 친구들과 과일을 사러 갑니다. 학교에서 사진 촬영 수업을 들었어요."
};
const methods = {dictionary: "사전 일치", normalized: "복원 일치", pattern: "게시글 표현 규칙", watchlist: "문맥 목록 대조", initials: "초성 원형 후보", unresolved_initials: "원형 미확인 초성", jamo: "자모 유사 후보", context: "문맥 검토 후보"};
const candidateMethods = new Set(["jamo", "context", "initials", "unresolved_initials"]);
const evidenceLabels = {documented: "풀이 용례 확인", literal: "일반·표면 의미", hypothesis: "미확인 풀이 후보", unknown: "원형 미확인"};
const assessmentLabels = {neutral: "일반 단서", contextual: "조합 문맥 있음", candidate: "목록 일치", unresolved: "원형 미확인"};
let lastResult = null;
let entries = [];
let lexiconPage = 0;
let toastTimer;

function element(tag, className, text) {
  const el = document.createElement(tag);
  if (className) el.className = className;
  if (text !== undefined) el.textContent = text;
  return el;
}
function sourceLinks(sources) {
  const wrapper = element("div", "source-links");
  sources.forEach(source => {
    if (!source.url?.startsWith("https://")) return;
    const link = element("a", "", `${source.title || source.id}${source.license ? ` · ${source.license}` : ""} ↗`);
    link.href = source.url; link.target = "_blank"; link.rel = "noopener noreferrer";
    wrapper.append(link);
  });
  return wrapper;
}
function toast(message, error = false) {
  $("toast").textContent = message;
  $("toast").className = error ? "error" : "";
  $("toast").hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { $("toast").hidden = true; }, error ? 9000 : 4000);
}
async function api(path, options = {}) {
  const response = await fetch(path, {headers: {"Content-Type": "application/json"}, ...options});
  const data = await response.json();
  if (!response.ok) {
    const detail = Array.isArray(data.detail) ? data.detail.map(e => e.msg.replace(/^Value error, /, "")).join(" / ") : data.detail;
    throw new Error(detail || "요청을 처리하지 못했습니다.");
  }
  return data;
}
async function busy(button, action, pending) {
  if (button.disabled) return;
  const original = button.textContent;
  button.disabled = true;
  button.textContent = pending;
  try { await action(); } catch (error) { toast(error.message, true); }
  finally { button.disabled = false; button.textContent = original; }
}
function download(name, value) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], {type: "application/json;charset=utf-8"}));
  const link = element("a"); link.href = url; link.download = name;
  link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function setPage(page) {
  document.querySelectorAll(".page").forEach(p => { p.hidden = p.id !== `page-${page}`; });
  document.querySelectorAll(".nav-item").forEach(b => {
    b.classList.toggle("active", b.dataset.page === page);
    if (b.dataset.page === page) b.setAttribute("aria-current", "page"); else b.removeAttribute("aria-current");
  });
  $("breadcrumb").textContent = {analyze: "텍스트 분석", image: "이미지 OCR", lexicon: "은어 사전", discovery: "새 후보 발굴"}[page];
  if (page === "lexicon") refreshLexicon().catch(e => toast(e.message, true));
  if (page === "discovery") refreshCandidates().catch(e => toast(e.message, true));
}
document.querySelectorAll("[data-page]").forEach(button => button.addEventListener("click", () => setPage(button.dataset.page)));
function updateCount() { $("char-count").textContent = Array.from($("input-text").value).length.toLocaleString(); }
$("input-text").addEventListener("input", updateCount);
$("threshold").addEventListener("input", () => { $("threshold-value").textContent = $("threshold").value; });
document.querySelectorAll("[data-sample]").forEach(button => button.addEventListener("click", () => {
  $("input-text").value = samples[button.dataset.sample]; updateCount(); $("input-text").focus();
}));
$("clear").addEventListener("click", () => { $("input-text").value = ""; updateCount(); $("input-text").focus(); });
$("text-file").addEventListener("change", async () => {
  const file = $("text-file").files[0]; if (!file) return;
  try {
    if (file.size > 200000) throw new Error("TXT 파일은 200KB 이하로 선택하세요.");
    const text = await file.text();
    if (Array.from(text).length > 20000) throw new Error("분석할 텍스트는 20,000자 이하로 입력하세요.");
    if (text.includes("\ufffd")) throw new Error("파일을 UTF-8 인코딩으로 저장한 뒤 다시 불러오세요.");
    $("input-text").value = text; updateCount(); toast("텍스트를 불러왔습니다.");
  } catch (error) { toast(error.message, true); }
  finally { $("text-file").value = ""; }
});
function renderResult(data) {
  lastResult = data;
  $("result-empty").hidden = true; $("result-content").hidden = false; $("export-result").hidden = false;
  $("result-caption").textContent = `사전 v${data.dictionary_version} · ${data.summary.total}개 표현${data.signals?.length ? ` · ${data.signals.length}개 문맥 단서` : ""}`;
  $("stat-total").textContent = data.summary.total;
  $("stat-known").textContent = data.summary.dictionary + (data.summary.patterns || 0) + (data.summary.watchlist_matches || 0);
  $("stat-candidates").textContent = data.summary.candidates;
  $("stat-time").replaceChildren(document.createTextNode(data.elapsed_ms), element("small", "", " ms"));
  $("result-notice").textContent = data.notice;
  const highlighted = $("highlighted-text"); highlighted.replaceChildren();
  // API의 Unicode 문자 위치를 유지하도록 UTF-16 단위 대신 코드 포인트로 나눕니다.
  const chars = Array.from(data.text); let cursor = 0;
  data.matches.forEach(item => {
    highlighted.append(document.createTextNode(chars.slice(cursor, item.start).join("")));
    const mark = element("mark", candidateMethods.has(item.method) ? "candidate" : "", item.surface);
    mark.title = `${methods[item.method]} · ${item.canonical}`; highlighted.append(mark); cursor = item.end;
  });
  highlighted.append(document.createTextNode(chars.slice(cursor).join("")));
  const list = $("match-list"); list.replaceChildren();
  if (!data.matches.length) {
    const empty = element("div", "empty-state");
    empty.append(element("h3", "", data.normalizations?.length ? "늘임 복원 후보가 있습니다. 의미는 문맥으로 확인하세요." : "현재 사전과 규칙에 일치하는 표현이 없습니다."), element("p", "", "탐지되지 않았다는 결과가 안전성이나 은어 부재를 보장하지는 않습니다.")); list.append(empty);
  }
  data.matches.slice(0, 150).forEach((item, index) => {
    const card = element("article", "match-card");
    const heading = element("div", "match-heading");
    const candidate = candidateMethods.has(item.method);
    heading.append(element("strong", "", item.surface), element("span", `method-badge${candidate ? " candidate" : ""}`, methods[item.method]));
    const score = element("span", "score"); score.append(element("b", "", item.score), document.createTextNode(" / 100 근거 강도")); heading.append(score);
    const expansion = element("div", "expansion-line");
    const originals = item.alternatives?.length > 1 ? item.alternatives.join(" / ") : item.expansion;
    expansion.append(element("span", "", "추정 원형"), element("strong", "", originals || "아직 확인되지 않음"));
    const canonical = element("p", "canonical", `의미 / 분류 · ${item.canonical}`);
    const reasons = element("ul", "reasons"); item.reasons.forEach(reason => reasons.append(element("li", "", reason)));
    const context = element("div", "context-chips"); item.context.forEach(c => context.append(element("span", "", `${c.group} · ${c.words.join(", ")}`)));
    card.append(heading, expansion, canonical, reasons, context, element("p", "match-note", `${item.note} · 원문 ${item.start + 1}–${item.end}자`));
    if (item.provenance?.length) card.append(sourceLinks(item.provenance));
    if (candidate) {
      const button = element("button", "secondary-button", "이 표현 사전 등록 검토 ↗");
      button.addEventListener("click", () => prepareEntry(item.term.replace(/[^가-힣ㄱ-ㅎㅏ-ㅣa-zA-Z0-9]/g, ""), item.method === "jamo" ? item.canonical : ""));
      card.append(button);
    }
    card.id = `match-${index}`; list.append(card);
  });
  if (data.matches.length > 150) list.append(element("p", "muted", "화면에는 앞 150개를 표시합니다. 전체 결과는 JSON으로 내보낼 수 있습니다."));
  $("normalized-text").textContent = data.normalized;
  $("tokens").replaceChildren(...data.tokens.slice(0, 250).map(t => element("span", "", `${t.surface} → ${t.canonical} / ${t.tag}`)));
  let signals = $("context-signals");
  if (!signals) { signals = element("section", "panel context-signals"); signals.id = "context-signals"; $("match-list").before(signals); }
  signals.replaceChildren(); signals.hidden = !data.signals?.length;
  if (data.signals?.length) {
    signals.append(element("h3", "", "문맥 단서 · 은어와 구분"));
    data.signals.forEach(signal => {
      const row = element("div", "signal-row");
      row.append(element("strong", "", signal.surface), element("p", "", signal.explanation), element("small", "", signal.note)); signals.append(row);
    });
  }
  contextPanel().hidden = true;
  renderNormalizations(data);
  renderWatchlist(data);
}
function renderNormalizations(data) {
  let panel = $("normalization-results");
  if (!panel) { panel = element("section", "panel watchlist-panel normalization-panel"); panel.id = "normalization-results"; $("match-list").before(panel); }
  panel.replaceChildren(); panel.hidden = !data.normalizations?.length;
  if (panel.hidden) return;
  panel.append(element("h2", "", `늘임·반복 복원 후보 · ${data.normalizations.length}개`), element("p", "muted", "등록된 표현과 맞는 반복 표기만 복원합니다. 일반적인 말 늘임일 수 있으며, 복원 자체가 성적 의미나 우회 의도의 판정은 아닙니다."));
  data.normalizations.slice(0, 100).forEach(item => {
    const row = element("article", "watchlist-row");
    row.append(element("strong", "", item.surface), element("p", "", `복원 후보 → ${item.restored}`), element("small", "", `원문 ${item.start + 1}–${item.end}자 · 문맥과 함께 확인`));
    panel.append(row);
  });
  if (data.normalizations.length > 100) panel.append(element("p", "muted", "앞 100개를 표시합니다. 전체 복원 위치는 JSON으로 확인할 수 있습니다."));
}
function watchlistRow(hit) {
  const row = element("article", "watchlist-row");
  const title = element("div", "context-chips");
  title.append(element("strong", "", hit.surface || hit.keyword), element("span", "", hit.type), element("span", "", evidenceLabels[hit.evidence]));
  if (!hit.surface) title.append(element("span", "", hit.status));
  if (hit.assessment) title.append(element("span", "", assessmentLabels[hit.assessment]));
  row.append(title, element("p", "", hit.meaning));
  if (hit.candidates?.length > 1) row.append(element("p", "muted", `다른 원형 후보: ${hit.candidates.slice(1).map(c => `${c.expansion} (${evidenceLabels[c.evidence]})`).join(" / ")}`));
  row.append(element("small", "", `${hit.group_label || ""} · ${hit.note}`));
  if (hit.definition_sources?.length) row.append(sourceLinks([...new Map(hit.definition_sources.map(s => [s.id, s])).values()]));
  return row;
}
function renderWatchlist(data) {
  let panel = $("watchlist-results");
  if (!panel) { panel = element("section", "panel watchlist-panel"); panel.id = "watchlist-results"; $("match-list").before(panel); }
  panel.replaceChildren(); panel.hidden = !data.watchlist_hits?.length;
  if (panel.hidden) return;
  panel.append(element("h2", "", `문맥 목록 대조 · ${data.watchlist_hits.length}개 위치`), element("p", "muted", "일반 단서·추정 풀이·원형 미확인을 구분합니다. 목록 일치 자체는 성착취 판정이 아닙니다."));
  (data.watchlist_contexts || []).slice(0, 30).forEach(context => {
    const row = element("div", "watchlist-context");
    row.append(element("strong", "", context.explanation), element("p", "clause", context.clause), element("small", "", context.note)); panel.append(row);
  });
  if (data.watchlist_contexts?.length > 30) panel.append(element("p", "muted", "문맥 조합은 앞 30개를 표시합니다. 전체는 JSON에서 확인하세요."));
  const details = element("details", "watchlist-hits"); details.open = data.watchlist_hits.length <= 15;
  details.append(element("summary", "", "목록 일치 표현과 풀이 보기"));
  data.watchlist_hits.slice(0, 100).forEach(hit => details.append(watchlistRow(hit)));
  if (data.watchlist_hits.length > 100) details.append(element("p", "muted", "표현은 앞 100개를 표시합니다. 전체 위치·근거는 JSON으로 내보낼 수 있습니다."));
  panel.append(details);
}
function contextPanel() {
  let panel = $("context-interpretation");
  if (!panel) { panel = element("section", "context-interpretation"); panel.id = "context-interpretation"; $("match-list").before(panel); }
  return panel;
}
function renderInterpretation(data) {
  lastResult.interpretation = data;
  const panel = contextPanel(); panel.hidden = false; panel.replaceChildren();
  panel.append(element("h2", "", "문장 속 의미 비교"), element("p", "result-notice", data.notice || data.message));
  if (data.status !== "ok") { panel.append(element("p", "muted", data.message)); return; }
  panel.append(element("p", "muted", `로컬 ${data.model} · ${(data.elapsed_ms || 0).toLocaleString()}ms · 자료 기반 후보와 모델 가설을 구분합니다.`));
  if (!data.items.length) panel.append(element("p", "muted", "추가로 해석할 은어 후보가 없습니다."));
  data.items.forEach(item => {
    const card = element("article", "match-card interpretation-card");
    card.append(element("strong", "", item.surface), element("p", "clause", item.clause));
    if (!item.choices.length) card.append(element("p", "unresolved", "원형 미확인 · 추가 문맥이나 자료가 필요합니다."));
    if (item.reference_candidates?.length) {
      card.append(element("p", "canonical", `비교할 원형 후보: ${item.reference_candidates.map(c => `${c.expansion}${c.evidence ? ` (${evidenceLabels[c.evidence]})` : ""}`).join(" / ")}`));
      const refs = item.reference_candidates.flatMap(c => c.sources || []);
      if (refs.length) card.append(sourceLinks([...new Map(refs.map(s => [s.id, s])).values()].map(s => ({...s, license: "후보 용례"}))));
    }
    item.choices.forEach(choice => {
      const row = element("div", "interpretation-choice");
      row.append(element("strong", "", `${item.status === "ordinary" ? "일반 용례 해석" : "가능한 해석"} → ${choice.expansion}`), element("span", "method-badge candidate", choice.grounding === "context_rule" ? "일상 문맥 규칙 · 원형 후보" : choice.grounding === "documented_candidate" ? "자료에 있는 후보 · 적용은 추정" : "모델 가설 · 자료 미확인"), element("p", "", choice.rationale));
      if (choice.support) row.append(element("small", "", `주변 단서: ${choice.support}`));
      if (choice.sources?.length) row.append(sourceLinks(choice.sources.map(s => ({...s, license: "용례 참고"}))));
      if (/^[가-힣ㄱ-ㅎㅏ-ㅣa-zA-Z0-9]{2,30}$/.test(item.surface)) {
        const review = element("button", "secondary-button", "이 원형 사전 등록 검토 ↗");
        review.addEventListener("click", () => prepareEntry(item.surface, "문맥 검토 후 등록", choice.expansion));
        row.append(review);
      }
      card.append(row);
    });
    panel.append(card);
  });
}
$("analyze-button").addEventListener("click", () => busy($("analyze-button"), async () => {
  if (!$("input-text").value.trim()) { $("input-text").focus(); throw new Error("분석할 텍스트를 입력하세요."); }
  const data = await api("/api/analyze", {method: "POST", body: JSON.stringify({text: $("input-text").value, threshold: Number($("threshold").value), discover: $("discover-toggle").checked})});
  renderResult(data); $("results").scrollIntoView({behavior: "smooth", block: "start"});
  if ($("deep-toggle").checked) {
    const panel = contextPanel(); panel.hidden = false; panel.replaceChildren(element("h2", "", "문장 속 의미 비교"), element("p", "result-notice", "로컬 모델이 문맥과 가능한 원형을 비교하고 있습니다. 첫 실행은 모델 준비 시간이 필요합니다."));
    if (Array.from(data.text).length > 6000) { renderInterpretation({status: "too_long", message: "문맥 모델은 6,000자까지 지원합니다. 빠른 분석 결과는 유지됩니다."}); return; }
    try { renderInterpretation(await api("/api/context/interpret", {method: "POST", body: JSON.stringify({text: data.text, threshold: Number($("threshold").value), discover: $("discover-toggle").checked})})); }
    catch (error) { renderInterpretation({status: "failed", message: `${error.message} 빠른 분석 결과는 유지됩니다.`}); }
  }
}, "분석 중…"));
$("input-text").addEventListener("keydown", event => { if ((event.ctrlKey || event.metaKey) && event.key === "Enter") { event.preventDefault(); $("analyze-button").click(); } });
$("export-result").addEventListener("click", () => { if (lastResult) download("slang-analysis.json", lastResult); });
async function refreshLexicon() {
  const [data, dataset, watchlist] = await Promise.all([api("/api/lexicon"), api("/api/dataset"), api("/api/watchlist")]); entries = data.entries;
  $("nav-count").textContent = entries.length; $("entry-count").textContent = `${entries.length}개`; renderLexicon();
  $("dataset-info").replaceChildren(element("strong", "", `활성 표현 ${dataset.active_entries.toLocaleString()}개 · 초성 대조 ${dataset.initial_forms.toLocaleString()}종`), element("p", "", `공개 수집 묶음 ${dataset.entries}개 · 출처 ${dataset.sources.length}곳 · 수집일 ${dataset.collected_at.slice(0, 10)}`), element("p", "muted", "성적 표현·신체 비속표현과 성착취 관련 표현을 구분합니다. 자동 초성은 수집어 개수에 합산하지 않습니다."), sourceLinks(dataset.sources));
  renderWatchlistCatalog(watchlist);
}
function renderWatchlistCatalog(data) {
  let panel = $("watchlist-catalog");
  if (!panel) { panel = element("details", "panel watchlist-panel"); panel.id = "watchlist-catalog"; $("dataset-info").after(panel); }
  panel.replaceChildren(element("summary", "", `문맥 검토 목록 · 활성 ${data.active} / 전체 ${data.total}개`), element("p", "muted", data.notice));
  const label = element("label", "watchlist-search", "문맥 목록 검색 ");
  const search = element("input"); search.type = "search"; search.id = "watchlist-search"; search.placeholder = "키워드·뜻·타입 검색"; label.append(search);
  const count = element("p", "muted"); count.id = "watchlist-count";
  const rows = element("div"); rows.id = "watchlist-catalog-rows";
  const more = element("button", "secondary-button", "다음 50개 더 보기"); more.type = "button";
  let limit = 50;
  function draw() {
    const value = search.value.toLowerCase();
    const filtered = data.entries.filter(e => `${e.keyword} ${e.meaning} ${e.type}`.toLowerCase().includes(value));
    rows.replaceChildren(...filtered.slice(0, limit).map(entry => watchlistRow({...entry, group_label: data.group_labels[entry.group]})));
    count.textContent = `${filtered.length}개 중 ${Math.min(limit, filtered.length)}개 표시 · 원본 타입·행 상태 유지`;
    more.hidden = filtered.length <= limit;
  }
  search.addEventListener("input", () => { limit = 50; draw(); });
  more.addEventListener("click", () => { limit += 50; draw(); });
  panel.append(label, count, rows, more, sourceLinks(data.sources)); draw();
}
function renderLexicon() {
  const filter = $("lexicon-search").value.toLowerCase(); const list = $("lexicon-list"); list.replaceChildren();
  const filtered = entries.filter(e => `${e.alias} ${e.expansion} ${e.canonical}`.toLowerCase().includes(filter));
  const pages = Math.max(1, Math.ceil(filtered.length / 50)); lexiconPage = Math.min(lexiconPage, pages - 1);
  filtered.slice(lexiconPage * 50, (lexiconPage + 1) * 50).forEach(entry => {
    const row = element("div", "lexicon-row"); const info = element("div", "lexicon-info"); const title = element("div");
    title.append(element("strong", "", entry.alias), element("span", "source-badge", {starter: "기본 시드", corpus: "공개 수집", user: "사용자 등록"}[entry.source] || entry.source));
    info.append(title, element("p", "lexicon-expansion", `추정 원형 → ${entry.expansion}`), element("p", "", entry.canonical), element("small", "", `${entry.category} · ${entry.note}`));
    if (entry.provenance?.length) info.append(sourceLinks(entry.provenance));
    const button = element("button", "delete-button", "삭제"); button.setAttribute("aria-label", `${entry.alias} 사전에서 삭제`);
    button.addEventListener("click", () => {
      if (!confirm(`'${entry.alias}' 항목을 사전에서 삭제할까요?`)) return;
      busy(button, async () => { await api(`/api/lexicon/${entry.id}`, {method: "DELETE"}); await refreshLexicon(); toast("사전 항목을 삭제했습니다."); }, "삭제 중…");
    });
    row.append(info, button); list.append(row);
  });
  if (!filtered.length) list.append(element("div", "empty-state", "일치하는 사전 항목이 없습니다."));
  if (pages > 1) {
    const pagination = element("div", "pagination");
    const previous = element("button", "secondary-button", "← 이전"); previous.disabled = lexiconPage === 0;
    previous.addEventListener("click", () => { lexiconPage--; renderLexicon(); });
    const next = element("button", "secondary-button", "다음 →"); next.disabled = lexiconPage === pages - 1;
    next.addEventListener("click", () => { lexiconPage++; renderLexicon(); });
    pagination.append(previous, element("span", "muted", `${lexiconPage + 1} / ${pages} · 검색 결과 ${filtered.length}개`), next); list.append(pagination);
  }
}
$("lexicon-search").addEventListener("input", () => { lexiconPage = 0; renderLexicon(); });
$("entry-form").addEventListener("submit", event => {
  event.preventDefault(); const button = event.submitter;
  busy(button, async () => {
    await api("/api/lexicon", {method: "POST", body: JSON.stringify({alias: $("entry-alias").value.trim(), expansion: $("entry-expansion").value.trim(), canonical: $("entry-canonical").value.trim(), category: $("entry-category").value.trim(), note: $("entry-note").value.trim() || "사용자가 등록한 검토용 표현", needs_context: $("entry-context").checked})});
    $("entry-form").reset(); await refreshLexicon(); toast("사전에 등록했습니다. 다음 분석부터 적용됩니다.");
  }, "등록 중…");
});
$("export-lexicon").addEventListener("click", () => download("slang-lexicon.json", entries));
function prepareEntry(term, canonical = "", expansion = "") {
  setPage("lexicon"); $("entry-alias").value = term; $("entry-canonical").value = canonical;
  $("entry-expansion").value = expansion;
  $("entry-note").value = "자동 발굴 후보에서 검토 후 등록"; $("entry-context").checked = true;
  $("entry-canonical").focus(); window.scrollTo({top: 0, behavior: "smooth"});
}
async function refreshCandidates() {
  const data = await api("/api/candidates"); const list = $("candidate-list"); list.replaceChildren();
  data.candidates.forEach(item => {
    const row = element("div", "lexicon-row"); const info = element("div", "lexicon-info");
    info.append(element("strong", "", item.term), element("p", "", `배치 내 ${item.document_count}개 문서 · ${item.trigger_groups}`), element("small", "", "문맥 기반 검토 후보 · 의미 미확인"));
    const actions = element("div", "candidate-actions"); const approve = element("button", "secondary-button", "등록 검토 ↗");
    approve.addEventListener("click", () => prepareEntry(item.term));
    const dismiss = element("button", "delete-button", "제외");
    dismiss.addEventListener("click", () => busy(dismiss, async () => { await api(`/api/candidates/${item.id}`, {method: "DELETE"}); await refreshCandidates(); toast("검토 대기에서 제외했습니다."); }, "처리 중…"));
    actions.append(approve, dismiss); row.append(info, actions); list.append(row);
  });
  if (!data.candidates.length) list.append(element("div", "empty-state", "검토 대기 중인 후보가 없습니다. 문서 묶음에서 새 표현을 찾아보세요."));
}
$("discover-button").addEventListener("click", () => busy($("discover-button"), async () => {
  const texts = $("batch-text").value.split(/\r?\n/).map(t => t.trim()).filter(Boolean);
  if (texts.length < 2) throw new Error("줄바꿈으로 구분한 서로 다른 문서 2개 이상을 입력하세요.");
  const data = await api("/api/discover", {method: "POST", body: JSON.stringify({texts, min_count: Number($("min-count").value)})});
  await refreshCandidates(); $("discovery-caption").textContent = `${data.documents}개 문서 분석 · ${data.candidates.length}개 후보`; toast(data.notice);
}, "문서 분석 중…"));
async function initialize() {
  try {
    const health = await api("/api/health");
    $("engine-status").replaceChildren(document.createTextNode("Kiwi 분석기 준비됨"), element("small", "", "로컬에서 처리 · 외부 전송 없음"));
    $("status-dot").classList.add("ready"); $("nav-count").textContent = health.entries;
    try {
      const model = await api("/api/context/info");
      $("deep-toggle").checked = model.available;
      $("deep-status").textContent = model.available ? `로컬 ${model.model} 연결됨 · 최대 6,000자` : model.message;
    } catch { $("deep-toggle").checked = false; $("deep-status").textContent = "로컬 모델 연결을 확인하세요. 빠른 분석은 계속 사용할 수 있습니다."; }
  } catch (error) {
    $("engine-status").replaceChildren(document.createTextNode("분석기 연결 확인 필요"), element("small", "", "잠시 후 페이지를 새로고침하세요.")); toast(error.message, true);
  }
}
initialize();
