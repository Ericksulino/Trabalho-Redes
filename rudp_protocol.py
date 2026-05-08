# =============================================================================
# rudp_protocol.py — Estrutura de pacotes e funções auxiliares do R-UDP
# =============================================================================
#
# Este arquivo define como cada pacote R-UDP é montado e desmontado.
# É usado tanto pelo cliente quanto pelo servidor.
#
# Estrutura do pacote (cabeçalho de 20 bytes + dados):
#
#  Bytes  0- 3 : Número de sequência (int, 4 bytes)
#  Bytes  4- 7 : Número de ACK      (int, 4 bytes)
#  Bytes  8- 8 : Flags              (1 byte: SYN=1, FIN=2, ACK=4, DATA=8)
#  Bytes  9-12 : Tamanho dos dados  (int, 4 bytes)
#  Bytes 13-16 : Checksum CRC32     (int, 4 bytes)
#  Bytes 17-19 : Reservado (zeros)  (3 bytes)
#  Bytes 20+   : Payload (dados)
# =============================================================================

import struct
import zlib
import logging

# Formato do cabeçalho para struct.pack / struct.unpack
# ! = big-endian (padrão de rede)
# I = unsigned int (4 bytes)  B = unsigned byte (1 byte)
HEADER_FORMAT = "!IIBI4sxxx"   # seq, ack, flags, length, checksum, 3 bytes padding
HEADER_SIZE   = struct.calcsize(HEADER_FORMAT)  # deve dar 20 bytes

# ── Flags de controle ─────────────────────────────────────────────────────────
FLAG_SYN  = 0x01   # Início de conexão
FLAG_FIN  = 0x02   # Fim de transferência
FLAG_ACK  = 0x04   # Confirmação de recebimento
FLAG_DATA = 0x08   # Pacote carrega dados

logger = logging.getLogger("rudp_protocol")


def calcular_checksum(dados: bytes) -> bytes:
    """
    Calcula o CRC32 dos dados e retorna como 4 bytes.
    CRC32 detecta corrupção de bits no payload.
    """
    crc = zlib.crc32(dados) & 0xFFFFFFFF  # garante valor unsigned de 32 bits
    return struct.pack("!I", crc)


def montar_pacote(seq: int, ack: int, flags: int, payload: bytes = b"") -> bytes:
    """
    Monta um pacote R-UDP completo (cabeçalho + payload).

    Parâmetros:
        seq     : número de sequência deste pacote
        ack     : número do próximo pacote esperado (confirma recebimento)
        flags   : combinação de FLAG_SYN, FLAG_FIN, FLAG_ACK, FLAG_DATA
        payload : dados a transportar (pode ser vazio para pacotes de controle)

    Retorna:
        bytes completos prontos para envio via socket UDP
    """
    checksum = calcular_checksum(payload)
    cabecalho = struct.pack(
        HEADER_FORMAT,
        seq,           # número de sequência
        ack,           # número de confirmação
        flags,         # flags de controle
        len(payload),  # tamanho do payload
        checksum,      # CRC32 do payload
    )
    return cabecalho + payload


def desmontar_pacote(dados_brutos: bytes):
    """
    Desmonta um pacote R-UDP recebido.

    Retorna:
        (seq, ack, flags, payload) ou None se o pacote estiver corrompido.
    """
    if len(dados_brutos) < HEADER_SIZE:
        logger.warning("Pacote muito pequeno para ter cabeçalho válido.")
        return None

    try:
        seq, ack, flags, length, checksum_recebido = struct.unpack(
            HEADER_FORMAT, dados_brutos[:HEADER_SIZE]
        )
        payload = dados_brutos[HEADER_SIZE:]

        # Verifica se o tamanho declarado no cabeçalho bate com os dados recebidos
        if len(payload) != length:
            logger.warning(f"Tamanho inconsistente: cabeçalho diz {length}, mas recebemos {len(payload)} bytes.")
            return None

        # Verifica integridade via checksum
        checksum_calculado = calcular_checksum(payload)
        if checksum_recebido != checksum_calculado:
            logger.warning(f"Checksum inválido no pacote seq={seq}. Pacote descartado.")
            return None

        return seq, ack, flags, payload

    except struct.error as e:
        logger.error(f"Erro ao desmontar pacote: {e}")
        return None


def tem_flag(flags: int, flag: int) -> bool:
    """Verifica se uma flag específica está ativa."""
    return bool(flags & flag)
