## ADDED Requirements

### Requirement: Home arrival uses the fixed polygon and a false-to-true transition

The home area MUST be the polygon whose vertices, in `(longitude, latitude)` order, are `(-35.2073938, -5.8312213)`, `(-35.2075107, -5.831536)`, `(-35.2073933, -5.8315756)`, `(-35.207277, -5.8312686)`, and `(-35.2073938, -5.8312213)`. For each accepted position message, the process MUST store whether that point is inside the polygon at the Redis key `come_home`, with no expiration. The process MUST send a WhatsApp message only when the stored value changes from false to true. A missing previous value MUST NOT send a message. Staying inside, staying outside, or leaving the polygon MUST NOT send a message.

#### Scenario: Entering home

- **WHEN** `come_home` is false and the new point is inside the polygon
- **THEN** one WhatsApp message is sent and `come_home` becomes true

#### Scenario: Already home

- **WHEN** `come_home` is true and the new point is inside the polygon
- **THEN** no WhatsApp message is sent

#### Scenario: First point is already inside

- **WHEN** `come_home` is absent and the new point is inside the polygon
- **THEN** no WhatsApp message is sent and `come_home` becomes true

#### Scenario: Leaving home

- **WHEN** `come_home` is true and the new point is outside the polygon
- **THEN** no WhatsApp message is sent and `come_home` becomes false

### Requirement: WhatsappEvolutionClient posts both messages to the emergency contact

The repository MUST provide `WhatsappEvolutionClient`. Its `BASE_URL` MUST be the Evolution address from `EVOLUTION_SERVER_URL`, without a trailing slash. When `EVOLUTION_SERVER_URL` is unset, `BASE_URL` MUST be `http://evolution-api:8080`. `send_message` MUST POST to `{BASE_URL}/message/sendText/{EVOLUTION_PERSONAL_INSTANCE_NAME}` with header `apikey` set to `EVOLUTION_API_KEY` and JSON body `number` equal to `EMERGENCY_CONTACT` and `text` equal to the message it received. `process_come_home` and `alert_movement` MUST be ordinary functions in this repository. They MUST send their texts only by calling `send_message`. They MUST NOT enqueue a Celery task.

#### Scenario: Arrival text uses the client

- **WHEN** `process_come_home` sends the arrival notice
- **THEN** `send_message` POSTs the text `Chegando em casa` and the JSON `number` is `EMERGENCY_CONTACT`

#### Scenario: Movement text uses the same contact

- **WHEN** `alert_movement` sends an ignition alert
- **THEN** `send_message` POSTs that alert text and the JSON `number` is the same `EMERGENCY_CONTACT`

### Requirement: Arrival WhatsApp is deduplicated per local hour

`process_come_home` MUST send the text `Chegando em casa` through `WhatsappEvolutionClient.send_message`. A successful send MUST set `come_home:logged:{yyyyMMddHH}` for 3600 seconds, using the current hour in `America/Bahia`. A later false-to-true transition in that same local hour MUST NOT call `send_message`. If the POST fails, the process MUST delete that hour key, MUST leave `come_home` true, and MUST keep the STOMP session open.

#### Scenario: Successful send records the hour

- **WHEN** an arrival transition is detected and the current local hour key is absent
- **THEN** `send_message` is called once and `come_home:logged:{yyyyMMddHH}` is set for the current `America/Bahia` hour

#### Scenario: Second entry in the same hour

- **WHEN** the current local hour key is already set and the vehicle enters the polygon again
- **THEN** `send_message` is not called

#### Scenario: Evolution failure releases the hour key

- **WHEN** `send_message` fails for an arrival transition
- **THEN** the hour key is absent, `come_home` is true, and the STOMP session remains open

### Requirement: Night ignition alerts fire for every matching position

When the current hour in `America/Bahia` is 23 or greater, or lower than 6, every accepted position message with `ignicao` equal to `LIGADA` MUST call `alert_movement` once. The first such message MUST call it even when no previous snapshot exists. From hour 6 through hour 22 inclusive, the process MUST NOT call `alert_movement`. `ignicao` equal to `DESLIGADA` MUST NOT call `alert_movement` at any hour. A message that is not an accepted position MUST NOT call `alert_movement`.

#### Scenario: Each critical message alerts

- **WHEN** the local hour is 23 and two accepted positions arrive with ignition `LIGADA`
- **THEN** `alert_movement` is called twice

#### Scenario: Daytime ignition does not alert

- **WHEN** the local hour is 22 and an accepted position arrives with ignition `LIGADA`
- **THEN** `alert_movement` is not called

#### Scenario: First critical message has no previous position

- **WHEN** no snapshot exists, the local hour is 0, and an accepted position arrives with ignition `LIGADA`
- **THEN** `alert_movement` is called once and the text it sends marks the previous coordinates as unavailable

#### Scenario: Ignition off at night

- **WHEN** the local hour is 1 and an accepted position arrives with ignition `DESLIGADA`
- **THEN** `alert_movement` is not called

### Requirement: alert_movement sends the ignition text through WhatsApp

`alert_movement` MUST send one WhatsApp text through `WhatsappEvolutionClient.send_message`. The text MUST include the event `Ignição ligada`, the plate or the text `sem placa` when the position has no plate, the vehicle id, the previous coordinates or `indisponível`, the current coordinates, and `ultimaTransmissao`. A failed POST MUST leave the STOMP session open.

#### Scenario: Message content

- **WHEN** `alert_movement` runs for a position that has no plate
- **THEN** the text passed to `send_message` contains `Ignição ligada` and `sem placa`, plus the current coordinates and `ultimaTransmissao`

#### Scenario: Evolution failure during the night alert

- **WHEN** `send_message` fails for an ignition alert
- **THEN** the STOMP session remains open

### Requirement: Alert destinations are required before the session starts

The process MUST refuse to open a STOMP session when `EVOLUTION_API_KEY`, `EVOLUTION_PERSONAL_INSTANCE_NAME`, or `EMERGENCY_CONTACT` is missing or empty.

#### Scenario: Missing Evolution key

- **WHEN** `EVOLUTION_API_KEY` is empty and the MaxGo configuration is valid
- **THEN** the process exits with an error and does not open a WebSocket
