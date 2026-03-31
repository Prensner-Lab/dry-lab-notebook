COMPOSE = podman compose
PROJECT_NAME ?= dry-lab-notebook-app
BASE = -p $(PROJECT_NAME) -f docker-compose.yml
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

.PHONY: dev-up dev-down dev-logs dev-shell migrate makemigrations createsuperuser test build staticfiles-dir image-check prod-up prod-down collectstatic live-test-setup live-test-snakemake collect-workflow-events

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
	$(COMPOSE) $(BASE) exec web python manage.py migrate

makemigrations:
	$(COMPOSE) $(BASE) exec web python manage.py makemigrations

createsuperuser:
	$(COMPOSE) $(BASE) exec web python manage.py createsuperuser

test:
	$(COMPOSE) $(BASE) exec web python manage.py test

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
	$(COMPOSE) $(BASE) up -d --build --force-recreate

prod-down:
	$(COMPOSE) $(BASE) down

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