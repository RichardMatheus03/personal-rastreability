## 1. Configuração e Redis

- [x] 1.1 Criar `requirements.txt` com `redis`, `websocket-client` e `shapely`, e a dependência de teste `pytest`
- [x] 1.2 Implementar a leitura de ambiente: variáveis MaxGo obrigatórias, HTTPS/WSS, `MAXGO_VEHICLE_ID` positivo, default de `MAXGO_STOMP_URL`, e recusa de subir sem `EVOLUTION_API_KEY`, `EVOLUTION_PERSONAL_INSTANCE_NAME` e `EMERGENCY_CONTACT`
- [x] 1.3 Usar `REDIS_URL` exatamente como está no ambiente, já com o database de cache
- [x] 1.4 Cobrir validação e escolha de database com testes que não abrem rede

## 2. Sessão MaxGo e stream STOMP

- [x] 2.1 Implementar o login MaxGo, o cache de `LGSESSIONID` por 5 horas em `maxgo:session:{sha256}` e a leitura de `userInfo.stompToken`
- [x] 2.2 Implementar o handshake SockJS/STOMP, as três inscrições, o monitoramento do veículo e a falha quando o id não volta em `/user/queue/monitorando`
- [x] 2.3 Implementar o loop de reconexão (1s até 60s, reset após sessão de 60s) e a parada por SIGINT/SIGTERM sem nova sessão
- [x] 2.4 Testar token em cache, veículo confirmado, veículo rejeitado e parada por sinal com socket falso

## 3. Histórico e snapshots

- [x] 3.1 Gravar `position_history` como JSON, no máximo 20 objetos, sem expiração, inclusive mensagens `ALIVE`
- [x] 3.2 Gravar `maxgo:position:{veiculoId}` e `maxgo:ignition:{veiculoId}` só para posição aceita, e ignorar mensagem sem veículo ou coordenada
- [x] 3.3 Repetir a gravação do histórico com backoff até 60s quando o Redis cair, e só então processar avisos; sair sem nova sessão se a parada chegar durante a espera
- [x] 3.4 Testar o limite de 20, o `ALIVE`, a posição sem coordenada e a recuperação do Redis

## 4. Avisos de cerca e ignição

- [x] 4.1 Implementar `WhatsappEvolutionClient` com `BASE_URL` vindo de `EVOLUTION_SERVER_URL` e `send_message` fazendo o POST para `{BASE_URL}/message/sendText/{EVOLUTION_PERSONAL_INSTANCE_NAME}` com `apikey` e `number` igual a `EMERGENCY_CONTACT`
- [x] 4.2 Implementar `process_come_home` como função local que chama `send_message` com `Chegando em casa`, com dedupe `come_home:logged:{yyyyMMddHH}` em `America/Bahia`; apagar a chave horária se o POST falhar, sem fechar a sessão STOMP
- [x] 4.3 Implementar `alert_movement` como função local que chama `send_message` com o texto de ignição ligada, placa ou `sem placa`, id, coordenadas e `ultimaTransmissao`, para cada posição aceita com ignição `LIGADA` entre 23h e 06h, inclusive sem snapshot anterior; falha do POST não fecha a sessão
- [x] 4.4 Portar o polígono fixo e atualizar `come_home` em toda posição aceita, chamando `process_come_home` só na transição de falso para verdadeiro
- [x] 4.5 Testar o POST do client para `EMERGENCY_CONTACT`, entrada, permanência, primeira posição já dentro, saída, segunda entrada na mesma hora, falha da Evolution, janela noturna, horário diurno e posição sem placa

## 5. Compose e ambiente

- [x] 5.1 Manter toda a implementação dentro de personal-rastreability, sem criar, editar ou apagar arquivo no `sigti-backend`, e sem executar `docker compose up` ou `docker compose stop`
- [x] 5.2 Criar o `Dockerfile` em `python:3.14-slim` com `tzdata` e entrypoint do processo listener
- [x] 5.3 Criar `docker-compose.yml` com o único serviço `maxgo-listener` (`restart: unless-stopped`, `stop_grace_period: 30s`, `env_file: .env`, `TZ` padrão `America/Bahia`, sem porta publicada) na rede externa cujo nome é só `${SIGTI_DOCKER_NETWORK}` vindo do `.env`
- [x] 5.4 Criar `.env.example` só neste repositório, com todas as variáveis que o processo e o Compose leem: nomes e endereços lidos do sigti (`REDIS_URL=redis://redis:6379/1`, `EVOLUTION_SERVER_URL=http://evolution-api:8080`, `MAXGO_STOMP_URL` padrão, credenciais vazias), `EMERGENCY_CONTACT=` com comentário de que recebe `process_come_home` e `alert_movement`, `SIGTI_DOCKER_NETWORK=` vazio com comentário de `{COMPOSE_PROJECT_NAME}_default` e os nomes `touros-educacao-backend_default` e `touros-transporte-backend_default`, e o comentário de que o `sigti-backend` é referência somente leitura e não é alterado
- [x] 5.5 Ligar o módulo executável para carregar a configuração, tratar sinais e chamar o loop

## 6. Verificação

- [x] 6.1 Rodar a suíte de testes e deixá-la verde
- [x] 6.2 Rodar `docker compose config` com `SIGTI_DOCKER_NETWORK` vindo de um `.env` de teste e confirmar que o único serviço é `maxgo-listener`, sem portas publicadas e anexado a essa rede externa, sem subir nem parar container
