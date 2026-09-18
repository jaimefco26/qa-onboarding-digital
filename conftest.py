"""
Fixtures globales compartidas por todos los modulos de prueba.

Los servidores mock se levantan una sola vez por sesion de pytest en hilos
daemon, de modo que se detienen automaticamente cuando el proceso termina.
Cada prueba es responsable de limpiar su propio estado llamando al endpoint
/reset en el teardown, garantizando independencia y repetibilidad.
"""

import os
import sys
import threading
import time

import pytest
import requests
import uvicorn

sys.path.insert(0, os.path.dirname(__file__))

from config.settings import (
    PAYMENT_MOCK_HOST,
    PAYMENT_MOCK_PORT,
    QUEUE_MOCK_HOST,
    QUEUE_MOCK_PORT,
)


def _start_server(app, host, port):
    config = uvicorn.Config(app, host=host, port=port, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    # Espera activa hasta que el servidor acepta conexiones
    for _ in range(30):
        try:
            requests.get(f"http://{host}:{port}/counter", timeout=1)
            break
        except (ConnectionError, OSError):
            time.sleep(0.2)


@pytest.fixture(scope="session", autouse=True)
def payment_mock_server():
    from mocks.payment_server import app
    _start_server(app, PAYMENT_MOCK_HOST, PAYMENT_MOCK_PORT)
    yield
    # El hilo daemon se termina con el proceso


@pytest.fixture(scope="session", autouse=True)
def queue_mock_server():
    from mocks.queue_simulator import app
    _start_server(app, QUEUE_MOCK_HOST, QUEUE_MOCK_PORT)
    yield
