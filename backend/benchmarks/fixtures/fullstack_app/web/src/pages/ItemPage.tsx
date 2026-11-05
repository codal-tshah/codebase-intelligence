import { useEffect, useState } from "react";
import { api } from "../api/client";
import { ItemCard } from "../components/ItemCard";

export default function ItemPage() {
  const [item, setItem] = useState<any>(null);
  useEffect(() => {
    api.getItem("1").then(setItem);
  }, []);
  return item ? <ItemCard name={item.name} onBuy={() => api.checkout(item.id)} /> : null;
}
