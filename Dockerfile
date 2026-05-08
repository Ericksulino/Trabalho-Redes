# =============================================================================
# Dockerfile — Container Ubuntu para os testes de rede
# =============================================================================
# Este container inclui Python, iproute2 (para o tc) e tcpdump.
# O comando 'tc' exige que o container seja executado com NET_ADMIN capability.

FROM ubuntu:22.04

# Evita prompts interativos durante instalação
ENV DEBIAN_FRONTEND=noninteractive

# Instala dependências do sistema
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    iproute2 \        
    tcpdump \         
    net-tools \       
    iputils-ping \    
    && rm -rf /var/lib/apt/lists/*

# Define o diretório de trabalho
WORKDIR /app

# Copia os arquivos do projeto
COPY . .

# Instala dependências Python (nenhuma externa necessária, mas deixamos para expansão)
# RUN pip3 install -r requirements.txt

# Cria diretório para logs/capturas
RUN mkdir -p /app/capturas

# Expõe as portas dos servidores
EXPOSE 5001/tcp
EXPOSE 5002/udp
