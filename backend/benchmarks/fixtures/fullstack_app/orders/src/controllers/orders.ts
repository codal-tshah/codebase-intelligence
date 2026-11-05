import Redis from "ioredis";

const cache = new Redis();

export async function listOrders(req: any, res: any) {
  const cached = await cache.get("orders");
  res.json(cached ?? []);
}

export async function createOrder(req: any, res: any) {
  await fetch("https://api.stripe.com/v1/payment_intents", { method: "POST" });
  res.status(201).json({});
}
