COMPOSE = podman compose
BASE = -f docker-compose.yml
DEV = -f docker-compose.dev.yml

.PHONY: dev-up dev-down dev-logs dev-shell migrate makemigrations createsuperuser test build prod-up prod-down collectstatic

db.sqlite3:
	@echo "WARNING: db.sqlite3 not found — creating empty file to prevent Docker mount issue."
	@touch db.sqlite3

dev-up: db.sqlite3
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

collectstatic:
	sudo mkdir -p /var/www/dry-lab-notebook/staticfiles/
	sudo chmod 777 /var/www/dry-lab-notebook/staticfiles/
	podman compose run --rm -v /var/www/dry-lab-notebook/staticfiles:/app/staticfiles collectstatic

prod-up: db.sqlite3
	$(COMPOSE) $(BASE) up -d --build

prod-down:
	$(COMPOSE) $(BASE) down