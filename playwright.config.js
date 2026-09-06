import { defineConfig, devices } from "@playwright/test";
import os from "node:os";
import path from "node:path";

const TEST_DB_PATH = path.join(os.tmpdir(), `chat-platform-e2e-${Date.now()}.db`);
// A dedicated port, distinct from the app's usual :5000, so this never
// collides with (or needs to touch) a real dev server someone has running.
const TEST_PORT = 5799;

export default defineConfig({
  testDir: "./tests/frontend/e2e",
  fullyParallel: true,
  reporter: [["list"]],
  use: {
    baseURL: `http://127.0.0.1:${TEST_PORT}`,
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: {
    // Uses `flask run` (not `python app.py`) so debug/reload stays off
    // regardless of the hardcoded `app.run(debug=True)` in app.py's
    // `__main__` block, and points the app at a throwaway SQLite file so
    // the real chat.db is never touched.
    command: `venv/bin/flask --app app run --no-debug -p ${TEST_PORT}`,
    url: `http://127.0.0.1:${TEST_PORT}`,
    reuseExistingServer: false,
    env: {
      CHAT_DB_PATH: TEST_DB_PATH,
      OPENROUTER_API_KEY: "test-key",
    },
  },
});
