// Markdown의 로컬 링크·상대 이미지 경로와 배포 문서의 기본 조건을 확인합니다.
const fs = require("node:fs");
const path = require("node:path");
const assert = require("node:assert/strict");
const root = path.resolve(__dirname, "..");
const walk = directory => fs.readdirSync(directory, {withFileTypes: true}).flatMap(entry => {
  const target = path.join(directory, entry.name);
  return entry.isDirectory() ? walk(target) : [target];
});
const files = [...fs.readdirSync(root).filter(name => name.endsWith(".md")).map(name => path.join(root, name)),
  ...walk(path.join(root, "docs")).filter(name => name.endsWith(".md")), path.join(root, "reports/README.md")];
const issues = [];
let links = 0;
for (const file of files) {
  const source = fs.readFileSync(file, "utf8");
  for (const match of source.matchAll(/!?\[[^\]]*\]\(([^)\s]+)(?:\s+"[^"]*")?\)/g)) {
    const href = match[1];
    if (/^[a-z][a-z0-9+.-]*:/i.test(href) || href.startsWith("#")) continue;
    const target = path.resolve(path.dirname(file), decodeURIComponent(href.split("#")[0]));
    links++;
    if (!fs.existsSync(target)) issues.push(`${path.relative(root, file)}: ${href}`);
  }
}
for (const name of ["workflow.gif", "performance.png", "text.png", "ocr.png", "mobile.png", "ocr-input.png"]) {
  const file = path.join(root, "docs/media", name);
  assert(fs.statSync(file).size > 1000, `Empty media: ${name}`);
  if (name.endsWith(".gif")) assert(fs.readFileSync(file).subarray(0, 6).toString().startsWith("GIF8"));
}
assert.deepEqual(issues, [], "Broken local Markdown links");
assert(!fs.readFileSync(path.join(root, "README.md"), "utf8").includes("C:\\Users\\"));
assert(fs.existsSync(path.join(root, ".env.example")));
console.log(JSON.stringify({status: "passed", documents: files.length, local_links: links, media: 6}));
