# Valetis Control 4 – Documentación del Sistema 🚀

**Valetis Control** es un sistema integral multiplataforma (Hardware/Software) diseñado para la gestión de parqueos, facturación, control de espacios físicos de estacionamientos y validación automatizada mediante cámaras inteligentes LPR (reconocimiento de placas) y escáneres QR. 

Cuenta con estética premium Dark Mode e inyección de datos asíncrona hacia una placa hardware (Arduino) mediante Python.

---

## 🏗 Arquitectura Tecnológica

1. **Backend / Motor Central:** 
   * Escrito completamente en **Python**.
   * Framework web asíncrono puro corriendo de manera persistente sobre un servidor personalizado (`web_server.py`) expuesto en el puerto `8080`.
   * Incluye persistencia y control de sesión (basado en un motor de base de datos para manejo de tickets activos y pasivos mediante el wrapper `ParkingManager`).

2. **Frontend UI/UX:**
   * Patrón de diseño ultra-moderno minimalista (*Premium Glassmorphism + Estilo Espacial*).
   * Motor responsivo puro (`Vanilla CSS, JS + HTML5`) sin necesidad de dependencias pesadas tipo React, permitiendo altísima velocidad.
   * Cuenta con un **Canvas Animado Generador de Estrellas de 60fps** desarrollado en JS nativo para efectos de fondo.
   * Utiliza la librería **Html5QrcodeScanner** interactiva, rediseñada geométricamente sin bordes residuales.
   * Gráficas de estadística generadas en tiempo real con `Chart.js`.

3. **Integración IoT (Hardware):**
   * **Arduino Bridge:** El servidor Python escanea activamente puertos USB (ej. `/dev/cu.usbmodem11301`) y se comunica mediante protocolo Serial (`pyserial`).
   * Interpreta comandos específicos (definidos en `config.py`) para interactuar con el entorno físico: 
     * `OPEN_ENTRY`: Sube la plumilla/barrera de ingreso tras una lectura LPR autorizada.
     * `OPEN_EXIT`: Sube la plumilla/barrera de salida si el vehículo no tiene deudas activas.
     * `PARKING_FULL`: Emite señales de cierre a la placa o paneles LCD si el ParkingManager calcula 0 espacios disponibles.

---

## 💻 Módulos y Flujos de Usuario 

### 1. Panel de Autenticación
Diseño premium nativo con *Split Layout*. Modificado en su última versión para lograr una superposición arquitectónica de paneles en donde la caja de Logueo crea un margen negativo que "atraviesa" la fotografía del estacionamiento, inyectando sombras 3D masivas. Para dispositivos celulares, el diseño se colapsa inteligentemente ocultando la foto y maximizando los campos de entrada.

### 2. Tablero Principal (Dashboard Central)
El corazón de mando. Cuenta con indicadores estadísticos (Vehículos Activos, Cobros del día, Reloj en tiempo real) y un botón interactivo de "Cierre/Apertura de Caja".

Desde este panel se invocan los tres Modales clave de operación, que ahora cuentan con **Auto-Inicios Físicos** (las cámaras se encienden solas al dar clic):
* **Nuevo Ingreso:** Solicita placa, emite folio y asigna el cajón dinámicamente. Enciende de inmediato la interfaz de la cámara LPR y el botón rojo de rotación de lente.
* **Registrar Cobro:** Cuenta con un recuadro lector QR *Full Screen cuadrado* reescrito desde cero con dimensiones `250x250` inyectadas desde CSS para evitar bandas grises. Al leer un boleto válido, el Back-End evalúa la hora e informa la Tarifa acentuada.
* **Proceso de Salida:** Inicializa el lector general para descifrar placas o decodificar tickets físicos QR. De proceder con éxito, manda los pulsos eléctricos de apertura de barrera directamente a los Servomotores vía USB.

### 3. Histórico y Trazabilidad (History Dashboard)
* El DOM del historial mutó para incorporar una **Paginación Dinámica**. Extrae matrices enteras de vehículos pero sólo renderiza en el Frontend ventanas asíncronas de 12 registros por página.
* Todo el contenedor cuenta con escudo deslizante táctil *overflow-x* en equipos móviles.
* Inyección de End-point oficial `/api/export_excel`, permitiendo el vaciado en caliente de bases de datos XLSX con 1 clic.
* **Componente Tracking Timeline:** Reemplaza el anticuado texto terminal. Al consultar cualquier folio, despliega una línea de tiempo vertical animada, denotando cronológicamente el estatus de (1) Entrada, (2) Caja/Pagos, y (3) Retiro oficial del complejo.

---

## 🌐 Endpoints y Rutas de API (Integración Backend)

Toda la aplicación de Frontend se comunica de forma asíncrona mediante peticiones en capa RESTful al `http.server` de Python a través de estas rutas clave:

### Rutas Analíticas (Conexión GET)
* **`GET /api/status`:** Consulta en vivo (cada 3 segundos) el conteo de *Vehículos en Patrio*, Espacios Libres y la Caja.
* **`GET /api/tickets_today`:** Recolecta el arreglo JSON general cargado de boletos vigentes y finalizados para poblar dinámicamente nuestra tabla frontal.
* **`GET /api/export_excel`:** Engancha un driver local que forja y devuelve crudo un formato binario `.xlsx` de Microsoft Excel con los cierres, ingresos e impuestos computados de los vehículos.

### Rutas Transaccionales (Conexión POST)
* **`POST /api/login`:** Autorización e inicio de la sesión del administrador.
* **`POST /api/entry`**: Emite un nuevo ticket atado a una placa, validando matemáticamente si hay cupo en `TOTAL_SPACES`.
* **`POST /api/ticket`**: Herramienta de auditoría para nuestro *Timeline*. Devuelve el trayecto vitalicio, timestamps y acumulaciones de un folio enviado.
* **`POST /api/payment_info` / `POST /api/payment`**: La primera calcula y cifra el adeudo del boleto (evaluando los minutos). La segunda autoriza el Token de liberación para la salida.
* **`POST /api/exit`**: Última compuerta lógica. Comprueba el folio contra *Adeudos 0.00$* y manda un bloque `OPEN_EXIT` al Hardware físico.
* **`POST /api/force_exit`**: Botón rojo del administrador (Override) para dar salida libre e impune.

### Integración Nube Externa
* **`ZPK Plate-Scanner (LPR)`**: El backend cuenta con un inyector perimetral a `https://zpk.systems/api/plate-scanner/image` para derivar fotos en crudo (Base64) de nuestras Webcams al procesador global y retornarnos las letras del coche limpio.

---

## ⚙️ Reglas Operacionales y Config (`config.py`)

* **Capacidad Máxima (`TOTAL_SPACES`):** Límite configurado fijo de bahías de parking (Por defecto 6).
* **Ventana de Retiro (`PAYMENT_VALID_MINUTES`):** Minutos que se inyectan como amortiguador para que un cliente pueda salir físicamente del parqueo hacia la barrera sin reactivar cargos en su placa después de pagar (Por defecto 2 mins).
* **Reglas Financieras:** Parametrizadas a partir de `TARIFA_MINIMA` y cobros incrementales dictados por `TARIFA_POR_HORA`.
