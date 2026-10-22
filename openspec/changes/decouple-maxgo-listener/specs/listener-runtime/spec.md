## ADDED Requirements

### Requirement: sigti-backend is a read-only reference

This change MUST be implemented only inside personal-rastreability. It MUST NOT create, modify, or delete any file in sigti-backend. It MUST NOT change that repository's Compose files, environment files, or running containers. sigti-backend MUST be used only as a read-only reference for the current listener behavior, the Redis and Evolution addresses, and the MaxGo connection variable names. `.env.example` MUST state that sigti-backend is a read-only reference and that this repository does not change it. The change MUST replicate that behavior, including the differences described in this change, as code, Compose, and `.env.example`. It MUST NOT start or stop containers and MUST NOT run `docker compose up` or `docker compose stop`.

#### Scenario: Implementation writes only in this repository

- **WHEN** the listener is implemented
- **THEN** every created or edited file is inside personal-rastreability and no file in sigti-backend is created, modified, or deleted

#### Scenario: Addresses are copied by reading

- **WHEN** a Redis, Evolution, or MaxGo address is taken from sigti-backend
- **THEN** the value is written only into personal-rastreability configuration and the sigti-backend source remains as it was read

#### Scenario: No container is started or stopped

- **WHEN** the change is complete
- **THEN** the listener exists as code and Compose in personal-rastreability and no `docker compose up` or `docker compose stop` was run

### Requirement: Listener image uses Python 3.14

The listener image MUST be built from `python:3.14-slim`. The process inside the container MUST run on Python 3.14.

#### Scenario: Image interpreter

- **WHEN** the listener image is built
- **THEN** `python --version` inside the image reports Python 3.14

### Requirement: Compose runs only the listener

The repository Compose file MUST define exactly one service, named `maxgo-listener`. It MUST NOT define Redis, Evolution API, Postgres, Caddy, or a Celery worker. The service MUST restart unless stopped, MUST set `stop_grace_period` to 30 seconds, MUST load its environment from `.env`, and MUST set `TZ` to `America/Bahia` when `TZ` is absent. The service command MUST be the listener process. The service MUST NOT publish a host port.

#### Scenario: Rendered service list

- **WHEN** the Compose file is rendered with a valid environment
- **THEN** the only service is `maxgo-listener` and it has no published ports

#### Scenario: Time zone default

- **WHEN** `TZ` is unset
- **THEN** the service runs with `TZ` equal to `America/Bahia`

### Requirement: The listener joins the existing sigti Docker network

The Compose file MUST attach `maxgo-listener` to an external network. The network name MUST come only from `SIGTI_DOCKER_NETWORK` in the project `.env`. The Compose file MUST NOT hardcode `touros-educacao-backend_default` or `touros-transporte-backend_default`. It MUST NOT create that network. Redis and Evolution API MUST be reached through that network, not by services declared in this file.

#### Scenario: Network name comes from the env file

- **WHEN** `.env` sets `SIGTI_DOCKER_NETWORK` to `touros-educacao-backend_default`
- **THEN** the service is attached to the external network `touros-educacao-backend_default`

#### Scenario: Missing network name

- **WHEN** `SIGTI_DOCKER_NETWORK` is absent from `.env`
- **THEN** Compose fails before starting the container

### Requirement: Example environment matches sigti connection names

`.env.example` MUST document every variable this repository reads, including those used only by Compose. That list MUST include `REDIS_URL`, `EVOLUTION_API_KEY`, `EVOLUTION_PERSONAL_INSTANCE_NAME`, `EVOLUTION_SERVER_URL`, `MAXGO_WEB_URL`, `MAXGO_API_URL`, `MAXGO_STOMP_URL`, `MAXGO_USERNAME`, `MAXGO_PASSWORD`, and `MAXGO_VEHICLE_ID`, plus `SIGTI_DOCKER_NETWORK`, `TZ`, and `EMERGENCY_CONTACT`. It MUST NOT define `REDIS_CACHE_DB` or `REDIS_CACHE_URL`. A comment on `EMERGENCY_CONTACT` MUST state that this number receives both the `process_come_home` message and the `alert_movement` message. A comment on `EVOLUTION_SERVER_URL` MUST state that `WhatsappEvolutionClient.BASE_URL` is taken from it.

The example MUST set `REDIS_URL` to `redis://redis:6379/1`. It MUST set `EVOLUTION_SERVER_URL` to `http://evolution-api:8080` and `MAXGO_STOMP_URL` to `wss://srvskr.logicasolucoes.com.br/stomp`. `MAXGO_WEB_URL`, `MAXGO_API_URL`, `MAXGO_USERNAME`, `MAXGO_PASSWORD`, `MAXGO_VEHICLE_ID`, `EVOLUTION_API_KEY`, `EVOLUTION_PERSONAL_INSTANCE_NAME`, `EMERGENCY_CONTACT`, and `SIGTI_DOCKER_NETWORK` MUST be empty assignments in the example. `TZ` MUST be `America/Bahia`.

A comment on `REDIS_URL` MUST state that this is the address the listener connects to and that database 1 is the sigti cache. The comment on `SIGTI_DOCKER_NETWORK` MUST state that the value is the sigti Compose project name plus `_default`, and MUST name both existing networks: `touros-educacao-backend_default` when `COMPOSE_PROJECT_NAME` is `touros-educacao-backend`, and `touros-transporte-backend_default` when `COMPOSE_PROJECT_NAME` is `touros-transporte-backend`. The example MUST NOT contain real credentials.

#### Scenario: Redis and Evolution addresses

- **WHEN** an operator reads `.env.example`
- **THEN** `REDIS_URL` is `redis://redis:6379/1` and `EVOLUTION_SERVER_URL` is `http://evolution-api:8080`

#### Scenario: MaxGo address names

- **WHEN** an operator compares `.env.example` with the MaxGo section of the sigti-backend example
- **THEN** `MAXGO_WEB_URL`, `MAXGO_API_URL`, `MAXGO_STOMP_URL`, `MAXGO_USERNAME`, `MAXGO_PASSWORD`, and `MAXGO_VEHICLE_ID` are present, and `MAXGO_STOMP_URL` is `wss://srvskr.logicasolucoes.com.br/stomp`

#### Scenario: No secrets in the example

- **WHEN** an operator reads `.env.example`
- **THEN** the credential and destination variables listed above are empty

#### Scenario: Sigti network name is an env assignment

- **WHEN** an operator reads `.env.example`
- **THEN** it contains the assignment `SIGTI_DOCKER_NETWORK=` and comments naming `touros-educacao-backend_default` and `touros-transporte-backend_default`

### Requirement: Listener state uses the configured Redis URL

The process MUST open Redis at `REDIS_URL` exactly as configured, including the database number in that URL. It MUST NOT rewrite the URL from another variable.

#### Scenario: Configured URL is the connection

- **WHEN** `REDIS_URL` is `redis://redis:6379/1`
- **THEN** the listener connects to that URL and writes `position_history` on database 1
