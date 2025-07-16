
init-env:
	python3 -m venv .env
win-init-env:
	python -m venv .env

install:
	pip install pip-tools && CFLAGS="-Wno-error=implicit-function-declaration" pip install -r requirements.txt && npm install
win-install:
	pip install pip-tools & $env:CFLAGS="-Wno-error=implicit-function-declaration" & pip install -r requirements.txt && npm install

install-test:
	pip install -r requirements-test.txt

install-dev:
	pip install -r requirements-dev.txt

run:
	DEBUG=1 DEBUG_TOOLBAR=1 ./node_modules/.bin/concurrently -r -k "python manage.py runserver 8080" "./node_modules/.bin/webpack --config webpack.config.js --mode development --watch"
win-run:
	$env:DEBUG="1" & $env:DEBUG_TOOLBAR="1" & $env:DATABASE_DSN="postgresql://postgres:postgres@localhost:5433/ksicht" & .\node_modules\.bin\concurrently -r -k "python manage.py runserver 8080" ".\node_modules\.bin\webpack --config webpack.config.js --mode development --watch"

dep-freeze:
	pip-compile requirements.in

test:
	pytest

migrate:
	DEBUG=1 python manage.py migrate
win-migrate:
	$env:DEBUG="1" & $env:DATABASE_DSN='postgresql://postgres:postgres@localhost:5433/ksicht' & python manage.py migrate

migrations:
	DEBUG=1 python manage.py makemigrations
win-migrations:
	$env:DEBUG="1" & python manage.py makemigrations

build-assets:
	.\node_modules\.bin\webpack --config webpack.config.js --mode production

build-image:
	docker buildx build --platform linux/amd64 -t ksicht/web:latest .

build:
	make build-assets
	make build-image

push:
	docker push ksicht/web:latest

release:
	make build
	make push


# --- code checks ---

MODULES ?= ksicht tests
ALL_MODULES ?= $(MODULES)

.PHONY: code-checks
code-checks: pylint isort black

PYLINT_ARGS ?=

.PHONY: pylint
pylint:  ## lint code
	pylint $(PYLINT_ARGS) $(ALL_MODULES)

BLACK_ARGS ?=

.PHONY: black
black:  ## check code formating
	black $(BLACK_ARGS) $(ALL_MODULES)

.PHONY: isort
isort:
	isort --profile black $(ALL_MODULES)
