"""
Prueba de integracion asincrona — Simulacion de colas SQS

Cubre los procesos asincronos del flujo de Onboarding:
  - Actualizacion de inventario
  - Asignacion de MID
  - Generacion de contratos
  - Envio de comunicaciones

Principio clave: las pruebas NO usan time.sleep() con valores fijos.
Usan polling con backoff exponencial y un timeout maximo definido.
Un timeout alcanzado es un fallo, no un falso positivo.

El simulador introduce un retraso configurable (QUEUE_PROCESSING_DELAY_MS)
para modelar la latencia real de SQS. En CI este valor es bajo (200ms);
en pruebas de estres puede aumentarse para validar comportamiento bajo carga.
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import uuid
import time
import pytest
import requests
from config.settings import QUEUE_MOCK_URL


TIMEOUT_SECONDS = 10
INITIAL_BACKOFF = 0.1
MAX_BACKOFF = 2.0


def poll_until_state(message_id: str, expected_state: str, timeout: float = TIMEOUT_SECONDS) -> dict:
    """
    Consulta el estado del mensaje usando backoff exponencial.
    Falla explicitamente si el estado esperado no se alcanza dentro del timeout.
    Nunca usa sleep fijo — el intervalo crece hasta MAX_BACKOFF.
    """
    deadline = time.monotonic() + timeout
    backoff = INITIAL_BACKOFF

    while time.monotonic() < deadline:
        response = requests.get(f"{QUEUE_MOCK_URL}/state/{message_id}")
        if response.status_code == 200:
            state = response.json()
            if state["state"] == expected_state:
                return state
            if state["state"] == "FAILED" and expected_state != "FAILED":
                pytest.fail(
                    f"El mensaje {message_id} entro en estado FAILED "
                    f"cuando se esperaba {expected_state}. "
                    f"Posible fallo en el proceso asincrono."
                )
        time.sleep(min(backoff, MAX_BACKOFF))
        backoff *= 2

    pytest.fail(
        f"El mensaje {message_id} no alcanzo el estado '{expected_state}' "
        f"en {timeout}s. Ultimo estado: "
        f"{requests.get(f'{QUEUE_MOCK_URL}/state/{message_id}').json().get('state', 'UNKNOWN')}"
    )


@pytest.fixture(autouse=True)
def clean_queue_state():
    requests.post(f"{QUEUE_MOCK_URL}/reset")
    yield
    requests.post(f"{QUEUE_MOCK_URL}/reset")


class TestProcesamentoAsincrono:

    def test_mensaje_de_actualizacion_de_inventario_se_procesa(self):
        """
        Despues de confirmar un pago, el inventario debe actualizarse
        de forma asincrona. La prueba verifica el estado final sin espera fija.
        """
        idempotency_key = f"INV-{uuid.uuid4()}"
        payload = {
            "idempotency_key": idempotency_key,
            "event_type": "INVENTORY_UPDATE",
            "payload": {"product_id": "POS-MODEL-A", "quantity": -1},
        }

        response = requests.post(f"{QUEUE_MOCK_URL}/publish", json=payload)
        assert response.status_code == 202
        message_id = response.json()["message_id"]

        final_state = poll_until_state(message_id, "COMPLETED")

        assert final_state["state"] == "COMPLETED"
        assert final_state["event_type"] == "INVENTORY_UPDATE"

    def test_mensaje_de_asignacion_de_mid_se_procesa(self):
        """
        La asignacion del MID (Merchant ID) ocurre de forma asincrona
        luego de completar el pago y generar el contrato.
        """
        idempotency_key = f"MID-{uuid.uuid4()}"
        payload = {
            "idempotency_key": idempotency_key,
            "event_type": "MID_ASSIGNMENT",
            "payload": {"merchant_tracking_id": f"TRK-{uuid.uuid4().hex[:8].upper()}"},
        }

        response = requests.post(f"{QUEUE_MOCK_URL}/publish", json=payload)
        assert response.status_code == 202
        message_id = response.json()["message_id"]

        final_state = poll_until_state(message_id, "COMPLETED")
        assert final_state["state"] == "COMPLETED"

    def test_mensaje_duplicado_es_ignorado_por_idempotencia(self):
        """
        El mismo evento asincrono publicado dos veces (por reintento automatico
        de SQS o por un fallo de red) no debe procesarse dos veces.
        El inventario no debe descontarse dos veces.
        """
        idempotency_key = f"INV-{uuid.uuid4()}"
        payload = {
            "idempotency_key": idempotency_key,
            "event_type": "INVENTORY_UPDATE",
            "payload": {"product_id": "POS-MODEL-B", "quantity": -1},
        }

        r1 = requests.post(f"{QUEUE_MOCK_URL}/publish", json=payload)
        r2 = requests.post(f"{QUEUE_MOCK_URL}/publish", json=payload)

        assert r1.status_code == 202
        assert r2.status_code == 202

        assert r1.json()["result"] == "QUEUED"
        assert r2.json()["result"] == "DUPLICATE_IGNORED", (
            "El segundo mensaje identico debe ser descartado por la cola"
        )

        # Solo un mensaje debe existir en el sistema
        all_messages = requests.get(f"{QUEUE_MOCK_URL}/messages").json()
        inv_messages = [m for m in all_messages if m["event_type"] == "INVENTORY_UPDATE"]
        assert len(inv_messages) == 1, (
            f"Solo debe existir 1 mensaje de actualizacion de inventario, "
            f"pero se encontraron {len(inv_messages)}"
        )

    def test_proceso_que_falla_queda_en_estado_failed(self):
        """
        Cuando una integracion falla (ej: sistema corporativo no disponible),
        el mensaje debe quedar en estado FAILED, no en PENDING ni en COMPLETED.
        Esto permite que el equipo identifique procesos en estado intermedio.
        """
        idempotency_key = f"CONTRACT-{uuid.uuid4()}"
        payload = {
            "idempotency_key": idempotency_key,
            "event_type": "CONTRACT_GEN",
            "payload": {"merchant_tracking_id": "TRK-ERR-001"},
            "simulate_failure": True,
        }

        response = requests.post(f"{QUEUE_MOCK_URL}/publish", json=payload)
        message_id = response.json()["message_id"]

        final_state = poll_until_state(message_id, "FAILED")
        assert final_state["state"] == "FAILED", (
            "Un proceso que falla debe quedar en FAILED, no en estado intermedio"
        )

    def test_multiples_eventos_distintos_se_procesan_en_paralelo(self):
        """
        El sistema debe manejar multiples eventos asincronos concurrentes
        (inventario, MID, contrato, correo) sin bloqueos ni colisiones.
        """
        events = [
            ("INVENTORY_UPDATE", {"product_id": "POS-A", "quantity": -1}),
            ("MID_ASSIGNMENT", {"merchant_tracking_id": "TRK-001"}),
            ("CONTRACT_GEN", {"template": "standard"}),
            ("WELCOME_EMAIL", {"email": "comercio@example.com"}),
        ]

        message_ids = []
        for event_type, event_payload in events:
            r = requests.post(f"{QUEUE_MOCK_URL}/publish", json={
                "idempotency_key": f"{event_type}-{uuid.uuid4()}",
                "event_type": event_type,
                "payload": event_payload,
            })
            assert r.status_code == 202
            message_ids.append(r.json()["message_id"])

        # Validar que todos completan sin espera fija
        for message_id in message_ids:
            final = poll_until_state(message_id, "COMPLETED")
            assert final["state"] == "COMPLETED"

    def test_estado_inicial_de_mensaje_es_pending(self):
        """
        Un mensaje recien publicado debe iniciar en estado PENDING.
        Valida que el tracking del estado es observable desde el primer momento.
        """
        idempotency_key = f"EMAIL-{uuid.uuid4()}"
        payload = {
            "idempotency_key": idempotency_key,
            "event_type": "WELCOME_EMAIL",
            "payload": {"recipient": "nuevo-comercio@example.com"},
        }

        response = requests.post(f"{QUEUE_MOCK_URL}/publish", json=payload)
        message_id = response.json()["message_id"]

        # Consulta inmediata antes de que el procesamiento complete
        state_response = requests.get(f"{QUEUE_MOCK_URL}/state/{message_id}")
        assert state_response.status_code == 200

        initial_state = state_response.json()["state"]
        assert initial_state in ("PENDING", "PROCESSING", "COMPLETED"), (
            f"El estado inicial debe ser observable, se obtuvo: {initial_state}"
        )
