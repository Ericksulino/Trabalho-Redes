#!/bin/bash
# =============================================================================
# servidor_cenario.sh — Roda no container do SERVIDOR
# Uso: bash servidor_cenario.sh A tcp    (cenário A, modo TCP)
#      bash servidor_cenario.sh A rudp   (cenário A, modo R-UDP)
# =============================================================================

CENARIO=$1
MODO=$2
INTERFACE="eth0"
CAPTURAS_DIR="/app/capturas"
mkdir -p "$CAPTURAS_DIR"

VERDE="\033[0;32m"; RESET="\033[0m"
log() { echo -e "${VERDE}[$(date +%H:%M:%S)]${RESET} $1"; }

if [ -z "$CENARIO" ] || [ -z "$MODO" ]; then
    echo "Uso: bash servidor_cenario.sh [A|B|C] [tcp|rudp]"
    exit 1
fi

case $CENARIO in
    A) DELAY=10;  PERDA=0  ;;
    B) DELAY=50;  PERDA=10 ;;
    C) DELAY=100; PERDA=20 ;;
    *) echo "Cenário inválido. Use A, B ou C."; exit 1 ;;
esac

log "========================================================"
log " CENÁRIO $CENARIO — MODO $MODO"
log " Delay: ${DELAY}ms | Perda: ${PERDA}%"
log "========================================================"

# Mata processos anteriores
pkill -f "servidor.py" 2>/dev/null
pkill -f "tcpdump" 2>/dev/null
sleep 1

# Configura tc
tc qdisc del dev "$INTERFACE" root 2>/dev/null || true
if [ "$PERDA" -eq 0 ]; then
    tc qdisc add dev "$INTERFACE" root netem delay "${DELAY}ms"
else
    tc qdisc add dev "$INTERFACE" root netem delay "${DELAY}ms" loss "${PERDA}%"
fi
log "TC: $(tc qdisc show dev $INTERFACE)"

# Inicia tcpdump
PCAP="$CAPTURAS_DIR/cenario${CENARIO}_${MODO}.pcap"
log "Capturando → $PCAP"
tcpdump -i "$INTERFACE" -w "$PCAP" "port 5001 or port 5002" &
TCPDUMP_PID=$!
sleep 1

log "========================================================"
log " Servidor $MODO pronto. Execute no CLIENTE:"
log "   bash cliente_cenario.sh $CENARIO $MODO"
log "========================================================"

# Servidor encerra sozinho após receber 1 arquivo
python3 servidor.py --modo "$MODO" --uma-vez

# Para tcpdump e exporta CSV
kill $TCPDUMP_PID 2>/dev/null
wait $TCPDUMP_PID 2>/dev/null

CSV="$CAPTURAS_DIR/cenario${CENARIO}_${MODO}.csv"
tcpdump -r "$PCAP" -nn -tttt 2>/dev/null \
    | awk '{print $1","$2","$3","$4","$5}' \
    > "$CSV"

log "✓ $(wc -l < $CSV) pacotes capturados → $CSV"
log "Cenário $CENARIO $MODO concluído!"
