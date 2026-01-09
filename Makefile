.PHONY: help migrate test runserver shell

help:
	@echo "Available commands:"
	@echo "  make migrate      - Run database migrations"
	@echo "  make test         - Run tests"
	@echo "  make runserver    - Start development server"
	@echo "  make shell        - Open Django shell"
	@echo "  make init-accounts - Initialize required accounts"

migrate:
	python manage.py migrate

test:
	pytest

runserver:
	python manage.py runserver

shell:
	python manage.py shell

init-accounts:
	python manage.py init_accounts




