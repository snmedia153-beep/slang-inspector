const { chromium } = require("playwright");
const assert = require("node:assert/strict");
const path = require("node:path");

(async () => {
  const browser = await chromium.launch({headless: true, executablePath: process.env.SLANG_CHROMIUM_PATH || undefined});
  const page = await browser.newPage({viewport: {width: 1440, height: 1000}});
  await page.addInitScript(() => {
    const original = window.fetch;
    window.fetch = async (...args) => {
      const response = await original(...args);
      if (String(args[0]).includes("/api/ocr/")) await response.clone().json().then(data => { window.__ocrResponse = data; });
      return response;
    };
  });
  const errors = [];
  page.on("pageerror", error => errors.push(error.message));
  page.on("console", message => { if (message.type() === "error") errors.push(message.text()); });
  async function correct(values) {
    const inputs = page.locator("#ocr-word-editors input");
    for (let i = 0; i < await inputs.count(); i++) await inputs.nth(i).fill(values[i] || "");
    assert.equal(await page.locator("#ocr-overlay rect").count(), 0);
    const pending = page.waitForResponse(response => response.url().endsWith("/api/ocr/reanalyze"));
    await page.locator("#ocr-reanalyze").click();
    const response = await pending;
    assert.equal(response.status(), 200);
    await page.waitForFunction(() => !document.querySelector("#ocr-reanalyze").disabled);
    return page.evaluate(() => window.__ocrResponse);
  }
  try {
    await page.goto(process.env.SLANG_UI_URL || "http://127.0.0.1:18640", {waitUntil: "networkidle"});
    await page.locator('[data-page="image"]').click();
    await page.waitForFunction(() => document.querySelector("#ocr-status").textContent.includes("준비됨"));
    await page.locator("#ocr-file").setInputFiles(path.resolve("artifacts/ocr-sample.png"));
    await page.waitForFunction(() => !document.querySelector("#ocr-run").disabled);
    const pending = page.waitForResponse(response => response.url().includes("/api/ocr/analyze"));
    await page.locator("#ocr-run").click();
    const response = await pending;
    assert.equal(response.status(), 200);
    await page.waitForFunction(() => !document.querySelector("#ocr-run").disabled);
    const original = await page.evaluate(() => window.__ocrResponse);
    assert(original.words.length >= 3);
    await page.locator(".ocr-correction summary").click();
    let data = await correct(["ㅇㄹㄴ", "오줌ㄱㄲ", "사탕ㅈㅇ"]);
    assert.deepEqual(data.regions.map(region => region.surface), ["ㅇㄹㄴ", "ㄱㄲ", "ㅈㅇ"]);
    assert.equal(await page.locator("#ocr-overlay rect").count(), 3);
    for (let i = 0; i < 3; i++) {
      const word = original.words[i];
      assert.deepEqual(data.regions[i].boxes, [{x: word.x, y: word.y, width: word.width, height: word.height}]);
    }
    assert.equal(await page.locator("#ocr-overlay rect").first().evaluate(el => getComputedStyle(el).stroke), "rgb(220, 38, 38)");
    assert.equal(await page.locator("#ocr-regions button").filter({hasText: "원형 미확인"}).count(), 2);
    assert((await page.locator("#ocr-regions").innerText()).includes("지원"));
    await page.screenshot({path: path.resolve("artifacts/ocr-initials-desktop.png"), fullPage: true});
    for (const width of [768, 390]) {
      await page.setViewportSize({width, height: 844});
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
      const delta = await page.locator("#ocr-stage").evaluate(el => {
        const img = el.querySelector("img").getBoundingClientRect(), svg = el.querySelector("svg").getBoundingClientRect();
        return [Math.abs(img.x - svg.x), Math.abs(img.y - svg.y), Math.abs(img.width - svg.width), Math.abs(img.height - svg.height)];
      });
      assert(delta.every(value => value < 1));
    }
    await page.screenshot({path: path.resolve("artifacts/ocr-initials-mobile.png"), fullPage: true});
    data = await correct(["ㅇ", "ㄹ", "ㄴ"]);
    assert.equal(data.regions.length, 1);
    assert.equal(data.regions[0].surface, "ㅇ ㄹ ㄴ");
    assert.equal(data.regions[0].boxes.length, 3);
    assert(data.regions[0].expansion.includes("미확인"));
    data = await correct(["채용ㅈㅇ 이력서"]);
    assert.equal(data.regions.length, 0);
    assert.equal(await page.locator("#ocr-overlay rect").count(), 0);
    assert.deepEqual(errors, []);
    console.log(JSON.stringify({status: "passed", checks: ["actual OCR then exact recognized text", "three red boxes", "original coordinates", "unknown labels and alternatives", "split initials longest match", "ordinary context", "dirty state", "responsive alignment", "console"], errors}));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
