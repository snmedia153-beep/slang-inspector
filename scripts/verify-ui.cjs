/* Set NODE_PATH to an installed Playwright package directory before running. */
const {chromium} = require("playwright");
const fs = require("node:fs/promises");
const path = require("node:path");
const assert = require("node:assert/strict");

(async () => {
  const url = process.env.SLANG_UI_URL || "http://127.0.0.1:18640";
  const output = path.resolve("artifacts");
  await fs.mkdir(output, {recursive: true});
  const browser = await chromium.launch({headless: true, executablePath: process.env.SLANG_CHROMIUM_PATH || undefined});
  const context = await browser.newContext({viewport: {width: 1440, height: 1100}, acceptDownloads: true});
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", error => errors.push(error.message));
  page.on("console", message => { if (message.type() === "error") errors.push(message.text()); });
  try {
    await page.goto(url, {waitUntil: "networkidle"});
    await page.waitForFunction(() => document.querySelector("#status-dot").classList.contains("ready"));
    await page.waitForFunction(() => !document.querySelector("#deep-status").textContent.includes("확인 중"));
    await page.locator(".options summary").click();
    await page.locator("#deep-toggle").uncheck();
    await page.locator(".options summary").click();
    await page.screenshot({path: path.join(output, "desktop.png"), fullPage: true});
    await page.getByRole("button", {name: "초성 원형", exact: true}).click();
    await page.getByRole("button", {name: "텍스트 분석 ↗", exact: true}).click();
    await page.locator(".expansion-line strong").filter({hasText: "고딩"}).waitFor();
    assert((await page.locator("#match-list").innerText()).includes("대딸"));
    await page.screenshot({path: path.join(output, "initials.png"), fullPage: true});
    await page.getByRole("button", {name: "변형 표현", exact: true}).click();
    await page.getByRole("button", {name: "텍스트 분석 ↗", exact: true}).click();
    await page.locator("#match-list .match-heading strong").filter({hasText: "끄.딩.물"}).waitFor();
    assert((await page.locator("#match-list").innerText()).includes("끄.딩.물"));
    assert((await page.locator("#highlighted-text").innerText()).includes("끄.딩.물"));
    await page.screenshot({path: path.join(output, "analysis.png"), fullPage: true});
    const downloadPromise = page.waitForEvent("download");
    await page.getByRole("button", {name: "JSON 내보내기"}).click();
    assert.equal((await downloadPromise).suggestedFilename(), "slang-analysis.json");

    await page.locator("#input-text").fill("🧪 <img src=x onerror=alert(1)> 불법촬영물 신고 예방");
    await page.locator("#input-text").press("Control+Enter");
    await page.waitForFunction(() => document.querySelector("#highlighted-text").textContent.startsWith("🧪"));
    assert.equal(await page.locator("#highlighted-text img").count(), 0);
    assert.equal(await page.locator("#highlighted-text mark").innerText(), "불법촬영물");
    await page.locator("#text-file").setInputFiles({name: "example.txt", mimeType: "text/plain", buffer: Buffer.from("오늘 사과를 먹습니다.", "utf8")});
    await page.waitForFunction(() => document.querySelector("#input-text").value === "오늘 사과를 먹습니다.");
    await page.getByRole("button", {name: "텍스트 분석 ↗", exact: true}).click();
    await page.getByText("현재 사전과 규칙에 일치하는 표현이 없습니다.", {exact: true}).waitFor();

    await page.locator('[data-page="lexicon"]').click();
    await page.locator("#lexicon-list .lexicon-row").first().waitFor();
    await page.locator("#entry-alias").fill("임시검증표현");
    await page.locator("#entry-canonical").fill("검토용표현");
    await page.getByRole("button", {name: "사전에 등록 +"}).click();
    await page.locator("#lexicon-search").fill("임시검증표현");
    await page.getByRole("button", {name: "임시검증표현 사전에서 삭제"}).waitFor();
    page.once("dialog", dialog => dialog.accept());
    await page.getByRole("button", {name: "임시검증표현 사전에서 삭제"}).click();
    await page.getByText("일치하는 사전 항목이 없습니다.", {exact: true}).waitFor();
    await page.locator("#lexicon-search").fill("");
    await page.locator('[data-page="discovery"]').click();
    await page.getByRole("heading", {name: "문서 묶음에서 후보 찾기"}).waitFor();

    for (const viewport of [{width: 1280, height: 900}, {width: 768, height: 1024}, {width: 390, height: 844}]) {
      await page.setViewportSize(viewport);
      for (const section of ["analyze", "lexicon", "discovery"]) {
        await page.locator(`[data-page="${section}"]`).click();
        assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), `${section}: overflow at ${viewport.width}`);
      }
    }
    await page.locator('[data-page="analyze"]').click();
    await page.getByRole("button", {name: "변형 표현", exact: true}).click();
    await page.getByRole("button", {name: "텍스트 분석 ↗", exact: true}).click();
    await page.locator("#match-list .match-heading strong").filter({hasText: "끄.딩.물"}).waitFor();
    await page.screenshot({path: path.join(output, "mobile.png"), fullPage: true});
    assert.deepEqual(errors, [], "Browser console and page errors");
    console.log(JSON.stringify({status: "passed", checks: ["analysis", "unicode offsets", "XSS rendering", "TXT upload", "JSON export", "dictionary add/delete", "discovery screen", "responsive 1280/768/390", "console errors"], errors}));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
