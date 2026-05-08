#!/bin/bash
# =============================================================================
# cliente_cenario.sh — Roda no container do CLIENTE
# Uso: bash cliente_cenario.sh A tcp    (cenário A, modo TCP)
#      bash cliente_cenario.sh A rudp   (cenário A, modo R-UDP)
# =============================================================================

CENARIO=$1
MODO=$2
ARQUIVO="arquivo_teste.bin"

VERDE="\033[0;32m"; RESET="\033[0m"
log() { echo -e "${VERDE}[$(date +%H:%M:%S)]${RESET} $1"; }

if [ -z "$CENARIO" ] || [ -z "$MODO" ]; then
    echo "Uso: bash cliente_cenario.sh [A|B|C] [tcp|rudp]"
    exit 1
fi

if [ ! -f "$ARQUIVO" ]; then
    log "Arquivo de teste não encontrado. Gerando..."
    python3 gerar_teste.py
fi

log "Iniciando cliente $MODO — Cenário $CENARIO"
python3 cliente.py --modo "$MODO" --arquivo "$ARQUIVO"
log "✓ Cliente $MODO finalizado."
