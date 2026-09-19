"""
Prueba E2E — Flujo completo de Onboarding (proxy sobre saucedemo.com)

Correspondencia entre el flujo real y la aplicacion de practica:

  Onboarding Digital (real)              saucedemo.com (proxy)
  ─────────────────────────────────────  ──────────────────────────────────────
  Inicio del proceso / identificacion    Login con credenciales del comercio
  Seleccion de equipo POS                Seleccion de producto del catalogo
  Calculo de precio y total              Vista del carrito con precio calculado
  Registro de direccion de entrega       Paso de informacion de envio (checkout)
  Confirmacion de la orden / pago        Pantalla de orden completada

Limitaciones documentadas:
  - saucedemo.com no tiene integracion real con Ecommerce ni con AWS.
  - Los datos ingresados son sinteticos y no alteran sistemas de terceros.
  - La validacion de idempotencia de pago se cubre en tests/transactional/.

Ejecucion: pytest tests/e2e/ -v
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
from playwright.sync_api import Page, expect, sync_playwright

from config.settings import E2E_BASE_URL, E2E_HEADLESS, E2E_PASSWORD, E2E_USERNAME

# Datos sinteticos de comercio (nunca datos reales)
MERCHANT_DATA = {
    "first_name": "Demo",
    "last_name": "Comercio",
    "postal_code": "110111",
}


def _slow_mo() -> float:
    return float(os.getenv("E2E_SLOW_MO", "0"))


@pytest.fixture(scope="module")
def browser_context():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=E2E_HEADLESS, slow_mo=_slow_mo())
        context = browser.new_context(viewport={"width": 1280, "height": 720})
        yield context
    context.close()
    browser.close()


@pytest.fixture
def page(browser_context):
    page = browser_context.new_page()
    yield page
    # Limpieza completa: localStorage + sessionStorage + cookies
    # Necesario porque saucedemo persiste el carrito en localStorage
    # El try-catch en JS evita excepciones de Python si la pagina ya esta cerrada
    page.evaluate("() => { try { localStorage.clear(); sessionStorage.clear(); } catch(_) {} }")
    browser_context.clear_cookies()
    page.close()


class TestFlujoOnboardingCompleto:

    def test_paso1_inicio_proceso_login_exitoso(self, page: Page):
        """
        Onboarding real: inicio del proceso y generacion del tracking ID.
        Proxy: login con credenciales validas del comercio.
        """
        page.goto(E2E_BASE_URL)
        page.fill("#user-name", E2E_USERNAME)
        page.fill("#password", E2E_PASSWORD)
        page.click("#login-button")

        expect(page).to_have_url(f"{E2E_BASE_URL}/inventory.html")
        expect(page.locator(".inventory_list")).to_be_visible()

    def test_paso2_seleccion_equipo_pos(self, page: Page):
        """
        Onboarding real: el comercio selecciona el modelo de equipo POS.
        Proxy: el comercio selecciona un producto del catalogo.
        """
        page.goto(E2E_BASE_URL)
        page.fill("#user-name", E2E_USERNAME)
        page.fill("#password", E2E_PASSWORD)
        page.click("#login-button")

        # Seleccionar el primer equipo disponible
        first_item = page.locator(".inventory_item").first
        product_name = first_item.locator(".inventory_item_name").inner_text()
        product_price = first_item.locator(".inventory_item_price").inner_text()

        first_item.locator("button").click()

        # Verificar que el carrito refleja la seleccion
        cart_badge = page.locator(".shopping_cart_badge")
        expect(cart_badge).to_have_text("1")

        assert product_name, "El nombre del equipo POS debe estar presente"
        assert product_price.startswith("$"), "El precio debe tener formato monetario"

    def test_paso3_calculo_total_carrito(self, page: Page):
        """
        Onboarding real: calculo de precio, impuestos y total de la compra.
        Proxy: vista del carrito con desglose de precio.
        """
        page.goto(E2E_BASE_URL)
        page.fill("#user-name", E2E_USERNAME)
        page.fill("#password", E2E_PASSWORD)
        page.click("#login-button")

        page.locator(".inventory_item button").first.click()
        page.click(".shopping_cart_link")

        expect(page).to_have_url(f"{E2E_BASE_URL}/cart.html")

        cart_items = page.locator(".cart_item")
        expect(cart_items).to_have_count(1)

        item_price = page.locator(".inventory_item_price").first.inner_text()
        assert item_price, "El precio del equipo debe ser visible en el carrito"

    def test_paso4_registro_direccion_entrega(self, page: Page):
        """
        Onboarding real: registro de direccion de entrega y georreferencia.
        Proxy: formulario de informacion de envio en el checkout.
        """
        page.goto(E2E_BASE_URL)
        page.fill("#user-name", E2E_USERNAME)
        page.fill("#password", E2E_PASSWORD)
        page.click("#login-button")

        page.locator(".inventory_item button").first.click()
        page.click(".shopping_cart_link")
        page.click("#checkout")

        expect(page).to_have_url(f"{E2E_BASE_URL}/checkout-step-one.html")

        # Ingresa datos del comercio (sinteticos)
        page.fill("#first-name", MERCHANT_DATA["first_name"])
        page.fill("#last-name", MERCHANT_DATA["last_name"])
        page.fill("#postal-code", MERCHANT_DATA["postal_code"])
        page.click("#continue")

        expect(page).to_have_url(f"{E2E_BASE_URL}/checkout-step-two.html")

    def test_paso5_confirmacion_pago_exitosa(self, page: Page):
        """
        Onboarding real: recepcion y validacion del resultado del pago.
        Equivalente a recibir APPROVED del Ecommerce y actualizar el tracking.
        """
        page.goto(E2E_BASE_URL)
        page.fill("#user-name", E2E_USERNAME)
        page.fill("#password", E2E_PASSWORD)
        page.click("#login-button")

        page.locator(".inventory_item button").first.click()
        page.click(".shopping_cart_link")
        page.click("#checkout")
        page.fill("#first-name", MERCHANT_DATA["first_name"])
        page.fill("#last-name", MERCHANT_DATA["last_name"])
        page.fill("#postal-code", MERCHANT_DATA["postal_code"])
        page.click("#continue")
        page.click("#finish")

        expect(page).to_have_url(f"{E2E_BASE_URL}/checkout-complete.html")

        confirmation = page.locator(".complete-header")
        expect(confirmation).to_be_visible()
        expect(confirmation).to_contain_text("Thank you")

    def test_flujo_completo_punta_a_punta(self, page: Page):
        """
        Recorrido completo del flujo de Onboarding en un solo test.
        Valida que cada transicion de estado ocurre correctamente.
        """
        page.goto(E2E_BASE_URL)

        # Paso 1: Login (inicio del proceso)
        page.fill("#user-name", E2E_USERNAME)
        page.fill("#password", E2E_PASSWORD)
        page.click("#login-button")
        expect(page.locator(".inventory_list")).to_be_visible()

        # Paso 2: Seleccion del equipo POS
        page.locator(".inventory_item button").first.click()
        expect(page.locator(".shopping_cart_badge")).to_have_text("1")

        # Paso 3: Calculo del carrito
        page.click(".shopping_cart_link")
        expect(page.locator(".cart_item")).to_have_count(1)

        # Paso 4: Registro de direccion
        page.click("#checkout")
        page.fill("#first-name", MERCHANT_DATA["first_name"])
        page.fill("#last-name", MERCHANT_DATA["last_name"])
        page.fill("#postal-code", MERCHANT_DATA["postal_code"])
        page.click("#continue")

        # Verificar resumen antes de confirmar
        expect(page.locator(".summary_info")).to_be_visible()

        # Paso 5: Confirmacion del pago
        page.click("#finish")
        expect(page.locator(".complete-header")).to_contain_text("Thank you")

    # ─── Casos negativos E2E ──────────────────────────────────────────────────

    def test_login_invalido_muestra_error(self, page: Page):
        """
        Un comercio con credenciales invalidas no debe acceder al proceso.
        Onboarding real: validacion de identidad fallida en el primer paso.
        """
        page.goto(E2E_BASE_URL)
        page.fill("#user-name", "usuario_invalido")
        page.fill("#password", "clave_incorrecta")
        page.click("#login-button")

        error = page.locator("[data-test='error']")
        expect(error).to_be_visible()
        expect(page).not_to_have_url(f"{E2E_BASE_URL}/inventory.html")

    def test_checkout_sin_datos_de_envio_muestra_error(self, page: Page):
        """
        No debe ser posible completar el proceso sin registrar la direccion.
        Onboarding real: validacion de la direccion de entrega obligatoria.
        """
        page.goto(E2E_BASE_URL)
        page.fill("#user-name", E2E_USERNAME)
        page.fill("#password", E2E_PASSWORD)
        page.click("#login-button")
        page.locator(".inventory_item button").first.click()
        page.click(".shopping_cart_link")
        page.click("#checkout")

        # Intentar continuar sin completar el formulario
        page.click("#continue")

        error = page.locator("[data-test='error']")
        expect(error).to_be_visible()
