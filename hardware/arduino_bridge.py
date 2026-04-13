import time
import serial
import serial.tools.list_ports


class ArduinoBridge:
    def __init__(self, port=None, baudrate=9600):
        self.baudrate = baudrate
        self.ser = None
        self.connected = False

        if port is None:
            port = self._auto_detect_port()

        self.port = port

        if self.port:
            try:
                self.ser = serial.Serial(self.port, self.baudrate, timeout=1)
                time.sleep(2)
                self.connected = True
                print(f"[ArduinoBridge] Conectado a {self.port}")
            except Exception as e:
                print(f"[ArduinoBridge] ERROR al conectar en {self.port}: {e}")
                print("[ArduinoBridge] Modo simulado activo")
        else:
            print("[ArduinoBridge] No se encontro Arduino. Modo simulado activo.")

    def _auto_detect_port(self):
        ports = serial.tools.list_ports.comports()
        keywords = ["arduino", "usb", "usbmodem", "usbserial", "ch340", "cp210", "ftdi"]
        for p in ports:
            desc = (p.description or "").lower()
            hwid = (p.hwid or "").lower()
            name = (p.device or "").lower()
            if any(k in desc or k in hwid or k in name for k in keywords):
                print(f"[ArduinoBridge] Puerto detectado: {p.device} - {p.description}")
                return p.device
        if ports:
            print(f"[ArduinoBridge] Usando primer puerto disponible: {ports[0].device}")
            return ports[0].device
        return None

    def _send(self, byte, label):
        if self.connected and self.ser:
            try:
                self.ser.write(byte)
                self.ser.flush()
                print(f"[ArduinoBridge] Comando enviado: {label}")
            except Exception as e:
                print(f"[ArduinoBridge] ERROR enviando {label}: {e}")
        else:
            print(f"[ArduinoBridge] Simulado: {label}")

    # ── SERVO 1 — ENTRADA ──────────────────────────────────────────
    def abrir_entrada(self):
        self._send(b"A", "A (SERVO 1 - ENTRADA)")

    def open_entry(self):          # alias usado por main.py
        self.abrir_entrada()

    # ── SERVO 2 — SALIDA ───────────────────────────────────────────
    def abrir_salida(self):
        self._send(b"B", "B (SERVO 2 - SALIDA)")

    def open_exit(self):           # alias usado por main.py
        self.abrir_salida()

    # ── COMPATIBILIDAD GENERAL ────────────────────────────────────
    def abrir_barrera(self):       # admin manual → abre entrada
        self.abrir_entrada()

    def cerrar_barrera(self):
        self._send(b"C", "C (CERRAR)")

    # ── MÉTODOS LEGACY (no hacen nada físico, solo log) ───────────
    def update_lcd(self, spaces=None):
        print(f"[ArduinoBridge] LCD: {spaces} espacios disponibles")

    def parking_full(self):
        print("[ArduinoBridge] Parking full - sin accion fisica")

    # ── CIERRE ────────────────────────────────────────────────────
    def close(self):
        try:
            if self.ser and self.ser.is_open:
                self.ser.close()
                print("[ArduinoBridge] Puerto serial cerrado")
        except Exception as e:
            print(f"[ArduinoBridge] ERROR cerrando puerto: {e}")
