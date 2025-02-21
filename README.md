# Chatterer

This is a simple Telegram bot that uses OpenaiSDK to provide helpful answers to user's messages. Can work in webhook or polling mode.

## Run

```bash
docker-compose up --build -d
```

## Environment variables

Must be set in `.env` file.

| Name | Description | Required |
| --- | --- | --- |
| `OPENAI__BASE_URL` | OpenAI API base URL | Yes |
| `OPENAI__TOKEN` | OpenAI API token | Yes |
| `OPENAI__MODEL` | OpenAI model to use | Yes |
| `OPENAI__CONTEXT_LENGTH` | Number of messages to keep in context | No. Default - `10` |
| `BOT__TOKEN` | Telegram bot token | For polling mode |
| `BOT__SECRET_TOKEN` | Telegram bot secret token | For webhook mode |
| `BOT__KEY_PATH` | Path to private key file | For webhook mode |
| `BOT__CERT_PATH` | Path to certificate file | For webhook mode |
| `BOT__DOMAIN` | Domain to use for webhook | For webhook mode |
| `BOT__PERSISTENCE_PATH` | Path to persistence file | Not in docker |
| `BOT__MODE` | Mode to run bot in. Can be `webhook` or `polling` | Yes |
| `BOT__LISTEN` | Listen address | No. Default - `0.0.0.0` |
| `BOT__PORT` | Port to listen on | No. Default - `8443` |
| `BOT__GROUP_CHAT_REACT` | Reaction to use for group chats | No. |
| `LOGGING_LEVEL` | Logging level | No. Default - `INFO` |

## Development

### Requirements

- Python 3.12
- [UV](https://docs.astral.sh/uv/)

### Setup

- Install dependencies `uv sync`
- Run `uv run main.py`

## License

This project is licensed under the MIT License. For details, see the [LICENSE](LICENSE) file.
