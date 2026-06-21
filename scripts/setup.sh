#!/bin/bash
set -e

echo "🔧 Setting up Agentic Voice Customer Support Agent..."

# Check Python version
python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo "✓ Python version: $python_version"

# Copy env
if [ ! -f .env ]; then
  cp .env.example .env
  echo "✓ Created .env from .env.example — please fill in your credentials"
fi

# Install dependencies
pip install -r requirements.txt
echo "✓ Python dependencies installed"

# Start Docker services
docker-compose up -d
echo "✓ PostgreSQL and Qdrant started"

# Wait for Postgres
echo "⏳ Waiting for PostgreSQL..."
until docker exec voice_support_postgres pg_isready -U support_user -d voice_support > /dev/null 2>&1; do
  sleep 1
done
echo "✓ PostgreSQL ready"

# Pull Ollama model
if command -v ollama &> /dev/null; then
  echo "⬇️  Pulling Ollama model..."
  ollama pull qwen2.5:8b
  echo "✓ Ollama model ready"
else
  echo "⚠️  Ollama not found. Install from https://ollama.com"
fi

echo ""
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "  1. Fill in your credentials in .env (Twilio, Gmail)"
echo "  2. Run: bash scripts/seed_db.sh"
echo "  3. Run: uvicorn backend.api.main:app --reload --port 8000"
echo "  4. Run: streamlit run frontend/app.py"
