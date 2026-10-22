## Why

O `sigti-backend` permanece como está. Ele entra nesta change só como leitura: o serviço `maxgo-listener` de lá é a referência da sessão STOMP, do Redis, dos endereços da Evolution e da MaxGo, e das funções `process_come_home` e `alert_movement`. O personal-rastreability cria o próprio listener a partir dessa leitura, com as diferenças já descritas nesta change. O trabalho termina nessa réplica: não inclui subir o processo, nem `docker compose stop`, nem qualquer outro passo de operação. Nenhuma alteração é planejada no `sigti-backend`.

## What Changes

- Novo processo Python, sem Django e sem Celery, que mantém a sessão SockJS/STOMP com a MaxGo, guarda o histórico e o snapshot no Redis e reage à posição recebida.
- Este repositório implementa `process_come_home` e `alert_movement` como funções locais. As duas deixam de ser tasks Celery. As duas enviam WhatsApp pelo `WhatsappEvolutionClient.send_message`, para o número `EMERGENCY_CONTACT`.
- `WhatsappEvolutionClient` usa como `BASE_URL` o endereço da Evolution vindo do `.env` (`EVOLUTION_SERVER_URL`). `send_message` faz o POST nessa API.
- O texto de `alert_movement` deixa o e-mail Mailgun e passa a ser a mensagem de WhatsApp dessa função. **BREAKING** para quem esperava o alerta noturno na caixa de e-mail.
- `docker-compose.yml` deste repositório declara somente o serviço `maxgo-listener`. Redis e Evolution API não são definidos aqui. A change entrega esse arquivo; não executa `up` nem `stop`.
- `.env.example` copia, por leitura, os nomes e os endereços do `sigti-backend`: Redis de cache, Evolution API e URLs/credenciais MaxGo, mais o fuso. Documenta `EMERGENCY_CONTACT` vazio, destinatário das duas mensagens. O comentário deixa explícito que o `sigti-backend` não é alterado.
- A rede Docker já existente do sigti entra como rede externa, para este container alcançar `redis` e `evolution-api`. O nome fica na variável `SIGTI_DOCKER_NETWORK` do `.env`, documentada no `.env.example` junto com os dois nomes lidos do sigti (`touros-educacao-backend_default` e `touros-transporte-backend_default`). O compose daqui não fixa nenhum dos dois.
- As chaves deste processo são JSON, sem o prefixo `:1:` e sem pickle do cache do Django. Isso vale só para o que este repositório grava.

## Capabilities

### New Capabilities

- `maxgo-position-stream`: sessão STOMP, reconexão, histórico das últimas 20 posições e snapshots de posição e ignição no Redis.
- `vehicle-alerts`: `process_come_home` e `alert_movement` locais, enviadas pelo `WhatsappEvolutionClient` ao `EMERGENCY_CONTACT`.
- `listener-runtime`: compose com o único serviço `maxgo-listener`, `.env.example` alinhado por leitura ao Redis, à Evolution API e aos endereços de conexão do sigti, e a regra de que o `sigti-backend` não é modificado.

### Modified Capabilities

- Nenhuma. Não há specs existentes em `openspec/specs/`.

## Impact

- Todo arquivo criado ou editado fica em personal-rastreability: processo do listener, Dockerfile, `docker-compose.yml`, `.env.example` e testes sem Django.
- O `sigti-backend` é somente referência de leitura. Esta change não cria, edita nem apaga arquivo lá, e não opera container nenhum, nem lá nem aqui.
- Dependências de runtime deste processo: cliente Redis, WebSocket e geometria da cerca. Sem Django, Celery, Postgres ou a imagem do sigti.
- Endereços lidos do `sigti-backend` e configurados só no `.env` daqui: Redis (database de cache, padrão 1), Evolution API (`EVOLUTION_SERVER_URL`, chave e instância pessoal) e MaxGo (`MAXGO_WEB_URL`, `MAXGO_API_URL`, `MAXGO_STOMP_URL`). O destinatário das duas mensagens é `EMERGENCY_CONTACT`.
- `MAXGO_PLATE` e a task `check_maxgo_position`, vistos no sigti, não entram neste serviço.
