COMPOSE = podman compose
PROJECT_NAME ?= dry-lab-notebook-app
BASE = -p $(PROJECT_NAME) -f docker-compose.yml
COMPOSE_CMD = $(COMPOSE) $(BASE)
PYTHON ?= /app/.venv/bin/python

-include .env
export

STATICFILES_HOST_DIR ?= $(PWD)/staticfiles
STOMP_HOST ?= rabbitmq
STOMP_PORT ?= 61613
STOMP_VHOST ?= /
STOMP_STREAM_QUEUE ?= /queue/test
STOMP_USE_STREAM ?= 1
STOMP_STREAM_OFFSET ?= last
STOMP_PREFETCH_COUNT ?= 100
STOMP_MAX_EVENTS ?= 20
STOMP_IDLE_TIMEOUT_SECONDS ?= 2
STOMP_FOLLOW ?= 0
STOMP_DEBUG ?=
WORKFLOW_EVENTS_OUT ?= workflow-events.jsonl
SSH_TUNNEL_SSH_PORT ?= 22
SSH_TUNNEL_USER ?= tunnel
STOMP_TUNNEL_REMOTE_PORT ?= 61613

.PHONY: dev-up dev-down dev-logs dev-shell migrate makemigrations createsuperuser test build staticfiles-dir image-check prod-up prod-down collectstatic tunnel-helper-up tunnel-refresh tunnel-up tunnel-connect tunnel-status tunnel-stop live-test-setup live-test-snakemake collect-workflow-events

db.sqlite3:
	@echo "WARNING: db.sqlite3 not found — creating empty file to prevent Docker mount issue."
	@touch db.sqlite3

dev-up: db.sqlite3
	@echo "Dev workflow has been consolidated into the VS Code devcontainer."
	@echo "Open this workspace in the devcontainer to run the development stack."

dev-down:
	@echo "Dev workflow has been consolidated into the VS Code devcontainer."
	@echo "Use 'Dev Containers: Rebuild and Reopen in Container' / 'Reopen Locally' from VS Code."

dev-logs:
	@echo "Dev workflow has been consolidated into the VS Code devcontainer."
	@echo "Use the devcontainer terminal and Docker/Podman logs for the dev stack."

dev-shell:
	@echo "Dev workflow has been consolidated into the VS Code devcontainer."
	@echo "Use the integrated terminal inside the devcontainer."

migrate:
	$(COMPOSE_CMD) exec web python manage.py migrate

makemigrations:
	$(COMPOSE_CMD) exec web python manage.py makemigrations

createsuperuser:
	$(COMPOSE_CMD) exec web python manage.py createsuperuser

test:
	$(COMPOSE_CMD) exec web python manage.py test

build:
	podman build -t dry-lab-notebook .

staticfiles-dir: $(STATICFILES_HOST_DIR)

$(STATICFILES_HOST_DIR):
	mkdir -p "$(STATICFILES_HOST_DIR)" || { echo "ERROR: Cannot create $(STATICFILES_HOST_DIR). Try running with sudo: sudo make staticfiles-dir"; exit 1; }
	chmod 777 "$(STATICFILES_HOST_DIR)" || { echo "ERROR: Cannot chmod $(STATICFILES_HOST_DIR). Try running with sudo: sudo make staticfiles-dir"; exit 1; }

image-check:
	@podman image exists dry-lab-notebook || \
		{ echo "Image 'dry-lab-notebook' not found. Run: make build"; exit 1; }

collectstatic: image-check staticfiles-dir
	podman run --rm \
		-v "$(STATICFILES_HOST_DIR):/app/staticfiles" \
		dry-lab-notebook \
		python manage.py collectstatic --noinput

prod-up: db.sqlite3
	$(COMPOSE_CMD) up -d --build --force-recreate

prod-down:
	$(COMPOSE_CMD) down

# Internal helper: ensure helper services are up and ssh-tunnel accepts exec.
tunnel-helper-up:
	@test -n "$(SSH_TUNNEL_HOST)" || { echo "ERROR: SSH_TUNNEL_HOST is not set in .env"; exit 1; }
	$(COMPOSE_CMD) up -d rabbitmq ssh-tunnel
	@ready=0; \
	for i in 1 2 3 4 5 6 7 8 9 10; do \
		if $(COMPOSE_CMD) exec ssh-tunnel true >/dev/null 2>&1; then \
			ready=1; \
			break; \
		fi; \
		sleep 1; \
	done; \
	if [ "$$ready" -ne 1 ]; then \
		echo "ERROR: ssh-tunnel helper did not become ready in time."; \
		$(COMPOSE_CMD) ps rabbitmq ssh-tunnel; \
		exit 1; \
	fi

tunnel-refresh:
	@test -n "$(SSH_TUNNEL_HOST)" || { echo "ERROR: SSH_TUNNEL_HOST is not set in .env"; exit 1; }
	$(COMPOSE_CMD) up -d --force-recreate rabbitmq ssh-tunnel
	$(MAKE) tunnel-helper-up

tunnel-up: tunnel-helper-up
	$(COMPOSE_CMD) ps rabbitmq ssh-tunnel

tunnel-connect: tunnel-helper-up
	@if $(COMPOSE_CMD) exec ssh-tunnel sh -lc 'pidfile=/tmp/autossh.pid; [ -f "$${pidfile}" ] && pid=$$(cat "$${pidfile}") && kill -0 "$${pid}"' >/dev/null 2>&1; then \
		echo "autossh already running; reusing existing process."; \
		echo "PID: $$($(COMPOSE_CMD) exec ssh-tunnel sh -lc 'cat /tmp/autossh.pid')"; \
		exit 0; \
	fi
	@read -r -p "SSH username [$(SSH_TUNNEL_USER)]: " SSH_USER; \
	SSH_USER=$${SSH_USER:-$(SSH_TUNNEL_USER)}; \
	if [ -z "$$SSH_USER" ]; then echo "ERROR: SSH username is required."; exit 1; fi; \
	read -r -p "SSH host [$(SSH_TUNNEL_HOST)]: " SSH_HOST; \
	SSH_HOST=$${SSH_HOST:-$(SSH_TUNNEL_HOST)}; \
	if [ -z "$$SSH_HOST" ]; then echo "ERROR: SSH host is required."; exit 1; fi; \
	read -r -p "SSH port [$(SSH_TUNNEL_SSH_PORT)]: " SSH_PORT; \
	SSH_PORT=$${SSH_PORT:-$(SSH_TUNNEL_SSH_PORT)}; \
	printf "SSH password: "; stty -echo; read -r SSH_PASS; stty echo; printf "\n"; \
	if [ -z "$$SSH_PASS" ]; then echo "ERROR: SSH password is required."; exit 1; fi; \
	echo "Starting autossh in background..."; \
	$(COMPOSE_CMD) exec \
		-e SSHPASS="$$SSH_PASS" \
		-e SSH_TUNNEL_RUNTIME_USER="$$SSH_USER" \
		-e SSH_TUNNEL_RUNTIME_HOST="$$SSH_HOST" \
		-e SSH_TUNNEL_RUNTIME_PORT="$$SSH_PORT" \
		ssh-tunnel sh -lc 'nohup sshpass -e autossh -M 0 -N -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ServerAliveInterval=10 -o ServerAliveCountMax=3 -o ExitOnForwardFailure=yes -R 0.0.0.0:$(STOMP_TUNNEL_REMOTE_PORT):rabbitmq:61613 -p "$${SSH_TUNNEL_RUNTIME_PORT}" "$${SSH_TUNNEL_RUNTIME_USER}@$${SSH_TUNNEL_RUNTIME_HOST}" >/tmp/autossh.log 2>&1 & echo $$! >/tmp/autossh.pid'; \
	sleep 1; \
	if $(COMPOSE_CMD) exec ssh-tunnel sh -lc 'pidfile=/tmp/autossh.pid; [ -f "$${pidfile}" ] && pid=$$(cat "$${pidfile}") && kill -0 "$${pid}"' >/dev/null 2>&1; then \
		echo "autossh started. PID: $$($(COMPOSE_CMD) exec ssh-tunnel sh -lc 'cat /tmp/autossh.pid')"; \
		echo "Check logs with: make tunnel-status"; \
	else \
		echo "ERROR: autossh failed to start. Recent log output:"; \
		$(COMPOSE_CMD) exec ssh-tunnel sh -lc "tail -n 80 /tmp/autossh.log || true"; \
		exit 1; \
	fi

tunnel-status: tunnel-helper-up
	@if $(COMPOSE_CMD) exec ssh-tunnel sh -lc 'pidfile=/tmp/autossh.pid; [ -f "$${pidfile}" ] && pid=$$(cat "$${pidfile}") && kill -0 "$${pid}"' >/dev/null 2>&1; then \
		echo "autossh running. PID: $$($(COMPOSE_CMD) exec ssh-tunnel sh -lc 'cat /tmp/autossh.pid')"; \
	else \
		echo "autossh is not running."; \
	fi
	@echo "Recent autossh log:"; \
	if $(COMPOSE_CMD) exec ssh-tunnel sh -lc "tail -n 40 /tmp/autossh.log" >/dev/null 2>&1; then \
		$(COMPOSE_CMD) exec ssh-tunnel sh -lc "tail -n 40 /tmp/autossh.log"; \
	else \
		echo "ssh-tunnel helper container not running yet or no log file present."; \
	fi

tunnel-stop: tunnel-helper-up
	@if $(COMPOSE_CMD) exec ssh-tunnel sh -lc 'pidfile=/tmp/autossh.pid; [ -f "$${pidfile}" ] && pid=$$(cat "$${pidfile}") && kill -0 "$${pid}"' >/dev/null 2>&1; then \
		$(COMPOSE_CMD) exec ssh-tunnel sh -lc "kill $$(cat /tmp/autossh.pid) && rm -f /tmp/autossh.pid"; \
		echo "autossh stopped."; \
	else \
		echo "autossh is not running."; \
	fi

check:
	$(PYTHON) manage.py check

deploy:
	@test -n "$(DEPLOY_PATH)" || { echo "ERROR: DEPLOY_PATH is not set in .env"; exit 1; }
	@test -n "$(WEB_IMAGE)" || { echo "ERROR: WEB_IMAGE is not set in .env"; exit 1; }
	cd $(DEPLOY_PATH) && \
	git pull && \
	sed -i 's|^WEB_IMAGE=.*|WEB_IMAGE=$(WEB_IMAGE)|' .env && \
	podman compose pull web && \
	podman compose up -d; \

live-test-setup:
	$(PYTHON) -m pip install -r requirements-live-test.txt

live-test-snakemake: live-test-setup
	$(PYTHON) scripts/live_snakemake_stomp_test.py

collect-workflow-events: live-test-setup
	$(PYTHON) scripts/collect_workflow_events.py \
		--host "$(STOMP_HOST)" \
		--port "$(STOMP_PORT)" \
		--user "$${STOMP_USER:-$${RABBITMQ_USER:-guest}}" \
		--password "$${STOMP_PASSWORD:-$${RABBITMQ_PASSWORD:-guest}}" \
		--virtual-host "$(STOMP_VHOST)" \
		--destination "$(STOMP_STREAM_QUEUE)" \
		$(if $(filter 1 true TRUE yes YES on ON,$(STOMP_USE_STREAM)),--use-stream,) \
		--stream-offset "$(STOMP_STREAM_OFFSET)" \
		--prefetch-count "$(STOMP_PREFETCH_COUNT)" \
		--max-events "$(STOMP_MAX_EVENTS)" \
		--idle-timeout-seconds "$(STOMP_IDLE_TIMEOUT_SECONDS)" \
		$(if $(filter 1 true TRUE yes YES on ON,$(STOMP_FOLLOW)),--follow,) \
		--output "$(WORKFLOW_EVENTS_OUT)" \
		$(if $(STOMP_DEBUG),--debug-stomp,)

print-events: workflow-events.jsonl
	jq '.body | fromjson' workflow-events.jsonl