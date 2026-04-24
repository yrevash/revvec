.PHONY: help venv install up down logs reset smoke test fmt clean

SHELL := /bin/bash
PY := .venv/bin/python
PIP := .venv/bin/python -m pip

help:
	@echo "revvec — make targets"
	@echo "  make install    - install Python 3.12 via uv + venv + deps"
	@echo "  make up         - bring Actian up (requires Docker Desktop running)"
	@echo "  make serve      - start the FastAPI sidecar on 127.0.0.1:8000 (needed by the .app)"
	@echo "  make app        - open the built .app bundle"
	@echo "  make down       - stop Actian"
	@echo "  make reset      - stop Actian and wipe data volume"
	@echo "  make smoke      - run phase 0 smoke test"
	@echo "  make test       - run unit tests"
	@echo "  make fmt        - format + lint"
	@echo "  make logs       - tail Actian logs"
	@echo "  make clean      - remove venv"

serve:
	$(PY) -m revvec.server

app:
	open app/src-tauri/target/release/bundle/macos/revvec.app

venv:
	uv python install 3.12
	uv venv --python 3.12 .venv

install: venv
	. .venv/bin/activate && uv pip install -e ".[dev]"

up:
	@docker info >/dev/null 2>&1 || (echo "[make up] ERROR: Docker daemon not running. Open Docker Desktop." && exit 1)
	docker compose up -d
	@echo "[make up] Waiting for Actian on localhost:50052..."
	@for i in $$(seq 1 30); do \
		if $(PY) -c "from actian_vectorai import VectorAIClient; c=VectorAIClient('localhost:50052'); c.connect(); c.health_check(); c.close()" >/dev/null 2>&1; then \
			echo "[make up] Actian ready."; exit 0; \
		fi; \
		sleep 1; \
	done; \
	echo "[make up] ERROR: Actian did not respond within 30s"; docker compose logs --tail=30; exit 1

stop:
	docker compose stop

down:
	docker compose down

logs:
	docker compose logs -f actian

reset:
	docker compose down -v
	rm -rf data/actian

smoke:
	$(PY) scripts/phase0_smoke.py

fetch:
	$(PY) scripts/fetch.py

fetch-dry:
	$(PY) scripts/fetch.py --dry-run

phase1-log:
	$(PY) scripts/phase1_log_ingest.py

phase1-image:
	$(PY) scripts/phase1_image_ingest.py

phase1-sop:
	$(PY) scripts/phase1_sop_ingest.py

phase1-sop-reset:
	$(PY) scripts/phase1_sop_reset.py

phase2-sensor:
	$(PY) scripts/phase2_sensor_ingest.py

phase2-promote:
	$(PY) scripts/phase2_promotion_demo.py

phase3-query:
	$(PY) scripts/phase3_query_demo.py

phase4-answer:
	$(PY) scripts/phase4_answer_demo.py

phase5-voice:
	$(PY) scripts/phase5_voice_demo.py --repeat 2 --persona maintenance

image-pull:
	$(PY) -c "from transformers import AutoModel, AutoImageProcessor; mid='$(shell grep PHOTO_EMBED_MODEL src/revvec/config.py | head -1 | cut -d'\"' -f2)'; AutoImageProcessor.from_pretrained(mid); AutoModel.from_pretrained(mid); print('image embed cached')"

test:
	.venv/bin/pytest -q -m 'not slow'

test-slow:
	.venv/bin/pytest -q -m slow

embed-pull:
	$(PY) -c "from revvec.embed.service import get_embedder; get_embedder().embed_text('warmup')"

fmt:
	.venv/bin/ruff format src tests scripts
	.venv/bin/ruff check --fix src tests scripts

clean:
	rm -rf .venv
