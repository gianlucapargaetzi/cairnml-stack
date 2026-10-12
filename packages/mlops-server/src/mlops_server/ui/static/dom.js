import { attributeAllowed, linkAllowed } from "./lib.js";

// Builds an element from attributes and children. Only allowlisted attributes are set, and
// href/src must pass linkAllowed; anything else throws so a mistake fails loudly in development.
export function h(tag, attrs, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key === "class") el.className = value;
    else if (key === "dataset") Object.assign(el.dataset, value);
    else if (key.startsWith("on")) {
      if (typeof value !== "function") throw new Error(`event handler ${key} must be a function`);
      el.addEventListener(key.slice(2), value);
    } else {
      if (!attributeAllowed(key)) throw new Error(`attribute not allowed: ${key}`);
      if (!linkAllowed(key, value)) throw new Error(`unsafe link for ${key}`);
      el.setAttribute(key, value === true ? "" : String(value));
    }
  }
  for (const child of children.flat(Infinity)) {
    if (child === null || child === undefined || child === false) continue;
    el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return el;
}
