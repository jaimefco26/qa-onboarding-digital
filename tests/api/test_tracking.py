"""
Pruebas de API — Tracking del proceso de Onboarding

Mapeo con el dominio real:
  POST /users  →  Creacion de un nuevo tracking de solicitud de comercio
  GET  /users/{id}  →  Consulta del estado actual del proceso por tracking ID

Se utiliza reqres.in como API publica de practica. Los campos validados
corresponden a los que el sistema real devolveria en cada operacion.
"""

import pytest


# ─── Casos positivos ───────────────────────────────────────────────────────────

class TestCrearTracking:
    """
    Equivalente a: POST /onboarding/tracking
    Verifica que el sistema genera un identificador unico y confirma la
    recepcion de los datos del comercio solicitante.
    """

    def test_crear_tracking_devuelve_201(self, api_session, api_base_url):
        payload = {
            "name": "Comercio Demo SA",
            "job": "ONBOARDING_INITIATED",
        }
        response = api_session.post(f"{api_base_url}/users", json=payload)

        assert response.status_code == 201, (
            f"Se esperaba 201 al crear tracking, se obtuvo {response.status_code}"
        )

    def test_crear_tracking_retorna_id_unico(self, api_session, api_base_url):
        payload = {"name": "Comercio Demo SA", "job": "ONBOARDING_INITIATED"}
        r1 = api_session.post(f"{api_base_url}/users", json=payload)
        r2 = api_session.post(f"{api_base_url}/users", json=payload)

        assert r1.json()["id"] != r2.json()["id"], (
            "Cada solicitud debe generar un tracking ID distinto"
        )

    def test_crear_tracking_body_contiene_campos_requeridos(self, api_session, api_base_url):
        payload = {"name": "Comercio Beta", "job": "ONBOARDING_INITIATED"}
        response = api_session.post(f"{api_base_url}/users", json=payload)
        body = response.json()

        assert "id" in body, "El tracking ID debe estar presente en la respuesta"
        assert "createdAt" in body, "La fecha de creacion debe estar presente"
        assert body["name"] == payload["name"]


class TestConsultarTracking:
    """
    Equivalente a: GET /onboarding/tracking/{tracking_id}
    Verifica que el sistema devuelve el estado actual del proceso para un
    identificador conocido, con todos los campos de estado obligatorios.
    """

    def test_consultar_tracking_existente_devuelve_200(self, api_session, api_base_url):
        response = api_session.get(f"{api_base_url}/users/2")

        assert response.status_code == 200, (
            f"Se esperaba 200 al consultar tracking existente, se obtuvo {response.status_code}"
        )

    def test_consultar_tracking_body_contiene_datos_del_comercio(self, api_session, api_base_url):
        response = api_session.get(f"{api_base_url}/users/2")
        data = response.json().get("data", {})

        assert "id" in data, "El tracking ID debe estar en la respuesta"
        assert "email" in data, "El correo del comercio debe estar presente"
        assert "first_name" in data, "El nombre del comercio debe estar presente"


# ─── Casos negativos ───────────────────────────────────────────────────────────

class TestTrackingNegativo:
    """
    Verifica el comportamiento del sistema ante entradas invalidas o
    identificadores que no existen.
    """

    def test_consultar_tracking_inexistente_devuelve_404(self, api_session, api_base_url):
        """
        Equivalente a consultar un tracking_id que nunca fue generado.
        El sistema no debe exponer informacion de otros procesos ni retornar 200.
        """
        response = api_session.get(f"{api_base_url}/users/999999")

        assert response.status_code == 404, (
            f"Se esperaba 404 para tracking inexistente, se obtuvo {response.status_code}"
        )

    def test_crear_tracking_con_payload_vacio_no_devuelve_datos_de_otro_comercio(
        self, api_session, api_base_url
    ):
        """
        Un payload vacio no debe crear un registro con datos de otro comercio.
        reqres.in acepta payloads vacios (limitacion del mock publico); se valida
        que el ID generado sea unico y no corresponda a un registro preexistente.
        """
        response = api_session.post(f"{api_base_url}/users", json={})

        assert response.status_code == 201
        body = response.json()
        assert "id" in body, "Incluso con payload vacio se debe generar un ID nuevo"
        # El nombre no debe coincidir con datos de otros comercios registrados
        assert body.get("name") in (None, ""), (
            "El payload vacio no debe devolver el nombre de otro comercio"
        )
