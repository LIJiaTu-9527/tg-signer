# TG Signer

[中文文档](./README.md)

TG Signer is an open-source Telegram automation toolkit for check-ins, monitoring, auto-replies, instant operations, and WebUI-based management.

It supports both:

- CLI workflows for scripting and automation
- WebUI workflows for browser-based login, configuration, task management, and logs

![TG Signer WebUI](./assets/webui.jpeg)

## Features

- Telegram login and session management
- Automated check-in task configuration and execution
- Personal, group, and channel monitoring
- Keyword-based auto reply, forward, and notification workflows
- Instant text sending, Dice sending, member listing, and scheduled message management
- Full WebUI for login, run configuration, config management, users, records, and logs
- Optional LLM integration for image-based and AI-assisted actions
- Docker-ready WebUI deployment

## Installation

### Install from PyPI

CLI only:

```bash
pip install -U tg-signer
```

With WebUI:

```bash
pip install -U "tg-signer[gui]"
```

With performance speedup:

```bash
pip install -U "tg-signer[gui,speedup]"
```

### Install from source

```bash
git clone <your-repo-url>
cd tg-signer
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e ".[gui,speedup]"
```

## Quick Start

Login:

```bash
tg-signer login
```

Create or edit a sign task:

```bash
tg-signer run my_sign
```

Run it:

```bash
tg-signer run my_sign
tg-signer run-once my_sign
```

Run a monitor task:

```bash
tg-signer monitor run my_monitor
```

Start the WebUI:

```bash
tg-signer webgui -H 0.0.0.0 -P 8080 --auth-code your-access-code
```

## WebUI Pages

The current WebUI includes:

- `Login`
- `Run Config`
- `Immediate Ops`
- `LLM Config`
- `Configs`
- `Users`
- `Records`
- `Logs`

LLM configuration is optional. Standard sign, monitor, and instant-message features work without it.

## Documentation

- [CLI Guide](./docs/CLI.md)
- [WebUI Guide](./docs/WEBUI.md)
- [Docker Deployment](./DOCKER_DEPLOY.md)
- [Contributing](./CONTRIBUTING.md)
- [Security Policy](./SECURITY.md)

## Project Data Layout

By default the working directory is `.signer`:

```text
.signer/
  signs/
  monitors/
  users/
  webui_keepalive.json
```

## Docker

Ready-to-use deployment files are included in the repository root:

- [Dockerfile](./Dockerfile)
- [docker-compose.yml](./docker-compose.yml)
- [.env.example](./.env.example)

Start quickly:

```bash
cp .env.example .env
docker compose up -d --build
```

## Security Note

Do not commit runtime data such as:

- `.signer/`
- `*.session`
- `*.session_string`
- `data/`
- `logs/`
- `.env`

These paths are already ignored by `.gitignore`.

## License

Licensed under [BSD-3-Clause](./LICENSE).
