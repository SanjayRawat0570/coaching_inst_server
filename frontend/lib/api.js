import { supabase } from "./supabase";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function authHeaders() {
  const {
    data: { session },
  } = await supabase.auth.getSession();
  const token = session?.access_token;
  return {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

/** Standard JSON request to the FastAPI backend. */
export async function api(path, { method = "GET", body } = {}) {
  const res = await fetch(`${API_URL}${path}`, {
    method,
    headers: await authHeaders(),
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(detail || `Request failed: ${res.status}`);
  }
  return res.json();
}

/**
 * Stream a doubt answer over SSE-style chunks.
 * EventSource can't send the auth header, so we read the POST response body manually.
 *
 * onToken(textChunk), onStatus(nodeName), onDone(), onError(message)
 */
export async function streamDoubt(payload, { onToken, onStatus, onDone, onError }) {
  try {
    const res = await fetch(`${API_URL}/doubt/stream`, {
      method: "POST",
      headers: await authHeaders(),
      body: JSON.stringify(payload),
    });
    if (!res.ok || !res.body) {
      throw new Error(`Stream failed: ${res.status}`);
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      const lines = buffer.split("\n\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        const data = line.slice(6);
        if (data === "[DONE]") {
          onDone?.();
          return;
        }
        if (data.startsWith("[STATUS]")) {
          onStatus?.(data.replace("[STATUS]", ""));
        } else if (data.startsWith("[ERROR]")) {
          onError?.(data.replace("[ERROR]", ""));
        } else {
          onToken?.(data);
        }
      }
    }
    onDone?.();
  } catch (e) {
    onError?.(e.message);
  }
}

export { API_URL };
