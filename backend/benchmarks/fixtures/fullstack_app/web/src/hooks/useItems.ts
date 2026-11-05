import { useEffect, useState } from "react";
import { api } from "../api/client";

export function useItems() {
  const [items, setItems] = useState([]);
  useEffect(() => {
    api.listItems().then(setItems);
  }, []);
  return items;
}
