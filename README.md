# QA Onboarding Digital — Repositorio semilla

Repositorio de evaluacion tecnica para el rol de Analista de QA. Cubre la
estrategia de pruebas para una plataforma de onboarding digital de comercios
con arquitectura AWS (API Gateway, Lambda, DynamoDB, SQS) e integraciones externas.

## Requisitos previos

| Herramienta | Version minima | Verificar con |
|---|---|---|
| Python | 3.11 | `py --version` |
| pip | cualquiera | `py -m pip --version` |
| k6 | 0.50+ | `k6 version` |
| Git | cualquiera | `git --version` |

> k6 instalacion: https://grafana.com/docs/k6/latest/set-up/install-k6/

## Instalacion

```bash
# 1. Clonar el repositorio
git clone <url-del-repo>
cd qa-onboarding-digital

# 2. Copiar variables de entorno
cp config/.env.example .env

# 3. Instalar dependencias Python
py -m pip install -r requirements.txt

# 4. Instalar navegador para pruebas E2E
py -m playwright install chromium
```

## Variables de entorno

El archivo `.env` (copiado de `config/.env.example`) contiene todos los valores
necesarios para ejecutar las pruebas localmente. **No requiere credenciales reales.**

| Variable | Valor de ejemplo | Descripcion |
|---|---|---|
| `API_BASE_URL` | `https://reqres.in/api` | API publica de practica (tracking) |
| `FAKESTORE_BASE_URL` | `https://fakestoreapi.com` | API publica de practica (catalogo) |
| `PAYMENT_MOCK_HOST` | `127.0.0.1` | Host del mock de pago local |
| `PAYMENT_MOCK_PORT` | `8001` | Puerto del mock de pago local |
| `QUEUE_MOCK_HOST` | `127.0.0.1` | Host del simulador de cola local |
| `QUEUE_MOCK_PORT` | `8002` | Puerto del simulador de cola local |
| `QUEUE_PROCESSING_DELAY_MS` | `200` | Retraso de procesamiento en ms |
| `E2E_BASE_URL` | `https://www.saucedemo.com` | Aplicacion proxy para E2E |
| `E2E_USERNAME` | `standard_user` | Usuario de practica (publico) |
| `E2E_PASSWORD` | `secret_sauce` | Contrasena de practica (publica) |
| `E2E_HEADLESS` | `true` | Ejecutar navegador sin UI |

## Comandos de ejecucion

### Pruebas de API
```bash
py -m pytest tests/api/ -v --html=reports/api-report.html --self-contained-html
```

### Prueba transaccional de idempotencia (criterio minimo de aprobacion)

> Requiere el mock de pago corriendo. 

```bash
# Terminal 1 — levantar el mock
py mocks/payment_server.py
```

```bash
# Terminal 2 — ejecutar los tests
py -m pytest tests/transactional/ -v --html=reports/transactional-report.html --self-contained-html
```

### Pruebas de asincronismo y colas

> Requiere el simulador de cola corriendo. Abre **dos terminales**:

```bash
# Terminal 1 — levantar el simulador
py mocks/queue_simulator.py
```

```bash
# Terminal 2 — ejecutar los tests
py -m pytest tests/async_sim/ -v --html=reports/async-report.html --self-contained-html
```

### Prueba E2E (flujo completo de onboarding)
```bash
py -m pytest tests/e2e/ -v --html=reports/e2e-report.html --self-contained-html
```

### Escenario de carga (requiere k6 instalado)
```bash
# Levanta el mock de pago en background y ejecuta la carga
py mocks/payment_server.py &
k6 run --env TARGET_HOST=http://127.0.0.1:8001 tests/load/onboarding_load.js
```

### Ejecucion completa (API + transaccional + async, sin dependencias externas extra)
```bash
py -m pytest tests/api/ tests/transactional/ tests/async_sim/ -v \
  --html=reports/full-report.html --self-contained-html
```

## Ubicacion de evidencias

| Evidencia | Ruta |
|---|---|
| Reporte HTML de API | `reports/api-report.html` |
| Reporte HTML transaccional | `reports/transactional-report.html` |
| Reporte HTML async | `reports/async-report.html` |
| Reporte HTML E2E | `reports/e2e-report.html` |
| Reporte HTML completo | `reports/full-report.html` |
| Resumen JSON de carga (k6) | `reports/load-summary.json` |

## Estructura del repositorio

```
qa-onboarding-digital/
├── .github/workflows/ci.yml     # Pipeline CI con GitHub Actions
├── strategy/                    # Documento de estrategia PDF
├── tests/
│   ├── api/                     # Pruebas de API (reqres.in + fakestoreapi)
│   ├── transactional/           # Idempotencia del callback de pago
│   ├── e2e/                     # Flujo E2E (saucedemo.com como proxy)
│   ├── async_sim/               # Simulacion de colas asincronas
│   └── load/                    # Escenario de carga k6
├── mocks/
│   ├── payment_server.py        # Mock FastAPI del servicio de pagos
│   └── queue_simulator.py       # Simulador de cola SQS
├── config/
│   ├── settings.py              # Configuracion parametrizable por ambiente
│   └── .env.example             # Plantilla de variables de entorno
├── conftest.py                  # Fixtures globales (arranque de mocks)
├── pytest.ini                   # Configuracion de pytest
├── requirements.txt             # Dependencias Python
└── Makefile                     # Comandos abreviados
```

## Decisiones de diseno

### Lenguaje y herramientas
**Python + pytest** para API, transaccional y async: alinea con el stack Lambda/Python
del proyecto real. Un solo lenguaje reduce la friccion cognitiva del equipo de desarrollo
al revisar las pruebas.

**Playwright (Python)** para E2E: permite usar el mismo lenguaje del resto del proyecto.
Se eligio sobre Selenium por mejor soporte de auto-espera y APIs modernas.

**k6** para carga: los umbrales se expresan como codigo JavaScript ejecutable, lo que
permite bloquear el pipeline automaticamente cuando se superan. 

**FastAPI** para los mocks locales: levanta en menos de 1 segundo, expone endpoints
observables (`/counter`, `/state`) que las pruebas consultan para verificar el
comportamiento sin esperas fijas.

### Asincronismo sin sleeps fijos
El simulador de cola introduce retrasos configurables via `QUEUE_PROCESSING_DELAY_MS`.
Las pruebas usan `poll_until_state()` con backoff exponencial (0.1s → 2s max, timeout
de 10s). Un timeout alcanzado cuenta como fallo, no como falso positivo.

### Aislamiento de pruebas
- Cada prueba llama a `/reset` en su `autouse fixture` (antes y despues).
- Las pruebas E2E limpian `localStorage` + `sessionStorage` + cookies entre cada test.
- Los mocks levantan una sola vez por sesion (scope `session`) pero su estado se limpia
  por prueba individual (scope `function`).

### Aplicacion proxy para E2E
Se uso `saucedemo.com` como proxy del flujo real. La correspondencia entre pasos esta
documentada en el docstring de cada test. Esta decision permite demostrar la estructura
de pruebas E2E sin requerir acceso a sistemas reales.

### Que haria con mas tiempo

1. **Prueba de seguridad de logs**: verificar automaticamente que los campos sensibles
   (documento de identidad, numero de tarjeta, llaves AWS) no aparecen en los logs.
2. **Prueba de estado intermedio**: forzar el fallo de DynamoDB durante una escritura
   y verificar que el proceso de recuperacion es correcto.
3. **Reportes en el pipeline**: integrar Allure para reportes con historial y tendencias.
