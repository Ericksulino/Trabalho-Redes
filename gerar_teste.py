#!/usr/bin/env python3
# =============================================================================
# gerar_teste.py — Gera arquivo de teste e executa todos os cenários
# =============================================================================
#
# Use este script para:
#   1. Gerar um arquivo binário de teste (10 MB por padrão)
#   2. (Opcional) Verificar se o arquivo recebido é idêntico ao enviado
#
# Execute:
#   python gerar_teste.py
# =============================================================================

import os
import hashlib
import logging

from config import TEST_FILE, FILE_SIZE_MB

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger("gerar_teste")


def gerar_arquivo(caminho: str, tamanho_mb: int):
    """
    Gera um arquivo binário com dados aleatórios para usar nos testes.
    Dados aleatórios são melhores para teste pois não sofrem compressão.
    """
    tamanho_bytes = tamanho_mb * 1024 * 1024
    logger.info(f"Gerando arquivo de teste: '{caminho}' ({tamanho_mb} MB = {tamanho_bytes} bytes)")

    with open(caminho, "wb") as f:
        # Grava em blocos de 1 MB para não consumir muita RAM
        bloco = 1024 * 1024
        for i in range(tamanho_mb):
            f.write(os.urandom(bloco))
            print(f"\r  Progresso: {i+1}/{tamanho_mb} MB", end="", flush=True)

    print()
    logger.info(f"✓ Arquivo gerado: {os.path.getsize(caminho)} bytes")
    return caminho


def calcular_md5(caminho: str) -> str:
    """Calcula o MD5 de um arquivo para verificar integridade."""
    md5 = hashlib.md5()
    with open(caminho, "rb") as f:
        while True:
            bloco = f.read(8192)
            if not bloco:
                break
            md5.update(bloco)
    return md5.hexdigest()


def verificar_integridade(original: str, recebido: str):
    """
    Compara os MD5 do arquivo original e do recebido.
    Se forem iguais, a transferência foi perfeita (sem corrupção).
    """
    if not os.path.exists(recebido):
        logger.warning(f"Arquivo recebido '{recebido}' não encontrado. Execute o teste primeiro.")
        return False

    md5_orig = calcular_md5(original)
    md5_recv = calcular_md5(recebido)

    if md5_orig == md5_recv:
        logger.info(f"✓ Integridade OK! MD5: {md5_orig}")
        return True
    else:
        logger.error(f"✗ ERRO DE INTEGRIDADE!")
        logger.error(f"  Original : {md5_orig}")
        logger.error(f"  Recebido : {md5_recv}")
        return False


if __name__ == "__main__":
    # Gera o arquivo de teste se não existir
    if not os.path.exists(TEST_FILE):
        gerar_arquivo(TEST_FILE, FILE_SIZE_MB)
    else:
        logger.info(f"Arquivo '{TEST_FILE}' já existe ({os.path.getsize(TEST_FILE)} bytes). Pulando geração.")

    print()
    print("=" * 60)
    print("PRÓXIMOS PASSOS:")
    print("=" * 60)
    print()
    print("1. Em um terminal, inicie o SERVIDOR:")
    print("     python servidor.py --modo tcp")
    print("   ou")
    print("     python servidor.py --modo rudp")
    print()
    print("2. Em outro terminal, execute o CLIENTE:")
    print(f"     python cliente.py --modo tcp  --arquivo {TEST_FILE}")
    print(f"     python cliente.py --modo rudp --arquivo {TEST_FILE}")
    print()
    print("3. Para simular cenários de perda (dentro do container Docker):")
    print()
    print("   Cenário A - 0% perda / 10ms delay:")
    print("     tc qdisc add dev eth0 root netem delay 10ms")
    print()
    print("   Cenário B - 10% perda / 50ms delay:")
    print("     tc qdisc change dev eth0 root netem delay 50ms loss 10%")
    print()
    print("   Cenário C - 20% perda / 100ms delay:")
    print("     tc qdisc change dev eth0 root netem delay 100ms loss 20%")
    print()
    print("   Para remover as regras tc:")
    print("     tc qdisc del dev eth0 root")
    print()
    print("4. Para verificar integridade após transferência:")
    print("     python gerar_teste.py --verificar")
    print()

    # Verifica integridade se solicitado
    import sys
    if "--verificar" in sys.argv:
        print("Verificando integridade dos arquivos recebidos...")
        for modo in ["tcp", "rudp"]:
            recebido = f"recebido_{modo}_{TEST_FILE}"
            print(f"\nModo {modo.upper()}:")
            verificar_integridade(TEST_FILE, recebido)
