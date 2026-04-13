import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from hardware.bluetooth_printer import BluetoothPrinter
from config import BLUETOOTH_PRINTER_MAC, BLUETOOTH_PRINTER_WINDOWS_PORT, BLUETOOTH_PRINTER_BAUDRATE

print("=== TEST IMPRESORA ===")
print(f"MAC: {BLUETOOTH_PRINTER_MAC}")
print(f"Puerto: {BLUETOOTH_PRINTER_WINDOWS_PORT}")
print(f"Baudrate: {BLUETOOTH_PRINTER_BAUDRATE}")
print()

p = BluetoothPrinter(
    mac_address=BLUETOOTH_PRINTER_MAC,
    serial_port=BLUETOOTH_PRINTER_WINDOWS_PORT,
    baudrate=BLUETOOTH_PRINTER_BAUDRATE,
)

print(f"\nConectada: {p.connected}")
print(f"Modo: {p.connection_mode}")
print(f"Ultimo error: {p.last_error}")

if p.connected:
    print("\nImprimiendo ticket de prueba...")
    p.print_entry_ticket({
        "ticket_id": "TKT-PRUEBA",
        "plate": "ABC-123",
        "entry_time": "13/04/2026 10:00",
        "qr_data": "TKT-PRUEBA",
    })
else:
    print("\nNo conectada. Intentando forzar...")
    ok = p.ensure_connected(retries=5, delay=2)
    print(f"Resultado: {'OK' if ok else 'FALLO'}")
    if ok:
        p.print_entry_ticket({
            "ticket_id": "TKT-PRUEBA",
            "plate": "ABC-123",
            "entry_time": "13/04/2026 10:00",
            "qr_data": "TKT-PRUEBA",
        })
