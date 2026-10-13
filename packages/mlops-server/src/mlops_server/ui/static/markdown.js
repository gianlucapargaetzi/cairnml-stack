import { h } from "./dom.js";
import { safeHttpsUrl } from "./lib.js";

// Inline pattern: `code`, **bold**, [text](url). A URL may contain one level of balanced parentheses.
const INLINE = /`([^`]+)`|\*\*([^*]+)\*\*|\[([^\]]+)\]\(((?:[^()\s]|\([^()\s]*\))+)\)/g;

export function parseInline(text) {
  const out = [];
  let last = 0;
  let match;
  INLINE.lastIndex = 0;
  while ((match = INLINE.exec(text))) {
    if (match.index > last) out.push({ type: "text", text: text.slice(last, match.index) });
    if (match[1] !== undefined) out.push({ type: "code", text: match[1] });
    else if (match[2] !== undefined) out.push({ type: "bold", text: match[2] });
    else {
      const href = safeHttpsUrl(match[4]);
      out.push(href ? { type: "link", text: match[3], href } : { type: "text", text: match[3] });
    }
    last = INLINE.lastIndex;
  }
  if (last < text.length) out.push({ type: "text", text: text.slice(last) });
  return out;
}

const LIST_ITEM = /^\s*[-*]\s+/;
const HEADING = /^(#{1,3})\s+(.*)$/;
const BLOCK_START = /^(#{1,3}\s|```|\s*[-*]\s)/;

// Block pattern: headings (#, ##, ###), paragraphs, bullet lists and fenced code. Anything else is text.
export function parseMarkdown(text) {
  const lines = String(text).replace(/\r\n/g, "\n").split("\n");
  const blocks = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (/^\s*$/.test(line)) { i++; continue; }
    if (line.startsWith("```")) {
      const code = [];
      i++;
      while (i < lines.length && !/^```\s*$/.test(lines[i])) code.push(lines[i++]);
      i++; // the closing fence, or past the end when the fence is never closed
      blocks.push({ type: "code", text: code.join("\n") });
      continue;
    }
    const heading = line.match(HEADING);
    if (heading) {
      blocks.push({ type: "heading", level: heading[1].length, inline: parseInline(heading[2]) });
      i++;
      continue;
    }
    if (LIST_ITEM.test(line)) {
      const items = [];
      while (i < lines.length && LIST_ITEM.test(lines[i])) items.push(parseInline(lines[i++].replace(LIST_ITEM, "")));
      blocks.push({ type: "list", items });
      continue;
    }
    const paragraph = [];
    while (i < lines.length && !/^\s*$/.test(lines[i]) && !BLOCK_START.test(lines[i])) paragraph.push(lines[i++]);
    blocks.push({ type: "paragraph", inline: parseInline(paragraph.join(" ")) });
  }
  return blocks;
}

// Only text nodes and the four elements below are created, so card content can never become markup.
const inlineNode = (part) => {
  if (part.type === "code") return h("code", {}, part.text);
  if (part.type === "bold") return h("strong", {}, part.text);
  if (part.type === "link") return h("a", { href: part.href }, part.text);
  return part.text;
};

// Card headings start two levels down (# becomes h3) so the card cannot compete with the page title.
export function renderMarkdown(text) {
  const fragment = document.createDocumentFragment();
  for (const block of parseMarkdown(text)) {
    if (block.type === "heading") fragment.append(h(`h${Math.min(block.level + 2, 5)}`, {}, block.inline.map(inlineNode)));
    else if (block.type === "paragraph") fragment.append(h("p", {}, block.inline.map(inlineNode)));
    else if (block.type === "list") fragment.append(h("ul", {}, block.items.map((item) => h("li", {}, item.map(inlineNode)))));
    else fragment.append(h("pre", { class: "log" }, block.text));
  }
  return fragment;
}
