"""
Simulador de cola asincrona (proxy de Amazon SQS para pruebas locales).

Modela el comportamiento de los procesos asincronos del flujo de Onboarding:
actualizacion de inventario, asignacion de MID, generacion de contratos, etc.

El simulador procesa mensajes con un retraso configurable y mantiene un
registro de estados para que las pruebas validen el resultado final sin
depender de esperas fijas (usan polling con backoff exponencial).

Expone:
  POST /publish            encola un mensaje
  GET  /state/{message_id} devuelve el estado actual del mensaje
  GET  /messages           lista todos los mensajes registrados
  POST /reset              limpia el estado (teardown de pruebas)
"""

import os
import sys
import threading
import time
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from config.settings import QUEUE_MOCK_HOST, QUEUE_MOCK_PORT, QUEUE_PROCESSING_DELAY_MS

app = FastAPI(title="Queue Simulator")

_messages: dict[str, dict] = {}
_seen_idempotency_keys: set[str] = set()
_lock = threading.Lock()

STATES = ["PENDING", "PROCESSING", "COMPLETED", "FAILED"]


class QueueMessage(BaseModel):
    idempotency_key: str
    event_type: str           # e.g. INVENTORY_UPDATE, MID_ASSIGNMENT, CONTRACT_GEN
    payload: dict
    simulate_failure: bool = False


def _process_async(message_id: str, delay_ms: int, simulate_failure: bool):
    time.sleep(delay_ms / 1000)

    with _lock:
        if message_id not in _messages:
            return
        _messages[message_id]["state"] = "PROCESSING"

    time.sleep(delay_ms / 1000)

    with _lock:
        if message_id not in _messages:
            return
        if simulate_failure:
            _messages[message_id]["state"] = "FAILED"
            _messages[message_id]["retries"] = _messages[message_id].get("retries", 0) + 1
        else:
            _messages[message_id]["state"] = "COMPLETED"


@app.post("/publish", status_code=202)
def publish(msg: QueueMessage):
    with _lock:
        if msg.idempotency_key in _seen_idempotency_keys:
            existing_id = next(
                mid for mid, m in _messages.items()
                if m["idempotency_key"] == msg.idempotency_key
            )
            return {
                "result": "DUPLICATE_IGNORED",
                "message_id": existing_id,
                "idempotency_key": msg.idempotency_key,
            }

        message_id = str(uuid.uuid4())
        _seen_idempotency_keys.add(msg.idempotency_key)
        _messages[message_id] = {
            "idempotency_key": msg.idempotency_key,
            "event_type": msg.event_type,
            "payload": msg.payload,
            "state": "PENDING",
            "retries": 0,
        }

    threading.Thread(
        target=_process_async,
        args=(message_id, QUEUE_PROCESSING_DELAY_MS, msg.simulate_failure),
        daemon=True,
    ).start()

    return {"result": "QUEUED", "message_id": message_id}


@app.get("/state/{message_id}")
def get_state(message_id: str):
    with _lock:
        record = _messages.get(message_id)
    if not record:
        raise HTTPException(status_code=404, detail="Mensaje no encontrado.")
    return {"message_id": message_id, **record}


@app.get("/messages")
def list_messages():
    with _lock:
        return list(_messages.values())


@app.post("/reset", status_code=204)
def reset():
    with _lock:
        _messages.clear()
        _seen_idempotency_keys.clear()


if __name__ == "__main__":
    uvicorn.run(app, host=QUEUE_MOCK_HOST, port=QUEUE_MOCK_PORT, log_level="warning")
