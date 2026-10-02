"""
=============================================================================
Surazense Cancer Detection Backend - Stripe Webhook & Session Integration
=============================================================================
FastAPI module for Stripe Checkout Sessions and Webhook handling.

How to integrate into your main FastAPI app:
    from backend_stripe_service import init_stripe_routes, stripe_router
    # Method 1: Router with custom DB models
    init_stripe_routes(app, get_db=get_db, OrderModel=Order, OrderItemModel=OrderItem)
    # Method 2: Or simply include the router if using standard schema
    app.include_router(stripe_router)

Dependencies:
    pip install stripe fastapi sqlalchemy pydantic

Environment Variables:
    STRIPE_SECRET_KEY=sk_live_... (or sk_test_...)
    STRIPE_WEBHOOK_SECRET=whsec_... (from Stripe Dashboard > Developers > Webhooks)
    FRONTEND_URL=http://localhost:5173 (or your deployed frontend domain)
=============================================================================
"""

import os
import json
import logging
from datetime import datetime
from typing import Optional, List, Callable

from fastapi import APIRouter, Depends, HTTPException, Header, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
import stripe

# Logger setup
logger = logging.getLogger("stripe_service")
logger.setLevel(logging.INFO)

# Config from Environment
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")

stripe.api_key = STRIPE_SECRET_KEY

stripe_router = APIRouter(tags=["Stripe Checkout & Webhook"])

# Database dependency and model placeholders (configured via init_stripe_routes)
_get_db: Optional[Callable] = None
_OrderModel = None
_OrderItemModel = None
_PaymentTransactionModel = None


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------
class OrderItemPayload(BaseModel):
    product_id: Optional[int] = None
    product_name: str
    price: float
    quantity: int

class OrderCreatePayload(BaseModel):
    user_id: Optional[int] = None
    customer_name: str
    customer_email: str
    customer_phone: Optional[str] = None
    shipping_address: str
    payment_method: str = "Credit Card"
    payment_status: Optional[str] = "pending"
    items: List[OrderItemPayload]
    stripe_session_id: Optional[str] = None


# ---------------------------------------------------------------------------
# 1. Endpoint: สร้าง Stripe Checkout Session
# POST /api/checkout/create-session
# ---------------------------------------------------------------------------
@stripe_router.post("/api/checkout/create-session")
async def create_stripe_checkout_session(order_data: OrderCreatePayload):
    """
    สร้าง Stripe Checkout Session พร้อมผูก Metadata ข้อมูลผู้ซื้อ & รายการสินค้า
    (ใช้ dynamic payment methods ตาม Best Practices ของ Stripe)
    """
    current_key = os.getenv("STRIPE_SECRET_KEY", STRIPE_SECRET_KEY)
    if not current_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="STRIPE_SECRET_KEY is not configured on the server."
        )
    stripe.api_key = current_key

    frontend_base = os.getenv("FRONTEND_URL", FRONTEND_URL).rstrip("/")

    line_items = []
    for item in order_data.items:
        # Stripe expects amounts in satang (1 THB = 100 satang)
        unit_amount = int(round(item.price * 100))
        line_items.append({
            "price_data": {
                "currency": "thb",
                "product_data": {
                    "name": item.product_name,
                },
                "unit_amount": unit_amount,
            },
            "quantity": item.quantity,
        })

    # Summary metadata (limited to 500 chars)
    items_summary = [
        {"id": it.product_id, "name": it.product_name[:30], "price": it.price, "qty": it.quantity}
        for it in order_data.items
    ]

    try:
        # Stripe Best Practice: Omit payment_method_types to enable Dynamic Payment Methods (Card, PromptPay, etc.)
        session = stripe.checkout.Session.create(
            line_items=line_items,
            mode="payment",
            customer_email=order_data.customer_email,
            client_reference_id=str(order_data.user_id) if order_data.user_id else None,
            success_url=f"{frontend_base}/checkout?status=success&session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{frontend_base}/checkout?status=cancelled",
            locale="auto",
            metadata={
                "user_id": str(order_data.user_id or ""),
                "customer_name": order_data.customer_name[:100],
                "customer_email": order_data.customer_email[:100],
                "customer_phone": order_data.customer_phone or "",
                "shipping_address": order_data.shipping_address[:450],
                "items_json": json.dumps(items_summary)[:490],
            },
        )
        return {
            "checkout_url": session.url,
            "session_id": session.id,
        }
    except Exception as e:
        logger.error(f"Error creating Stripe checkout session: {e}")
        raise HTTPException(status_code=400, detail=str(e))


# ---------------------------------------------------------------------------
# 2. Endpoint: ค้นหา Order จาก Stripe Session ID (สำหรับ Frontend Polling)
# GET /api/orders/by-session/{session_id}
# ---------------------------------------------------------------------------
@stripe_router.get("/api/orders/by-session/{session_id}")
async def get_order_by_session(session_id: str, request: Request):
    if _OrderModel is None or _get_db is None:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Database model not initialized for Stripe session query."
        )
    
    # Get DB session generator
    db_gen = _get_db()
    db: Session = next(db_gen)
    try:
        order = db.query(_OrderModel).filter(
            getattr(_OrderModel, "stripe_session_id", None) == session_id
        ).first()
        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Order not found for this session ID"
            )
        return order
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 3. Endpoint: รับ Webhook Event จาก Stripe
# POST /webhook/stripe or /api/webhook/stripe
# ---------------------------------------------------------------------------
@stripe_router.post("/webhook/stripe")
@stripe_router.post("/api/webhook/stripe")
async def stripe_webhook(request: Request):
    """
    รับและตรวจสอบ Event จาก Stripe
    เมื่อ event คือ 'checkout.session.completed' จะบันทึก Order ลง Database อัตโนมัติ
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET", STRIPE_WEBHOOK_SECRET)

    if not webhook_secret:
        logger.warning("STRIPE_WEBHOOK_SECRET is not set. Skipping signature verification.")
        try:
            event = json.loads(payload.decode("utf-8"))
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid payload")
    else:
        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, webhook_secret
            )
        except stripe.error.SignatureVerificationError as e:
            logger.error(f"Webhook signature verification failed: {e}")
            raise HTTPException(status_code=400, detail="Invalid Stripe signature")
        except Exception as e:
            logger.error(f"Webhook error: {e}")
            raise HTTPException(status_code=400, detail=f"Webhook error: {str(e)}")

    event_type = event.get("type")
    logger.info(f"Received Stripe Event: {event_type}")

    if event_type == "checkout.session.completed":
        session = event["data"]["object"]
        session_id = session.get("id")

        if _OrderModel is None or _get_db is None:
            logger.warning("Database models not bound to Stripe webhook. Order creation delegated to frontend.")
            return {"status": "unbound_db", "session_id": session_id}

        db_gen = _get_db()
        db: Session = next(db_gen)
        try:
            # Check idempotency
            existing_order = db.query(_OrderModel).filter(
                getattr(_OrderModel, "stripe_session_id", None) == session_id
            ).first()

            if existing_order:
                logger.info(f"Order for session {session_id} already exists (ID: {existing_order.id}).")
                return {"status": "already_processed", "order_id": existing_order.id}

            metadata = session.get("metadata", {})
            customer_details = session.get("customer_details") or {}

            user_id_str = metadata.get("user_id") or session.get("client_reference_id")
            user_id = int(user_id_str) if (user_id_str and user_id_str.isdigit()) else None

            customer_name = (
                metadata.get("customer_name")
                or customer_details.get("name")
                or "Valued Customer"
            )
            customer_email = (
                metadata.get("customer_email")
                or customer_details.get("email")
                or session.get("customer_email")
                or ""
            )
            customer_phone = (
                metadata.get("customer_phone")
                or customer_details.get("phone")
                or ""
            )
            shipping_address = metadata.get("shipping_address") or "N/A"
            total_amount = (session.get("amount_total", 0) or 0) / 100.0

            new_order = _OrderModel(
                user_id=user_id,
                customer_name=customer_name,
                customer_email=customer_email,
                customer_phone=customer_phone,
                shipping_address=shipping_address,
                payment_method="Credit Card",
                payment_status="paid",
                order_status="confirmed",
                total_amount=total_amount,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )

            if hasattr(new_order, "stripe_session_id"):
                setattr(new_order, "stripe_session_id", session_id)

            db.add(new_order)
            db.flush()

            if _OrderItemModel is not None:
                items_json_str = metadata.get("items_json")
                if items_json_str:
                    try:
                        items_data = json.loads(items_json_str)
                        for it in items_data:
                            order_item = _OrderItemModel(
                                order_id=new_order.id,
                                product_id=it.get("id"),
                                product_name=it.get("name", "Product"),
                                price=float(it.get("price", 0)),
                                quantity=int(it.get("qty", 1)),
                            )
                            db.add(order_item)
                    except Exception as ex:
                        logger.warning(f"Could not parse items_json: {ex}")

            if _PaymentTransactionModel is not None:
                tx = _PaymentTransactionModel(
                    order_id=new_order.id,
                    gateway="stripe",
                    transaction_ref=session.get("payment_intent") or session_id,
                    amount=total_amount,
                    currency=session.get("currency", "THB").upper(),
                    status="completed",
                    payment_method="card",
                    raw_response=json.dumps({"session_id": session_id, "event_id": event.get("id")}),
                    created_at=datetime.utcnow(),
                )
                db.add(tx)

            db.commit()
            db.refresh(new_order)
            logger.info(f"✅ Successfully created Order #{new_order.id} from Stripe Webhook")
            return {"status": "success", "order_id": new_order.id}
        finally:
            db.close()

    return {"status": "ignored"}


# ---------------------------------------------------------------------------
# Helper to initialize router with app and DB models
# ---------------------------------------------------------------------------
def init_stripe_routes(app, get_db=None, OrderModel=None, OrderItemModel=None, PaymentTransactionModel=None):
    """
    Helper function to bind database models and include the stripe router into FastAPI app.
    Usage in main server file:
        init_stripe_routes(app, get_db=get_db, OrderModel=Order, OrderItemModel=OrderItem)
    """
    global _get_db, _OrderModel, _OrderItemModel, _PaymentTransactionModel
    _get_db = get_db
    _OrderModel = OrderModel
    _OrderItemModel = OrderItemModel
    _PaymentTransactionModel = PaymentTransactionModel
    app.include_router(stripe_router)

