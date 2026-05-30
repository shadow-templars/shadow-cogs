# MqttBridge

Bridge Discord events and commands to an MQTT broker for external processing. Generic and config-driven — the cog has no knowledge of what consumes the messages.

## Setup

### Broker (global, set in DMs)

```
[p]mqttbridge set broker <host> [port]
[p]mqttbridge set credentials <username> <password>
```

> ⚠️ Run `set credentials` in DMs to avoid leaking secrets. The message will be auto-deleted if sent in a server.

### Per-server settings

```
[p]mqttbridge set topic <topic>
[p]mqttbridge set channel enable
```

Each server can publish to a different MQTT topic. Channels must be explicitly enabled — run the enable command in the target channel.

## Usage

```
[p]mqttbridge relay <command> [args...]
```

Publishes a JSON payload to the server's configured MQTT topic (QoS 1) and reacts with ⏳ on success or ❌ on failure.

### Create an alias for convenience

```
[p]alias add mqtt mqttbridge relay
```

Then use `[p]mqtt whoami` instead of `[p]mqttbridge relay whoami`.

## Channel Restrictions

The bridge is disabled by default. Enable it per channel by running the command in the target channel:

```
[p]mqttbridge set channel enable
[p]mqttbridge set channel disable
[p]mqttbridge set channel list
```

## Message Format

Each command publishes a JSON payload:

```json
{
  "version": 1,
  "id": "uuid",
  "command": "whoami",
  "args": ["arg1", "arg2"],
  "raw": "whoami arg1 arg2",
  "context": {
    "guildId": "123456789",
    "channelId": "987654321",
    "userId": "111222333",
    "messageId": "444555666",
    "username": "DisplayName",
    "timestamp": "2026-05-29T01:23:45+00:00"
  }
}
```

## Requirements

- MQTT broker (e.g., [Eclipse Mosquitto](https://mosquitto.org/))
- Broker credentials with publish access to the configured topic
