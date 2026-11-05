import express from "express";
import ordersRouter from "./routes/orders";

const app = express();
app.use("/v1/orders", ordersRouter);
app.get("/status", (req, res) => res.json({ ok: true }));
app.listen(3000);
