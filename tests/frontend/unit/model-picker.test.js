import { afterEach, describe, expect, it, vi } from "vitest";
import { closeApp, jsonResponse, loadApp } from "./helpers/loadApp.js";

const MODELS = [
  { id: "openai/gpt-4o-mini", name: "GPT-4o mini", is_free: false },
  { id: "meta/llama-free", name: "Llama Free", is_free: true },
];

function fetchModels(models) {
  return vi.fn(() => Promise.resolve(jsonResponse(models)));
}

function toggleFreeOnly(window, checked) {
  const toggle = window.document.getElementById("free-only-toggle");
  toggle.checked = checked;
  toggle.dispatchEvent(new window.Event("change"));
}

describe("populateModelSelect (via loadModels + the free-only toggle)", () => {
  let app;

  afterEach(() => {
    if (app) closeApp(app);
  });

  it("lists all models when free-only is off", async () => {
    app = loadApp({ fetchImpl: fetchModels(MODELS) });
    await app.window.loadModels();

    const options = [...app.window.document.getElementById("model-select").options];
    expect(options.map((o) => o.value)).toEqual(["openai/gpt-4o-mini", "meta/llama-free"]);
    expect(options[1].textContent).toBe("Llama Free (Free)");
  });

  it("filters to only free models when free-only is on", async () => {
    app = loadApp({ fetchImpl: fetchModels(MODELS) });
    await app.window.loadModels();
    toggleFreeOnly(app.window, true);

    const options = [...app.window.document.getElementById("model-select").options];
    expect(options).toHaveLength(1);
    expect(options[0].value).toBe("meta/llama-free");
  });

  it("shows a disabled placeholder when no free models are available", async () => {
    app = loadApp({ fetchImpl: fetchModels([MODELS[0]]) });
    await app.window.loadModels();
    toggleFreeOnly(app.window, true);

    const options = [...app.window.document.getElementById("model-select").options];
    expect(options).toHaveLength(1);
    expect(options[0].disabled).toBe(true);
  });

  it("preserves the current selection if it's still present after re-populating", async () => {
    app = loadApp({ fetchImpl: fetchModels(MODELS) });
    await app.window.loadModels();
    const select = app.window.document.getElementById("model-select");
    select.value = "meta/llama-free";

    app.window.populateModelSelect();
    expect(select.value).toBe("meta/llama-free");
  });
});

describe("loadModels", () => {
  let app;

  afterEach(() => {
    if (app) closeApp(app);
  });

  it("populates the select on success", async () => {
    app = loadApp({ fetchImpl: fetchModels(MODELS) });
    await app.window.loadModels();

    const options = [...app.window.document.getElementById("model-select").options];
    expect(options).toHaveLength(2);
  });

  it("keeps the default option when the request fails", async () => {
    const fetchImpl = vi.fn(() => Promise.resolve(jsonResponse([], { ok: false, status: 500 })));
    app = loadApp({ fetchImpl });
    const select = app.window.document.getElementById("model-select");
    const before = select.innerHTML;

    await app.window.loadModels();
    expect(select.innerHTML).toBe(before);
  });

  it("keeps the default option when the response is an empty array", async () => {
    app = loadApp({ fetchImpl: fetchModels([]) });
    const select = app.window.document.getElementById("model-select");
    const before = select.innerHTML;

    await app.window.loadModels();
    expect(select.innerHTML).toBe(before);
  });

  it("keeps the default option when fetch itself throws", async () => {
    const fetchImpl = vi.fn(() => Promise.reject(new Error("network down")));
    app = loadApp({ fetchImpl });
    const select = app.window.document.getElementById("model-select");
    const before = select.innerHTML;

    await app.window.loadModels();
    expect(select.innerHTML).toBe(before);
  });
});

describe("free-only toggle", () => {
  let app;

  afterEach(() => {
    if (app) closeApp(app);
  });

  it("persists to localStorage and re-filters the model list on change", async () => {
    app = loadApp({ fetchImpl: fetchModels(MODELS) });
    await app.window.loadModels();

    toggleFreeOnly(app.window, true);

    expect(app.window.localStorage.getItem("freeOnly")).toBe("true");
    const options = [...app.window.document.getElementById("model-select").options];
    expect(options).toHaveLength(1);
    expect(options[0].value).toBe("meta/llama-free");
  });

  it("starts free-only based on a prior localStorage value", async () => {
    app = loadApp({ fetchImpl: fetchModels(MODELS), localStorageSeed: { freeOnly: "true" } });
    expect(app.window.document.getElementById("free-only-toggle").checked).toBe(true);

    await app.window.loadModels();
    const options = [...app.window.document.getElementById("model-select").options];
    expect(options).toHaveLength(1);
    expect(options[0].value).toBe("meta/llama-free");
  });
});
