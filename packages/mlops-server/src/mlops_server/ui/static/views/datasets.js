import { h } from "../dom.js";

// Placeholder until this page is built; it renders its heading only.
export default async function datasets(root) {
  root.replaceChildren(h("h1", {}, "Datasets"));
}
