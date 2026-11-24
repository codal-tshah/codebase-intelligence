"use client";

import { useEffect } from "react";

export default function Home() {
  useEffect(() => {
    fetch("/api/items");
  }, []);
  return <main>Home</main>;
}