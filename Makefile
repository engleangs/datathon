.PHONY: install run test build up down logs dbt

install:
	python -m pip install -r requirements-app.txt -r requirements-dev.txt

run:
	streamlit run app/main.py

test:
	pytest -q

build:
	docker compose build

up:
	docker compose up -d app

down:
	docker compose down

logs:
	docker compose logs -f app

dbt:
	docker compose run --rm dbt
