const { chromium } = require("playwright");
const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const path = require("node:path");
(async () => {
  const browser = await chromium.launch({headless: true, executablePath: process.env.SLANG_CHROMIUM_PATH || undefined});
  const page = await browser.newPage({viewport: {width: 1440, height: 1000}});
  const errors = [];
  page.on("pageerror", error => errors.push(error.message));
  page.on("console", message => { if (message.type() === "error") errors.push(message.text()); });
  try {
    await page.goto(process.env.SLANG_UI_URL || "http://127.0.0.1:18640", {waitUntil: "networkidle"});
    await page.waitForFunction(() => !document.querySelector("#deep-status").textContent.includes("확인 중"));
    await page.locator(".options summary").click();
    await page.locator("#deep-toggle").uncheck();
    await page.locator("#input-text").fill("서울에서 몸사를 보내면 용돈 줄게. #맘눌피 #야상극 ㅇㄹ");
    await page.locator("#analyze-button").click();
    await page.locator("#watchlist-results .watchlist-row").first().waitFor();
    const body = await page.locator("#watchlist-results").innerText();
    assert(body.includes("몸 사진"));
    assert(body.includes("원형 미확인"));
    assert(body.includes("오랄"));
    assert(body.includes("금전·물품 제공"));
    assert.equal(await page.locator("#watchlist-results .watchlist-row").count(), 6);
    await fs.mkdir("artifacts", {recursive: true});
    await page.screenshot({path: path.resolve("artifacts/watchlist-desktop.png"), fullPage: true});

    await page.locator('[data-page="lexicon"]').click();
    await page.locator("#watchlist-catalog summary").click();
    assert((await page.locator("#watchlist-catalog summary").textContent()).includes("전체 200개"));
    assert.equal(await page.locator("#watchlist-catalog-rows .watchlist-row").count(), 50);
    await page.locator("#watchlist-search").fill("맘눌피");
    assert.equal(await page.locator("#watchlist-catalog-rows .watchlist-row").count(), 1);
    assert((await page.locator("#watchlist-catalog-rows").innerText()).includes("피드를 보러 감"));
    await page.locator("#watchlist-search").fill("");
    for (let i = 0; i < 3; i++) await page.getByRole("button", {name: "다음 50개 더 보기"}).click();
    assert.equal(await page.locator("#watchlist-catalog-rows .watchlist-row").count(), 200);
    for (const width of [768, 390]) {
      await page.setViewportSize({width, height: 844});
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
      await page.locator('[data-page="analyze"]').click();
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
      await page.locator('[data-page="lexicon"]').click();
    }
    await page.locator('[data-page="analyze"]').click();
    await page.screenshot({path: path.resolve("artifacts/watchlist-mobile.png"), fullPage: true});
    await page.locator("#input-text").fill("서울 학생 용돈 관리 교육. 강아지 발 사진 수업");
    await page.locator("#analyze-button").click();
    await page.waitForFunction(() => !document.querySelector("#analyze-button").disabled);
    assert.equal(await page.locator("#match-list .match-card").count(), 0);
    assert.equal(await page.locator("#watchlist-results .watchlist-context").count(), 0);
    assert((await page.locator("#watchlist-results").innerText()).includes("일반 단서"));
    await page.locator("#deep-toggle").check();
    await page.locator("#input-text").fill("오늘 ㅇㄹ 레시피를 알려줘");
    const pending = page.waitForResponse(r => r.url().endsWith("/api/context/interpret"), {timeout: 90000});
    await page.locator("#analyze-button").click();
    const data = await (await pending).json();
    assert.equal(data.status, "ok", JSON.stringify(data));
    const oral = data.items.find(item => item.surface === "ㅇㄹ");
    assert(oral);
    assert(oral.reference_candidates.some(c => c.expansion === "오랄"));
    assert(oral.choices.some(c => c.expansion.includes("요리")), JSON.stringify(oral));
    await page.waitForFunction(() => !document.querySelector("#analyze-button").disabled);
    assert.deepEqual(errors, []);
    console.log(JSON.stringify({status: "passed", watchlist: 200, model: data.model, ordinary: oral.choices.map(c => c.expansion), errors}));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
