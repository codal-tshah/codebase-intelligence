import { Router } from "express";
import { createOrder, listOrders } from "../controllers/orders";
import { requireAuth } from "../middleware/auth";

const router = Router();
router.get("/", listOrders);
router.post("/", requireAuth, createOrder);
router.get("/:id", (req, res) => {
  listOrders(req, res);
});

export default router;
