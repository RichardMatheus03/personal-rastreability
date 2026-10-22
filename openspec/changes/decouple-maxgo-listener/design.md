## Context

No `sigti-backend`, o serviço `maxgo-listener` usa a mesma imagem Django do backend e o entrypoint `python manage.py run_maxgo_listener`. O comando abre uma sessão SockJS/STOMP com a MaxGo, grava estado pelo cache do Django e enfileira duas tasks Celery:

- `process_come_home` envia o texto "Chegando em casa" pela Evolution API, no máximo uma vez por hora local.
- `alert_movement` envia e-mail via Mailgun quando a ignição chega `LIGADA` entre 23h e 06h em `America/Bahia`. Neste repositório essa função passa a enviar o mesmo conteúdo por WhatsApp.

O cache do Django não usa o database 0 do `REDIS_URL` (broker Celery). `REDIS_CACHE_DB` (padrão `1`), ou `REDIS_CACHE_URL` quando definida, escolhe o database. As chaves saem com o prefixo de versão `:1:` e o valor em pickle. Nenhum outro módulo em execução lê `position_history`, `maxgo:position:*`, `maxgo:ignition:*` ou `come_home`. A task HTTP `check_maxgo_position` ainda existe no código, mas saiu do Celery Beat.

Redis e Evolution API continuam no compose do sigti. Redis publica porta no host; dentro da rede do compose o hostname é `redis`. A Evolution usa `http://evolution-api:8080` (`EVOLUTION_SERVER_URL`). Os projetos Compose conhecidos são `touros-educacao-backend` (local) e `touros-transporte-backend` (produção), então as redes externas são `touros-educacao-backend_default` e `touros-transporte-backend_default`.

Este repositório ainda não tem aplicação. A change cria o processo, o compose de um serviço e o contrato de ambiente aqui. O `sigti-backend` é referência de leitura e permanece intacto: nenhum arquivo, compose, ambiente ou container de lá entra no plano desta change.

## Goals / Non-Goals

**Goals:**

- Reproduzir, neste repositório, a sessão STOMP, o histórico de 20 posições, os snapshots, a cerca de casa e o alerta noturno de ignição, lendo o comportamento atual no `sigti-backend`.
- Declarar só o serviço `maxgo-listener` neste compose, apontando para a rede Docker já existente, sem editar o compose que a criou e sem executar `up` ou `stop`.
- Fazer o `.env.example` repetir os nomes de Redis, Evolution e MaxGo lidos no `.env.example` do sigti, com o database de cache explícito, e declarar que aquele repositório não é alterado.
- Implementar aqui `process_come_home` e `alert_movement`, as duas chamando `WhatsappEvolutionClient.send_message` para `EMERGENCY_CONTACT`.
- Falha do POST à Evolution não derruba a sessão STOMP. Falha de Redis na gravação do histórico continua tentando de novo.

**Non-Goals:**

- Qualquer escrita no `sigti-backend`: arquivo, commit, compose, `.env` ou follow-up naquele repositório.
- Operar containers. A change replica o comportamento em código, compose e `.env.example`. Não executa `docker compose up` nem `docker compose stop`.
- Rodar Redis, Evolution API, Postgres, Caddy ou Celery neste compose.
- Trazer `check_maxgo_position`, `MAXGO_PLATE` ou o cliente de consulta por placa.
- Ler ou migrar as chaves pickle `:1:*` que o Django já gravou.
- Compartilhar o `LGSESSIONID` com o cache do Django.

## Decisions

### Processo Python próprio, não a imagem do sigti

O listener passa a ser um pacote Python 3.14 executado como entrypoint do container. A imagem base é `python:3.14-slim`. O Shapely 2.1.2 publica wheel para essa versão, então a imagem slim instala o pacote sem compilador. Dependências de runtime: `redis`, `websocket-client` e `shapely`. HTTP de login e o POST da Evolution ficam na biblioteca padrão.

Alternativa considerada: apontar o compose daqui para a imagem do sigti. Isso continuaria dependente do Django, do Celery e do settings daquele repositório. O processo é escrito de novo neste repositório, com o código de lá só como leitura.

Layout alvo:

- `listener/` — configuração, cliente MaxGo, `WhatsappEvolutionClient`, `process_come_home`, `alert_movement`, sessão STOMP, histórico e cerca
- `Dockerfile` — `python:3.14-slim`, `tzdata`, `TZ=America/Bahia`
- `requirements.txt` — runtime; `pytest` só em dev
- `tests/` — os contratos de histórico, STOMP, cerca e avisos, com Redis e HTTP falsos

### Redis e Evolution permanecem no sigti; este compose só entra na rede deles

`docker-compose.yml` declara um serviço e uma rede `external`. O nome dessa rede é só `${SIGTI_DOCKER_NETWORK}`, lido do `.env` do projeto. O arquivo de compose não grava `touros-educacao-backend_default` nem `touros-transporte-backend_default`. O `.env.example` traz a atribuição vazia `SIGTI_DOCKER_NETWORK=` e o comentário dos dois nomes: `{COMPOSE_PROJECT_NAME}_default`, com `touros-educacao-backend` no ambiente local e `touros-transporte-backend` na VPS. Quem copia o exemplo para `.env` escolhe um. Não há `depends_on`: se o Redis ainda não responde, o loop de reconexão que já existe (1s até 60s) espera. `stop_grace_period: 30s` e `restart: unless-stopped` repetem o serviço atual. Nenhuma porta é publicada.

Alternativa considerada: usar `host.docker.internal` e as portas publicadas (`6379`, `8080`). Funciona no host, mas troca os hostnames que o sigti já usa dentro da rede. A rede externa preserva `redis://redis:6379/1` e `http://evolution-api:8080`.

### Redis no endereço em que o listener grava

`REDIS_URL` é a URL da conexão, já com o database. No exemplo ela é `redis://redis:6379/1`, o cache do sigti. Não há `REDIS_CACHE_DB` nem `REDIS_CACHE_URL` para reescrever esse valor. O database 0 é o broker Celery do sigti; este processo não recebe essa URL.

Chaves, sem prefixo e com valor JSON, sem TTL, salvo onde o comportamento atual já expira:

| Chave | Valor |
| --- | --- |
| `position_history` | array JSON, no máximo 20 objetos, do mais antigo ao mais recente |
| `maxgo:position:{veiculoId}` | objeto da última posição aceita |
| `maxgo:ignition:{veiculoId}` | string da ignição, ou null |
| `come_home` | booleano |
| `come_home:logged:{yyyyMMddHH}` | marcador com TTL de 3600s, hora em `America/Bahia` |
| `maxgo:session:{sha256}` | `LGSESSIONID`, TTL de 5 horas; a conta é `WEB`, `API` e usuário separados por NUL |

Alternativa considerada: imitar pickle e o prefixo `:1:` para o `manage.py shell` do sigti continuar lendo o histórico. Nada em produção consome essas chaves fora do próprio listener. JSON é inspecionável com `redis-cli` e não arrasta o Django. As chaves antigas ficam intactas para rollback.

### process_come_home e alert_movement no próprio processo

As duas funções existem neste repositório e deixam de ser `@shared_task`. Nenhuma das duas chama `.delay()` nem publica no broker.

`WhatsappEvolutionClient` guarda em `BASE_URL` o valor de `EVOLUTION_SERVER_URL` (ausente, `http://evolution-api:8080`). `send_message(text)` faz `POST {BASE_URL}/message/sendText/{EVOLUTION_PERSONAL_INSTANCE_NAME}` com header `apikey: EVOLUTION_API_KEY` e corpo `{"number": EMERGENCY_CONTACT, "text": text}`. O número não varia por função: chegada e ignição vão para o mesmo `EMERGENCY_CONTACT`.

`process_come_home` manda o texto `Chegando em casa`. O marcador horário usa `SET` com NX em `come_home:logged:{yyyyMMddHH}`. Se o POST falha, a chave horária é apagada e a sessão STOMP segue. `come_home` permanece verdadeiro: um novo envio só entra depois de sair e voltar, e ainda respeita a hora.

`alert_movement(previous_position, current_position)` monta o texto que hoje vai no e-mail — evento `Ignição ligada`, placa ou `sem placa`, id, coordenadas anteriores ou `indisponível`, coordenadas atuais e `ultimaTransmissao` — e entrega esse texto a `send_message`. O listener a chama entre 23h e 06h para cada posição com `ignicao` `LIGADA`, inclusive a primeira, sem posição anterior. Timeout do POST: 10 segundos. Falha do POST não fecha a sessão.

`EVOLUTION_API_KEY`, `EVOLUTION_PERSONAL_INSTANCE_NAME` e `EMERGENCY_CONTACT` vazios impedem a abertura do socket.

Alternativa considerada: manter `alert_movement` no Mailgun e só a chegada na Evolution. As duas reações passam a compartilhar o cliente e o contato de emergência. Outra alternativa: publicar as tasks no broker do sigti. O listener continuaria dependente dos nomes `sigti.notifications.tasks.*` e do worker.

### Contrato STOMP e cerca permanecem os atuais

Validação de ambiente, handshake SockJS, destinos `/user/queue/posicao`, `/user/queue/definido` e `/user/queue/monitorando`, `defineMonitoramento` e `monitoramento` do `MAXGO_VEHICLE_ID` são portados. `MAXGO_STOMP_URL` ausente vale `wss://srvskr.logicasolucoes.com.br/stomp`. Web e API exigem HTTPS; STOMP exige WSS. `MAXGO_VEHICLE_ID` é inteiro positivo.

`ALIVE` e qualquer `tipo` fora de `POSICAO` entram no histórico quando chegam na fila de posição, e não atualizam snapshot nem disparam aviso. Mensagem sem veículo ou sem coordenada não atualiza snapshot nem dispara aviso.

A cerca é o polígono já fixo, vértices `(longitude, latitude)`:

- `(-35.2073938, -5.8312213)`
- `(-35.2075107, -5.831536)`
- `(-35.2073933, -5.8315756)`
- `(-35.207277, -5.8312686)`
- fechando em `(-35.2073938, -5.8312213)`

O relógio da janela noturna e da chave horária é `America/Bahia` (`TZ`).

SIGINT e SIGTERM apenas sinalizam parada. Sessão que durou 60 segundos ou mais zera o atraso de reconexão para 1 segundo.

### Gravação replicada

O histórico é leitura-modificação-gravação, como o `cache.get`/`cache.set` visto no código de referência. As chaves deste processo são JSON, sem o prefixo `:1:` e sem pickle. SIGINT e SIGTERM encerram o loop porque o processo de referência faz isso; tratar o sinal faz parte da réplica. Esta change não invoca `docker compose stop`.

## Risks / Trade-offs

- [Histórico e `come_home` deste processo começam vazios quando alguém o executar depois] → As chaves JSON daqui não leem o pickle `:1:*`. Veículo que já está dentro da cerca não gera "Chegando em casa" neste processo até sair e entrar de novo. O alerta noturno não depende desse estado. Esta change não executa o processo.
- [As chaves `:1:*` ficam fora desta réplica] → O código daqui não converte nem apaga o que o Django já gravou.
- [Nome da rede] → `SIGTI_DOCKER_NETWORK` fica vazio no `.env.example`. O comentário registra os dois nomes lidos do sigti. O `.env` real, fora desta change, recebe o do ambiente em que o sigti está. A change não sobe o compose para verificar a rede.
- [O alerta noturno muda de e-mail para WhatsApp] → O texto de `alert_movement` é preservado; o destino passa a ser `EMERGENCY_CONTACT`, o mesmo número de `process_come_home`. Quem operava pelo e-mail precisa acompanhar esse contato.
- [Chamada HTTP no fio do STOMP] → Timeout de 10s. A ociosidade que derruba a sessão é 90s. Falha de aviso não entra no `except` de reconexão.
- [Login MaxGo em paralelo] → O token deste processo fica numa chave JSON própria. O cache do Django, lido como referência, continua com a chave pickle. Esta change não agenda nem desliga `check_maxgo_position`.

## Migration Plan

Não há migração nem operação. A change entrega a réplica no personal-rastreability: processo, testes, `Dockerfile`, `docker-compose.yml` e `.env.example`, com as diferenças já descritas (Python 3.14, funções locais, `WhatsappEvolutionClient`, `EMERGENCY_CONTACT`, chaves JSON). Não há `docker compose up`, `docker compose stop`, rollback nem passo no `sigti-backend`.

## Open Questions

Nenhuma. Não há follow-up planejado no `sigti-backend`.
