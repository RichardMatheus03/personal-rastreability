## ADDED Requirements

### Requirement: Listener configuration is validated before any connection

The process MUST refuse to start when `MAXGO_WEB_URL`, `MAXGO_API_URL`, `MAXGO_USERNAME`, `MAXGO_PASSWORD`, or `MAXGO_VEHICLE_ID` is missing or empty. `MAXGO_WEB_URL` and `MAXGO_API_URL` MUST use HTTPS and include a hostname. `MAXGO_STOMP_URL` MUST use WSS and include a hostname. When `MAXGO_STOMP_URL` is unset, the process MUST use `wss://srvskr.logicasolucoes.com.br/stomp`. `MAXGO_VEHICLE_ID` MUST be a positive integer. The process MUST NOT open a socket when validation fails.

#### Scenario: Missing credential

- **WHEN** `MAXGO_USERNAME` is empty and the other required MaxGo variables are present
- **THEN** the process exits with an error that names `MAXGO_USERNAME` and does not open a WebSocket

#### Scenario: Invalid vehicle id

- **WHEN** `MAXGO_VEHICLE_ID` is not a positive integer
- **THEN** the process exits with an error and does not open a WebSocket

#### Scenario: Default STOMP URL

- **WHEN** `MAXGO_STOMP_URL` is unset and the remaining configuration is valid
- **THEN** the process connects to `wss://srvskr.logicasolucoes.com.br/stomp`

### Requirement: STOMP session subscribes and confirms the vehicle

The process MUST obtain `userInfo.stompToken` from MaxGo with the configured account, open a SockJS WebSocket at `{MAXGO_STOMP_URL}/{server}/{session}/websocket` with `Origin` set to `MAXGO_WEB_URL`, send STOMP `CONNECT` using that token, and subscribe to `/user/queue/posicao`, `/user/queue/definido`, and `/user/queue/monitorando`. It MUST then send monitoring for `MAXGO_VEHICLE_ID` and treat the session as active only after `/user/queue/monitorando` returns a list containing that vehicle id. A monitoring reply that does not contain the vehicle MUST fail the session.

#### Scenario: Vehicle confirmed

- **WHEN** the monitoring destination returns a list that includes the configured vehicle id
- **THEN** the session stays open and later `/user/queue/posicao` messages are accepted

#### Scenario: Vehicle rejected

- **WHEN** the monitoring destination returns a list that does not include the configured vehicle id
- **THEN** the session is treated as failed and the process schedules a reconnect

### Requirement: Session token is reused from Redis

The process MUST cache the MaxGo `LGSESSIONID` in Redis for 5 hours under `maxgo:session:{sha256}`, where the hash input is `MAXGO_WEB_URL`, `MAXGO_API_URL`, and `MAXGO_USERNAME` separated by NUL bytes. While that key is present and unexpired, the process MUST reuse it instead of submitting the login form again.

#### Scenario: Cached session

- **WHEN** `maxgo:session:{sha256}` already holds a token for the configured account
- **THEN** the process does not submit the MaxGo login form before requesting `stompToken`

### Requirement: Position history keeps the latest twenty objects

Every JSON object received on `/user/queue/posicao` MUST be appended to the Redis key `position_history`. The value MUST be a JSON array ordered from oldest to newest, MUST contain at most 20 objects, and MUST have no expiration. When the array already has 20 objects, the oldest object MUST be discarded before the new one is appended.

#### Scenario: History below the limit

- **WHEN** `position_history` has 19 objects and a new position object arrives
- **THEN** the key holds 20 objects and the new object is last

#### Scenario: History at the limit

- **WHEN** `position_history` has 20 objects and a new position object arrives
- **THEN** the previous oldest object is absent and the new object is last

#### Scenario: Alive message is stored

- **WHEN** a message on `/user/queue/posicao` has `tipo` equal to `ALIVE`
- **THEN** that object is appended to `position_history`

### Requirement: Position and ignition snapshots ignore non-position messages

For a message whose `tipo` is absent or `POSICAO` and which includes `veiculoId`, `latitude`, and `longitude`, the process MUST store the whole object at `maxgo:position:{veiculoId}` and the `ignicao` value at `maxgo:ignition:{veiculoId}`, both with no expiration. A message whose `tipo` is anything else MUST NOT change those keys. A message missing `veiculoId`, `latitude`, or `longitude` MUST NOT change those keys.

#### Scenario: Position snapshot

- **WHEN** a `POSICAO` message includes vehicle id and both coordinates
- **THEN** `maxgo:position:{veiculoId}` equals that object and `maxgo:ignition:{veiculoId}` equals its `ignicao`

#### Scenario: Alive does not snapshot

- **WHEN** a message has `tipo` equal to `ALIVE` and a vehicle id
- **THEN** `maxgo:position:{veiculoId}` and `maxgo:ignition:{veiculoId}` stay unchanged

#### Scenario: Missing coordinates

- **WHEN** a `POSICAO` message has no latitude
- **THEN** no snapshot key is written

### Requirement: Redis outage delays alert processing until the history write succeeds

If appending to `position_history` fails because Redis is unreachable, the process MUST retry that append with backoff from 1 second up to 60 seconds until the write succeeds or a stop signal is set. Alert processing for that message MUST run only after the append succeeds. A stop signal during the wait MUST end the process without another STOMP session.

#### Scenario: Redis recovers

- **WHEN** the first append fails with a connection error and a later attempt succeeds
- **THEN** `position_history` contains the object and alert processing for that object runs once

#### Scenario: Stop while Redis is down

- **WHEN** a stop signal is set while the process is waiting to retry the append
- **THEN** the process exits and does not open a new STOMP session

### Requirement: The stream reconnects until stopped

After a network, timeout, protocol, or MaxGo session error, the process MUST wait with exponential backoff from 1 second up to 60 seconds and then open a new session. A session that stayed up for at least 60 seconds MUST reset the next delay to 1 second. SIGINT and SIGTERM MUST stop the loop and MUST NOT be followed by another session.

#### Scenario: Socket closes

- **WHEN** the active WebSocket closes unexpectedly
- **THEN** the process waits the current delay and opens a new STOMP session

#### Scenario: Long session resets delay

- **WHEN** a session stays active for at least 60 seconds and then fails
- **THEN** the wait before the next session is 1 second

#### Scenario: Termination

- **WHEN** the process receives SIGTERM
- **THEN** it exits without opening another STOMP session
