.PHONY: install-api install-web api web worker migrate seed animation runtime-evidence test lint typecheck screenshots compose-up compose-down import-tests phase3-tests verify-backend
install-api:
	cd backend && python -m pip install -e '.[dev]'
install-web:
	cd frontend && npm install
api:
	cd backend && python -m uvicorn app.main:app --app-dir . --reload --port 8000
web:
	cd frontend && npm run dev
migrate:
	cd backend && alembic upgrade head
seed:
	cd backend && python -m app.seed
animation:
	python scripts/generate_animation_sequence.py
runtime-evidence:
	python scripts/generate_real_runtime_evidence.py
worker:
	cd backend && python -m app.worker
import-tests:
	cd backend && pytest -q tests/test_phase2_enterprise.py
lint:
	cd backend && ruff check app tests
	cd frontend && npm run lint
typecheck:
	cd backend && mypy app
	cd frontend && npm run typecheck
test:
	cd backend && pytest -q
	cd frontend && npm run test:e2e
phase3-tests:
	cd backend && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q
verify-backend:
	cd backend && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q
	cd backend && python -m compileall -q app tests
	cd backend && rm -f phase3_migration_test.db && PYTHONPATH=. DATABASE_URL=sqlite:///./phase3_migration_test.db alembic upgrade head
compose-up:
	docker compose up --build
compose-down:
	docker compose down -v
