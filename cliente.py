# =============================================================================
# cliente.py — Cliente de transferência de arquivos (TCP e R-UDP)
# =============================================================================
#
# Como usar:
#   python cliente.py --modo tcp  --arquivo arquivo_teste.bin
#   python cliente.py --modo rudp --arquivo arquivo_teste.bin
#
# O cliente lê o arquivo, envia para o servidor e registra métricas.
# =============================================================================

import socket
import argparse
import logging
import time
import json
import os
import threading
from datetime import datetime

from config import (
    SERVER_IP, PORT_TCP, PORT_RUDP, BUFFER_SIZE,
    WINDOW_SIZE, CHUNK_SIZE, TIMEOUT_SEC, MAX_RETRIES,
    X_CUSTOM_AUTH
)
from rudp_protocol import (
    montar_pacote, desmontar_pacote,
    FLAG_SYN, FLAG_FIN, FLAG_ACK, FLAG_DATA,
    tem_flag, HEADER_SIZE
)

# ── Configuração de logs ───────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("cliente")


# =============================================================================
# MODO TCP
# =============================================================================

def enviar_tcp(caminho_arquivo: str):
    """
    Envia um arquivo via TCP.

    Passos:
    1. Conecta ao servidor
    2. Envia metadados (nome, tamanho, auth) como JSON
    3. Envia os dados do arquivo em chunks
    4. Registra métricas
    """
    nome_arquivo = os.path.basename(caminho_arquivo)
    tamanho = os.path.getsize(caminho_arquivo)

    logger.info(f"[TCP] Conectando a {SERVER_IP}:{PORT_TCP}")

    metricas = {
        "modo": "TCP",
        "arquivo": nome_arquivo,
        "tamanho_bytes": tamanho,
        "inicio": datetime.now().isoformat(),
        "bytes_enviados": 0,
        "tempo_transferencia_s": 0.0,
        "throughput_mbps": 0.0,
        "x_custom_auth": X_CUSTOM_AUTH,
    }

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect((SERVER_IP, PORT_TCP))
        logger.info(f"[TCP] Conectado! Enviando '{nome_arquivo}' ({tamanho} bytes)")

        # ── 1. Envia metadados ──────────────────────────────────────────────
        meta = json.dumps({
            "nome": nome_arquivo,
            "tamanho": tamanho,
            "x_custom_auth": X_CUSTOM_AUTH  # Cabeçalho obrigatório pelo enunciado
        }).encode() + b"\n"
        s.sendall(meta)

        # ── 2. Envia dados do arquivo ───────────────────────────────────────
        bytes_enviados = 0
        inicio = time.perf_counter()

        with open(caminho_arquivo, "rb") as f:
            while True:
                chunk = f.read(BUFFER_SIZE)
                if not chunk:
                    break
                s.sendall(chunk)
                bytes_enviados += len(chunk)
                _mostrar_progresso(bytes_enviados, tamanho)

        fim = time.perf_counter()
        tempo = fim - inicio
        throughput = (bytes_enviados / tempo) / (1024 * 1024) if tempo > 0 else 0

        metricas["bytes_enviados"] = bytes_enviados
        metricas["tempo_transferencia_s"] = round(tempo, 4)
        metricas["throughput_mbps"] = round(throughput, 4)
        metricas["fim"] = datetime.now().isoformat()

        logger.info(
            f"[TCP] ✓ Concluído: {bytes_enviados} bytes em {tempo:.3f}s "
            f"| Throughput: {throughput:.2f} MB/s"
        )

    _salvar_metricas(metricas, "metricas_cliente_tcp.json")
    return metricas


# =============================================================================
# MODO R-UDP com SELECTIVE REPEAT
# =============================================================================

def enviar_rudp(caminho_arquivo: str):
    """
    Envia um arquivo via R-UDP com Selective Repeat.

    Como o Selective Repeat funciona no cliente (emissor):
    - Divide o arquivo em pacotes numerados (0, 1, 2, ...)
    - Mantém uma janela deslizante: envia até WINDOW_SIZE pacotes sem ACK
    - Cada pacote tem seu próprio timer individual
    - Ao receber ACK(n): marca pacote n como confirmado
    - Se o timer de um pacote esgotar: retransmite APENAS aquele pacote
    - A janela avança quando o pacote com menor seq recebe ACK
    """
    nome_arquivo = os.path.basename(caminho_arquivo)
    tamanho = os.path.getsize(caminho_arquivo)

    logger.info(f"[R-UDP] Iniciando envio de '{nome_arquivo}' ({tamanho} bytes)")
    logger.info(f"[R-UDP] Janela: {WINDOW_SIZE} | Timeout: {TIMEOUT_SEC}s | Chunk: {CHUNK_SIZE} bytes")

    metricas = {
        "modo": "R-UDP",
        "arquivo": nome_arquivo,
        "tamanho_bytes": tamanho,
        "inicio": datetime.now().isoformat(),
        "bytes_enviados": 0,
        "tempo_transferencia_s": 0.0,
        "throughput_mbps": 0.0,
        "retransmissoes": 0,
        "pacotes_enviados": 0,
        "x_custom_auth": X_CUSTOM_AUTH,
    }

    # ── Fragmenta o arquivo em chunks ────────────────────────────────────────
    chunks = _fragmentar_arquivo(caminho_arquivo, CHUNK_SIZE)
    total_pacotes = len(chunks)
    logger.info(f"[R-UDP] Arquivo dividido em {total_pacotes} pacotes")

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.settimeout(0.1)  # timeout curto para o recvfrom não bloquear

        destino = (SERVER_IP, PORT_RUDP)

        # ── HANDSHAKE: envia SYN com metadados ───────────────────────────────
        if not _enviar_syn(s, destino, nome_arquivo, tamanho):
            logger.error("[R-UDP] Falha no handshake. Abortando.")
            return None

        # ── TRANSFERÊNCIA com Selective Repeat ───────────────────────────────
        inicio = time.perf_counter()

        # Estado da janela deslizante
        base           = 0            # Índice do pacote mais antigo sem ACK
        proximo_seq    = 0            # Próximo pacote a enviar
        acks           = {}           # {seq: True} — pacotes confirmados
        timers         = {}           # {seq: tempo_do_envio}
        retries        = {}           # {seq: contagem_de_retransmissoes}
        retransmissoes = 0
        pacotes_enviados = 0

        while base < total_pacotes:
            # ── Envia pacotes dentro da janela ────────────────────────────────
            while proximo_seq < total_pacotes and proximo_seq < base + WINDOW_SIZE:
                if proximo_seq not in acks:
                    _enviar_pacote_data(s, destino, proximo_seq, chunks[proximo_seq])
                    timers[proximo_seq] = time.perf_counter()
                    retries.setdefault(proximo_seq, 0)
                    pacotes_enviados += 1
                proximo_seq += 1

            # ── Aguarda ACKs ──────────────────────────────────────────────────
            try:
                dados_brutos, _ = s.recvfrom(HEADER_SIZE + 100)
                resultado = desmontar_pacote(dados_brutos)

                if resultado:
                    _, ack_num, flags, _ = resultado
                    if tem_flag(flags, FLAG_ACK) and ack_num not in acks:
                        acks[ack_num] = True
                        logger.debug(f"[R-UDP] ACK recebido: seq={ack_num}")

                        # Avança a base da janela enquanto tiver ACKs consecutivos
                        while base in acks:
                            base += 1
                            _mostrar_progresso(base, total_pacotes, unidade="pacotes")

            except socket.timeout:
                pass  # Nenhum ACK chegou agora — verifica timeouts abaixo

            # ── Verifica timeouts e retransmite ───────────────────────────────
            agora = time.perf_counter()
            for seq in range(base, min(proximo_seq, base + WINDOW_SIZE)):
                if seq not in acks and seq in timers:
                    if agora - timers[seq] > TIMEOUT_SEC:
                        retries[seq] = retries.get(seq, 0) + 1

                        if retries[seq] > MAX_RETRIES:
                            logger.error(
                                f"[R-UDP] Pacote seq={seq} excedeu {MAX_RETRIES} retransmissões. Abortando."
                            )
                            return None

                        # Retransmite apenas o pacote que deu timeout (Selective Repeat!)
                        logger.debug(f"[R-UDP] Timeout! Retransmitindo seq={seq} (tentativa {retries[seq]})")
                        _enviar_pacote_data(s, destino, seq, chunks[seq])
                        timers[seq] = agora  # Reinicia o timer
                        retransmissoes += 1

        # ── ENCERRAMENTO: envia FIN ───────────────────────────────────────────
        _enviar_fin(s, destino)

        fim = time.perf_counter()
        tempo = fim - inicio
        bytes_enviados = tamanho
        throughput = (bytes_enviados / tempo) / (1024 * 1024) if tempo > 0 else 0

        metricas["bytes_enviados"] = bytes_enviados
        metricas["tempo_transferencia_s"] = round(tempo, 4)
        metricas["throughput_mbps"] = round(throughput, 4)
        metricas["retransmissoes"] = retransmissoes
        metricas["pacotes_enviados"] = pacotes_enviados
        metricas["fim"] = datetime.now().isoformat()

        logger.info(
            f"[R-UDP] ✓ Concluído: {bytes_enviados} bytes em {tempo:.3f}s "
            f"| Throughput: {throughput:.2f} MB/s "
            f"| Retransmissões: {retransmissoes}"
        )

    _salvar_metricas(metricas, "metricas_cliente_rudp.json")
    return metricas


# =============================================================================
# FUNÇÕES AUXILIARES DO R-UDP
# =============================================================================

def _fragmentar_arquivo(caminho: str, tamanho_chunk: int) -> list:
    """Lê o arquivo e retorna uma lista de bytes (um por pacote)."""
    chunks = []
    with open(caminho, "rb") as f:
        while True:
            dados = f.read(tamanho_chunk)
            if not dados:
                break
            chunks.append(dados)
    return chunks


def _enviar_pacote_data(s: socket.socket, destino, seq: int, payload: bytes):
    """Monta e envia um pacote DATA."""
    pkt = montar_pacote(seq=seq, ack=0, flags=FLAG_DATA, payload=payload)
    s.sendto(pkt, destino)


def _enviar_syn(s: socket.socket, destino, nome: str, tamanho: int) -> bool:
    """
    Envia SYN com metadados e aguarda SYN+ACK.
    Tenta até MAX_RETRIES vezes antes de desistir.
    """
    meta = json.dumps({
        "nome": nome,
        "tamanho": tamanho,
        "x_custom_auth": X_CUSTOM_AUTH  # Cabeçalho obrigatório pelo enunciado
    }).encode()

    syn_pkt = montar_pacote(seq=0, ack=0, flags=FLAG_SYN, payload=meta)

    for tentativa in range(1, MAX_RETRIES + 1):
        s.sendto(syn_pkt, destino)
        logger.info(f"[R-UDP] SYN enviado (tentativa {tentativa})")

        try:
            s.settimeout(TIMEOUT_SEC * 2)
            dados, _ = s.recvfrom(HEADER_SIZE + 100)
            resultado = desmontar_pacote(dados)
            if resultado:
                _, _, flags, _ = resultado
                if tem_flag(flags, FLAG_SYN) and tem_flag(flags, FLAG_ACK):
                    logger.info("[R-UDP] SYN+ACK recebido. Conexão estabelecida!")
                    s.settimeout(0.1)
                    return True
        except socket.timeout:
            logger.warning(f"[R-UDP] SYN timeout na tentativa {tentativa}")

    return False


def _enviar_fin(s: socket.socket, destino):
    """Envia FIN e aguarda FIN+ACK para encerrar graciosamente."""
    fin_pkt = montar_pacote(seq=0, ack=0, flags=FLAG_FIN)

    for tentativa in range(1, MAX_RETRIES + 1):
        s.sendto(fin_pkt, destino)
        try:
            s.settimeout(TIMEOUT_SEC * 2)
            dados, _ = s.recvfrom(HEADER_SIZE + 100)
            resultado = desmontar_pacote(dados)
            if resultado:
                _, _, flags, _ = resultado
                if tem_flag(flags, FLAG_FIN) and tem_flag(flags, FLAG_ACK):
                    logger.info("[R-UDP] FIN+ACK recebido. Conexão encerrada.")
                    return
        except socket.timeout:
            logger.warning(f"[R-UDP] FIN timeout na tentativa {tentativa}")


# =============================================================================
# UTILITÁRIOS
# =============================================================================

def _mostrar_progresso(atual: int, total: int, unidade: str = "bytes"):
    """Exibe barra de progresso simples no terminal."""
    if total == 0:
        return
    pct = (atual / total) * 100
    barras = int(pct / 2)
    barra = "█" * barras + "░" * (50 - barras)
    print(f"\r  [{barra}] {pct:5.1f}% ({atual}/{total} {unidade})", end="", flush=True)
    if atual >= total:
        print()  # Quebra a linha ao concluir


def _salvar_metricas(metricas: dict, caminho: str):
    """Salva métricas em um arquivo JSON (acumulando resultados)."""
    historico = []
    if os.path.exists(caminho):
        try:
            with open(caminho, "r") as f:
                historico = json.load(f)
        except Exception:
            pass

    historico.append(metricas)

    with open(caminho, "w") as f:
        json.dump(historico, f, indent=2, ensure_ascii=False)

    logger.info(f"Métricas salvas em '{caminho}'")


# =============================================================================
# PONTO DE ENTRADA
# =============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Cliente de transferência de arquivos")
    parser.add_argument("--modo",    choices=["tcp", "rudp"], required=True)
    parser.add_argument("--arquivo", required=True, help="Caminho do arquivo a enviar")
    args = parser.parse_args()

    if not os.path.exists(args.arquivo):
        logger.error(f"Arquivo '{args.arquivo}' não encontrado.")
        exit(1)

    if args.modo == "tcp":
        enviar_tcp(args.arquivo)
    else:
        enviar_rudp(args.arquivo)
