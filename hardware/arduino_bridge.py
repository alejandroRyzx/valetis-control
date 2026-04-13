import os
import time
import threading
import queue

try:
    import serial
    import serial.tools.list_ports
    HAS_SERIAL = True
except Exception:
    serial = None
    HAS_SERIAL = False

try:
    from config import ENTRY_SENSOR_KEYWORDS, ENTRY_SENSOR_ENABLED
except Exception:
    ENTRY_SENSOR_KEYWORDS = ["ENTRY_PASS", "PASO_ENTRADA", "CAR_PASSED", "SENSOR_ENTRADA"]
    ENTRY_SENSOR_ENABLED = True


class ArduinoBridge:
    def __init__(self, port=None, baudrate=9600):
        self.baudrate = baudrate
        self.ser = None
        self.connected = False
        self._lock = threading.Lock()
        self._button_events = queue.Queue()
        self._sensor_events = queue.Queue()
        self._payment_events = queue.Queue()
        self._reader_thread = None
        self._running = False

        if port is None:
            port = self._auto_detect_port()
        self.port = port

        if self.port:
            try:
                self.ser = serial.Serial(self.port, self.baudrate, timeout=1)
                time.sleep(2)
                self.connected = True
                print(f"[ArduinoBridge] Conectado a {self.port}")
                self._start_reader()
            except Exception as e:
                print(f"[ArduinoBridge] ERROR al conectar en {self.port}: {e}")
                print("[ArduinoBridge] Modo simulado activo")
        else:
            print("[ArduinoBridge] No se encontro Arduino. Modo simulado activo.")

    def _auto_detect_port(self):
        if not HAS_SERIAL:
            return None
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

    def _start_reader(self):
        self._running = True
        self._reader_thread = threading.Thread(target=self._serial_reader, daemon=True)
        self._reader_thread.start()
        print("[ArduinoBridge] Lector serial iniciado en segundo plano")

    def _serial_reader(self):
        while self._running:
            try:
                if self.ser and self.ser.is_open:
                    if self.ser.in_waiting:
                        line = self.ser.readline().decode('utf-8', errors='ignore').strip()
                        if not line:
                            continue
                        print(f"[ArduinoBridge] <<< {line}")
                        line_lower = line.lower()

                        if "pulsador_entrada" in line_lower:
                            self._button_events.put(line)
                            print("[ArduinoBridge] Evento: BOTON ENTRADA")

                        if "pulsador_pago" in line_lower:
                            self._payment_events.put(line)
                            print("[ArduinoBridge] Evento: BOTON PAGO")

                        if ENTRY_SENSOR_ENABLED:
                            for kw in ENTRY_SENSOR_KEYWORDS:
                                if kw.lower() in line_lower:
                                    self._sensor_events.put(line)
                                    print("[ArduinoBridge] Evento: SENSOR PASO")
                                    break
                    else:
                        time.sleep(0.05)
                else:
                    time.sleep(0.2)
            except Exception as e:
                print(f"[ArduinoBridge] Error en lector serial: {e}")
                time.sleep(0.5)

    def pop_button_event(self):
        """Drains button event queue. Returns True if at least one event was pending."""
        found = False
        while not self._button_events.empty():
            try:
                self._button_events.get_nowait()
                found = True
            except queue.Empty:
                break
        return found

    def pop_sensor_event(self):
        """Drains sensor event queue. Returns True if at least one event was pending."""
        found = False
        while not self._sensor_events.empty():
            try:
                self._sensor_events.get_nowait()
                found = True
            except queue.Empty:
                break
        return found

    def pop_payment_event(self):
        """Drains payment button event queue. Returns True if at least one event was pending."""
        found = False
        while not self._payment_events.empty():
            try:
                self._payment_events.get_nowait()
                found = True
            except queue.Empty:
                break
        return found

    def _send(self, byte, label):
        with self._lock:
            if self.connected and self.ser:
                try:
                    self.ser.write(byte)
                    self.ser.flush()
                    print(f"[ArduinoBridge] >>> {label}")
                except Exception as e:
                    print(f"[ArduinoBridge] ERROR enviando {label}: {e}")
            else:
                print(f"[ArduinoBridge] Simulado: {label}")

    # ── SERVO 1 — ENTRADA ──────────────────────────────────────────
    def abrir_entrada(self):
        self._send(b"A", "A (SERVO 1 - ENTRADA)")

    def open_entry(self):
        self.abrir_entrada()

    # ── SERVO 2 — SALIDA ───────────────────────────────────────────
    def abrir_salida(self):
        self._send(b"B", "B (SERVO 2 - SALIDA)")

    def open_exit(self):
        self.abrir_salida()

    # ── COMPATIBILIDAD GENERAL ────────────────────────────────────
    def abrir_barrera(self):
        self.abrir_entrada()

    def cerrar_barrera(self):
        self._send(b"C", "C (CERRAR)")

    # ── MÉTODOS LEGACY ────────────────────────────────────────────
    def update_lcd(self, spaces=None):
        print(f"[ArduinoBridge] LCD: {spaces} espacios disponibles")

    def parking_full(self):
        print("[ArduinoBridge] Parking full - sin accion fisica")

    # ── CIERRE ────────────────────────────────────────────────────
    def close(self):
        self._running = False
        try:
            if self.ser and self.ser.is_open:
                self.ser.close()
                print("[ArduinoBridge] Puerto serial cerrado")
        except Exception as e:
            print(f"[ArduinoBridge] ERROR cerrando puerto: {e}")
