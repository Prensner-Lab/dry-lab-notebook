COMPOSE = podman compose
PROJECT_NAME ?= dry-lab-notebook-prod
BASE = -p $(PROJECT_NAME) -f docker-compose.yml

-include .env
export

STATICFILES_HOST_DIR ?= $(PWD)/staticfiles

.PHONY: dev-up dev-down dev-logs dev-shell migrate makemigrations createsuperuser test build staticfiles-dir image-check prod-up prod-down collectstatic

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

prod-up: image-check db.sqlite3
	$(COMPOSE) $(BASE) up -d

prod-down:
	$(COMPOSE) $(BASE) down