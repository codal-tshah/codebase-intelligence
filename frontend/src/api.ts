export const API = "/api";

async function parse<T>(res: Response): Promise<T> {
  const body = await res.json().catch(() => ({}));
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

export const getJson = <T,>(path: string): Promise<T> => fetch(`${API}${path}`).then((r) => parse<T>(r));

export const postJson = <T,>(path: string, body: unknown): Promise<T> =>
  fetch(`${API}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).then((r) => parse<T>(r));
