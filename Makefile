COMPOSE = podman compose
BASE = -f docker-compose.yml
DEV = -f docker-compose.dev.yml

.PHONY: dev-up dev-down dev-logs dev-shell migrate makemigrations createsuperuser test build prod-up prod-down

dev-up:
	$(COMPOSE) $(BASE) $(DEV) up --build

dev-down:
	$(COMPOSE) $(BASE) $(DEV) down

dev-logs:
	$(COMPOSE) $(BASE) $(DEV) logs -f web

dev-shell:
	$(COMPOSE) $(BASE) $(DEV) exec web /bin/sh

migrate:
	$(COMPOSE) $(BASE) $(DEV) exec web python manage.py migrate

makemigrations:
	$(COMPOSE) $(BASE) $(DEV) exec web python manage.py makemigrations

createsuperuser:
	$(COMPOSE) $(BASE) $(DEV) exec web python manage.py createsuperuser

test:
	$(COMPOSE) $(BASE) $(DEV) exec web python manage.py test

build:
	podman build -t dry-lab-notebook .

prod-up:
	$(COMPOSE) $(BASE) up -d --build

prod-down:
	$(COMPOSE) $(BASE) down