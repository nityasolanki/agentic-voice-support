.PHONY: setup infra seed backend frontend all

setup:
	cp .env.example .env
	cd backend && pip install -r requirements.txt
	cd frontend && pip install -r requirements.txt
	ollama pull qwen2.5:7b
	ollama pull nomic-embed-text

infra:
	docker-compose up -d

seed:
	cd backend && python -m db.seed

backend:
	cd backend && uvicorn main:app --reload --port 8000

frontend:
	cd frontend && streamlit run app.py --server.port 8501

scheduler:
	cd backend && python -m agents.scheduler

all:
	make infra
	sleep 5
	make seed
	make backend &
	make frontend
