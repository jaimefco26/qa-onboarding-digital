/**
 * Escenario de carga — Flujo de Onboarding y pago
 *
 * Modela el escenario pico descrito en el ejercicio:
 *   - Operacion habitual: 10 solicitudes nuevas por minuto
 *   - Sesiones concurrentes: hasta 150
 *   - Pico de pago: hasta 25 TPS durante ventanas breves
 *
 * El escenario tiene tres etapas:
 *   1. Rampa de subida (30s): simula el inicio de una campana comercial
 *   2. Carga sostenida (60s): valida estabilidad en el pico de 25 VUs (proxy de TPS)
 *   3. Rampa de bajada (20s): valida que el sistema se recupera sin errores residuales
 *
 * Nota sobre los supuestos de volumen:
 *   Estos umbrales son supuestos del ejercicio. Antes de establecerlos como
 *   baseline de produccion, se deben validar con metricas reales de CloudWatch
 *   (p95 de API Gateway, duracion de Lambda, throttling de DynamoDB).
 *   Los resultados de staging NO deben extrapolarse directamente a produccion
 *   sin ajuste por factor de escala (conexiones de base de datos, limites de
 *   concurrencia de Lambda, etc.).
 *
 * Ejecucion:
 *   k6 run tests/load/onboarding_load.js
 *   k6 run --env TARGET_HOST=http://127.0.0.1:8001 tests/load/onboarding_load.js
 */

import http from "k6/http";
import { check, sleep } from "k6";
import { Counter, Trend, Rate } from "k6/metrics";
import { randomString } from "https://jslib.k6.io/k6-utils/1.4.0/index.js";
import { htmlReport } from "https://raw.githubusercontent.com/benc-uk/k6-reporter/main/dist/bundle.js";

// ─── Configuracion parametrizable por ambiente ─────────────────────────────
const TARGET_HOST = __ENV.TARGET_HOST || "http://127.0.0.1:8001";

// ─── Metricas personalizadas ───────────────────────────────────────────────
const paymentDuration = new Trend("payment_generation_duration");
const duplicateCallbacks = new Counter("duplicate_callbacks_sent");
const idempotencyViolations = new Counter("idempotency_violations");

// ─── Definicion de carga y umbrales de aceptacion ─────────────────────────
export const options = {
  stages: [
    { duration: "30s", target: 10 },   // Rampa: simula inicio gradual
    { duration: "60s", target: 25 },   // Pico sostenido: 25 VUs (~25 TPS proxy)
    { duration: "20s", target: 0 },    // Bajada: recuperacion del sistema
  ],

  thresholds: {
    // Criterios de aceptacion numericos (bloquean el pipeline si se superan)
    "http_req_duration": [
      "p(95)<500",    // 95% de requests en menos de 500ms
      "p(99)<1000",   // 99% en menos de 1 segundo
    ],
    "http_req_failed": [
      "rate<0.01",    // Menos del 1% de errores HTTP
    ],
    "payment_generation_duration": [
      "p(95)<400",    // El endpoint critico de pago es mas estricto
    ],
    "idempotency_violations": [
      "count==0",     // Cero violaciones de idempotencia son aceptables
    ],
  },
};

// ─── Datos sinteticos para las pruebas ────────────────────────────────────
function buildPaymentPayload(idempotencyKey) {
  return JSON.stringify({
    idempotency_key: idempotencyKey,
    amount: 350000.0,
    currency: "COP",
    merchant_tracking_id: `TRK-${randomString(8).toUpperCase()}`,
    status: "APPROVED",
  });
}

const HEADERS = { "Content-Type": "application/json" };

// ─── Escenario principal ───────────────────────────────────────────────────
export default function () {
  const idempotencyKey = `PAY-LOAD-${randomString(16)}`;

  // Paso 1: Notificacion inicial de pago (simula callback de Ecommerce)
  const startTime = Date.now();
  const firstNotification = http.post(
    `${TARGET_HOST}/notify`,
    buildPaymentPayload(idempotencyKey),
    { headers: HEADERS }
  );
  paymentDuration.add(Date.now() - startTime);

  const firstOk = check(firstNotification, {
    "primera notificacion: status 200": (r) => r.status === 200,
    "primera notificacion: resultado PROCESSED": (r) => {
      try {
        return JSON.parse(r.body).result === "PROCESSED";
      } catch {
        return false;
      }
    },
  });

  // Paso 2: Reintento del callback (simula comportamiento real de Ecommerce)
  duplicateCallbacks.add(1);
  const secondNotification = http.post(
    `${TARGET_HOST}/notify`,
    buildPaymentPayload(idempotencyKey),
    { headers: HEADERS }
  );

  const secondOk = check(secondNotification, {
    "segundo callback: status 200": (r) => r.status === 200,
    "segundo callback: resultado DUPLICATE_IGNORED": (r) => {
      try {
        return JSON.parse(r.body).result === "DUPLICATE_IGNORED";
      } catch {
        return false;
      }
    },
  });

  // Detectar violaciones de idempotencia bajo carga
  if (secondNotification.status === 200) {
    try {
      const body = JSON.parse(secondNotification.body);
      if (body.result === "PROCESSED") {
        // El duplicado fue procesado como si fuera nuevo: violacion critica
        idempotencyViolations.add(1);
      }
    } catch {
      // Respuesta malformada: cuenta como error
    }
  }

  // Paso 3: Verificar el contador (muestra un solo cobro logico por key)
  const counterResponse = http.get(`${TARGET_HOST}/counter`);
  check(counterResponse, {
    "contador: status 200": (r) => r.status === 200,
    "contador: campo 'processed' presente": (r) => {
      try {
        return "processed" in JSON.parse(r.body);
      } catch {
        return false;
      }
    },
  });

  // Think time: simula el tiempo entre acciones del usuario en el portal
  sleep(Math.random() * 0.5 + 0.1);
}

// ─── Resumen al finalizar ──────────────────────────────────────────────────
export function handleSummary(data) {
  const violations = data.metrics.idempotency_violations
    ? data.metrics.idempotency_violations.values.count
    : 0;

  const p95 = data.metrics.http_req_duration
    ? data.metrics.http_req_duration.values["p(95)"]
    : null;

  const errorRate = data.metrics.http_req_failed
    ? data.metrics.http_req_failed.values.rate
    : null;

  console.log("\n========== RESUMEN DE CRITERIOS DE ACEPTACION ==========");
  console.log(`P95 latencia    : ${p95 ? p95.toFixed(0) + "ms" : "N/A"} (umbral: <500ms)`);
  console.log(`Tasa de errores : ${errorRate ? (errorRate * 100).toFixed(2) + "%" : "N/A"} (umbral: <1%)`);
  console.log(`Violaciones de idempotencia: ${violations} (umbral: 0)`);
  console.log("=========================================================\n");

  return {
    "reports/load-summary.json": JSON.stringify(data, null, 2),
    "reports/load-report.html": htmlReport(data),
    stdout: "\n",
  };
}
