import os
import socket
import time
import threading

try:
    import serial
    import serial.tools.list_ports
    HAS_SERIAL = True
except Exception:
    serial = None
    HAS_SERIAL = False

try:
    import qrcode
except Exception:
    qrcode = None


class BluetoothPrinter:
    """
    Controlador para impresora térmica móvil Xiamen Hanin Electronic Technology MPT-II
    Se comunica por Bluetooth usando protocolo ESC/POS
    """

    ESC = b'\x1b'
    GS = b'\x1d'

    RESET = ESC + b'@'
    SET_ALIGNMENT_CENTER = ESC + b'a\x01'
    SET_ALIGNMENT_LEFT = ESC + b'a\x00'
    SET_ALIGNMENT_RIGHT = ESC + b'a\x02'

    FONT_NORMAL = ESC + b'!\x00'
    FONT_DOUBLE_WIDTH = ESC + b'!\x10'
    FONT_DOUBLE_HEIGHT = ESC + b'!\x01'
    FONT_DOUBLE_BOTH = ESC + b'!\x11'

    BOLD_ON = ESC + b'E\x01'
    BOLD_OFF = ESC + b'E\x00'
    UNDERLINE_ON = ESC + b'-\x01'
    UNDERLINE_OFF = ESC + b'-\x00'

    PAPER_CUT = GS + b'V\x41\x00'
    PAPER_PARTIAL_CUT = GS + b'V\x42\x00'

    LINE_FEED = b'\n'

    def __init__(self, mac_address=None, port=1, serial_port=None, baudrate=9600):
        self.mac_address = mac_address
        self.port = port
        self.serial_port = serial_port
        self.baudrate = baudrate
        self.socket = None
        self.serial_connection = None
        self.connected = False
        self.connection_mode = None
        self.last_error = None
        self._keepalive_running = False
        self._health_fail_count = 0  # Fallos consecutivos del health check
        # RLock permite que _send() llame a ensure_connected() sin deadlock
        self._lock = threading.RLock()

        self.connect()
        self._start_keepalive()

    def _start_keepalive(self):
        """Hilo daemon que reintenta la conexión cada 15s si está desconectada."""
        if self._keepalive_running:
            return
        self._keepalive_running = True
        t = threading.Thread(target=self._keepalive_loop, daemon=True)
        t.start()

    def _keepalive_loop(self):
        while self._keepalive_running:
            if self.connected:
                # Conectada: health check activo cada 5s
                time.sleep(5)
                if not self._keepalive_running:
                    break
                acquired = self._lock.acquire(blocking=False)
                if acquired:
                    try:
                        self._health_check()
                    finally:
                        self._lock.release()
            else:
                # Desconectada: reintentar cada 5s hasta reconectar
                time.sleep(5)
                if not self._keepalive_running:
                    break
                acquired = self._lock.acquire(blocking=False)
                if acquired:
                    try:
                        if not self.connected:
                            print("[BluetoothPrinter] Keepalive: buscando impresora...")
                            self.connect()
                            if self.connected:
                                # Verificar que realmente responde (en macOS el puerto
                                # Bluetooth existe aunque la impresora esté apagada)
                                self._health_check()
                                if self.connected:
                                    print("[BluetoothPrinter] Keepalive: ✅ impresora reconectada")
                                else:
                                    print("[BluetoothPrinter] Keepalive: puerto abierto pero impresora no responde")
                    finally:
                        self._lock.release()
                # Si no se pudo adquirir el lock hay una impresión en curso — reintenta en 5s

    def _health_check(self):
        """Verifica activamente que la impresora sigue respondiendo.
        Requiere 2 fallos consecutivos para marcar como desconectada."""
        if self.connection_mode == 'serial' and self.serial_connection:
            try:
                if not self.serial_connection.is_open:
                    raise OSError("Puerto serial cerrado")

                # Limpiar buffer de entrada antes del test
                self.serial_connection.reset_input_buffer()

                # Enviar comando ESC/POS DLE EOT (solicitar estado)
                # DLE (0x10) + EOT (0x04) + n=1 (estado de la impresora)
                self.serial_connection.write(b'\x10\x04\x01')
                self.serial_connection.flush()

                # Esperar brevemente a que la impresora procese
                time.sleep(0.1)

                # Intentar leer respuesta con timeout
                old_timeout = self.serial_connection.timeout
                self.serial_connection.timeout = 3
                response = self.serial_connection.read(1)
                self.serial_connection.timeout = old_timeout

                if len(response) == 0:
                    raise OSError("Sin respuesta de la impresora (timeout)")

                # Éxito — resetear contador de fallos
                self._health_fail_count = 0

            except Exception as e:
                self._health_fail_count += 1
                if self._health_fail_count >= 2:
                    print(f"[BluetoothPrinter] ❌ {self._health_fail_count} fallos consecutivos: {e} — desconectada")
                    self.connected = False
                    self.connection_mode = None
                    self.last_error = str(e)
                    self._health_fail_count = 0
                    try:
                        self.serial_connection.close()
                    except Exception:
                        pass
                    self.serial_connection = None
                else:
                    print(f"[BluetoothPrinter] ⚠️ Health check fallo {self._health_fail_count}/2: {e}")
        elif self.connection_mode == 'bluetooth' and self.socket:
            try:
                self.socket.send(b'')
            except Exception as e:
                print(f"[BluetoothPrinter] ❌ Health check BT falló: {e}")
                self.connected = False
                self.connection_mode = None
                self.last_error = str(e)
                try:
                    self.socket.close()
                except Exception:
                    pass
                self.socket = None

    def _serial_candidates(self):
        candidates = []
        if self.serial_port:
            # En Windows los puertos COM son case-insensitive, en Mac/Linux las rutas son case-sensitive
            candidates.append(self.serial_port.upper() if os.name == 'nt' else self.serial_port)
        if not HAS_SERIAL:
            return candidates
        ports = list(serial.tools.list_ports.comports())
        bluetooth_keywords = [
            "bluetooth", "bth", "rfcomm",
            "serial over bluetooth",
            "serie estandar sobre el vinculo bluetooth",
            "mpt",  # Impresora MPT-II
        ]
        preferred = []
        fallback = []
        for port_info in ports:
            device = port_info.device or ""
            if os.name == 'nt':
                device = device.upper()
            description = (port_info.description or "").lower()
            hwid = (port_info.hwid or "").lower()
            name = (port_info.name or "").lower()
            haystack = " ".join([description, hwid, name])
            if any(keyword in haystack for keyword in bluetooth_keywords):
                preferred.append(device)
            elif os.name == 'nt' and device.startswith("COM"):
                fallback.append(device)
        ordered = candidates + preferred + fallback
        unique = []
        seen = set()
        for device in ordered:
            if device and device not in seen:
                seen.add(device)
                unique.append(device)
        return unique

    def _connect_serial(self):
        if not HAS_SERIAL:
            return False
        for port_name in self._serial_candidates():
            try:
                if self.serial_connection:
                    try:
                        self.serial_connection.close()
                    except Exception:
                        pass
                    self.serial_connection = None
                self.serial_connection = serial.Serial(port_name, self.baudrate, timeout=2, write_timeout=4)
                time.sleep(1)
                self.connected = True
                self.connection_mode = 'serial'
                self.serial_port = port_name
                self.last_error = None
                print(f"[BluetoothPrinter] Conectado por puerto serial {port_name}")
                return True
            except Exception as e:
                self.last_error = str(e)
                print(f"[BluetoothPrinter] ERROR conectando por serial {port_name}: {e}")
        return False

    def _connect_bluetooth_socket(self):
        if not self.mac_address:
            return False
        if not hasattr(socket, 'AF_BLUETOOTH') or not hasattr(socket, 'BTPROTO_RFCOMM'):
            return False
        try:
            if self.socket:
                try:
                    self.socket.close()
                except Exception:
                    pass
                self.socket = None
            self.socket = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
            self.socket.settimeout(8)
            self.socket.connect((self.mac_address, self.port))
            self.socket.settimeout(5)
            self.connected = True
            self.connection_mode = 'bluetooth'
            self.last_error = None
            print(f"[BluetoothPrinter] Conectado a {self.mac_address} por RFCOMM")
            time.sleep(1)
            return True
        except Exception as e:
            self.last_error = str(e)
            print(f"[BluetoothPrinter] ERROR conectando a {self.mac_address}: {e}")
            self.socket = None
            return False

    def _close_resources(self):
        """Cierra sockets y puertos sin tocar el hilo keepalive."""
        try:
            if self.socket:
                try:
                    self.socket.close()
                except Exception:
                    pass
                self.socket = None
            if self.serial_connection:
                try:
                    self.serial_connection.close()
                except Exception:
                    pass
                self.serial_connection = None
            self.connected = False
            self.connection_mode = None
        except Exception as e:
            print(f"[BluetoothPrinter] ERROR liberando recursos: {e}")

    def connect(self):
        # Solo cierra recursos — NO mata el keepalive
        self._close_resources()
        if os.name == 'nt' and self._connect_serial():
            return
        if self._connect_bluetooth_socket():
            return
        if os.name != 'nt' and self._connect_serial():
            return
        print("[BluetoothPrinter] Modo simulado activo")

    def ensure_connected(self, retries=5, delay=2):
        if self.connected:
            return True
        for attempt in range(1, retries + 1):
            print(f"[BluetoothPrinter] Intento de conexión {attempt}/{retries}...")
            self.connect()
            if self.connected:
                return True
            if attempt < retries:
                print(f"[BluetoothPrinter] Esperando {delay}s antes del siguiente intento...")
                time.sleep(delay)
        print("[BluetoothPrinter] No se pudo conectar después de todos los intentos.")
        return False

    def _send(self, data, label=""):
        with self._lock:
            if not self.connected:
                self.ensure_connected()
            if self.connected and self.connection_mode == 'bluetooth' and self.socket:
                try:
                    self.socket.send(data)
                    if label:
                        print(f"[BluetoothPrinter] {label}")
                    return True
                except Exception as e:
                    print(f"[BluetoothPrinter] ERROR enviando BT: {e}")
                    self.connected = False
                    self.last_error = str(e)
            elif self.connected and self.connection_mode == 'serial' and self.serial_connection:
                try:
                    self.serial_connection.write(data)
                    self.serial_connection.flush()
                    if label:
                        print(f"[BluetoothPrinter] {label}")
                    return True
                except Exception as e:
                    print(f"[BluetoothPrinter] ERROR enviando serial: {e}")
                    self.connected = False
                    self.last_error = str(e)
                    # Reintentar una vez reconectando
                    self.connect()
                    if self.connected and self.serial_connection:
                        try:
                            self.serial_connection.write(data)
                            self.serial_connection.flush()
                            if label:
                                print(f"[BluetoothPrinter] {label} (reintento)")
                            return True
                        except Exception as retry_error:
                            print(f"[BluetoothPrinter] ERROR reintento serial: {retry_error}")
                            self.connected = False
                            self.last_error = str(retry_error)
            else:
                if label:
                    print(f"[BluetoothPrinter] Simulado: {label}")
            return False

    def reset(self):
        self._send(self.RESET, "Reset de impresora")

    def write(self, text):
        if isinstance(text, str):
            text = text.encode('utf-8', errors='ignore')
        self._send(text, f"Escribiendo: {text[:50]}")

    def linefeed(self, lines=1):
        self._send(self.LINE_FEED * lines, f"Saltos de línea: {lines}")

    def set_alignment(self, alignment='left'):
        if alignment == 'center':
            self._send(self.SET_ALIGNMENT_CENTER, "Alineación: Centro")
        elif alignment == 'right':
            self._send(self.SET_ALIGNMENT_RIGHT, "Alineación: Derecha")
        else:
            self._send(self.SET_ALIGNMENT_LEFT, "Alineación: Izquierda")

    def set_font_size(self, size='normal'):
        if size == 'double_width':
            self._send(self.FONT_DOUBLE_WIDTH, "Tamaño: Doble ancho")
        elif size == 'double_height':
            self._send(self.FONT_DOUBLE_HEIGHT, "Tamaño: Doble alto")
        elif size == 'double':
            self._send(self.FONT_DOUBLE_BOTH, "Tamaño: Doble (ambos)")
        else:
            self._send(self.FONT_NORMAL, "Tamaño: Normal")

    def set_bold(self, enabled=True):
        if enabled:
            self._send(self.BOLD_ON, "Negrita: ON")
        else:
            self._send(self.BOLD_OFF, "Negrita: OFF")

    def set_underline(self, enabled=True):
        if enabled:
            self._send(self.UNDERLINE_ON, "Subrayado: ON")
        else:
            self._send(self.UNDERLINE_OFF, "Subrayado: OFF")

    def cut_paper(self, partial=False):
        if partial:
            self._send(self.PAPER_PARTIAL_CUT, "Corte parcial")
        else:
            self._send(self.PAPER_CUT, "Corte completo")

    def print_qr(self, data, module_size=6, error_level='M'):
        if isinstance(data, str):
            data = data.encode('utf-8', errors='ignore')
        if not data:
            return
        error_map = {'L': 48, 'M': 49, 'Q': 50, 'H': 51}
        ec = error_map.get(error_level.upper(), 49)
        self._send(self.GS + b'(k\x04\x00\x31\x41\x32\x00', "QR modelo 2")
        size = max(3, min(16, int(module_size)))
        self._send(self.GS + b'(k\x03\x00\x31\x43' + bytes([size]), "QR tamaño")
        self._send(self.GS + b'(k\x03\x00\x31\x45' + bytes([ec]), "QR ECC")
        length = len(data) + 3
        p_l = length % 256
        p_h = length // 256
        self._send(self.GS + b'(k' + bytes([p_l, p_h, 49, 80, 48]) + data, "QR datos")
        self._send(self.GS + b'(k\x03\x00\x31\x51\x30', "QR imprimir")

    def print_qr_raster(self, data, scale=4, border=2):
        if qrcode is None:
            return False
        text = str(data or "").strip()
        if not text:
            return False
        try:
            qr = qrcode.QRCode(
                version=None,
                error_correction=qrcode.constants.ERROR_CORRECT_H,
                box_size=1,
                border=max(1, int(border)),
            )
            qr.add_data(text)
            qr.make(fit=True)
            matrix = qr.get_matrix()
            height_modules = len(matrix)
            width_modules = len(matrix[0]) if height_modules else 0
            if width_modules == 0:
                return False
            scale = max(2, int(scale))
            width_px = width_modules * scale
            height_px = height_modules * scale
            bytes_per_row = (width_px + 7) // 8
            raster = bytearray()
            for row in matrix:
                expanded_row = []
                for bit in row:
                    expanded_row.extend([1 if bit else 0] * scale)
                for _ in range(scale):
                    row_bytes = bytearray(bytes_per_row)
                    for x, bit in enumerate(expanded_row):
                        if bit:
                            row_bytes[x // 8] |= (0x80 >> (x % 8))
                    raster.extend(row_bytes)
            xL = bytes_per_row & 0xFF
            xH = (bytes_per_row >> 8) & 0xFF
            yL = height_px & 0xFF
            yH = (height_px >> 8) & 0xFF
            cmd = self.GS + b'v0' + bytes([0, xL, xH, yL, yH])
            self._send(cmd + bytes(raster), "QR raster imprimir")
            return True
        except Exception as e:
            print(f"[BluetoothPrinter] ERROR QR raster: {e}")
            return False

    def print_entry_ticket(self, ticket_data):
        try:
            self.reset()
            self.set_alignment('center')
            self.set_font_size('double')
            self.set_bold(True)
            self.write("TICKET DE INGRESO\n")
            self.set_bold(False)
            self.set_font_size('normal')
            self.linefeed(1)
            self.write("=" * 32 + "\n")
            self.set_alignment('center')
            self.write(f"Ticket: {ticket_data.get('ticket_id', 'N/A')}\n")
            self.write(f"Placa: {ticket_data.get('plate', 'N/A')}\n")
            if ticket_data.get('entry_time'):
                self.write(f"Entrada: {ticket_data.get('entry_time')}\n")
            self.linefeed(1)
            self.write("ESCANEA QR PARA PAGAR\n")
            self.linefeed(1)
            qr_data = ticket_data.get('qr_data') or ticket_data.get('ticket_id', 'N/A')
            if not self.print_qr_raster(qr_data, scale=5, border=3):
                self.print_qr(qr_data, module_size=12, error_level='H')
            self.linefeed(1)
            self.linefeed(2)
            self.write("Conserve este ticket\n")
            self.write("para su salida\n")
            self.linefeed(2)
            self.cut_paper()
            print("[BluetoothPrinter] Ticket de ingreso impreso exitosamente")
        except Exception as e:
            print(f"[BluetoothPrinter] ERROR imprimiendo ticket de ingreso: {e}")

    def print_daily_report(self, report_data):
        try:
            self.reset()
            self.set_alignment('center')
            self.set_font_size('double')
            self.set_bold(True)
            self.write("REPORTE DIARIO\n")
            self.set_bold(False)
            self.set_font_size('normal')
            self.linefeed(1)
            self.write("=" * 32 + "\n")
            self.write(f"Fecha: {report_data.get('date', 'N/A')}\n")
            self.linefeed(1)
            self.set_alignment('left')
            self.write(f"Total vehículos: {report_data.get('total_vehicles', 0)}\n")
            self.set_bold(True)
            self.write(f"Ingreso Total: ${report_data.get('total_income', '0.00')}\n")
            self.set_bold(False)
            if report_data.get('payment_methods'):
                self.linefeed(1)
                self.write("Metodos de pago:\n")
                for method, amount in report_data['payment_methods'].items():
                    self.write(f"  {method}: ${amount}\n")
            self.linefeed(2)
            self.set_alignment('center')
            self.write("=" * 32 + "\n")
            self.cut_paper()
            print("[BluetoothPrinter] Reporte impreso exitosamente")
        except Exception as e:
            print(f"[BluetoothPrinter] ERROR imprimiendo reporte: {e}")

    def disconnect(self):
        """Desconexión total — detiene también el keepalive."""
        self._keepalive_running = False
        was_connected = self.connected
        self._close_resources()
        if was_connected:
            print("[BluetoothPrinter] Desconectado")

    def __del__(self):
        self.disconnect()
