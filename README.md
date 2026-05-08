# Projeto de Redes de Computadores — PPGCC/UFPI (2026-1)

## Estrutura do Projeto

```
projeto_redes/
├── config.py              ← Configurações globais (EDITE SEU NOME E MATRÍCULA AQUI)
├── rudp_protocol.py       ← Estrutura de pacotes R-UDP (Selective Repeat)
├── servidor.py            ← Servidor TCP e R-UDP
├── cliente.py             ← Cliente TCP e R-UDP
├── gerar_teste.py         ← Gera arquivo de teste e verifica integridade
├── executar_cenarios.sh   ← Automatiza os 3 cenários (rodar dentro do Docker)
├── Dockerfile             ← Imagem Ubuntu com Python, tc e tcpdump
├── docker-compose.yml     ← Orquestra servidor e cliente em containers separados
└── capturas/              ← Criado automaticamente: .pcap e .csv das capturas
```

---

## Passo 1 — Configure seu nome e matrícula

Abra `config.py` e preencha:

```python
MATRICULA = "2024100123"         # ← Sua matrícula
NOME      = "João da Silva"      # ← Seu nome completo
```

---

## Passo 2 — Suba os containers Docker

```bash
docker-compose up --build -d
```

Isso cria dois containers na mesma rede:
- `srv_redes` — IP 172.20.0.10 (servidor)
- `cli_redes` — IP 172.20.0.20 (cliente)

---

## Passo 3 — Gere o arquivo de teste

```bash
docker-compose exec servidor python3 gerar_teste.py
```

---

## Passo 4 — Teste manual (opcional)

### Terminal 1 — Servidor:
```bash
docker-compose exec servidor bash
python3 servidor.py --modo tcp
# ou
python3 servidor.py --modo rudp
```

### Terminal 2 — Cliente:
```bash
docker-compose exec cliente bash
python3 cliente.py --modo tcp  --arquivo arquivo_teste.bin
python3 cliente.py --modo rudp --arquivo arquivo_teste.bin
```

---

## Passo 5 — Configurar cenários com `tc`

Dentro do container do **servidor**:

```bash
docker-compose exec servidor bash

# Cenário A: 0% perda / 10ms delay
tc qdisc add dev eth0 root netem delay 10ms

# Cenário B: 10% perda / 50ms delay
tc qdisc change dev eth0 root netem delay 50ms loss 10%

# Cenário C: 20% perda / 100ms delay
tc qdisc change dev eth0 root netem delay 100ms loss 20%

# Remover regras
tc qdisc del dev eth0 root
```

---

## Passo 6 — Captura com tcpdump

```bash
# Captura tráfego nas portas 5001 e 5002
tcpdump -i eth0 -w capturas/cenarioA_tcp.pcap "port 5001 or port 5002" &

# ... execute o cliente ...

# Para a captura e exporta CSV
kill %1
tcpdump -r capturas/cenarioA_tcp.pcap -nn -tttt \
    | awk '{print $1","$2","$3","$4","$5}' \
    > capturas/cenarioA_tcp.csv
```

---

## Passo 7 — Automatizar tudo

Para rodar os 3 cenários automaticamente:

```bash
docker-compose exec servidor bash executar_cenarios.sh
```

---

## Passo 8 — Verificar integridade

```bash
python3 gerar_teste.py --verificar
```

---

## Métricas geradas automaticamente

Após cada execução, os seguintes arquivos JSON são criados:

| Arquivo | Conteúdo |
|---------|----------|
| `metricas_cliente_tcp.json`  | Tempo, throughput, bytes enviados (TCP) |
| `metricas_cliente_rudp.json` | Tempo, throughput, retransmissões (R-UDP) |
| `metricas_servidor_tcp.json` | Tempo, throughput, bytes recebidos (TCP) |
| `metricas_servidor_rudp.json`| Tempo, throughput, pacotes duplicados (R-UDP) |

Use esses JSONs no Google Colab para gerar os gráficos com Plotly/Seaborn.

---

## Protocolo R-UDP — Selective Repeat

### Por que Selective Repeat?
- **Go-Back-N**: ao perder 1 pacote, retransmite N pacotes → ineficiente com alta perda
- **Selective Repeat**: retransmite apenas o pacote perdido → muito mais eficiente no Cenário C (20% perda)

### Estrutura do pacote (20 bytes de cabeçalho):
```
[ seq (4B) | ack (4B) | flags (1B) | length (4B) | CRC32 (4B) | reservado (3B) ] + payload
```

### Flags:
- `0x01` SYN — início da conexão
- `0x02` FIN — fim da transferência
- `0x04` ACK — confirmação
- `0x08` DATA — pacote com dados

### Cabeçalho X-Custom-Auth:
Incluído no payload do SYN e nos metadados TCP, contendo `MATRÍCULA NOME`.
