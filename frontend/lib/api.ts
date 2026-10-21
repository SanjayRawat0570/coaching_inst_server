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

type ApiOptions = { method?: string; body?: any };

/** Standard JSON request to the FastAPI backend. */
export async function api(path: string, { method = "GET", body }: ApiOptions = {}) {
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

/** Multipart upload (FormData) to the backend — the browser sets the boundary header. */
export async function apiUpload(path: string, form: FormData) {
  const { Authorization } = (await authHeaders()) as any;
  const res = await fetch(`${API_URL}${path}`, {
    method: "POST",
    headers: Authorization ? { Authorization } : {},
    body: form,
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(detail || `Upload failed: ${res.status}`);
  }
  return res.json();
}

/** Pull FastAPI's {"detail": "..."} out of an api()/apiUpload() error message. */
export function errorDetail(e: any) {
  try {
    return JSON.parse(e?.message)?.detail || e?.message;
  } catch {
    return e?.message || "Something went wrong.";
  }
}

/**
 * Stream a doubt answer over SSE-style chunks.
 * EventSource can't send the auth header, so we read the POST response body manually.
 *
 * onToken(textChunk), onStatus(text), onMeta(meta), onDone(), onError(message)
 *
 * meta (sent once, after the answer): {doubt_id, citations: [{source, page}],
 * answerable, confidence: "high"|"medium"|"low"|null, conversation_id, provider}
 */
export async function streamDoubt(payload: any, { onToken, onStatus, onMeta, onDone, onError }: any = {}) {
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

      const events = buffer.split("\n\n");
      buffer = events.pop() || "";

      for (const event of events) {
        // A token containing newlines arrives as several "data:" lines; per the
        // SSE spec they are joined back with "\n".
        const dataLines = event.split("\n").filter((l) => l.startsWith("data:"));
        if (!dataLines.length) continue;
        const data = dataLines.map((l) => l.slice(l.startsWith("data: ") ? 6 : 5)).join("\n");
        if (data === "[DONE]") {
          onDone?.();
          return;
        }
        if (data.startsWith("[STATUS]")) {
          onStatus?.(data.replace("[STATUS]", ""));
        } else if (data.startsWith("[ERROR]")) {
          onError?.(data.replace("[ERROR]", ""));
        } else if (data.startsWith("[META]")) {
          try {
            onMeta?.(JSON.parse(data.slice(6)));
          } catch {
            // a malformed meta line must never break the answer
          }
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
