from datetime import datetime, timedelta
import math
from config import PAYMENT_VALID_MINUTES, TARIFA_MINIMA, TARIFA_POR_HORA


class PaymentManager:
    def __init__(self, db):
        self.db = db
        self.tokens = ["*", "@", "#", "%", "&"]
        self.token_index = 0

    def calculate_amount(self, ticket: dict):
        now = datetime.now()
        entry_dt = datetime.fromisoformat(ticket["entry_time"])
        elapsed = now - entry_dt
        total_minutes = elapsed.total_seconds() / 60

        if total_minutes <= 60:
            amount = TARIFA_MINIMA
        else:
            billed_hours = math.ceil(total_minutes / 60)
            amount = billed_hours * TARIFA_POR_HORA

        ticket["amount_due"] = amount
        self.db.update_ticket(ticket)
        return amount

    def register_payment(self, ticket: dict):
        token = self.tokens[self.token_index % len(self.tokens)]
        self.token_index += 1

        now = datetime.now()
        ticket["paid"] = 1
        ticket["payment_token"] = token
        ticket["payment_time"] = now.isoformat()
        ticket["payment_deadline"] = (now + timedelta(minutes=PAYMENT_VALID_MINUTES)).isoformat()
        ticket["status"] = "PAGADO"

        self.db.update_ticket(ticket)
        return token

    def can_exit(self, ticket: dict):
        if not ticket:
            return False, "Ticket no existe"

        if ticket["used"]:
            return False, "Ticket ya fue usado"

        if not ticket["paid"]:
            return False, "Ticket no pagado"

        if datetime.now() > datetime.fromisoformat(ticket["payment_deadline"]):
            return False, "Tiempo de salida vencido"

        return True, "Salida permitida"