import sqlite3
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
REPORTS_DIR = BASE_DIR / "reports"
CIERRES_DIR = REPORTS_DIR / "cierres"
REGISTROS_DIR = REPORTS_DIR / "registros"
DB_PATH = DATA_DIR / "parking.db"


class DatabaseManager:
    def __init__(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        CIERRES_DIR.mkdir(parents=True, exist_ok=True)
        REGISTROS_DIR.mkdir(parents=True, exist_ok=True)

        self.conn = sqlite3.connect(DB_PATH)
        self.conn.row_factory = sqlite3.Row
        self.create_tables()

    def create_tables(self):
        cursor = self.conn.cursor()

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS tickets (
            code TEXT PRIMARY KEY,
            plate TEXT NOT NULL,
            entry_time TEXT NOT NULL,
            exit_time TEXT,
            paid INTEGER NOT NULL DEFAULT 0,
            payment_token TEXT,
            payment_time TEXT,
            payment_deadline TEXT,
            used INTEGER NOT NULL DEFAULT 0,
            spot INTEGER,
            expires_at TEXT NOT NULL,
            amount_due REAL NOT NULL DEFAULT 0.0,
            status TEXT NOT NULL
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS system_state (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            system_closed INTEGER NOT NULL DEFAULT 0
        )
        """)

        cursor.execute("""
        INSERT OR IGNORE INTO system_state (id, system_closed)
        VALUES (1, 0)
        """)

        self.conn.commit()

    def insert_ticket(self, ticket: dict):
        cursor = self.conn.cursor()
        cursor.execute("""
        INSERT INTO tickets (
            code, plate, entry_time, exit_time, paid, payment_token,
            payment_time, payment_deadline, used, spot, expires_at,
            amount_due, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            ticket["code"],
            ticket["plate"],
            ticket["entry_time"],
            ticket.get("exit_time"),
            ticket.get("paid", 0),
            ticket.get("payment_token"),
            ticket.get("payment_time"),
            ticket.get("payment_deadline"),
            ticket.get("used", 0),
            ticket.get("spot"),
            ticket["expires_at"],
            ticket.get("amount_due", 0.0),
            ticket["status"],
        ))
        self.conn.commit()

    def update_ticket(self, ticket: dict):
        cursor = self.conn.cursor()
        cursor.execute("""
        UPDATE tickets
        SET plate = ?, entry_time = ?, exit_time = ?, paid = ?, payment_token = ?,
            payment_time = ?, payment_deadline = ?, used = ?, spot = ?,
            expires_at = ?, amount_due = ?, status = ?
        WHERE code = ?
        """, (
            ticket["plate"],
            ticket["entry_time"],
            ticket.get("exit_time"),
            ticket.get("paid", 0),
            ticket.get("payment_token"),
            ticket.get("payment_time"),
            ticket.get("payment_deadline"),
            ticket.get("used", 0),
            ticket.get("spot"),
            ticket["expires_at"],
            ticket.get("amount_due", 0.0),
            ticket["status"],
            ticket["code"],
        ))
        self.conn.commit()

    def get_ticket(self, query: str):
        cursor = self.conn.cursor()
        # Buscar primero por el código exacto TKT-
        cursor.execute("SELECT * FROM tickets WHERE code = ?", (query,))
        row = cursor.fetchone()
        if row: return dict(row)

        # Si no se encuentra, buscar por placa (devuelve la más reciente)
        cursor.execute("SELECT * FROM tickets WHERE plate = ? ORDER BY entry_time DESC", (query,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_today_tickets(self, date_prefix: str):
        cursor = self.conn.cursor()
        cursor.execute("""
        SELECT * FROM tickets
        WHERE entry_time LIKE ?
        ORDER BY entry_time ASC
        """, (f"{date_prefix}%",))
        return [dict(row) for row in cursor.fetchall()]

    def get_all_tickets(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM tickets ORDER BY entry_time ASC")
        return [dict(row) for row in cursor.fetchall()]

    def get_paid_tickets(self):
        cursor = self.conn.cursor()
        cursor.execute("""
        SELECT * FROM tickets
        WHERE paid = 1
        ORDER BY payment_time ASC
        """)
        return [dict(row) for row in cursor.fetchall()]

    def get_system_closed(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT system_closed FROM system_state WHERE id = 1")
        row = cursor.fetchone()
        return bool(row["system_closed"])

    def set_system_closed(self, closed: bool):
        cursor = self.conn.cursor()
        cursor.execute("""
        UPDATE system_state
        SET system_closed = ?
        WHERE id = 1
        """, (1 if closed else 0,))
        self.conn.commit()

    def reset_system_closed(self):
        self.set_system_closed(False)

    def save_daily_record(self, content: str):
        now = datetime.now()
        filename = f"registro_{now.strftime('%Y-%m-%d_%H-%M-%S')}.txt"
        file_path = REGISTROS_DIR / filename

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)

        print(f"Registro guardado en: {file_path}")
        return str(file_path)

    def save_closure_report(self, content: str):
        now = datetime.now()
        filename = f"cierre_{now.strftime('%Y-%m-%d_%H-%M-%S')}.txt"
        file_path = CIERRES_DIR / filename

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)

        print(f"Cierre guardado en: {file_path}")
        return str(file_path)

    def generate_daily_record_text(self):
        tickets = self.get_all_tickets()
        lines = []
        lines.append("===== REGISTRO GENERAL DE TICKETS =====")
        lines.append(f"Fecha de generación: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")

        if not tickets:
            lines.append("No hay tickets registrados.")
        else:
            for t in tickets:
                lines.append(
                    f"Código: {t['code']} | "
                    f"Placa: {t['plate']} | "
                    f"Entrada: {t['entry_time']} | "
                    f"Salida: {t['exit_time'] or '---'} | "
                    f"Pagado: {'Sí' if t['paid'] else 'No'} | "
                    f"Monto: ${float(t['amount_due']):.2f} | "
                    f"Estado: {t['status']}"
                )

        return "\n".join(lines)

    def generate_closure_text(self):
        tickets = self.get_all_tickets()
        paid_tickets = [t for t in tickets if t["paid"] == 1]
        unpaid_tickets = [t for t in tickets if t["paid"] == 0]
        total_amount = sum(float(t["amount_due"]) for t in paid_tickets)

        lines = []
        lines.append("===== CIERRE DE CAJA / JORNADA =====")
        lines.append(f"Fecha de cierre: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")
        lines.append(f"Total de tickets: {len(tickets)}")
        lines.append(f"Tickets pagados: {len(paid_tickets)}")
        lines.append(f"Tickets no pagados: {len(unpaid_tickets)}")
        lines.append(f"Total recaudado: ${total_amount:.2f}")
        lines.append("")
        lines.append("----- DETALLE DE PAGADOS -----")

        if not paid_tickets:
            lines.append("No hay tickets pagados.")
        else:
            for t in paid_tickets:
                lines.append(
                    f"Código: {t['code']} | "
                    f"Placa: {t['plate']} | "
                    f"Pago: {t['payment_time'] or '---'} | "
                    f"Monto: ${float(t['amount_due']):.2f}"
                )

        return "\n".join(lines)

    def save_daily_record_auto(self):
        content = self.generate_daily_record_text()
        return self.save_daily_record(content)

    def save_closure_report_auto(self):
        content = self.generate_closure_text()
        return self.save_closure_report(content)

    def close(self):
        self.conn.close()