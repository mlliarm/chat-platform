import { afterEach, describe, expect, it, vi } from "vitest";
import { closeApp, loadApp } from "./helpers/loadApp.js";

function mathExtension(app) {
  const call = app.window.marked.use.mock.calls.find(([config]) => config.extensions);
  return call[0].extensions.find((ext) => ext.name === "math");
}

function tokenize(app, src) {
  return mathExtension(app).tokenizer(src);
}

function render(app, src) {
  const ext = mathExtension(app);
  return ext.renderer(ext.tokenizer(src));
}

describe("math tokenizer", () => {
  let app;

  afterEach(() => {
    if (app) closeApp(app);
  });

  it("is registered with marked as an inline extension", () => {
    app = loadApp();
    const ext = mathExtension(app);
    expect(ext.level).toBe("inline");
  });

  it("treats $$…$$ as display math", () => {
    app = loadApp();
    expect(tokenize(app, "$$x^2$$ rest")).toMatchObject({ display: true, text: "x^2", raw: "$$x^2$$" });
  });

  it("treats \\[…\\] as display math", () => {
    app = loadApp();
    expect(tokenize(app, "\\[x^2\\]")).toMatchObject({ display: true, text: "x^2" });
  });

  it("treats \\(…\\) as inline math", () => {
    app = loadApp();
    expect(tokenize(app, "\\(x^2\\)")).toMatchObject({ display: false, text: "x^2" });
  });

  it("treats $…$ as inline math", () => {
    app = loadApp();
    expect(tokenize(app, "$x^2$")).toMatchObject({ display: false, text: "x^2" });
  });

  it("spans newlines so a multi-line environment stays one token", () => {
    app = loadApp();
    const src = "$$\n\\begin{aligned}\na &= b \\\\\nc &= d\n\\end{aligned}\n$$";
    expect(tokenize(app, src).text).toContain("\\\\");
  });

  it("ignores currency amounts", () => {
    app = loadApp();
    expect(tokenize(app, "$5 and $10 total")).toBeUndefined();
  });

  it("ignores a lone dollar sign", () => {
    app = loadApp();
    expect(tokenize(app, "$100")).toBeUndefined();
  });

  it("ignores text that does not start with a delimiter", () => {
    app = loadApp();
    expect(tokenize(app, "plain text $x$")).toBeUndefined();
  });

  it("reports where the next delimiter starts so marked stops its text token there", () => {
    app = loadApp();
    const ext = mathExtension(app);
    expect(ext.start("consider \\(x\\) here")).toBe(9);
    expect(ext.start("no math here")).toBeUndefined();
  });
});

describe("math renderer", () => {
  let app;

  afterEach(() => {
    if (app) closeApp(app);
  });

  it("re-emits display math with MathJax's own delimiters", () => {
    app = loadApp();
    expect(render(app, "$$x^2$$")).toBe('<span class="math-display">\\[x^2\\]</span>');
  });

  it("re-emits inline math with MathJax's own delimiters", () => {
    app = loadApp();
    expect(render(app, "$x^2$")).toBe('<span class="math-inline">\\(x^2\\)</span>');
  });

  it("escapes HTML-significant characters in the expression body", () => {
    app = loadApp();
    expect(render(app, "$a < b & c$")).toBe('<span class="math-inline">\\(a &lt; b &amp; c\\)</span>');
  });

  it("leaves backslash escapes in the body alone", () => {
    app = loadApp();
    expect(render(app, "$\\{a\\}$")).toBe('<span class="math-inline">\\(\\{a\\}\\)</span>');
  });
});

describe("scheduleMathTypeset", () => {
  let app;

  afterEach(() => {
    if (app) closeApp(app);
  });

  function attach(app, html) {
    const el = app.document.createElement("div");
    el.innerHTML = html;
    app.document.body.appendChild(el);
    return el;
  }

  function markMathJaxReady(app) {
    const typesetPromise = vi.fn(() => Promise.resolve());
    app.window.MathJax = { typesetPromise };
    app.document.dispatchEvent(new app.window.Event("mathjax-ready"));
    return typesetPromise;
  }

  it("typesets elements queued before MathJax finished loading", () => {
    app = loadApp();
    const el = attach(app, '<span class="math-inline">\\(x\\)</span>');
    app.window.scheduleMathTypeset(el);

    const typesetPromise = markMathJaxReady(app);
    expect(typesetPromise).toHaveBeenCalledWith([el]);
  });

  it("skips elements that contain no math", () => {
    app = loadApp();
    const el = attach(app, "<p>just prose</p>");
    app.window.scheduleMathTypeset(el);

    const typesetPromise = markMathJaxReady(app);
    expect(typesetPromise).not.toHaveBeenCalled();
  });

  it("batches repeated calls for the same streaming element into one typeset", () => {
    app = loadApp();
    const el = attach(app, '<span class="math-display">\\[x\\]</span>');
    app.window.scheduleMathTypeset(el);
    app.window.scheduleMathTypeset(el);
    app.window.scheduleMathTypeset(el);

    const typesetPromise = markMathJaxReady(app);
    expect(typesetPromise).toHaveBeenCalledTimes(1);
    expect(typesetPromise).toHaveBeenCalledWith([el]);
  });

  it("drops elements removed from the DOM before the typeset ran", () => {
    app = loadApp();
    const el = attach(app, '<span class="math-inline">\\(x\\)</span>');
    app.window.scheduleMathTypeset(el);
    el.remove();

    const typesetPromise = markMathJaxReady(app);
    expect(typesetPromise).not.toHaveBeenCalled();
  });
});
