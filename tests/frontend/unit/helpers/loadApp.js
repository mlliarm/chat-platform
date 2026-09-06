import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { JSDOM } from "jsdom";
import { vi } from "vitest";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PROJECT_ROOT = path.resolve(__dirname, "../../../..");
const TEMPLATE_PATH = path.join(PROJECT_ROOT, "templates", "index.html");
const SCRIPT_PATH = path.join(PROJECT_ROOT, "static", "script.js");

const DEFAULT_MODEL = "test-model/default";

function renderTemplate(defaultModel) {
  let html = fs.readFileSync(TEMPLATE_PATH, "utf8");
  html = html.replace(/\{\{\s*url_for\(\s*'static',\s*filename='([^']+)'\s*\)\s*\}\}/g, "/static/$1");
  html = html.replace(/\{\{\s*default_model\s*\}\}/g, defaultModel);
  return html;
}

export function jsonResponse(data = [], { ok = true, status = 200 } = {}) {
  return { ok, status, json: async () => data };
}

function makeMarkedStub() {
  return {
    setOptions: vi.fn(),
    use: vi.fn(),
    // Real marked isn't loaded in tests; this stands in for it so
    // markdown-specific tests can assert on the wrapper behavior
    // (sanitize call, streaming re-render) without a real parser.
    parse: (content) => `<p>${content}</p>`,
  };
}

function makeDOMPurifyStub() {
  return {
    addHook: vi.fn(),
    sanitize: (html) => html,
  };
}

function makeHljsStub() {
  return {
    getLanguage: () => true,
    highlight: (text) => ({ value: text, language: "text" }),
    highlightAuto: (text) => ({ value: text, language: null }),
  };
}

/**
 * Loads the real static/script.js into a fresh JSDOM realm built from the
 * real templates/index.html (with the two Jinja placeholders substituted).
 * A fresh realm is required per call: script.js declares top-level
 * `let`/`const` bindings, which cannot be re-eval'd into the same global
 * scope twice.
 */
export function loadApp({
  defaultModel = DEFAULT_MODEL,
  fetchImpl = vi.fn(() => Promise.resolve(jsonResponse([]))),
  markdown = true,
  confirmImpl = vi.fn(() => true),
  localStorageSeed = {},
} = {}) {
  const html = renderTemplate(defaultModel);
  const dom = new JSDOM(html, {
    url: "http://localhost/",
    runScripts: "outside-only",
  });

  const { window } = dom;

  window.fetch = fetchImpl;
  window.confirm = confirmImpl;
  window.scrollTo = vi.fn();
  // Seeded before script.js runs, since it reads localStorage synchronously
  // at top level (e.g. the free-only toggle's initial checked state).
  for (const [key, value] of Object.entries(localStorageSeed)) {
    window.localStorage.setItem(key, value);
  }
  // jsdom's `window` global doesn't include the WHATWG encoding globals;
  // script.js needs them for SSE decoding.
  window.TextEncoder = TextEncoder;
  window.TextDecoder = TextDecoder;

  if (markdown) {
    window.marked = makeMarkedStub();
    window.DOMPurify = makeDOMPurifyStub();
    window.hljs = makeHljsStub();
  }

  if (typeof window.HTMLFormElement.prototype.requestSubmit !== "function") {
    window.HTMLFormElement.prototype.requestSubmit = function requestSubmit(submitter) {
      const event = new window.Event("submit", { bubbles: true, cancelable: true });
      if (submitter) Object.defineProperty(event, "submitter", { value: submitter });
      this.dispatchEvent(event);
    };
  }

  const scriptSource = fs.readFileSync(SCRIPT_PATH, "utf8");
  window.eval(scriptSource);

  return { window, document: window.document };
}

export function closeApp(app) {
  app.window.close();
}

/**
 * Freezes `Date.now()` inside the app's own realm (jsdom's `window.Date` is a
 * distinct constructor from Node's global `Date`, so vitest's fake timers
 * don't reach it).
 */
export function setNow(app, date) {
  const timestamp = new Date(date).getTime();
  app.window.Date.now = () => timestamp;
}
