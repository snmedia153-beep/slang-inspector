// 실제 API 응답이 화면에 반영된 장면만 저장합니다. 입력에는 개인 식별자를 넣지 않습니다.
const { chromium } = require("playwright");
const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const path = require("node:path");

(async () => {
  const root = path.resolve(__dirname, "..");
  const frames = path.join(root, "artifacts/portfolio-frames");
  const media = path.join(root, "docs/media");
  await fs.mkdir(frames, {recursive: true});
  const browser = await chromium.launch({headless: true, executablePath: process.env.SLANG_CHROMIUM_PATH || undefined});
  const page = await browser.newPage({viewport: {width: 1400, height: 920}, deviceScaleFactor: 1});
  const errors = [];
  page.on("pageerror", error => errors.push(error.message));
  page.on("console", message => { if (message.type() === "error") errors.push(message.text()); });
  const snapshot = name => page.screenshot({path: path.join(frames, name), animations: "disabled"});
  try {
    await page.goto(process.env.SLANG_UI_URL || "http://127.0.0.1:18640", {waitUntil: "networkidle"});
    await page.waitForFunction(() => document.querySelector("#status-dot").classList.contains("ready"));
    await page.locator(".options summary").click();
    await page.locator("#deep-toggle").uncheck();
    await page.locator(".options summary").click();
    await page.locator("#input-text").fill("불법촬영물 유포 신고 접수.\n재업ㄴㄴ · 나눠올리기\n간다아아아아아안");
    await page.locator("#input-text").blur();
    await snapshot("01-text-input.png");
    const pending = page.waitForResponse(response => response.url().endsWith("/api/analyze"));
    await page.locator("#analyze-button").click();
    assert.equal((await pending).status(), 200);
    await page.waitForFunction(() => !document.querySelector("#analyze-button").disabled);
    await page.locator("#results").scrollIntoViewIfNeeded();
    await snapshot("02-text-results.png");
    await page.screenshot({path: path.join(media, "text.png"), fullPage: true});
    assert(await page.locator("#highlighted-text mark").count());
    await page.locator('[data-page="image"]').click();
    await page.waitForFunction(() => document.querySelector("#ocr-status").textContent.includes("준비됨"));
    await page.locator("#ocr-file").setInputFiles(path.join(media, "ocr-input.png"));
    await page.waitForFunction(() => !document.querySelector("#ocr-run").disabled);
    await page.evaluate(() => scrollTo(0, 0));
    await snapshot("03-image-input.png");
    const recognized = page.waitForResponse(response => response.url().includes("/api/ocr/analyze"));
    await page.locator("#ocr-run").click();
    assert.equal((await recognized).status(), 200);
    await page.waitForFunction(() => !document.querySelector("#ocr-run").disabled);
    assert(await page.locator("#ocr-overlay rect").count());
    await page.locator("#ocr-preview-panel").scrollIntoViewIfNeeded();
    await page.evaluate(() => scrollBy(0, 240));
    await snapshot("04-image-results.png");
    await page.screenshot({path: path.join(media, "ocr.png"), fullPage: true});
    await page.setViewportSize({width: 390, height: 844});
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
    await page.screenshot({path: path.join(media, "mobile.png"), fullPage: true});
    assert.deepEqual(errors, []);
    console.log(JSON.stringify({status: "passed", frames: 4, actual_api: true, errors}));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
