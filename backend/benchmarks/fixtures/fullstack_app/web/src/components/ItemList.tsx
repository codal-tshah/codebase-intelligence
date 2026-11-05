import { api } from "@/api/client";
import { useItems } from "@/hooks/useItems";
import { ItemCard } from "./ItemCard";

export function ItemList() {
  const items = useItems();
  return (
    <ul>
      {items.map((it: any) => (
        <ItemCard key={it.id} name={it.name} onBuy={() => api.checkout(it.id)} />
      ))}
    </ul>
  );
}
