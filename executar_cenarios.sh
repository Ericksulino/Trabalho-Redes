#!/bin/bash
# =============================================================================
# executar_cenarios.sh — Automatiza os 3 cenários de teste (A, B, C)
# =============================================================================
#
# Execute DENTRO do container do servidor:
#   docker-compose exec servidor bash executar_cenarios.sh
#
# O script:
#   1. Configura o tc para cada cenário
#   2. Inicia o tcpdump em background
#   3. Sinaliza para o cliente rodar
#   4. Para o tcpdump e exporta CSV
# =============================================================================

# Interface de rede do container (ajuste se necessário)
INTERFACE="eth0"
ARQUIVO_TESTE="arquivo_teste.bin"
CAPTURAS_DIR="/app/capturas"
mkdir -p "$CAPTURAS_DIR"

# Cores para o terminal
VERDE="\033[0;32m"
AMARELO="\033[1;33m"
VERMELHO="\033[0;31m"
RESET="\033[0m"

log() { echo -e "${VERDE}[$(date +%H:%M:%S)]${RESET} $1"; }
aviso() { echo -e "${AMARELO}[AVISO]${RESET} $1"; }
erro() { echo -e "${VERMELHO}[ERRO]${RESET} $1"; }

# =============================================================================
# Função: configurar_tc
# Aplica regras de tráfego com o tc (Traffic Control)
# =============================================================================
configurar_tc() {
    local cenario=$1
    local delay=$2
    local perda=$3

    log "Configurando TC — Cenário $cenario: delay=${delay}ms, perda=${perda}%"

    # Remove qualquer regra anterior
    tc qdisc del dev "$INTERFACE" root 2>/dev/null || true

    if [ "$perda" -eq 0 ]; then
        # Só delay, sem perda
        tc qdisc add dev "$INTERFACE" root netem delay "${delay}ms"
    else
        # Delay + perda de pacotes (modelo Bernoulli independente)
        tc qdisc add dev "$INTERFACE" root netem delay "${delay}ms" loss "${perda}%"
    fi

    log "TC configurado. Verificando:"
    tc qdisc show dev "$INTERFACE"
}

# =============================================================================
# Função: iniciar_tcpdump
# Captura o tráfego e salva em .pcap
# =============================================================================
iniciar_tcpdump() {
    local nome_arquivo=$1
    local pcap_path="$CAPTURAS_DIR/${nome_arquivo}.pcap"

    log "Iniciando tcpdump → $pcap_path"

    # Captura todo o tráfego nas portas 5001 (TCP) e 5002 (UDP)
    # -i: interface | -w: arquivo de saída | &: roda em background
    tcpdump -i "$INTERFACE" \
        -w "$pcap_path" \
        "port 5001 or port 5002" &

    TCPDUMP_PID=$!
    log "tcpdump rodando (PID=$TCPDUMP_PID)"
    sleep 1  # Aguarda o tcpdump inicializar
}

# =============================================================================
# Função: parar_tcpdump_e_exportar
# Para a captura e converte para CSV
# =============================================================================
parar_tcpdump_e_exportar() {
    local nome_arquivo=$1
    local pcap_path="$CAPTURAS_DIR/${nome_arquivo}.pcap"
    local csv_path="$CAPTURAS_DIR/${nome_arquivo}.csv"

    log "Parando tcpdump (PID=$TCPDUMP_PID)..."
    kill "$TCPDUMP_PID" 2>/dev/null
    wait "$TCPDUMP_PID" 2>/dev/null

    log "Exportando $pcap_path → $csv_path"

    # Converte .pcap para CSV com campos básicos
    # -r: lê o pcap | -nn: não resolve nomes | -tttt: timestamp legível
    tcpdump -r "$pcap_path" -nn -tttt \
        | awk '{print $1","$2","$3","$4","$5}' \
        > "$csv_path"

    # Versão mais detalhada (se tshark estiver disponível)
    if command -v tshark &>/dev/null; then
        tshark -r "$pcap_path" \
            -T fields \
            -e frame.time_relative \
            -e ip.src \
            -e ip.dst \
            -e frame.len \
            -e tcp.analysis.retransmission \
            -E header=y \
            -E separator=, \
            > "$CAPTURAS_DIR/${nome_arquivo}_detalhado.csv"
        log "CSV detalhado (tshark) salvo."
    fi

    log "✓ Capturas salvas em $CAPTURAS_DIR/"
}

# =============================================================================
# Executa os 3 cenários
# =============================================================================

log "========================================================"
log " INICIANDO BATERIA DE TESTES — 3 CENÁRIOS"
log "========================================================"

# Gera arquivo de teste se não existir
if [ ! -f "$ARQUIVO_TESTE" ]; then
    log "Gerando arquivo de teste..."
    python3 gerar_teste.py
fi

for CENARIO in A B C; do
    case $CENARIO in
        A) DELAY=10;  PERDA=0  ;;
        B) DELAY=50;  PERDA=10 ;;
        C) DELAY=100; PERDA=20 ;;
    esac

    log ""
    log "========================================================"
    log " CENÁRIO $CENARIO: ${DELAY}ms delay | ${PERDA}% perda"
    log "========================================================"

    # Configura o ambiente de rede
    configurar_tc "$CENARIO" "$DELAY" "$PERDA"

    # ── Teste TCP ─────────────────────────────────────────────────────────────
    log "--- MODO TCP ---"
    iniciar_tcpdump "cenario${CENARIO}_tcp"

    # Inicia o servidor TCP em background
    python3 servidor.py --modo tcp &
    SRV_PID=$!
    sleep 1

    # Executa o cliente TCP
    python3 cliente.py --modo tcp --arquivo "$ARQUIVO_TESTE"
    sleep 2

    # Para servidor e tcpdump
    kill "$SRV_PID" 2>/dev/null
    parar_tcpdump_e_exportar "cenario${CENARIO}_tcp"
    sleep 2

    # ── Teste R-UDP ───────────────────────────────────────────────────────────
    log "--- MODO R-UDP ---"
    iniciar_tcpdump "cenario${CENARIO}_rudp"

    # Inicia o servidor R-UDP em background
    python3 servidor.py --modo rudp &
    SRV_PID=$!
    sleep 1

    # Executa o cliente R-UDP
    python3 cliente.py --modo rudp --arquivo "$ARQUIVO_TESTE"
    sleep 2

    # Para servidor e tcpdump
    kill "$SRV_PID" 2>/dev/null
    parar_tcpdump_e_exportar "cenario${CENARIO}_rudp"
    sleep 2

done

# Remove regras do tc ao final
tc qdisc del dev "$INTERFACE" root 2>/dev/null || true
log "Regras TC removidas."

log ""
log "========================================================"
log " ✓ TODOS OS CENÁRIOS CONCLUÍDOS"
log " Resultados em: $CAPTURAS_DIR/"
log "========================================================"

# Lista os arquivos gerados
ls -lh "$CAPTURAS_DIR/"
