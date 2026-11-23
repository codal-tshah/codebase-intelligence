export const API = "/api";

/**
 * Server mode (`CI_MODE=server`) requires an API key on every request. The dashboard asks for it
 * once (see ApiKeyPrompt) and keeps it in sessionStorage: it survives reloads in this tab but is
 * dropped when the tab closes, and is never written to localStorage, cookies or the URL.
 */
const KEY_STORAGE = "ci.apiKey";
export const AUTH_REQUIRED_EVENT = "ci:auth-required";

export function getApiKey(): string | null {
  try {
    return window.sessionStorage.getItem(KEY_STORAGE);
  } catch {
    return null;
  }
}

export function setApiKey(key: string | null) {
  try {
    if (key) window.sessionStorage.setItem(KEY_STORAGE, key);
    else window.sessionStorage.removeItem(KEY_STORAGE);
  } catch {
    /* storage unavailable: the key lives only until the next reload */
  }
}

export function authHeaders(extra: Record<string, string> = {}): Record<string, string> {
  const key = getApiKey();
  return key ? { ...extra, "X-API-Key": key } : extra;
}

/** fetch() against the API with the key attached; announces a 401 so the UI can ask for a key. */
export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const res = await fetch(`${API}${path}`, {
    ...init,
    headers: authHeaders((init.headers as Record<string, string> | undefined) ?? {}),
  });
  if (res.status === 401) window.dispatchEvent(new Event(AUTH_REQUIRED_EVENT));
  return res;
}

async function parse<T>(res: Response): Promise<T> {
  const body: unknown = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = (body as { detail?: unknown }).detail;
    const msg =
      typeof detail === "string"
        ? detail
        : Array.isArray(detail)
          ? detail.map((d: { msg?: string }) => d.msg).join(", ")
          : `Request failed (${res.status})`;
    throw new Error(msg);
  }
  return body as T;
}

export const getJson = <T>(path: string): Promise<T> => apiFetch(path).then((r) => parse<T>(r));

export const postJson = <T>(path: string, body: unknown): Promise<T> =>
  apiFetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).then((r) => parse<T>(r));

/** PUT / PATCH / DELETE with a JSON body (or none). */
export const sendJson = <T>(method: "PUT" | "PATCH" | "DELETE" | "POST", path: string, body?: unknown): Promise<T> =>
  apiFetch(path, {
    method,
    headers: body === undefined ? {} : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  }).then((r) => parse<T>(r));

/** Save a blob as a file (no server round-trip, works with the API key header). */
export function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
