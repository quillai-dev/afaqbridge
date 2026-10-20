# Application Office - make targets.
#  * dev-*  : native sandbox bench (what was actually run and tested while building this repo)
#  * others : Docker Compose deployment (setup/up/down/logs/test/backup/restore/status). NOT executed in the build
#             sandbox (no Docker there) - they refuse to run without Docker rather than pretend to succeed.
SHELL := /bin/bash
SITE ?= office.localhost
FD := upstream/frappe_docker
COMPOSE := docker compose --env-file .env -f $(FD)/compose.yaml -f $(FD)/overrides/compose.mariadb.yaml \
           -f $(FD)/overrides/compose.redis.yaml -f $(FD)/overrides/compose.https.yaml -f compose.yaml
.DEFAULT_GOAL := help

help:
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | sed 's/:.*##/ -/' | sort

need-docker:
	@command -v docker >/dev/null || { echo "docker is not installed on this machine; this target needs Docker Compose" >&2; exit 1; }
	@test -f .env || { echo ".env missing - run 'make setup'" >&2; exit 1; }

# ---------------------------------------------------------------- container deployment
setup: ## create .env from .env.example and generate random secrets (does not start anything)
	@test -f .env || cp .env.example .env
	@bash scripts/gen-secrets.sh .env
	@echo "Edit .env (domain names, image tag), then: make image && make up"

image: need-docker ## build the pinned custom image (frappe + erpnext + application_office) from deploy/apps.json
	@APPS_JSON_BASE64=$$(base64 -w0 deploy/apps.json) ; docker build --no-cache \
	  --build-arg=FRAPPE_PATH=https://github.com/frappe/frappe --build-arg=FRAPPE_BRANCH=v16.52.0 \
	  --build-arg=APPS_JSON_BASE64=$$APPS_JSON_BASE64 --tag=$$(grep ^CUSTOM_IMAGE= .env|cut -d= -f2):$$(grep ^CUSTOM_TAG= .env|cut -d= -f2) \
	  --file=$(FD)/images/layered/Containerfile $(FD)

up: need-docker ## start the stack (creates the site on first run)
	$(COMPOSE) up -d --wait

down: need-docker ## stop the stack (volumes are kept)
	$(COMPOSE) down

logs: need-docker ## follow logs
	$(COMPOSE) logs -f --tail=100

status: need-docker ## container health
	$(COMPOSE) ps

test: need-docker ## run the application_office unit/integration tests inside the backend container (needs allow_tests on a NON-production site)
	$(COMPOSE) exec backend bench --site $${TEST_SITE:?set TEST_SITE to a disposable test site} run-tests --app application_office

backup: need-docker ## encrypted backup of the production site (see docs/backup-restore.md)
	bash scripts/backup-prod.sh

restore: need-docker ## restore: make restore FILE=path/to/backup.tar.enc TARGET=scratch.example.com
	bash scripts/restore-prod.sh $(FILE) $(TARGET)

# ---------------------------------------------------------------- native dev sandbox (verified)
dev-up: ## start MariaDB, Redis, SMTP sink and the dev web server
	scripts/start-dev-stack.sh
dev-site: ## (re)create the dev site from scratch: ERPNext + application_office + sample company
	su frappe -c $(CURDIR)/scripts/dev-site.sh
dev-test: ## run the in-app test suite on the dev site
	su frappe -c '/home/frappe/fb.sh --site $(SITE) run-tests --app application_office'
dev-http-test: dev-up ## run the HTTP-level security tests against the running dev server
	su frappe -c 'cd ~/frappe-bench && env/bin/python $(CURDIR)/tests/http/test_http.py'
dev-backup: ## encrypted backup of the dev site
	su frappe -c 'BACKUP_PASSPHRASE_FILE=/home/frappe/.ao-backup-pass $(CURDIR)/scripts/backup.sh $(SITE)'
.PHONY: help need-docker setup image up down logs status test backup restore dev-up dev-site dev-test dev-http-test dev-backup
