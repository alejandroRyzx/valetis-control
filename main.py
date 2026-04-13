from datetime import datetime
from pathlib import Path

from core.database import DatabaseManager
from core.ticket_manager import TicketManager
from core.payment_manager import PaymentManager
from core.parking_manager import ParkingManager
from hardware.arduino_bridge import ArduinoBridge


BASE_DIR = Path(__file__).resolve().parent
REPORTS_DIR = BASE_DIR / "reports"
REGISTROS_DIR = REPORTS_DIR / "registros"
CIERRES_DIR = REPORTS_DIR / "cierres"

REPORTS_DIR.mkdir(parents=True, exist_ok=True)
REGISTROS_DIR.mkdir(parents=True, exist_ok=True)
CIERRES_DIR.mkdir(parents=True, exist_ok=True)

db = DatabaseManager()
ticket_manager = TicketManager(db)
payment_manager = PaymentManager(db)
parking_manager = ParkingManager(db)
arduino = ArduinoBridge()

system_closed = db.get_system_closed()


def calculate_parked_time(ticket):
    entry_dt = datetime.fromisoformat(ticket["entry_time"])
    end_dt = datetime.fromisoformat(ticket["exit_time"]) if ticket["exit_time"] else datetime.now()
    delta = end_dt - entry_dt

    total_minutes = int(delta.total_seconds() // 60)
    hours = total_minutes // 60
    minutes = total_minutes % 60

    return f"{hours}h {minutes}min"


def do_entry():
    global system_closed

    if system_closed:
        print("El sistema ya fue cerrado hoy. No se permiten nuevos ingresos.")
        return

    if parking_manager.is_full():
        print("No hay espacios disponibles")
        arduino.parking_full()
        return

    plate = input("Placa del vehículo: ").strip().upper()
    ticket = ticket_manager.create_ticket(plate)

    print("\nTicket generado")
    print(ticket_manager.format_ticket(ticket))

    arduino.open_entry()
    arduino.update_lcd(parking_manager.available_spaces())

    while True:
        try:
            spot = int(input(f"Elegir parqueo (1-{parking_manager.total_spaces}): ")) - 1
            if parking_manager.occupy_space(spot, ticket["code"]):
                ticket_manager.assign_spot(ticket["code"], spot)
                ticket = ticket_manager.get_ticket(ticket["code"])
                print(f"Vehículo estacionado en espacio {spot + 1}")
                print(ticket_manager.format_ticket(ticket))
                arduino.update_lcd(parking_manager.available_spaces())
                break
            print("Ese espacio no está disponible")
        except ValueError:
            print("Ingresa un número válido")


def do_payment():
    code = input("Código del ticket: ").strip().upper()
    ticket = ticket_manager.get_ticket(code)

    if not ticket:
        print("Ticket no encontrado")
        return

    if ticket_manager.is_expired(code):
        print("Ticket vencido")
        return

    amount = payment_manager.calculate_amount(ticket)
    ticket = ticket_manager.get_ticket(code)

    print(f"Monto a pagar: ${amount:.2f}")

    confirmar = input("Confirmar pago? (s/n): ").strip().lower()
    if confirmar != "s":
        print("Pago cancelado")
        return

    token = payment_manager.register_payment(ticket)
    ticket = ticket_manager.get_ticket(code)

    print("Pago registrado")
    print("Token de validación:", token)
    print(ticket_manager.format_ticket(ticket))


def do_exit():
    code = input("Código del ticket: ").strip().upper()
    ticket = ticket_manager.get_ticket(code)

    if ticket:
        print(ticket_manager.format_ticket(ticket))

    ok, message = payment_manager.can_exit(ticket)
    print(message)

    if not ok:
        return

    parking_manager.free_space_by_ticket(code)
    ticket_manager.mark_used(code)
    ticket = ticket_manager.get_ticket(code)

    arduino.open_exit()
    arduino.update_lcd(parking_manager.available_spaces())
    print("Vehículo salió correctamente")
    print(ticket_manager.format_ticket(ticket))


def show_status():
    print("\n--- ESTADO PARQUEO ---")
    print("Disponibles:", parking_manager.available_spaces())
    print("Sistema cerrado:", "Sí" if system_closed else "No")
    for i, space in enumerate(parking_manager.spaces, start=1):
        print(f"Espacio {i}: {'LIBRE' if space is None else space}")


def show_ticket():
    code = input("Código del ticket: ").strip().upper()
    ticket = ticket_manager.get_ticket(code)
    print(ticket_manager.format_ticket(ticket))


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

    print(f"Archivo guardado en: {file_path}")
    return file_path


def download_daily_report():
    lines = build_report_lines("=== REGISTRO DEL DIA ===")
    file_path = save_unique_report(REGISTROS_DIR, "registro", lines)
    print(f"Registro descargado correctamente: {file_path}")


def do_close_day():
    global system_closed

    if system_closed:
        print("El cierre ya fue realizado.")
        return

    lines = build_report_lines("=== CIERRE DE CAJA / DIA ===")
    file_path = save_unique_report(CIERRES_DIR, "cierre", lines)

    system_closed = True
    db.set_system_closed(True)

    print(f"Cierre realizado correctamente: {file_path}")
    print("Ya no se permiten nuevos ingresos.")


def open_day():
    global system_closed
    db.reset_system_closed()
    system_closed = False
    print("Apertura realizada. El sistema está habilitado para nuevos ingresos.")



def manual_admin_open():
    try:
        arduino.abrir_barrera()
        print("Barrera abierta manualmente por administrador.")
        print("Se cerrará con el flujo normal al detectar la salida.")
    except Exception as e:
        print(f"Error al abrir barrera: {e}")

def menu():
    while True:
        print("\n1. Entrada")
        print("2. Pago")
        print("3. Salida")
        print("4. Estado")
        print("5. Ver ticket")
        print("6. Descargar registro del día")
        print("7. Realizar cierre")
        print("8. Apertura")
        print("9. Abrir barrera manual (admin)")
        print("10. Salir")

        op = input("> ").strip()

        if op == "1":
            do_entry()
        elif op == "2":
            do_payment()
        elif op == "3":
            do_exit()
        elif op == "4":
            show_status()
        elif op == "5":
            show_ticket()
        elif op == "6":
            download_daily_report()
        elif op == "7":
            do_close_day()
        elif op == "8":
            open_day()
        elif op == "9":
            manual_admin_open()
        elif op == "10":
            db.close()
            break
        else:
            print("Opción inválida")

if __name__ == "__main__":
    menu()