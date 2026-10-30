# Headless deployment

OpenBridge runs without a monitor, desktop, or browser. The CLI and the
server need only Python's standard library plus this repository.

## Foreground

```bash
openbridge serve --headless --port 18765
openbridge agent start --port 9876
```

Both handle SIGINT/SIGTERM (or Ctrl+C / service stop on Windows):
in-flight HTTP handling drains, journals flush, model workers and agent
listeners close, no orphan sockets remain.

## Health

- Startup prints the bound address to stderr.
- `openbridge doctor` reports per-feature readiness (`READY`, `MISSING`,
  `MODEL_NOT_FOUND`, `AUTH_REQUIRED`, `BLOCKED`, ...). Global `READY`
  appears only when every probed feature is ready.
- `openbridge test smoke` is the supervised liveness check.

## Linux (systemd)

```ini
[Unit]
Description=OpenBridge headless server
After=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/openbridge
ExecStart=/usr/bin/python3 -m src.cli serve --headless --port 18765
Restart=on-failure
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
```

Store `OPENBRIDGE_META_KEY` in the service manager's credential store
(`LoadCredential=`), never in the unit file.

## Windows (scheduled task, headless)

Run at logon without a console window:

```powershell
$action = New-ScheduledTaskAction -Execute 'python.exe' `
  -Argument '-m src.cli serve --headless --port 18765' `
  -WorkingDirectory 'C:\OpenBridge'
$trigger = New-ScheduledTaskTrigger -AtLogOn
Register-ScheduledTask -TaskName 'OpenBridge' -Action $action `
  -Trigger $trigger -RunLevel Highest
```

Stop via `Unregister-ScheduledTask` or Task Scheduler; SIGTERM-equivalent
shutdown flushes journals before exit.

## SSH workflow

```bash
ssh user@linux-node
openbridge doctor
openbridge agent start
```

Enroll the node from another machine only through the registered,
owner-approved transports (`devices discover`, `devices pair`). The CLI
never assumes arbitrary remote-shell access.
