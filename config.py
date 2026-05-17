# config.py Configurações globais do projeto

# Todos os parâmetros ficam aqui para facilitar ajustes sem mexer no código.

# Identificação (obrigatório pelo enunciado)
MATRICULA = "20261011376"   
NOME      = "ERICKSULINO_MANOEL_DE_ARAUJO_MOURA"      
X_CUSTOM_AUTH = f"{MATRICULA} {NOME}"  # Valor que vai no cabeçalho dos pacotes

# Rede
HOST = "0.0.0.0"          # O servidor escuta em todas as interfaces
SERVER_IP = "172.20.0.10"   # IP do servidor (cliente usa isso para conectar)

PORT_TCP  = 5001           # Porta para o modo TCP
PORT_RUDP = 5002           # Porta para o modo R-UDP

BUFFER_SIZE = 4096         # Tamanho do buffer de leitura/envio em bytes

#Parâmetros do R-UDP (Selective Repeat)
WINDOW_SIZE   = 8          # Tamanho da janela deslizante (número de pacotes)
TIMEOUT_SEC   = 1.0        # Tempo (segundos) antes de retransmitir um pacote
MAX_RETRIES   = 10         # Máximo de retransmissões por pacote antes de desistir
CHUNK_SIZE    = 1024       # Tamanho de cada fragmento de dados (bytes)

#Arquivo de teste
TEST_FILE = "arquivo_teste.bin"   # Nome do arquivo que será transferido
FILE_SIZE_MB = 10                 # Tamanho do arquivo de teste em MB
