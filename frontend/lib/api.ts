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

/** A 401 usually means the access token just expired: refresh it once and retry.
 * If the session can't be refreshed, go to /login with a message (never a broken page). */
async function withAuthRetry(send: () => Promise<Response>) {
  let res = await send();
  if (res.status !== 401) return res;
  const { data, error } = await supabase.auth.refreshSession();
  if (!error && data?.session) {
    res = await send();
    if (res.status !== 401) return res;
  }
  if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
    window.location.assign("/login?expired=1");
  }
  return res;
}

type ApiOptions = { method?: string; body?: any; signal?: AbortSignal };

/** Standard JSON request to the FastAPI backend. */
export async function api(path: string, { method = "GET", body, signal }: ApiOptions = {}) {
  const res = await withAuthRetry(async () =>
    fetch(`${API_URL}${path}`, {
      method,
      headers: await authHeaders(),
      body: body ? JSON.stringify(body) : undefined,
      signal,
    }),
  );
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(detail || `Request failed: ${res.status}`);
  }
  return res.json();
}

/** Multipart upload (FormData) to the backend — the browser sets the boundary header. */
export async function apiUpload(path: string, form: FormData) {
  const res = await withAuthRetry(async () => {
    const { Authorization } = (await authHeaders()) as any;
    return fetch(`${API_URL}${path}`, {
      method: "POST",
      headers: Authorization ? { Authorization } : {},
      body: form,
    });
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

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

/**
 * Start a slow backend task as a background job (`?job=1`) and wait for it,
 * polling GET /jobs/{id} with backoff (1 s, growing to 5 s). onStatus(status) gets
 * "queued" | "running" while it waits. Resolves with the job's result, rejects with
 * its friendly error.
 */
export async function runJob(
  path: string,
  { method = "POST", body, onStatus, onStart, timeoutMs = 10 * 60 * 1000 }: ApiOptions & {
    onStatus?: (s: string) => void; onStart?: (jobId: string) => void; timeoutMs?: number } = {},
) {
  const sep = path.includes("?") ? "&" : "?";
  const { job_id } = await api(`${path}${sep}job=1`, { method, body });
  onStart?.(job_id); // e.g. remember it, so a retry resumes this job instead of starting another
  return pollJob(job_id, { onStatus, timeoutMs });
}

/** Wait for a job started earlier (see runJob). */
export async function pollJob(
  job_id: string,
  { onStatus, timeoutMs = 10 * 60 * 1000 }: { onStatus?: (s: string) => void; timeoutMs?: number } = {},
) {
  const started = Date.now();
  let delay = 1000;
  while (Date.now() - started < timeoutMs) {
    await sleep(delay);
    const job = await api(`/jobs/${job_id}`);
    if (job.status === "done") return job.result;
    if (job.status === "failed") throw new Error(JSON.stringify({ detail: job.error }));
    onStatus?.(job.status);
    delay = Math.min(delay * 1.5, 5000);
  }
  throw new Error(JSON.stringify({ detail: "This is taking longer than expected. Please check back in a minute." }));
}

/**
 * Stream a doubt answer over SSE-style chunks.
 * EventSource can't send the auth header, so we read the POST response body manually.
 *
 * onToken(textChunk), onStatus(text), onMeta(meta), onDone(), onError(message)
 * signal: an AbortSignal — aborting stops the stream quietly (no onError).
 *
 * meta (sent once, after the answer): {doubt_id, citations: [{source, page}],
 * answerable, confidence: "high"|"medium"|"low"|null, conversation_id, provider}
 */
export async function streamDoubt(payload: any, { onToken, onStatus, onMeta, onDone, onError, signal }: any = {}) {
  try {
    const res = await withAuthRetry(async () =>
      fetch(`${API_URL}/doubt/stream`, {
        method: "POST",
        headers: await authHeaders(),
        body: JSON.stringify(payload),
        signal,
      }),
    );
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
    if (e?.name === "AbortError") {
      onDone?.();
      return;
    }
    onError?.(navigator.onLine === false
      ? "You're offline. Check your connection and try again."
      : "Couldn't reach the server. Please try again.");
  }
}

export { API_URL };
