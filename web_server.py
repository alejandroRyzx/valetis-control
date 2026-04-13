import json
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
from pathlib import Path
from datetime import datetime
import base64
import re

# Dependencias para cámara y OCR (Opcionales para no romper el servidor si no están instaladas)
try:
    import cv2
    import numpy as np
    import pytesseract
    
    # Descomentar y ajustar esta línea si corres el software en Windows y Tesseract no está en tus variables de entorno globales.
    # pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
    
    HAS_VISION = True
except ImportError:
    HAS_VISION = False


from core.database import DatabaseManager
from core.ticket_manager import TicketManager
from core.payment_manager import PaymentManager
from core.parking_manager import ParkingManager
from hardware.arduino_bridge import ArduinoBridge

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
REPORTS_DIR = BASE_DIR / "reports"
REGISTROS_DIR = REPORTS_DIR / "registros"
CIERRES_DIR = REPORTS_DIR / "cierres"

REPORTS_DIR.mkdir(parents=True, exist_ok=True)
REGISTROS_DIR.mkdir(parents=True, exist_ok=True)
CIERRES_DIR.mkdir(parents=True, exist_ok=True)


def calculate_parked_time(ticket):
    entry_dt = datetime.fromisoformat(ticket["entry_time"])
    end_dt = datetime.fromisoformat(ticket["exit_time"]) if ticket["exit_time"] else datetime.now()
    delta = end_dt - entry_dt

    total_minutes = int(delta.total_seconds() // 60)
    hours = total_minutes // 60
    minutes = total_minutes % 60

    return f"{hours}h {minutes}min"


def build_report_lines(report_title="=== REGISTRO DEL DIA ==="):
    tickets = ticket_manager.get_today_tickets()
    now = datetime.now()

    total_amount = 0.0
    lines = []
    lines.append(report_title)
    lines.append(f"Fecha: {now.strftime('%Y-%m-%d')}")
    lines.append(f"Hora de generación: {now.strftime('%H:%M:%S')}")
    lines.append("")

    if not tickets:
        lines.append("No hay registros hoy.")
    else:
        for ticket in tickets:
            entry = datetime.fromisoformat(ticket["entry_time"]).strftime("%Y-%m-%d %H:%M:%S")
            exit_time = (
                datetime.fromisoformat(ticket["exit_time"]).strftime("%Y-%m-%d %H:%M:%S")
                if ticket["exit_time"] else "Aún estacionado"
            )
            parked_time = calculate_parked_time(ticket)
            amount = float(ticket["amount_due"])
            total_amount += amount if ticket["paid"] else 0.0

            lines.append(f"Codigo: {ticket['code']}")
            lines.append(f"Placa: {ticket['plate']}")
            lines.append(f"Hora entrada: {entry}")
            lines.append(f"Hora salida: {exit_time}")
            lines.append(f"Tiempo estacionado: {parked_time}")
            lines.append(f"Espacio: {ticket['spot'] + 1 if ticket['spot'] is not None else 'No asignado'}")
            lines.append(f"Estado: {ticket['status']}")
            lines.append(f"Pagado: {'Si' if ticket['paid'] else 'No'}")
            lines.append(f"Monto: ${amount:.2f}")
            lines.append("-" * 40)

    lines.append("")
    lines.append(f"TOTAL COBRADO DEL DIA: ${total_amount:.2f}")
    return lines


def save_unique_report(base_dir: Path, prefix: str, lines):
    base_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"{prefix}_{timestamp}.txt"
    file_path = base_dir / filename

    with open(file_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"[OK] Archivo guardado en: {file_path}")
    return file_path


class APIHandler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200, "ok")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "X-Requested-With, Content-Type")
        self.end_headers()

    def send_json(self, status, payload):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/":
            self.serve_file(STATIC_DIR / "index.html", "text/html")
        elif path.startswith("/static/"):
            filepath = BASE_DIR / path.lstrip("/")
            self.serve_file(filepath)
        elif path == "/api/status":
            self.handle_get_status()
        elif path == "/api/tickets_today":
            self.handle_get_tickets_today()
        elif path == "/api/export_excel":
            self.handle_export_excel()
        elif path == "/api/download_report":
            self.handle_download_report()
        elif path == "/api/close_day":
            self.handle_close_day()
        elif path == "/api/open_day":
            self.handle_open_day()
        else:
            self.send_error(404, "Not Found")

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        content_length = int(self.headers.get("Content-Length", 0))
        post_data = self.rfile.read(content_length) if content_length > 0 else b"{}"

        try:
            data = json.loads(post_data.decode("utf-8"))
        except json.JSONDecodeError:
            data = {}

        if path == "/api/login":
            self.handle_login(data)
        elif path == "/api/entry":
            self.handle_entry(data)
        elif path == "/api/ticket":
            self.handle_get_ticket(data)
        elif path == "/api/payment_info":
            self.handle_payment_info(data)
        elif path == "/api/payment":
            self.handle_payment(data)
        elif path == "/api/exit":
            self.handle_exit(data)
        elif path == "/api/download_report":
            self.handle_download_report()
        elif path == "/api/close_day":
            self.handle_close_day()
        elif path == "/api/open_day":
            self.handle_open_day()
        elif path == "/api/recognize_plate":
            self.handle_recognize_plate(data)
        elif path == "/api/force_exit":
            self.handle_force_exit(data)
        elif path == "/api/manual_entry":
            self.handle_manual_entry()
        elif path == "/api/manual_exit":
            self.handle_manual_exit()
        else:
            self.send_error(404, "Not Found")

    def serve_file(self, filepath, content_type=None):
        if not filepath.exists() or filepath.is_dir():
            self.send_error(404, "File Not Found")
            return

        if not content_type:
            ext = filepath.suffix.lower()
            if ext == ".html":
                content_type = "text/html"
            elif ext == ".css":
                content_type = "text/css"
            elif ext == ".js":
                content_type = "application/javascript"
            elif ext == ".json":
                content_type = "application/json"
            else:
                content_type = "application/octet-stream"

        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.end_headers()

        with open(filepath, "rb") as f:
            self.wfile.write(f.read())

    def handle_get_status(self):
        system_closed = db.get_system_closed()
        spaces_list = []
        for code in parking_manager.spaces:
            if code is None:
                spaces_list.append(None)
            else:
                ticket = ticket_manager.get_ticket(code)
                plate = ticket["plate"] if ticket else code
                spaces_list.append({"code": code, "plate": plate})

        payload = {
            "system_closed": system_closed,
            "total_spaces": parking_manager.total_spaces,
            "available_spaces": parking_manager.available_spaces(),
            "spaces": spaces_list
        }
        self.send_json(200, payload)

    def handle_get_tickets_today(self):
        tickets = ticket_manager.get_today_tickets()
        system_closed = db.get_system_closed()
        self.send_json(200, {"tickets": tickets, "system_closed": system_closed})

    def handle_export_excel(self):
        from urllib.parse import urlparse, parse_qs
        import csv
        from io import StringIO
        
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        code = qs.get("code", [None])[0]
        
        if code:
            ticket = ticket_manager.get_ticket(code)
            if not ticket:
                self.send_error(404, "Ticket no encontrado")
                return
            tickets = [ticket]
            filename = f"detalle_ticket_{code}.csv"
        else:
            tickets = ticket_manager.get_today_tickets()
            filename = "historial_valetis.csv"
            
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(["Codigo", "Placa", "Hora Entrada", "Hora Salida", "Espacio", "Estado", "Monto", "Pagado", "Limite Salida"])
        for t in tickets:
            writer.writerow([
                t.get("code", ""), t.get("plate", ""), t.get("entry_time", ""), t.get("exit_time", ""),
                str(t.get("space_index", "")), t.get("status", ""), str(round(t.get("amount_due", 0.0), 2)),
                "Si" if t.get("paid") else "No", t.get("exit_deadline", "")
            ])
            
        csv_data = output.getvalue().encode('utf-8-sig') # Add BOM for Excel UTF-8 display
        
        self.send_response(200)
        self.send_header('Content-Type', 'text/csv; charset=utf-8')
        self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
        self.send_header('Content-Length', str(len(csv_data)))
        self.end_headers()
        self.wfile.write(csv_data)

    def handle_login(self, data):
        username = data.get("username", "")
        password = data.get("password", "")

        if username == "admin" and password == "admin123":
            self.send_json(200, {"token": "authenticated-token", "message": "Acceso Correcto"})
        else:
            self.send_json(401, {"error": "Credenciales inválidas"})

    def handle_entry(self, data):
        system_closed = db.get_system_closed()
        if system_closed:
            return self.send_json(400, {"error": "El sistema está cerrado."})

        if parking_manager.is_full():
            return self.send_json(400, {"error": "No hay espacios."})

        plate = data.get("plate", "").strip().upper()
        spot = data.get("spot")

        if not plate or spot is None:
            return self.send_json(400, {"error": "Placa y espacio requeridos."})

        try:
            spot = int(spot)
        except Exception:
            return self.send_json(400, {"error": "Espacio inválido."})

        if not (0 <= spot < parking_manager.total_spaces) or parking_manager.spaces[spot] is not None:
            return self.send_json(400, {"error": "Espacio inválido u ocupado."})

        ticket = ticket_manager.create_ticket(plate)

        if parking_manager.occupy_space(spot, ticket["code"]):
            ticket_manager.assign_spot(ticket["code"], spot)
            ticket = ticket_manager.get_ticket(ticket["code"])

            # SERVO 1 — ENTRADA
            if arduino:
                arduino.abrir_entrada()

            self.send_json(200, {
                "ticket": ticket,
                "message": f"Vehículo asignado a espacio {spot + 1}"
            })
        else:
            self.send_json(400, {"error": "Ocurrió un error al ocupar el espacio."})

    def handle_get_ticket(self, data):
        code = data.get("code", "").strip().upper()
        ticket = ticket_manager.get_ticket(code)

        if not ticket:
            return self.send_json(404, {"error": "Ticket no encontrado."})

        amount = payment_manager.calculate_amount(ticket)
        self.send_json(200, {
            "ticket": ticket,
            "amount": amount,
            "formatted": ticket_manager.format_ticket(ticket)
        })

    def handle_payment_info(self, data):
        code = data.get("code", "").strip().upper()
        ticket = ticket_manager.get_ticket(code)

        if not ticket:
            return self.send_json(404, {"error": "Ticket no encontrado."})

        if ticket_manager.is_expired(code):
            return self.send_json(400, {"error": "El ticket está vencido."})

        amount = payment_manager.calculate_amount(ticket)
        self.send_json(200, {"ticket": ticket, "amount": amount})

    def handle_payment(self, data):
        code = data.get("code", "").strip().upper()
        ticket = ticket_manager.get_ticket(code)

        if not ticket:
            return self.send_json(404, {"error": "Ticket no encontrado."})

        token = payment_manager.register_payment(ticket)
        ticket = ticket_manager.get_ticket(code)

        self.send_json(200, {
            "message": "Pago registrado exitosamente",
            "token": token,
            "ticket": ticket
        })

    def handle_exit(self, data):
        code = data.get("code", "").strip().upper()
        ticket = ticket_manager.get_ticket(code)

        if not ticket:
            return self.send_json(404, {"error": "Ticket no encontrado."})

        ok, message = payment_manager.can_exit(ticket)
        if not ok:
            return self.send_json(400, {"error": message})

        parking_manager.free_space_by_ticket(ticket["code"])
        ticket_manager.mark_used(ticket["code"])

        # SERVO 2 — SALIDA
        if arduino:
            arduino.abrir_salida()

        ticket = ticket_manager.get_ticket(code)
        self.send_json(200, {"message": "Vehículo salió correctamente.", "ticket": ticket})

    def handle_force_exit(self, data):
        code = data.get("code", "").strip().upper()
        ticket = ticket_manager.get_ticket(code)

        if not ticket:
            return self.send_json(404, {"error": "Ticket no encontrado."})

        parking_manager.free_space_by_ticket(ticket["code"])

        ticket["used"] = 1
        ticket["status"] = "FORZADO/LIBERADO"
        ticket["exit_time"] = datetime.now().isoformat()
        db.update_ticket(ticket)

        # SERVO 2 — SALIDA forzada
        if arduino:
            arduino.abrir_salida()

        return self.send_json(200, {"message": "El espacio fue liberado y el ticket desactivado correctamente."})

    def handle_manual_entry(self):
        if arduino:
            arduino.abrir_entrada()
        self.send_json(200, {"message": "Barrera de entrada abierta manualmente."})

    def handle_manual_exit(self):
        if arduino:
            arduino.abrir_salida()
        self.send_json(200, {"message": "Barrera de salida abierta manualmente."})

    def handle_download_report(self):
        try:
            lines = build_report_lines("=== REGISTRO DEL DIA ===")
            file_path = save_unique_report(REGISTROS_DIR, "registro", lines)
            self.send_json(200, {
                "message": "Registro generado correctamente",
                "file": str(file_path)
            })
        except Exception as e:
            print("[ERROR] handle_download_report:", e)
            self.send_json(500, {"error": f"No se pudo generar el registro: {str(e)}"})

    def handle_close_day(self):
        try:
            if db.get_system_closed():
                return self.send_json(400, {"error": "El cierre ya fue realizado."})

            lines = build_report_lines("=== CIERRE DE CAJA / DIA ===")
            file_path = save_unique_report(CIERRES_DIR, "cierre", lines)

            db.set_system_closed(True)

            self.send_json(200, {
                "message": "Cierre realizado correctamente",
                "file": str(file_path)
            })
        except Exception as e:
            print("[ERROR] handle_close_day:", e)
            self.send_json(500, {"error": f"No se pudo realizar el cierre: {str(e)}"})

    def handle_open_day(self):
        try:
            db.reset_system_closed()
            self.send_json(200, {"message": "Apertura realizada. Sistema habilitado."})
        except Exception as e:
            print("[ERROR] handle_open_day:", e)
            self.send_json(500, {"error": f"No se pudo abrir el sistema: {str(e)}"})

    def handle_recognize_plate(self, data):
        try:
            image_data = data.get("image", "")
            if not image_data:
                return self.send_json(400, {"error": "No se recibió imagen."})

            if "," in image_data:
                image_data = image_data.split(",")[1]

            import urllib.request
            import urllib.error

            app_id = "u454i168nm3j5M"
            api_key = "nxQDBePua5Uj3l9wrjA5BxsCIBUWpo6ifs8cYLlDLuxt7RSOBy"

            payload = {
                "application_id": app_id,
                "api_key": api_key,
                "image": image_data
            }

            req = urllib.request.Request(
                "https://zpk.systems/api/plate-scanner/image",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )

            try:
                with urllib.request.urlopen(req) as response:
                    resp_data = json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                try:
                    err_resp = json.loads(e.read().decode("utf-8"))
                    msg = err_resp.get("errors", [{}])[0].get("message", str(e))
                except:
                    msg = str(e)
                return self.send_json(400, {"error": f"ZPK Error: {msg}"})
            except urllib.error.URLError as e:
                return self.send_json(500, {"error": f"Error fallo de red ZPK: {e}"})

            if isinstance(resp_data, list):
                if len(resp_data) > 0:
                    top_match = resp_data[0]
                    plate = top_match.get("plate", "") if isinstance(top_match, dict) else ""
                else:
                    plate = ""
            else:
                if resp_data.get("success") or "results" in resp_data:
                    res = resp_data.get("results", {})
                    if isinstance(res, list) and len(res) > 0:
                        plate = res[0].get("plate", "")
                    elif isinstance(res, dict):
                        plate = res.get("plate", "")
                    else:
                        plate = ""
                else:
                    err_msg = resp_data.get("errors", [{}])[0].get("message", "Error desconocido")
                    return self.send_json(400, {"error": f"API ZPK: {err_msg}"})

            plate = "".join(c for c in plate if c.isalnum()).upper()
            if plate:
                return self.send_json(200, {"plate": plate})
            return self.send_json(400, {"error": "Placa ilegible para ZPK API."})

        except Exception as e:
            print("[ERROR] handle_recognize_plate:", e)
            return self.send_json(500, {"error": "Error interno procesando imagen hacia cloud API."})


if __name__ == "__main__":
    print("====================================")
    print("Iniciando servidor Valetis...")
    print("====================================")
    print("Iniciando servicios del parqueo...")

    db = DatabaseManager()
    ticket_manager = TicketManager(db)
    payment_manager = PaymentManager(db)
    parking_manager = ParkingManager(db)

    # Auto-detecta el puerto — no necesitas cambiar nada aquí
    arduino = ArduinoBridge(baudrate=9600)

    server = HTTPServer(("127.0.0.1", 8080), APIHandler)

    print("====================================")
    print("Interfaz visual iniciada en:")
    print("http://127.0.0.1:8080/")
    print("====================================")
    print("(Presiona CTRL+C para detener el servidor)")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDeteniendo servidor...")
    finally:
        try:
            if arduino:
                arduino.close()
        except Exception:
            pass
        db.close()
        server.server_close()
        print("Servidor detenido.")
