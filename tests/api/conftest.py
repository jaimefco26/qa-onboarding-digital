"""
Fixtures compartidas por los tests de API (tracking y carrito).
La sesion HTTP se reutiliza por modulo para evitar abrir una conexion por test.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
import requests

from config.settings import API_BASE_URL, FAKESTORE_BASE_URL


@pytest.fixture(scope="module")
def api_session():
    # Una sola sesion por modulo: reutiliza keep-alive y cabeceras comunes
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    yield session
    session.close()


@pytest.fixture
def api_base_url():
    return API_BASE_URL


@pytest.fixture
def fakestore_url():
    return FAKESTORE_BASE_URL
