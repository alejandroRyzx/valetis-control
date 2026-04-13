#!/bin/bash
# Script para iniciar Valetis Control en Mac

# Obtener la ruta exacta de donde está este archivo
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

echo "====================================="
echo "  🚀 Iniciando Valetis Control...  "
echo "====================================="

# Activar el entorno virtual y lanzar el servidor
source .venv/bin/activate
python web_server.py
