"""
Mock del servicio de pagos (Ecommerce callback).

Simula el endpoint que recibe notificaciones de pago desde la plataforma de
comercio electronico. El invariante critico: una misma clave de idempotencia
debe producir exactamente un cobro logico, sin importar cuantas veces llegue
la notificacion.

Expone:
  POST /notify          recibe la notificacion de pago
  GET  /status/{key}    devuelve el estado del pago para una clave dada
  GET  /counter         devuelve cuantas operaciones fueron realmente procesadas
  POST /reset           limpia el estado (usado en teardown de pruebas)
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn
import threading
from config.settings import PAYMENT_MOCK_HOST, PAYMENT_MOCK_PORT

app = FastAPI(title="Payment Mock Server")

# Estado en memoria (suficiente para pruebas locales aisladas)
_processed: dict[str, dict] = {}
_lock = threading.Lock()


class PaymentNotification(BaseModel):
    idempotency_key: str
    amount: float
    currency: str = "COP"
    merchant_tracking_id: str
    status: str = "APPROVED"


@app.post("/notify", status_code=200)
def receive_notification(payload: PaymentNotification):
    with _lock:
        if payload.idempotency_key in _processed:
            return {
                "result": "DUPLICATE_IGNORED",
                "idempotency_key": payload.idempotency_key,
                "message": "Notificacion ya procesada. No se genera un segundo cobro.",
            }

        _processed[payload.idempotency_key] = {
            "merchant_tracking_id": payload.merchant_tracking_id,
            "amount": payload.amount,
            "currency": payload.currency,
            "status": payload.status,
        }

    return {
        "result": "PROCESSED",
        "idempotency_key": payload.idempotency_key,
        "message": "Pago registrado correctamente.",
    }


@app.get("/status/{idempotency_key}")
def get_status(idempotency_key: str):
    with _lock:
        record = _processed.get(idempotency_key)
    if not record:
        raise HTTPException(status_code=404, detail="Clave de idempotencia no encontrada.")
    return {"idempotency_key": idempotency_key, **record}


@app.get("/counter")
def get_counter():
    with _lock:
        return {"processed": len(_processed)}


@app.post("/reset", status_code=204)
def reset():
    with _lock:
        _processed.clear()


if __name__ == "__main__":
    uvicorn.run(app, host=PAYMENT_MOCK_HOST, port=PAYMENT_MOCK_PORT, log_level="warning")
