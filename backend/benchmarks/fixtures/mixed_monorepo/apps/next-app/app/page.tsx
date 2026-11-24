import { SharedButton } from "@mixed/ui-shared";

async function loadItems() {
  const res = await fetch("http://localhost:8000/items");
  return res.json();
}

export default async function Page() {
  await loadItems();
  return <SharedButton />;
}