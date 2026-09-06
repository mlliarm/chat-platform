// Mirrors tests/conftest.py's sse_lines_for_reply, but as a fake
// `res.body.getReader()` stream for the frontend's fetch-based SSE consumer.

function frameLine(obj) {
  return `data: ${JSON.stringify(obj)}\n\n`;
}

export function chunkFrames(chunks) {
  return chunks.map((content) => ({ choices: [{ delta: { content } }] }));
}

export function buildSSEText(frames) {
  return frames.map(frameLine).join("") + "data: [DONE]\n\n";
}

/** A successful `fetch()` response whose body streams the given SSE frames. */
export function makeStreamingResponse(frames, { chunkSize } = {}) {
  const bytes = new TextEncoder().encode(buildSSEText(frames));
  const pieces = [];
  if (chunkSize && chunkSize > 0) {
    for (let i = 0; i < bytes.length; i += chunkSize) {
      pieces.push(bytes.slice(i, i + chunkSize));
    }
  } else {
    pieces.push(bytes);
  }

  let i = 0;
  const reader = {
    read: async () => {
      if (i < pieces.length) return { done: false, value: pieces[i++] };
      return { done: true, value: undefined };
    },
  };

  return {
    ok: true,
    status: 200,
    body: { getReader: () => reader },
    json: async () => ({}),
  };
}

/** A failed (non-ok) `fetch()` response, e.g. for the pre-stream error path. */
export function makeErrorResponse(errorBody, { status = 400 } = {}) {
  return {
    ok: false,
    status,
    body: null,
    json: async () => errorBody,
  };
}
