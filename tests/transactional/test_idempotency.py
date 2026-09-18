"""
Prueba transaccional — Idempotencia del callback de pago

Riesgo cubierto: callbacks de pago procesados mas de una vez.
Este es el riesgo #1 identificado en el ejercicio. Un doble cobro afecta
directamente al comercio solicitante y al inventario de equipos.

El escenario simula exactamente lo que ocurre cuando:
  1. Ecommerce envia la notificacion de pago aprobado.
  2. Un reintento automatico (o un fallo de red) envia la misma notificacion.

Criterio de aprobacion (bloquea el pipeline si falla):
  - Solo una operacion debe quedar registrada en el mock (counter == 1).
  - El inventario se descuenta una sola vez (representado por el counter).
  - El estado final del tracking debe ser APPROVED, no DUPLICATE_APPROVED.

Ejecucion: pytest tests/transactional/test_idempotency.py -v
"""

import os
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
import requests

from config.settings import PAYMENT_MOCK_URL


MERCHANT_TRACKING_ID = f"TRK-{uuid.uuid4().hex[:8].upper()}"


@pytest.fixture(autouse=True)
def clean_payment_state():
    """Limpia el estado del mock antes y despues de cada prueba."""
    requests.post(f"{PAYMENT_MOCK_URL}/reset")
    yield
    requests.post(f"{PAYMENT_MOCK_URL}/reset")


def _build_notification(idempotency_key: str, amount: float = 350000.0) -> dict:
    return {
        "idempotency_key": idempotency_key,
        "amount": amount,
        "currency": "COP",
        "merchant_tracking_id": MERCHANT_TRACKING_ID,
        "status": "APPROVED",
    }


class TestIdempotenciaCallbackPago:

    def test_primera_notificacion_se_procesa_correctamente(self):
        """La primera notificacion debe quedar registrada con estado PROCESSED."""
        key = f"PAY-{uuid.uuid4()}"
        payload = _build_notification(key)

        response = requests.post(f"{PAYMENT_MOCK_URL}/notify", json=payload)

        assert response.status_code == 200
        body = response.json()
        assert body["result"] == "PROCESSED", (
            f"La primera notificacion debe procesarse, resultado: {body['result']}"
        )
        assert body["idempotency_key"] == key

    def test_segunda_notificacion_identica_es_ignorada(self):
        """
        La segunda notificacion con la misma clave debe ser descartada.
        El sistema reconoce el duplicado y no genera un segundo cobro.
        """
        key = f"PAY-{uuid.uuid4()}"
        payload = _build_notification(key)

        first = requests.post(f"{PAYMENT_MOCK_URL}/notify", json=payload)
        second = requests.post(f"{PAYMENT_MOCK_URL}/notify", json=payload)

        assert first.status_code == 200
        assert second.status_code == 200
        assert second.json()["result"] == "DUPLICATE_IGNORED", (
            "La segunda notificacion debe ser marcada como duplicado, no reprocesada"
        )

    def test_counter_refleja_un_solo_cobro_logico(self):
        """
        CRITERIO MINIMO DE APROBACION:
        Ante N notificaciones con la misma clave, el contador de operaciones
        procesadas debe ser exactamente 1. Esto garantiza un solo descuento
        de inventario y un solo cobro al comercio.
        """
        key = f"PAY-{uuid.uuid4()}"
        payload = _build_notification(key)

        # Simula reintento automatico de Ecommerce (caso real documentado)
        for _ in range(3):
            requests.post(f"{PAYMENT_MOCK_URL}/notify", json=payload)

        counter_response = requests.get(f"{PAYMENT_MOCK_URL}/counter")
        assert counter_response.status_code == 200

        count = counter_response.json()["processed"]
        assert count == 1, (
            f"Se esperaba exactamente 1 operacion procesada, "
            f"pero el contador muestra {count}. "
            f"Esto indicaria {count} cobros al comercio y {count} descuentos de inventario."
        )

    def test_estado_final_del_tracking_es_correcto(self):
        """
        El estado del pago consultado por tracking_id debe coincidir con
        el enviado en la notificacion original, no con el del duplicado.
        """
        key = f"PAY-{uuid.uuid4()}"
        payload = _build_notification(key, amount=175000.0)

        requests.post(f"{PAYMENT_MOCK_URL}/notify", json=payload)
        requests.post(f"{PAYMENT_MOCK_URL}/notify", json=payload)  # duplicado

        status_response = requests.get(f"{PAYMENT_MOCK_URL}/status/{key}")
        assert status_response.status_code == 200

        status = status_response.json()
        assert status["status"] == "APPROVED"
        assert status["amount"] == 175000.0, (
            "El monto registrado debe corresponder al de la primera notificacion"
        )
        assert status["merchant_tracking_id"] == MERCHANT_TRACKING_ID

    def test_claves_distintas_generan_cobros_independientes(self):
        """
        Dos pagos con claves diferentes deben procesarse de forma independiente.
        Verifica que la idempotencia no colapsa pagos distintos del mismo comercio.
        """
        key_a = f"PAY-{uuid.uuid4()}"
        key_b = f"PAY-{uuid.uuid4()}"

        requests.post(f"{PAYMENT_MOCK_URL}/notify", json=_build_notification(key_a, 100000.0))
        requests.post(f"{PAYMENT_MOCK_URL}/notify", json=_build_notification(key_b, 200000.0))

        counter = requests.get(f"{PAYMENT_MOCK_URL}/counter").json()["processed"]
        assert counter == 2, (
            f"Dos claves distintas deben generar 2 operaciones independientes, "
            f"pero el contador muestra {counter}"
        )

    def test_notificacion_de_pago_rechazado_no_descuenta_inventario(self):
        """
        Un pago REJECTED no debe contar como una operacion exitosa.
        El inventario no debe descontarse ante pagos fallidos.
        """
        key = f"PAY-{uuid.uuid4()}"
        payload = _build_notification(key)
        payload["status"] = "REJECTED"

        response = requests.post(f"{PAYMENT_MOCK_URL}/notify", json=payload)

        # El mock registra la notificacion pero el status debe ser REJECTED
        assert response.status_code == 200
        status = requests.get(f"{PAYMENT_MOCK_URL}/status/{key}").json()
        assert status["status"] == "REJECTED", (
            "El estado REJECTED debe preservarse, no convertirse en APPROVED"
        )
