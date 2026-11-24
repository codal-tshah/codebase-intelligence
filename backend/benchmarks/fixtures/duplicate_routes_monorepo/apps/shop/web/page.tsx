export default async function ShopPage() {
  await fetch("http://localhost:8000/orders");
  return <main>Shop</main>;
}