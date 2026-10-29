"use strict";
(() => {
  const page = element("section", "page"); page.id = "page-image"; page.hidden = true;
  // Constant UI markup only. OCR strings and filenames are always rendered with textContent.
  page.innerHTML = `
    <div class="page-heading"><div><div class="eyebrow">READ THE IMAGE</div><h1>이미지 속 표현을 찾다<span>.</span></h1><p>이미지의 글자를 읽고 검토할 은어가 포함된 단어에 빨간 표식을 붙입니다.</p></div></div>
    <section class="panel ocr-input-panel"><h2>이미지 불러오기</h2>
      <div id="ocr-dropzone" class="ocr-dropzone" tabindex="0" role="button" aria-label="분석할 이미지 선택 또는 붙여넣기">이미지를 여기에 놓거나, 이 영역을 선택한 뒤 Ctrl+V로 붙여넣으세요.<small>PNG · JPEG · WebP / 최대 10MB · 1,600만 픽셀</small></div>
      <input id="ocr-file" type="file" accept="image/png,image/jpeg,image/webp" hidden>
      <div class="ocr-toolbar"><button id="ocr-choose" class="secondary-button">이미지 선택</button><span id="ocr-filename" class="muted">선택한 이미지 없음</span>
      <label>인식 크기 <select id="ocr-layout"><option value="11">기본</option><option value="6">작은 글씨·정밀</option></select></label>
      <button id="ocr-run" class="primary-button" disabled>OCR 및 은어 분석 ↗</button><button id="ocr-clear" class="text-button" disabled>이미지 지우기</button></div>
      <p id="ocr-status" class="muted" role="status">OCR 엔진 확인 중…</p><p class="small muted">이미지와 인식 원문은 서버 파일·DB에 저장하지 않습니다. 한글 초성·작은 글씨는 오인식될 수 있습니다.</p>
    </section>
    <section id="ocr-preview-panel" class="panel ocr-preview-panel" hidden><div class="panel-title"><h2>이미지에서 확인 <span id="ocr-count" class="muted"></span></h2><label><input id="ocr-show-marks" type="checkbox" checked> 빨간 표식 표시</label></div>
      <div class="ocr-image-scroll"><div id="ocr-stage" class="ocr-stage"><img id="ocr-preview" alt="분석할 이미지"><svg id="ocr-overlay" xmlns="http://www.w3.org/2000/svg" aria-label="은어 검토 표식"></svg></div></div>
      <p class="ocr-caption">표식이나 아래 키워드를 선택하면 같은 위치를 강조합니다. 상자는 인식된 단어 전체를 표시합니다.</p>
    </section>
    <section id="ocr-result-panel" hidden aria-live="polite"><p id="ocr-notice" class="result-notice"></p>
      <div class="ocr-toolbar"><button id="ocr-save-image" class="secondary-button">↓ 표식 이미지 PNG 저장</button><button id="ocr-save-json" class="secondary-button">↓ OCR 결과 JSON</button><button id="ocr-to-text" class="secondary-button">텍스트 화면에서 문맥 비교 ↗</button></div>
      <div id="ocr-regions" class="ocr-regions"></div>
      <details class="panel ocr-correction"><summary>OCR 글자 확인·수정</summary><p class="muted">원문과 다른 단어를 고친 뒤 다시 분석하세요. 원래 단어 상자에 수정한 표현을 대조합니다. 비운 단어는 제외합니다.</p><pre id="ocr-text"></pre><div id="ocr-word-editors" class="ocr-word-editors"></div><button id="ocr-more-words" class="secondary-button" hidden>단어 100개 더 보기</button><button id="ocr-reanalyze" class="primary-button">수정한 글자로 다시 분석</button></details>
    </section>`;
  document.querySelector("footer").before(page);
  let file = null, result = null, pending = false, ready = false, dirty = false, visibleWords = 100;
  const preview = $("ocr-preview"), overlay = $("ocr-overlay");
  const svgElement = (tag, attrs) => {
    const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
    Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, value)); return node;
  };
  function setPending(value) {
    pending = value;
    ["ocr-run", "ocr-choose", "ocr-clear", "ocr-layout", "ocr-reanalyze", "ocr-to-text", "ocr-save-image", "ocr-save-json"].forEach(id => { $(id).disabled = value; });
    $("ocr-run").disabled = value || !ready || !file;
    $("ocr-clear").disabled = value || !file;
    $("ocr-word-editors").querySelectorAll("input").forEach(input => { input.disabled = value; });
    $("ocr-run").textContent = value ? "글자를 읽고 있습니다…" : "OCR 및 은어 분석 ↗";
  }
  function clearResult() {
    result = null; dirty = false; overlay.replaceChildren(); $("ocr-result-panel").hidden = true; $("ocr-count").textContent = "";
  }
  async function chooseImage(selected) {
    if (pending) { toast("현재 이미지 분석이 끝난 뒤 변경하세요."); return; }
    if (!selected) return;
    if (!selected.size || selected.size > 10 * 1024 * 1024) { toast("이미지는 비어 있지 않은 10MB 이하 파일로 선택하세요.", true); return; }
    if (!["image/png", "image/jpeg", "image/webp"].includes(selected.type)) { toast("PNG·JPEG·WebP 이미지를 선택하세요.", true); return; }
    file = null; clearResult(); setPending(true); $("ocr-status").textContent = "이미지를 불러오고 있습니다…";
    const dataURL = await new Promise((resolve, reject) => { const r = new FileReader(); r.onload = () => resolve(r.result); r.onerror = () => reject(new Error("이미지를 읽지 못했습니다.")); r.readAsDataURL(selected); });
    await new Promise((resolve, reject) => { preview.onload = resolve; preview.onerror = () => reject(new Error("이미지 미리보기를 읽지 못했습니다.")); preview.src = dataURL; });
    if (preview.naturalWidth * preview.naturalHeight > 16000000 || Math.max(preview.naturalWidth, preview.naturalHeight) > 16000) {
      preview.removeAttribute("src"); throw new Error("이미지는 1,600만 픽셀, 한 변 16,000px 이하로 선택하세요.");
    }
    file = selected; visibleWords = 100; clearResult(); $("ocr-filename").textContent = selected.name || "붙여넣은 이미지";
    $("ocr-preview-panel").hidden = false; $("ocr-status").textContent = "이미지를 확인한 뒤 OCR 및 은어 분석을 누르세요.";
    setPending(false);
  }
  const handleImage = selected => chooseImage(selected).catch(error => { file = null; clearResult(); preview.removeAttribute("src"); $("ocr-preview-panel").hidden = true; $("ocr-filename").textContent = "선택한 이미지 없음"; setPending(false); toast(error.message, true); });
  $("ocr-choose").addEventListener("click", () => $("ocr-file").click());
  $("ocr-file").addEventListener("change", () => { handleImage($("ocr-file").files[0]); $("ocr-file").value = ""; });
  const zone = $("ocr-dropzone");
  zone.addEventListener("click", () => { if (!pending) $("ocr-file").click(); });
  zone.addEventListener("keydown", event => { if (["Enter", " "].includes(event.key)) { event.preventDefault(); if (!pending) $("ocr-file").click(); } });
  zone.addEventListener("dragover", event => { event.preventDefault(); zone.classList.add("dragging"); });
  zone.addEventListener("dragleave", () => zone.classList.remove("dragging"));
  zone.addEventListener("drop", event => { event.preventDefault(); zone.classList.remove("dragging"); handleImage(event.dataTransfer.files[0]); });
  page.addEventListener("paste", event => {
    const item = Array.from(event.clipboardData?.items || []).find(i => i.kind === "file" && i.type.startsWith("image/"));
    if (item) { event.preventDefault(); handleImage(item.getAsFile()); }
  });
  $("ocr-clear").addEventListener("click", () => {
    file = null; clearResult(); preview.removeAttribute("src"); $("ocr-preview-panel").hidden = true;
    $("ocr-filename").textContent = "선택한 이미지 없음"; $("ocr-status").textContent = "이미지를 선택하세요."; setPending(false);
  });
  function selectRegion(id) {
    overlay.querySelectorAll("[data-region]").forEach(node => node.classList.toggle("selected", Number(node.dataset.region) === id));
    $("ocr-regions").querySelectorAll("button").forEach(node => { node.classList.toggle("selected", Number(node.dataset.region) === id); node.setAttribute("aria-pressed", String(Number(node.dataset.region) === id)); });
    const region = result?.regions.find(r => r.id === id);
    if (region) { const first = overlay.querySelector(`[data-region="${id}"]`); first?.scrollIntoView({block: "nearest", behavior: "smooth"}); }
  }
  function renderMarks() {
    overlay.replaceChildren();
    if (!result || dirty) return;
    overlay.setAttribute("viewBox", `0 0 ${result.image_width} ${result.image_height}`);
    result.regions.forEach(region => region.boxes.forEach(box => {
      const group = svgElement("g", {"data-region": region.id});
      const rect = svgElement("rect", {x: box.x, y: box.y, width: box.width, height: box.height, rx: 2, tabindex: 0, role: "button", "aria-label": `${region.id + 1}. ${region.surface} · ${region.expansion || "원형 미확인"}`});
      const title = svgElement("title", {}); title.textContent = `${region.surface} → ${region.expansion || "원형 미확인"}`; rect.append(title);
      rect.addEventListener("click", () => selectRegion(region.id));
      rect.addEventListener("keydown", event => { if (["Enter", " "].includes(event.key)) { event.preventDefault(); selectRegion(region.id); } });
      group.append(rect); overlay.append(group);
    }));
    overlay.toggleAttribute("hidden", !$("ocr-show-marks").checked);
  }
  function renderEditors() {
    const list = $("ocr-word-editors"); list.replaceChildren();
    result.words.slice(0, visibleWords).forEach((word, index) => {
      const label = element("label", "", `${index + 1} · 인식 ${word.confidence.toFixed(0)}`);
      const input = element("input"); input.value = word.text; input.maxLength = 100; input.dataset.wordId = index; input.setAttribute("aria-label", `OCR 단어 ${index + 1} 수정`);
      input.addEventListener("input", () => {
        word.text = input.value; dirty = true; overlay.replaceChildren(); $("ocr-regions").replaceChildren();
        $("ocr-count").textContent = "수정 후 재분석 필요"; $("ocr-status").textContent = "수정한 글자로 다시 분석을 눌러 표식을 갱신하세요.";
        $("ocr-save-image").disabled = true; $("ocr-save-json").disabled = true; $("ocr-to-text").disabled = true;
      });
      label.append(input); list.append(label);
    });
    $("ocr-more-words").hidden = result.words.length <= visibleWords;
  }
  function render(data) {
    result = data; dirty = false;
    if (preview.naturalWidth !== data.image_width || preview.naturalHeight !== data.image_height) throw new Error("이미지 방향과 OCR 좌표가 다릅니다. PNG로 저장한 뒤 다시 선택하세요.");
    $("ocr-result-panel").hidden = false; $("ocr-count").textContent = `· ${data.regions.length}개 검토 표현`;
    $("ocr-notice").textContent = data.notice;
    $("ocr-text").textContent = data.text || "인식된 글자가 없습니다.";
    $("ocr-status").textContent = `${data.message || "수정된 글자의 표식을 갱신했습니다."}${data.ocr_elapsed_ms ? ` · ${(data.ocr_elapsed_ms / 1000).toFixed(2)}초` : ""}`;
    const list = $("ocr-regions"); list.replaceChildren();
    if (!data.regions.length) list.append(element("p", "result-notice", data.words.length ? "현재 OCR 텍스트에서 표시할 검토 표현이 없습니다. 원문의 글자가 정확히 인식됐는지 확인하세요." : "글자를 인식하지 못했습니다. 더 선명한 이미지나 다른 글 배치를 시도하세요."));
    data.regions.slice(0, 200).forEach(region => {
      const button = element("button", "ocr-keyword"); button.type = "button"; button.dataset.region = region.id; button.setAttribute("aria-pressed", "false");
      button.append(element("strong", "", `${region.id + 1}. ${region.surface}`), element("span", "", `추정 원형 · ${region.alternatives?.length > 1 ? region.alternatives.join(" / ") : region.expansion || "미확인"}`), element("small", "", `${region.category} · OCR 인식 점수 ${region.confidence} / 100`));
      button.addEventListener("click", () => selectRegion(region.id)); list.append(button);
    });
    if (data.regions.length > 200) list.append(element("p", "muted", "목록은 앞 200개를 표시합니다. 전체 위치는 이미지 표식과 JSON에 포함됩니다."));
    renderMarks(); renderEditors();
  }
  $("ocr-run").addEventListener("click", async () => {
    if (!file || pending) return;
    clearResult(); setPending(true); $("ocr-status").textContent = "로컬에서 글자를 읽고 문맥을 대조하고 있습니다…";
    try {
      const query = new URLSearchParams({layout: $("ocr-layout").value, threshold: $("threshold").value, discover: $("discover-toggle").checked});
      render(await api(`/api/ocr/analyze?${query}`, {method: "POST", headers: {"Content-Type": file.type}, body: file}));
    } catch (error) { clearResult(); $("ocr-status").textContent = error.message; toast(error.message, true); }
    finally { setPending(false); }
  });
  $("ocr-reanalyze").addEventListener("click", async () => {
    if (!result || pending) return;
    setPending(true);
    try { render(await api("/api/ocr/reanalyze", {method: "POST", body: JSON.stringify({image_width: result.image_width, image_height: result.image_height, words: result.words, threshold: Number($("threshold").value), discover: $("discover-toggle").checked})})); }
    catch (error) { toast(error.message, true); }
    finally { setPending(false); if (dirty) { $("ocr-save-image").disabled = true; $("ocr-save-json").disabled = true; $("ocr-to-text").disabled = true; } }
  });
  $("ocr-more-words").addEventListener("click", () => { visibleWords += 100; renderEditors(); });
  $("ocr-show-marks").addEventListener("change", () => { overlay.toggleAttribute("hidden", !$("ocr-show-marks").checked); });
  $("ocr-save-json").addEventListener("click", () => { if (result && !dirty) download("slang-ocr-analysis.json", result); });
  $("ocr-to-text").addEventListener("click", () => { if (!result || dirty) return; $("input-text").value = result.text; updateCount(); setPage("analyze"); $("input-text").focus(); toast("OCR 글자를 옮겼습니다. 텍스트 분석으로 문맥을 비교하세요."); });
  $("ocr-save-image").addEventListener("click", () => {
    if (!result || dirty) return;
    const canvas = document.createElement("canvas"); canvas.width = result.image_width; canvas.height = result.image_height;
    const context = canvas.getContext("2d"); context.drawImage(preview, 0, 0, canvas.width, canvas.height);
    context.strokeStyle = "#dc2626"; context.fillStyle = "rgba(220,38,38,0.10)"; context.lineWidth = Math.max(2, canvas.width / 600);
    result.regions.forEach(region => region.boxes.forEach(box => { context.fillRect(box.x, box.y, box.width, box.height); context.strokeRect(box.x, box.y, box.width, box.height); }));
    canvas.toBlob(blob => { if (!blob) { toast("이미지를 저장하지 못했습니다.", true); return; } const url = URL.createObjectURL(blob); const link = element("a"); link.href = url; link.download = "slang-ocr-marked.png"; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); }, "image/png");
  });
  api("/api/ocr/info").then(info => { ready = info.available; $("ocr-status").textContent = info.message; setPending(false); }).catch(error => { $("ocr-status").textContent = error.message; });
})();
