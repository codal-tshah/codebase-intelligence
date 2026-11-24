export async function relay() {
  await fetch("http://localhost:8000/orders");
}