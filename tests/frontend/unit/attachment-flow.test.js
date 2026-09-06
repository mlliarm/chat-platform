import { afterEach, describe, expect, it, vi } from "vitest";
import { closeApp, jsonResponse, loadApp } from "./helpers/loadApp.js";

function makeFile(win, { name, type, size }) {
  const bytes = new Uint8Array(size);
  const file = new win.File([bytes], name, { type });
  return file;
}

function setFiles(fileInput, files) {
  Object.defineProperty(fileInput, "files", { value: files, configurable: true });
}

async function flush() {
  await new Promise((resolve) => setTimeout(resolve, 0));
  await new Promise((resolve) => setTimeout(resolve, 0));
}

describe("file-input attachment flow", () => {
  let app;

  afterEach(() => {
    if (app) closeApp(app);
  });

  it("rejects an oversized image before reading it", async () => {
    app = loadApp();
    const { window } = app;
    const fileInput = window.document.getElementById("file-input");
    const file = makeFile(window, { name: "big.png", type: "image/png", size: 9 * 1024 * 1024 });
    setFiles(fileInput, [file]);

    fileInput.dispatchEvent(new window.Event("change"));
    await flush();

    const preview = window.document.getElementById("attachment-preview");
    expect(preview.hidden).toBe(false);
    expect(preview.classList.contains("error")).toBe(true);
    expect(preview.textContent).toMatch(/too large/i);
  });

  it("rejects an oversized non-image file before uploading it", async () => {
    app = loadApp();
    const { window } = app;
    const fileInput = window.document.getElementById("file-input");
    const file = makeFile(window, { name: "big.txt", type: "text/plain", size: 11 * 1024 * 1024 });
    setFiles(fileInput, [file]);

    fileInput.dispatchEvent(new window.Event("change"));
    await flush();

    const preview = window.document.getElementById("attachment-preview");
    expect(preview.classList.contains("error")).toBe(true);
    expect(preview.textContent).toMatch(/too large/i);
    expect(window.fetch).not.toHaveBeenCalledWith("/api/extract", expect.anything());
  });

  it("shows a thumbnail preview for a valid image", async () => {
    app = loadApp();
    const { window } = app;
    const fileInput = window.document.getElementById("file-input");
    const file = makeFile(window, { name: "photo.png", type: "image/png", size: 1024 });
    setFiles(fileInput, [file]);

    fileInput.dispatchEvent(new window.Event("change"));
    await flush();

    const preview = window.document.getElementById("attachment-preview");
    expect(preview.hidden).toBe(false);
    expect(preview.querySelector("img")).not.toBeNull();
    expect(preview.textContent).toContain("photo.png");
  });

  it("uploads a text file to /api/extract and shows its name on success", async () => {
    const fetchImpl = vi.fn((url) => {
      if (url === "/api/extract") {
        return Promise.resolve(jsonResponse({ filename: "notes.txt", text: "file contents" }));
      }
      return Promise.resolve(jsonResponse([]));
    });
    app = loadApp({ fetchImpl });
    const { window } = app;
    const fileInput = window.document.getElementById("file-input");
    const file = makeFile(window, { name: "notes.txt", type: "text/plain", size: 1024 });
    setFiles(fileInput, [file]);

    fileInput.dispatchEvent(new window.Event("change"));
    await flush();

    expect(fetchImpl).toHaveBeenCalledWith("/api/extract", expect.objectContaining({ method: "POST" }));
    const preview = window.document.getElementById("attachment-preview");
    expect(preview.classList.contains("error")).toBe(false);
    expect(preview.textContent).toContain("notes.txt");
  });

  it("shows an error banner when /api/extract fails", async () => {
    const fetchImpl = vi.fn((url) => {
      if (url === "/api/extract") {
        return Promise.resolve(jsonResponse({ error: "Could not read file." }, { ok: false, status: 400 }));
      }
      return Promise.resolve(jsonResponse([]));
    });
    app = loadApp({ fetchImpl });
    const { window } = app;
    const fileInput = window.document.getElementById("file-input");
    const file = makeFile(window, { name: "bad.txt", type: "text/plain", size: 1024 });
    setFiles(fileInput, [file]);

    fileInput.dispatchEvent(new window.Event("change"));
    await flush();

    const preview = window.document.getElementById("attachment-preview");
    expect(preview.classList.contains("error")).toBe(true);
    expect(preview.textContent).toContain("Could not read file.");
  });

  it("clears the pending attachment when the remove button is clicked", async () => {
    app = loadApp();
    const { window } = app;
    const fileInput = window.document.getElementById("file-input");
    const file = makeFile(window, { name: "photo.png", type: "image/png", size: 1024 });
    setFiles(fileInput, [file]);
    fileInput.dispatchEvent(new window.Event("change"));
    await flush();

    const preview = window.document.getElementById("attachment-preview");
    preview.querySelector(".remove-btn").dispatchEvent(new window.Event("click", { bubbles: true }));

    expect(preview.hidden).toBe(true);
  });
});
