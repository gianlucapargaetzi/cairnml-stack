import test from "node:test";
import assert from "node:assert/strict";
import { parseInline, parseMarkdown } from "../src/mlops_server/ui/static/markdown.js";

test("inline code, bold and safe links", () => {
  assert.deepEqual(parseInline("a `b` **c** [d](https://e.com/x) f"), [
    { type: "text", text: "a " }, { type: "code", text: "b" }, { type: "text", text: " " }, { type: "bold", text: "c" },
    { type: "text", text: " " }, { type: "link", text: "d", href: "https://e.com/x" }, { type: "text", text: " f" }]);
});

test("unsafe links become plain text", () => {
  for (const url of ["javascript:alert(1)", "http://insecure.example", "data:text/html,x"]) {
    assert.deepEqual(parseInline(`[click](${url})`), [{ type: "text", text: "click" }]);
  }
});

test("raw html stays text", () => {
  assert.deepEqual(parseInline("<img src=x onerror=alert(1)>"), [{ type: "text", text: "<img src=x onerror=alert(1)>" }]);
});

test("blocks", () => {
  const blocks = parseMarkdown("# Title\n\nSome **bold** text\nsecond line.\n\n- one\n- two `x`\n\n```\ncode here\n  indented\n```\n\n### Small\nend");
  assert.deepEqual(blocks.map((b) => b.type), ["heading", "paragraph", "list", "code", "heading", "paragraph"]);
  assert.equal(blocks[0].level, 1);
  assert.equal(blocks[2].items.length, 2);
  assert.equal(blocks[3].text, "code here\n  indented");
  assert.equal(blocks[4].level, 3);
  assert.deepEqual(blocks[1].inline.map((i) => i.type), ["text", "bold", "text"]);
});

test("an unterminated code fence does not hang or swallow nothing", () => {
  const blocks = parseMarkdown("```\nnever closed\nstill code");
  assert.deepEqual(blocks.map((b) => b.type), ["code"]);
  assert.equal(blocks[0].text, "never closed\nstill code");
});

test("empty and whitespace input", () => {
  assert.deepEqual(parseMarkdown(""), []);
  assert.deepEqual(parseMarkdown("\n\n   \n"), []);
});
