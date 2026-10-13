import { h } from "../dom.js";

// Placeholder until this page is built; it renders its heading only.
export default async function resources(root) {
  root.replaceChildren(h("h1", {}, "Resources"));
}
