# Projeto de Redes de Computadores — PPGCC/UFPI (2026-1)

## Estrutura do Projeto

```
Trabalho-Redes/
├── config.py              ← Configurações globais (EDITE SEU NOME E MATRÍCULA AQUI)
├── rudp_protocol.py       ← Estrutura de pacotes R-UDP (Selective Repeat)
├── servidor.py            ← Servidor TCP e R-UDP
├── cliente.py             ← Cliente TCP e R-UDP
├── gerar_teste.py         ← Gera arquivo de teste e verifica integridade
├── servidor_cenario.sh    ← Roda o servidor para um cenário/modo específico
├── cliente_cenario.sh     ← Roda o cliente para um cenário/modo específico
├── Dockerfile             ← Imagem Ubuntu com Python, tc e tcpdump
├── docker-compose.yml     ← Orquestra servidor e cliente em containers separados
├── arquivo_teste.bin      ← Arquivo binário de 10 MB usado nos testes
└── capturas/              ← Gerado automaticamente: .pcap e .csv das capturas
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

Isso cria dois containers Ubuntu na mesma rede virtual:
- `srv_redes` — IP `172.20.0.10` (servidor)
- `cli_redes` — IP `172.20.0.20` (cliente)

Verifique se estão rodando:
```bash
docker ps
```

---

## Passo 3 — Gere o arquivo de teste

```bash
docker-compose exec servidor python3 gerar_teste.py
docker cp srv_redes:/app/arquivo_teste.bin .
docker cp arquivo_teste.bin cli_redes:/app/arquivo_teste.bin
```

---

## Passo 4 — Execute os cenários de teste

Os testes são executados em **dois terminais simultaneamente**.

### Como funciona

O `servidor_cenario.sh` recebe dois argumentos: o cenário (`A`, `B` ou `C`) e o modo (`tcp` ou `rudp`). Ele configura o `tc`, inicia o `tcpdump`, sobe o servidor e **encerra sozinho** após receber o arquivo. O `cliente_cenario.sh` apenas dispara o cliente para o cenário/modo correspondente.

### Sequência completa

Abra dois terminais. Entre nos containers uma vez e rode os comandos na sequência:

**Terminal 1:**
```bash
docker-compose exec servidor bash
```

**Terminal 2:**
```bash
docker-compose exec cliente bash
```

Depois execute na ordem abaixo — sempre espere o Terminal 1 mostrar `Servidor pronto` antes de rodar o Terminal 2:

```
Terminal 1                          Terminal 2
──────────────────────────────────  ──────────────────────────────
bash servidor_cenario.sh A tcp   →  bash cliente_cenario.sh A tcp
bash servidor_cenario.sh A rudp  →  bash cliente_cenario.sh A rudp
bash servidor_cenario.sh B tcp   →  bash cliente_cenario.sh B tcp
bash servidor_cenario.sh B rudp  →  bash cliente_cenario.sh B rudp
bash servidor_cenario.sh C tcp   →  bash cliente_cenario.sh C tcp
bash servidor_cenario.sh C rudp  →  bash cliente_cenario.sh C rudp
```

### Parâmetros de cada cenário

| Cenário | Delay | Perda |
|---------|-------|-------|
| A | 10ms | 0% |
| B | 50ms | 10% |
| C | 100ms | 20% |

---

## Passo 5 — Copie os resultados para sua máquina

Fora dos containers:

```bash
docker cp srv_redes:/app/metricas_servidor_tcp.json  .
docker cp srv_redes:/app/metricas_servidor_rudp.json .
docker cp cli_redes:/app/metricas_cliente_tcp.json   .
docker cp cli_redes:/app/metricas_cliente_rudp.json  .
```

Os arquivos `.pcap` e `.csv` já estão em `capturas/` automaticamente (volume compartilhado).

---

## Passo 6 — Verifique a integridade

```bash
docker-compose exec servidor python3 gerar_teste.py --verificar
```

Compara o MD5 do arquivo original com o recebido. Se mostrar ✓, a transferência foi perfeita.

---

## Métricas geradas automaticamente

Após cada execução, os seguintes arquivos JSON são criados:

| Arquivo | Conteúdo |
|---------|----------|
| `metricas_cliente_tcp.json`   | Tempo, throughput, bytes enviados (TCP) |
| `metricas_cliente_rudp.json`  | Tempo, throughput, retransmissões (R-UDP) |
| `metricas_servidor_tcp.json`  | Tempo, throughput, bytes recebidos (TCP) |
| `metricas_servidor_rudp.json` | Tempo, throughput, pacotes duplicados (R-UDP) |

Use esses JSONs no Google Colab para gerar os gráficos com Plotly/Seaborn.

---

## Protocolo R-UDP — Selective Repeat

### Por que Selective Repeat?
- **Go-Back-N**: ao perder 1 pacote, retransmite todos os N pacotes da janela — ineficiente com alta perda
- **Selective Repeat**: retransmite apenas o pacote perdido — muito mais eficiente no Cenário C (20% perda)

### Estrutura do pacote (20 bytes de cabeçalho + payload):
```
[ seq (4B) | ack (4B) | flags (1B) | length (4B) | CRC32 (4B) | reservado (3B) ] + payload
```

### Flags:
- `0x01` SYN — início da conexão
- `0x02` FIN — fim da transferência
- `0x04` ACK — confirmação de recebimento
- `0x08` DATA — pacote carrega dados

### Cabeçalho X-Custom-Auth:
Incluído no payload do SYN (R-UDP) e nos metadados JSON (TCP), contendo `MATRÍCULA NOME`.