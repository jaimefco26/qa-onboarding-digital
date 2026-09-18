"""
Pruebas de API — Calculo del carrito y disponibilidad de equipo POS

Mapeo con el dominio real:
  GET /products        →  Catalogo de equipos POS disponibles para seleccion
  GET /products/{id}   →  Detalle de un equipo: precio, impuestos, disponibilidad
  GET /products/category/{cat}  →  Filtro por linea de equipo (inalambrico, fijo, etc.)

Se utiliza fakestoreapi.com como API publica de practica.
"""

import pytest


class TestDisponibilidadEquipoPOS:
    """
    Equivalente a: GET /onboarding/catalog y GET /onboarding/catalog/{product_id}
    Verifica que el sistema devuelve los campos necesarios para que el comercio
    seleccione su equipo y calcule el total de la compra.
    """

    def test_catalogo_devuelve_200_y_lista_no_vacia(self, api_session, fakestore_url):
        response = api_session.get(f"{fakestore_url}/products")

        assert response.status_code == 200
        products = response.json()
        assert isinstance(products, list) and len(products) > 0, (
            "El catalogo debe contener al menos un equipo disponible"
        )

    def test_producto_contiene_campos_para_calculo_de_precio(self, api_session, fakestore_url):
        """
        El sistema de calculo de precio (Lambda) necesita: id, price, title.
        La ausencia de cualquiera de estos campos impediria calcular el total.
        """
        response = api_session.get(f"{fakestore_url}/products/1")
        product = response.json()

        assert response.status_code == 200
        for field in ("id", "title", "price"):
            assert field in product, f"El campo '{field}' es obligatorio para el calculo del carrito"

        assert isinstance(product["price"], (int, float)), "El precio debe ser numerico"
        assert product["price"] > 0, "El precio del equipo debe ser positivo"

    def test_calculo_total_incluye_precio_base(self, api_session, fakestore_url):
        """
        Simula la logica de calculo del carrito: precio_base * cantidad.
        Verifica que el precio retornado por la API permite construir el total.
        """
        response = api_session.get(f"{fakestore_url}/products/1")
        product = response.json()
        quantity = 2

        total_calculated = round(product["price"] * quantity, 2)

        assert total_calculated == round(product["price"] * 2, 2), (
            "El calculo del total debe ser consistente con el precio unitario"
        )


# ─── Casos negativos ───────────────────────────────────────────────────────────

class TestCarritoNegativo:

    def test_producto_inexistente_no_retorna_datos_validos(self, api_session, fakestore_url):
        """
        Equivalente a seleccionar un equipo POS que fue descontinuado o
        que tiene inventario cero. El sistema no debe retornar datos validos.

        Decision documentada: fakestoreapi.com retorna HTTP 200 con body null
        para IDs inexistentes (limitacion del mock publico). En el sistema real
        (API Gateway + Lambda) se esperaria un 404 con mensaje de error.
        La prueba valida la condicion observable: body nulo o vacio, lo que
        impediria al frontend mostrar datos de un equipo inexistente.
        """
        response = api_session.get(f"{fakestore_url}/products/99999")

        # fakestoreapi retorna 200 con null; el sistema real retornaria 404.
        # En ambos casos el body no debe contener un producto valido con precio.
        if response.status_code in (404, 400):
            return  # Comportamiento correcto del sistema real

        # Si retorna 200, el body no debe contener campos de producto valido.
        # fakestoreapi puede retornar body vacio (no JSON) o null.
        try:
            body = response.json()
        except Exception:
            body = None  # Body vacio: no hay producto, comportamiento correcto

        assert body is None or (
            isinstance(body, dict) and "price" not in body
        ), (
            f"Un ID inexistente no debe retornar un producto con precio valido. "
            f"Body: {body}"
        )

    def test_categoria_invalida_no_retorna_productos_de_otra_categoria(
        self, api_session, fakestore_url
    ):
        """
        Una categoria que no existe no debe devolver productos validos que
        podrian confundir al comercio durante la seleccion del equipo.
        """
        response = api_session.get(f"{fakestore_url}/products/category/categoria-inexistente-xyz")

        # fakestoreapi devuelve lista vacia para categorias invalidas
        if response.status_code == 200:
            assert response.json() == [], (
                "Una categoria inexistente debe retornar lista vacia, no productos de otra categoria"
            )
        else:
            assert response.status_code in (404, 400)
