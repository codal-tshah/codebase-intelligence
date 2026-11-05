const API = "/api";

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API}${path}`);
  return res.json();
}

export const api = {
  listItems: () => getJson(`/api/items/`),
  getItem: (id: string) => fetch(`/api/items/${id}`).then((r) => r.json()),
  checkout: (itemId: number) =>
    fetch("/api/orders/", { method: "POST", body: JSON.stringify({ itemId }) }),
};
