const { chromium } = require("playwright");
const assert = require("node:assert/strict");
const path = require("node:path");
const fs = require("node:fs/promises");
(async () => {
  const browser = await chromium.launch({headless: true, executablePath: process.env.SLANG_CHROMIUM_PATH || undefined});
  const page = await browser.newPage({viewport: {width: 1440, height: 1000}});
  const errors = [];
  await page.addInitScript(() => {
    const original = window.fetch;
    window.fetch = async (...args) => {
      const response = await original(...args);
      if (String(args[0]).includes("/api/ocr/")) response.clone().json().then(data => { window.__ocrResponse = data; });
      return response;
    };
  });
  page.on("pageerror", e => errors.push(e.message));
  page.on("console", m => { if (m.type() === "error") errors.push(m.text()); });
  try {
    await page.goto(process.env.SLANG_UI_URL || "http://127.0.0.1:18640", {waitUntil: "networkidle"});
    await page.locator('[data-page="image"]').click();
    await page.waitForFunction(() => document.querySelector("#ocr-status").textContent.includes("준비됨"));
    await page.locator("#ocr-file").setInputFiles(path.resolve("artifacts/ocr-sample.png"));
    await page.waitForFunction(() => !document.querySelector("#ocr-run").disabled);
    const pending = page.waitForResponse(r => r.url().includes("/api/ocr/analyze"), {timeout: 60000});
    await page.locator("#ocr-run").click();
    const response = await pending;
    await page.waitForFunction(() => !document.querySelector("#ocr-run").disabled);
    await page.waitForFunction(() => Array.isArray(window.__ocrResponse?.regions));
    const data = await page.evaluate(() => window.__ocrResponse); assert.equal(response.status(), 200, JSON.stringify(data));
    assert(data.regions.some(r => r.surface.replace(/ /g, "").includes("몸사")));
    assert.equal(await page.locator("#ocr-overlay rect").count(), data.regions.reduce((n, r) => n + r.boxes.length, 0));
    assert.equal(await page.locator("#ocr-overlay rect").first().evaluate(el => getComputedStyle(el).stroke), "rgb(220, 38, 38)");
    assert((await page.locator("#ocr-regions").innerText()).includes("몸 사진"));
    await page.locator("#ocr-regions button").first().click();
    assert(await page.locator("#ocr-overlay .selected").count());
    await page.locator("#ocr-show-marks").uncheck(); assert(await page.locator("#ocr-overlay").isHidden());
    await page.locator("#ocr-show-marks").check(); assert(await page.locator("#ocr-overlay").isVisible());
    const download = page.waitForEvent("download"); await page.locator("#ocr-save-image").click();
    await (await download).saveAs(path.resolve("artifacts/ocr-marked.png"));
    assert((await fs.stat("artifacts/ocr-marked.png")).size > 1000);
    await page.screenshot({path: path.resolve("artifacts/ocr-desktop.png"), fullPage: true});
    for (const width of [768, 390]) {
      await page.setViewportSize({width, height: 844});
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
      const geometry = await page.locator("#ocr-stage").evaluate(el => {
        const img = el.querySelector("img").getBoundingClientRect(), svg = el.querySelector("svg").getBoundingClientRect();
        return {x: Math.abs(img.x - svg.x), y: Math.abs(img.y - svg.y), w: Math.abs(img.width - svg.width), h: Math.abs(img.height - svg.height)};
      });
      assert(Object.values(geometry).every(v => v < 1), JSON.stringify(geometry));
    }
    await page.screenshot({path: path.resolve("artifacts/ocr-mobile.png"), fullPage: true});
    await page.locator(".ocr-correction summary").click();
    await page.locator('#ocr-word-editors input[data-word-id="0"]').fill("ㅇㄹ");
    assert.equal(await page.locator("#ocr-overlay rect").count(), 0);
    assert(await page.locator("#ocr-save-image").isDisabled());
    const corrected = page.waitForResponse(r => r.url().endsWith("/api/ocr/reanalyze"));
    await page.locator("#ocr-reanalyze").click(); await corrected;
    await page.waitForFunction(() => !document.querySelector("#ocr-reanalyze").disabled);
    await page.waitForFunction(() => window.__ocrResponse?.text?.startsWith("ㅇㄹ"));
    const revised = await page.evaluate(() => window.__ocrResponse);
    const oral = revised.regions.find(r => r.surface === "ㅇㄹ");
    assert(oral && oral.expansion.includes("오랄"));
    assert.deepEqual(oral.boxes[0], {x: data.words[0].x, y: data.words[0].y, width: data.words[0].width, height: data.words[0].height});
    await page.locator("#ocr-to-text").click(); assert((await page.locator("#input-text").inputValue()).startsWith("ㅇㄹ"));
    await page.locator('[data-page="image"]').click();
    await page.locator("#ocr-file").setInputFiles(path.resolve("artifacts/ocr-neutral.png"));
    await page.waitForFunction(() => !document.querySelector("#ocr-run").disabled);
    assert.equal(await page.locator("#ocr-overlay rect").count(), 0);
    await page.locator("#ocr-run").click(); await page.waitForFunction(() => !document.querySelector("#ocr-run").disabled);
    assert.equal(await page.locator("#ocr-overlay rect").count(), 0);
    assert((await page.locator("#ocr-regions").innerText()).includes("표시할 검토 표현이 없습니다"));
    await page.locator("#ocr-file").setInputFiles(path.resolve("artifacts/ocr-oriented.jpg"));
    await page.waitForFunction(() => !document.querySelector("#ocr-run").disabled);
    await page.locator("#ocr-run").click(); await page.waitForFunction(() => !document.querySelector("#ocr-run").disabled);
    assert(!(await page.locator("#ocr-status").innerText()).includes("좌표가 다릅니다"));
    const encoded = (await fs.readFile("artifacts/ocr-sample.png")).toString("base64");
    for (const kind of ["drop", "paste"]) {
      await page.evaluate(({encoded, kind}) => {
        const bytes = Uint8Array.from(atob(encoded), char => char.charCodeAt(0));
        const transfer = new DataTransfer(); transfer.items.add(new File([bytes], `${kind}-sample.png`, {type: "image/png"}));
        const event = kind === "drop" ? new DragEvent("drop", {bubbles: true, cancelable: true, dataTransfer: transfer}) : new ClipboardEvent("paste", {bubbles: true, cancelable: true, clipboardData: transfer});
        document.querySelector("#ocr-dropzone").dispatchEvent(event);
      }, {encoded, kind});
      await page.waitForFunction(name => document.querySelector("#ocr-filename").textContent === name && !document.querySelector("#ocr-run").disabled, `${kind}-sample.png`);
    }
    await page.locator("#ocr-clear").click(); assert(await page.locator("#ocr-preview-panel").isHidden());
    assert.deepEqual(errors, []);
    console.log(JSON.stringify({status: "passed", regions: data.regions.length, words: data.words.length, elapsed_ms: data.ocr_elapsed_ms, checks: ["actual OCR", "red SVG coordinates", "PNG download", "responsive alignment", "manual initials correction", "neutral text", "EXIF orientation", "drop and paste", "clear image", "console"], errors}));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
