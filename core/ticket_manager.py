import uuid
from datetime import datetime, timedelta
from config import TICKET_EXPIRATION_HOURS


class TicketManager:

    def __init__(self, db):
        self.db = db

    def create_ticket(self, plate: str):

        code = f"TKT-{str(uuid.uuid4())[:8].upper()}"
        now = datetime.now()

        ticket = {
            "code": code,
            "plate": plate,
            "entry_time": now.isoformat(),
            "exit_time": None,
            "paid": 0,
            "payment_token": None,
            "payment_time": None,
            "payment_deadline": None,
            "used": 0,
            "spot": None,
            "expires_at": (now + timedelta(hours=TICKET_EXPIRATION_HOURS)).isoformat(),
            "amount_due": 0.0,
            "status": "ESTACIONADO",
        }

        self.db.insert_ticket(ticket)

        return ticket


    def get_ticket(self, code: str):
        return self.db.get_ticket(code)


    def assign_spot(self, code: str, spot_index: int):

        ticket = self.get_ticket(code)

        if ticket:
            ticket["spot"] = spot_index
            self.db.update_ticket(ticket)


    def mark_used(self, code: str):

        ticket = self.get_ticket(code)

        if ticket:

            ticket["used"] = 1
            ticket["status"] = "SALIDO"
            ticket["exit_time"] = datetime.now().isoformat()

            self.db.update_ticket(ticket)


    def is_expired(self, code: str):

        ticket = self.get_ticket(code)

        if not ticket:
            return True

        return datetime.now() > datetime.fromisoformat(ticket["expires_at"])


    def get_today_tickets(self):

        today = datetime.now().strftime("%Y-%m-%d")

        return self.db.get_today_tickets(today)


    def format_ticket(self, ticket: dict):

        if not ticket:
            return "Ticket no encontrado"

        entry_time = datetime.fromisoformat(ticket["entry_time"]).strftime("%Y-%m-%d %H:%M:%S")

        payment_time = (
            datetime.fromisoformat(ticket["payment_time"]).strftime("%Y-%m-%d %H:%M:%S")
            if ticket["payment_time"] else "No pagado"
        )

        payment_deadline = (
            datetime.fromisoformat(ticket["payment_deadline"]).strftime("%Y-%m-%d %H:%M:%S")
            if ticket["payment_deadline"] else "No aplica"
        )

        exit_time = (
            datetime.fromisoformat(ticket["exit_time"]).strftime("%Y-%m-%d %H:%M:%S")
            if ticket["exit_time"] else "Aún no sale"
        )

        return (
            f"\n--- TICKET ---\n"
            f"Codigo: {ticket['code']}\n"
            f"Placa: {ticket['plate']}\n"
            f"Hora entrada: {entry_time}\n"
            f"Hora salida: {exit_time}\n"
            f"Espacio: {ticket['spot'] + 1 if ticket['spot'] is not None else 'No asignado'}\n"
            f"Estado: {ticket['status']}\n"
            f"Pagado: {'Si' if ticket['paid'] else 'No'}\n"
            f"Monto a pagar: ${ticket['amount_due']:.2f}\n"
            f"Token pago: {ticket['payment_token'] if ticket['payment_token'] else 'No generado'}\n"
            f"Hora pago: {payment_time}\n"
            f"Limite salida: {payment_deadline}\n"
            f"Usado: {'Si' if ticket['used'] else 'No'}\n"
        )