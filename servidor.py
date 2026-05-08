# =============================================================================
# servidor.py — Servidor de transferência de arquivos (TCP e R-UDP)
# =============================================================================
#
# Como usar:
#   python servidor.py --modo tcp    (inicia servidor TCP na porta 5001)
#   python servidor.py --modo rudp   (inicia servidor R-UDP na porta 5002)
#
# O servidor recebe o arquivo e salva como "recebido_<modo>.bin"
# =============================================================================

import socket
import threading
import argparse
import logging
import time
import json
import os
from datetime import datetime

# Importa nossas configurações e o protocolo R-UDP
from config import (
    HOST, PORT_TCP, PORT_RUDP, BUFFER_SIZE,
    WINDOW_SIZE, CHUNK_SIZE, X_CUSTOM_AUTH
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
logger = logging.getLogger("servidor")


# =============================================================================
# MODO TCP
# =============================================================================

def servidor_tcp():
    """
    Servidor TCP simples.
    - Aceita conexões de clientes
    - Lê o nome e tamanho do arquivo que virá
    - Recebe os bytes e salva no disco
    - Registra tempo e throughput
    """
    logger.info(f"[TCP] Aguardando conexões em {HOST}:{PORT_TCP}")

    # Cria o socket TCP (SOCK_STREAM = orientado a conexão)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((HOST, PORT_TCP))
        srv.listen(5)  # Aceita até 5 conexões na fila

        while True:
            conn, addr = srv.accept()
            logger.info(f"[TCP] Conexão de {addr}")
            # Cada cliente é tratado em uma thread separada
            t = threading.Thread(target=_tratar_cliente_tcp, args=(conn, addr), daemon=True)
            t.start()


def _tratar_cliente_tcp(conn: socket.socket, addr):
    """Trata um cliente TCP individual."""
    metricas = {
        "modo": "TCP",
        "cliente": str(addr),
        "inicio": datetime.now().isoformat(),
        "bytes_recebidos": 0,
        "tempo_transferencia_s": 0.0,
        "throughput_mbps": 0.0,
        "x_custom_auth": ""
    }

    try:
        with conn:
            # ── 1. Recebe metadados do arquivo (JSON terminado em '\n') ──────
            meta_raw = b""
            while b"\n" not in meta_raw:
                chunk = conn.recv(BUFFER_SIZE)
                if not chunk:
                    break
                meta_raw += chunk

            linha, restante = meta_raw.split(b"\n", 1)
            meta = json.loads(linha.decode())

            nome_arquivo = meta["nome"]
            tamanho_total = meta["tamanho"]
            x_auth = meta.get("x_custom_auth", "N/A")
            metricas["x_custom_auth"] = x_auth

            logger.info(f"[TCP] Recebendo '{nome_arquivo}' ({tamanho_total} bytes) | Auth: {x_auth}")

            # ── 2. Recebe os dados do arquivo ─────────────────────────────────
            arquivo_saida = f"recebido_tcp_{nome_arquivo}"
            bytes_recebidos = len(restante)
            inicio = time.perf_counter()

            with open(arquivo_saida, "wb") as f:
                f.write(restante)  # escreve o que já veio junto com os metadados

                while bytes_recebidos < tamanho_total:
                    dados = conn.recv(BUFFER_SIZE)
                    if not dados:
                        break
                    f.write(dados)
                    bytes_recebidos += len(dados)

            fim = time.perf_counter()
            tempo = fim - inicio

            # ── 3. Calcula e registra métricas ────────────────────────────────
            throughput = (bytes_recebidos / tempo) / (1024 * 1024) if tempo > 0 else 0

            metricas["bytes_recebidos"] = bytes_recebidos
            metricas["tempo_transferencia_s"] = round(tempo, 4)
            metricas["throughput_mbps"] = round(throughput, 4)
            metricas["fim"] = datetime.now().isoformat()

            logger.info(
                f"[TCP] ✓ Transferência concluída: {bytes_recebidos} bytes "
                f"em {tempo:.3f}s | Throughput: {throughput:.2f} MB/s"
            )

            # Salva métricas em JSON (para análise posterior e gráficos)
            _salvar_metricas(metricas, "metricas_servidor_tcp.json")

    except Exception as e:
        logger.error(f"[TCP] Erro ao tratar cliente {addr}: {e}")


# =============================================================================
# MODO R-UDP com SELECTIVE REPEAT
# =============================================================================

def servidor_rudp():
    """
    Servidor R-UDP com Selective Repeat.

    Como o Selective Repeat funciona no servidor (receptor):
    - Mantém um buffer para aceitar pacotes fora de ordem
    - Envia ACK individual para cada pacote recebido corretamente
    - Só "entrega" os dados quando a sequência está completa e em ordem
    - A janela de recepção avança conforme pacotes consecutivos chegam
    """
    logger.info(f"[R-UDP] Aguardando no {HOST}:{PORT_RUDP}")

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as srv:
        srv.bind((HOST, PORT_RUDP))

        # Dicionário para guardar estado de cada cliente ativo
        # chave = endereço (ip, porta), valor = dicionário de estado
        clientes = {}

        while True:
            try:
                dados_brutos, addr = srv.recvfrom(BUFFER_SIZE + HEADER_SIZE + 100)
            except Exception as e:
                logger.error(f"[R-UDP] Erro ao receber: {e}")
                continue

            resultado = desmontar_pacote(dados_brutos)
            if resultado is None:
                # Pacote corrompido — ignora (sem enviar NAK, o timeout cuidará da retransmissão)
                logger.warning(f"[R-UDP] Pacote corrompido de {addr}, ignorando.")
                continue

            seq, ack_num, flags, payload = resultado

            # ── Inicializa estado para novo cliente ───────────────────────────
            if addr not in clientes:
                clientes[addr] = _novo_estado_cliente()

            estado = clientes[addr]

            # ── Trata SYN (início de transferência) ───────────────────────────
            if tem_flag(flags, FLAG_SYN):
                _tratar_syn_rudp(srv, addr, payload, estado)

            # ── Trata DATA (pacote de dados) ──────────────────────────────────
            elif tem_flag(flags, FLAG_DATA):
                _tratar_data_rudp(srv, addr, seq, payload, estado)

            # ── Trata FIN (fim de transferência) ──────────────────────────────
            elif tem_flag(flags, FLAG_FIN):
                _tratar_fin_rudp(srv, addr, estado)
                del clientes[addr]  # Limpa estado do cliente


def _novo_estado_cliente() -> dict:
    """Cria um dicionário de estado para um novo cliente R-UDP."""
    return {
        "nome_arquivo": "",
        "tamanho_total": 0,
        "x_custom_auth": "",
        "base": 0,              # Próximo seq esperado (início da janela)
        "buffer": {},           # Buffer de pacotes fora de ordem: {seq: payload}
        "arquivo": None,        # Handle do arquivo aberto para escrita
        "bytes_escritos": 0,
        "inicio": None,
        "pacotes_recebidos": 0,
        "pacotes_duplicados": 0,
    }


def _tratar_syn_rudp(srv: socket.socket, addr, payload: bytes, estado: dict):
    """Processa o SYN inicial: lê metadados e abre o arquivo de saída."""
    try:
        meta = json.loads(payload.decode())
        estado["nome_arquivo"] = meta["nome"]
        estado["tamanho_total"] = meta["tamanho"]
        estado["x_custom_auth"] = meta.get("x_custom_auth", "N/A")
        estado["inicio"] = time.perf_counter()
        estado["base"] = 0
        estado["buffer"] = {}

        arquivo_saida = f"recebido_rudp_{meta['nome']}"
        estado["arquivo"] = open(arquivo_saida, "wb")

        logger.info(
            f"[R-UDP] SYN de {addr}: '{meta['nome']}' ({meta['tamanho']} bytes) "
            f"| Auth: {meta.get('x_custom_auth', 'N/A')}"
        )

        # Responde com SYN+ACK confirmando o início
        syn_ack = montar_pacote(seq=0, ack=0, flags=FLAG_SYN | FLAG_ACK)
        srv.sendto(syn_ack, addr)

    except Exception as e:
        logger.error(f"[R-UDP] Erro no SYN de {addr}: {e}")


def _tratar_data_rudp(srv: socket.socket, addr, seq: int, payload: bytes, estado: dict):
    """
    Processa um pacote de dados com Selective Repeat.

    Regras:
    1. Se seq == base: escreve e avança a janela (e esvazia buffer em sequência)
    2. Se seq está dentro da janela e não recebemos antes: guarda no buffer
    3. Se já recebemos: envia ACK de novo (duplicado, cliente pode ter perdido o ACK)
    4. Fora da janela: ignora
    """
    base = estado["base"]
    limite_janela = base + WINDOW_SIZE

    # Pacote dentro da janela de recepção?
    if base <= seq < limite_janela:
        if seq not in estado["buffer"]:
            # Novo pacote — guarda no buffer
            estado["buffer"][seq] = payload
            estado["pacotes_recebidos"] += 1

            # Verifica se podemos avançar a janela (escrever dados em ordem)
            while estado["base"] in estado["buffer"]:
                dados = estado["buffer"].pop(estado["base"])
                estado["arquivo"].write(dados)
                estado["bytes_escritos"] += len(dados)
                estado["base"] += 1

        else:
            # Pacote duplicado — reenvia ACK para ajudar o cliente
            estado["pacotes_duplicados"] += 1
            logger.debug(f"[R-UDP] Pacote duplicado seq={seq} de {addr}")

        # Envia ACK individual para este pacote (Selective Repeat: ACK por pacote)
        ack_pkt = montar_pacote(seq=0, ack=seq, flags=FLAG_ACK)
        srv.sendto(ack_pkt, addr)

    elif seq < base:
        # Pacote muito antigo — reenvia ACK (cliente não recebeu o ACK anterior)
        ack_pkt = montar_pacote(seq=0, ack=seq, flags=FLAG_ACK)
        srv.sendto(ack_pkt, addr)

    else:
        # Fora da janela de recepção — ignora silenciosamente
        logger.debug(f"[R-UDP] Pacote seq={seq} fora da janela [{base}, {limite_janela}), ignorado.")


def _tratar_fin_rudp(srv: socket.socket, addr, estado: dict):
    """Finaliza a transferência: fecha arquivo, calcula métricas."""
    if estado["arquivo"]:
        estado["arquivo"].close()

    fim = time.perf_counter()
    tempo = fim - estado["inicio"] if estado["inicio"] else 0
    bytes_recebidos = estado["bytes_escritos"]
    throughput = (bytes_recebidos / tempo) / (1024 * 1024) if tempo > 0 else 0

    logger.info(
        f"[R-UDP] ✓ FIN de {addr}: {bytes_recebidos} bytes "
        f"em {tempo:.3f}s | Throughput: {throughput:.2f} MB/s | "
        f"Pacotes: {estado['pacotes_recebidos']} | Duplicados: {estado['pacotes_duplicados']}"
    )

    # Envia FIN+ACK para confirmar encerramento
    fin_ack = montar_pacote(seq=0, ack=0, flags=FLAG_FIN | FLAG_ACK)
    srv.sendto(fin_ack, addr)

    # Salva métricas
    metricas = {
        "modo": "R-UDP",
        "cliente": str(addr),
        "x_custom_auth": estado["x_custom_auth"],
        "bytes_recebidos": bytes_recebidos,
        "tempo_transferencia_s": round(tempo, 4),
        "throughput_mbps": round(throughput, 4),
        "pacotes_recebidos": estado["pacotes_recebidos"],
        "pacotes_duplicados": estado["pacotes_duplicados"],
        "fim": datetime.now().isoformat(),
    }
    _salvar_metricas(metricas, "metricas_servidor_rudp.json")


# =============================================================================
# UTILITÁRIOS
# =============================================================================

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
    parser = argparse.ArgumentParser(description="Servidor de transferência de arquivos")
    parser.add_argument(
        "--modo",
        choices=["tcp", "rudp"],
        required=True,
        help="Protocolo a usar: 'tcp' ou 'rudp'"
    )
    args = parser.parse_args()

    if args.modo == "tcp":
        servidor_tcp()
    else:
        servidor_rudp()
