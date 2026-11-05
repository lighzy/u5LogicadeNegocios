import http.server
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

# Asegurar importación de src
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from src.application import OrderService
from src.domain import CustomerHasDebt, Order
from src.repository import SqlOrderRepository, make_engine
from src.security import can_cancel
from sqlalchemy.orm import Session

# Base de datos en memoria para el servidor
engine = make_engine()
order_counter = 1

class MockPaymentGateway:
    def __init__(self, succeed=True):
        self.succeed = succeed

    def charge(self, amount):
        return self.succeed

HTML_PAGE = """<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Unidad 5 - Lógica de Negocio | Panel Interactivo</title>
    <style>
        :root {
            --primary: #2563eb;
            --primary-hover: #1d4ed8;
            --bg: #f8fafc;
            --card-bg: #ffffff;
            --text: #1e293b;
            --muted: #64748b;
            --success: #16a34a;
            --danger: #dc2626;
            --border: #e2e8f0;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; }
        body { background: var(--bg); color: var(--text); padding: 2rem 1rem; line-height: 1.5; }
        .container { max-width: 900px; margin: 0 auto; }
        header { text-align: center; margin-bottom: 2rem; }
        header h1 { font-size: 2rem; color: #0f172a; margin-bottom: 0.5rem; }
        header p { color: var(--muted); font-size: 1.1rem; }
        .badge { display: inline-block; background: #dbeafe; color: #1e40af; padding: 0.25rem 0.75rem; border-radius: 9999px; font-size: 0.875rem; font-weight: 600; margin-top: 0.5rem; }
        
        .grid { display: grid; grid-template-columns: 1fr; gap: 1.5rem; }
        @media(min-width: 768px) { .grid { grid-template-columns: 1fr 1fr; } }
        
        .card { background: var(--card-bg); border: 1px solid var(--border); border-radius: 12px; padding: 1.5rem; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05); }
        .card h2 { font-size: 1.25rem; margin-bottom: 1rem; color: #0f172a; border-bottom: 2px solid #f1f5f9; padding-bottom: 0.5rem; }
        
        .form-group { margin-bottom: 1rem; }
        label { display: block; font-weight: 500; font-size: 0.9rem; margin-bottom: 0.35rem; color: #334155; }
        input[type="number"], select { width: 100%; padding: 0.6rem 0.75rem; border: 1px solid var(--border); border-radius: 6px; font-size: 1rem; outline: none; }
        input[type="number"]:focus, select:focus { border-color: var(--primary); ring: 2px solid #bfdbfe; }
        .checkbox-label { display: flex; align-items: center; gap: 0.5rem; cursor: pointer; font-size: 0.95rem; }
        .checkbox-label input { width: 18px; height: 18px; }
        
        button { background: var(--primary); color: white; border: none; border-radius: 6px; padding: 0.75rem 1.25rem; font-size: 1rem; font-weight: 600; cursor: pointer; width: 100%; transition: background 0.2s; }
        button:hover { background: var(--primary-hover); }
        button.secondary { background: #475569; margin-top: 0.5rem; }
        button.secondary:hover { background: #334155; }
        
        .result-box { margin-top: 1rem; padding: 1rem; border-radius: 8px; font-size: 0.95rem; display: none; }
        .result-box.success { background: #dcfce7; border: 1px solid #bbf7d0; color: #166534; display: block; }
        .result-box.error { background: #fee2e2; border: 1px solid #fecaca; color: #991b1b; display: block; }
        
        .full-width { grid-column: 1 / -1; }
        pre { background: #0f172a; color: #f8fafc; padding: 1rem; border-radius: 8px; overflow-x: auto; font-size: 0.85rem; max-height: 250px; }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>📦 Sistema de Pedidos y Lógica de Negocio</h1>
            <p>Servidor local activo en <code>http://localhost:8000</code></p>
            <span class="badge">Unidad 5 CLN - Ejecución en vivo</span>
        </header>

        <div class="grid">
            <!-- Sección 1: Crear y Procesar Pedido -->
            <div class="card">
                <h2>🛒 Procesar Pedido (Checkout)</h2>
                <form id="orderForm">
                    <div class="form-group">
                        <label for="total">Total del pedido ($):</label>
                        <input type="number" id="total" value="100.00" step="0.01" required>
                    </div>
                    <div class="form-group">
                        <label class="checkbox-label">
                            <input type="checkbox" id="vip" checked>
                            Cliente VIP (15% de descuento)
                        </label>
                    </div>
                    <div class="form-group">
                        <label for="debt">Deuda pendiente del cliente ($):</label>
                        <input type="number" id="debt" value="0.00" step="0.01">
                    </div>
                    <div class="form-group">
                        <label for="gatewaySuccess">Pasarela de Pago:</label>
                        <select id="gatewaySuccess">
                            <option value="true">Aprobada (Simulación OK)</option>
                            <option value="false">Rechazada (Falla de cobro)</option>
                        </select>
                    </div>
                    <button type="submit">Ejecutar Checkout</button>
                </form>
                <div id="orderResult" class="result-box"></div>
            </div>

            <!-- Sección 2: Reglas de Cancelación -->
            <div class="card">
                <h2>🛡️ Regla de Negocio: Cancelar Pedido</h2>
                <form id="cancelForm">
                    <div class="form-group">
                        <label for="orderStatus">Estado del Pedido:</label>
                        <select id="orderStatus">
                            <option value="NEW">NEW (Nuevo)</option>
                            <option value="CONFIRMED">CONFIRMED (Confirmado)</option>
                            <option value="SHIPPED">SHIPPED (Enviado)</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label class="checkbox-label">
                            <input type="checkbox" id="isAdmin">
                            Usuario es Administrador
                        </label>
                    </div>
                    <div class="form-group">
                        <label for="hoursAgo">Horas transcurridas desde creación:</label>
                        <input type="number" id="hoursAgo" value="5" min="0" max="72">
                    </div>
                    <div class="form-group">
                        <label class="checkbox-label">
                            <input type="checkbox" id="isOwner" checked>
                            El usuario es el dueño del pedido
                        </label>
                    </div>
                    <button type="submit">Verificar Cancelación</button>
                </form>
                <div id="cancelResult" class="result-box"></div>
            </div>

            <!-- Sección 3: Tests y Cobertura -->
            <div class="card full-width">
                <h2>🧪 Verificación de Tests del Proyecto</h2>
                <p style="margin-bottom: 1rem; color: var(--muted);">Ejecuta la suite de pruebas unitarias y cobertura de código del proyecto.</p>
                <button type="button" class="secondary" id="btnRunTests" style="width: auto;">Ejecutar Pytest en Vivo</button>
                <div id="testOutputContainer" style="margin-top: 1rem; display: none;">
                    <pre><code id="testOutput">Ejecutando pruebas...</code></pre>
                </div>
            </div>
        </div>
    </div>

    <script>
        document.getElementById('orderForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            const resBox = document.getElementById('orderResult');
            resBox.className = 'result-box';
            resBox.style.display = 'none';

            const payload = {
                total: parseFloat(document.getElementById('total').value),
                vip: document.getElementById('vip').checked,
                debt: parseFloat(document.getElementById('debt').value || 0),
                gateway_ok: document.getElementById('gatewaySuccess').value === 'true'
            };

            try {
                const response = await fetch('/api/order/checkout', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                const data = await response.json();
                if (data.ok) {
                    resBox.className = 'result-box success';
                    resBox.innerHTML = `<strong>Éxito:</strong> ${data.message}<br>` +
                        `<ul>` +
                        `<li>ID Pedido: <b>#${data.order_id}</b></li>` +
                        `<li>Total original: $${data.total.toFixed(2)}</li>` +
                        `<li>Descuento VIP aplicado: $${data.discount.toFixed(2)}</li>` +
                        `<li>Monto final cobrado: <b>$${data.final_amount.toFixed(2)}</b></li>` +
                        `<li>Estado: <b>${data.status}</b></li>` +
                        `</ul>`;
                } else {
                    resBox.className = 'result-box error';
                    resBox.innerHTML = `<strong>Error de Lógica de Negocio:</strong> ${data.error}`;
                }
            } catch (err) {
                resBox.className = 'result-box error';
                resBox.innerText = 'Error al comunicarse con el servidor.';
            }
        });

        document.getElementById('cancelForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            const resBox = document.getElementById('cancelResult');
            resBox.className = 'result-box';

            const payload = {
                status: document.getElementById('orderStatus').value,
                is_admin: document.getElementById('isAdmin').checked,
                hours_ago: parseFloat(document.getElementById('hoursAgo').value || 0),
                is_owner: document.getElementById('isOwner').checked
            };

            try {
                const response = await fetch('/api/order/cancel-check', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                const data = await response.json();
                if (data.can_cancel) {
                    resBox.className = 'result-box success';
                    resBox.innerHTML = `<strong>Cancelación Permitida:</strong> ${data.reason}`;
                } else {
                    resBox.className = 'result-box error';
                    resBox.innerHTML = `<strong>Cancelación Denegada:</strong> ${data.reason}`;
                }
            } catch (err) {
                resBox.className = 'result-box error';
                resBox.innerText = 'Error al consultar regla.';
            }
        });

        document.getElementById('btnRunTests').addEventListener('click', async () => {
            const container = document.getElementById('testOutputContainer');
            const output = document.getElementById('testOutput');
            container.style.display = 'block';
            output.innerText = 'Corriendo pytest con cobertura... por favor espera...';
            try {
                const response = await fetch('/api/run-tests');
                const text = await response.text();
                output.innerText = text;
            } catch (err) {
                output.innerText = 'Error al ejecutar pytest: ' + err;
            }
        });
    </script>
</body>
</html>
"""

class RequestHandler(http.server.BaseHTTPRequestHandler):
    def _send_json(self, data, status=200):
        body = json.dumps(data).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(body)

    def do_HEAD(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()

    def do_GET(self):
        url = urlparse(self.path)
        if url.path == '/':
            body = HTML_PAGE.encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif url.path == '/api/run-tests':
            # Ejecutar pytest en subprocess
            try:
                res = subprocess.run(
                    [sys.executable, "-m", "pytest", "-v", "--cov=src", "--cov-report=term-missing"],
                    cwd=os.path.dirname(os.path.abspath(__file__)),
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                output = (res.stdout or "") + ("\n" + res.stderr if res.stderr else "")
            except Exception as e:
                output = f"Error ejecutando pruebas: {str(e)}"
            
            body = output.encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_error(404, "Not Found")

    def do_POST(self):
        global order_counter
        url = urlparse(self.path)
        length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(length)
        try:
            data = json.loads(post_data.decode('utf-8'))
        except Exception:
            data = {}

        if url.path == '/api/order/checkout':
            total = float(data.get('total', 0))
            vip = bool(data.get('vip', False))
            debt = float(data.get('debt', 0))
            gateway_ok = bool(data.get('gateway_ok', True))

            try:
                order = Order(total=total, vip=vip)
                gateway = MockPaymentGateway(succeed=gateway_ok)
                service = OrderService(gateway)

                # Confirmar y cobrar
                order.confirm(customer_debt=debt)
                if not gateway.charge(order.total - order.discount):
                    raise RuntimeError("payment rejected")

                # Guardar en repositorio
                current_id = order_counter
                order_counter += 1
                with Session(engine) as session:
                    repo = SqlOrderRepository(session)
                    repo.save(current_id, order)
                    session.commit()

                self._send_json({
                    "ok": True,
                    "message": "¡Pedido procesado y confirmado con éxito!",
                    "order_id": current_id,
                    "total": order.total,
                    "vip": order.vip,
                    "discount": order.discount,
                    "final_amount": order.total - order.discount,
                    "status": order.status
                })
            except CustomerHasDebt:
                self._send_json({"ok": False, "error": "El cliente tiene deuda pendiente (outstanding debt). No se puede confirmar el pedido."}, status=400)
            except ValueError as ve:
                self._send_json({"ok": False, "error": str(ve)}, status=400)
            except RuntimeError as re:
                self._send_json({"ok": False, "error": f"Fallo en la pasarela de pagos: {str(re)}"}, status=400)
            except Exception as e:
                self._send_json({"ok": False, "error": f"Error inesperado: {str(e)}"}, status=500)

        elif url.path == '/api/order/cancel-check':
            status = data.get('status', 'NEW')
            is_admin = bool(data.get('is_admin', False))
            hours_ago = float(data.get('hours_ago', 0))
            is_owner = bool(data.get('is_owner', True))

            owner_id = 1
            user_id = 1 if is_owner else 2

            now = datetime.now(timezone.utc)
            created_at = now - timedelta(hours=hours_ago)

            allowed = can_cancel(
                status=status,
                owner_id=owner_id,
                user_id=user_id,
                is_admin=is_admin,
                created_at=created_at,
                now=now
            )

            if status == "SHIPPED":
                reason = "El pedido ya fue enviado (SHIPPED). Por regla de negocio, ningún pedido enviado puede cancelarse (ni siquiera por administradores)."
            elif is_admin:
                reason = "El usuario es Administrador y el pedido no está enviado. Cancelación autorizada."
            elif not is_owner:
                reason = "El usuario no es el dueño del pedido ni es administrador. Acción rechazada."
            elif hours_ago >= 24:
                reason = "Han pasado más de 24 horas desde la creación del pedido. La ventana de cancelación expiró."
            else:
                reason = "El usuario es el dueño del pedido y está dentro de las 24 horas permitidas. Cancelación autorizada."

            self._send_json({
                "can_cancel": allowed,
                "reason": reason
            })
        else:
            self.send_error(404, "Not Found")

def run(port=8000):
    server_address = ('', port)
    httpd = http.server.HTTPServer(server_address, RequestHandler)
    print(f"Servidor iniciado en http://localhost:{port}")
    httpd.serve_forever()

if __name__ == '__main__':
    run(8000)
