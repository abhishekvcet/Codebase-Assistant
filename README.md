# 🧠 Intelligent Codebase Assistant

> AI-powered code understanding, debugging, dependency analysis, and documentation generation — with hybrid LLM support (Local + Cloud).

![Python](https://img.shields.io/badge/Python-3.11+-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green)
![License](https://img.shields.io/badge/License-MIT-yellow)

---

## ✨ Features

- **RAG Pipeline** — Chunk code, embed with sentence-transformers, search with FAISS, answer with LLM context
- **Debug Engine** — Parse logs, extract errors (Python/Java/JS), root cause analysis via LLM
- **Dependency Graph** — AST-based parsing, Neo4j storage, visual dependency mapping
- **Auto Documentation** — Generate module summaries and API docs
- **Hybrid LLM** — Ollama (local), Groq (cloud/fast), Gemini (cloud/deep)
- **Smart Routing** — Auto-classifies queries → picks the best model
- **Fallback Chain** — If one provider fails: local → groq → gemini
- **ChatGPT-like UI** — Dark theme, model selector, markdown rendering, chat history
- **CLI Tool** — Full terminal interface with rich output

---

## 🏗️ Architecture

```
├── shared/
│   ├── config.py              # Environment configuration
│   └── llm/
│       ├── base.py            # Abstract LLM client
│       ├── ollama_client.py   # Local Ollama integration
│       ├── groq_client.py     # Groq cloud API
│       ├── gemini_client.py   # Google Gemini API
│       └── orchestrator.py    # Model selection & fallback
├── services/
│   ├── api_gateway/main.py    # FastAPI application
│   ├── rag_service/           # RAG pipeline (FAISS)
│   ├── debug_service/         # Error analysis
│   └── graph_service/         # Dependency graph (Neo4j)
├── cli/cli.py                 # Typer CLI tool
├── frontend/
│   ├── index.html             # Chat UI
│   ├── style.css              # Premium dark theme
│   └── app.js                 # Chat logic
├── docker-compose.yml         # Infrastructure (Postgres, Neo4j, Redis)
├── requirements.txt           # Python dependencies
└── .env.example               # Environment template
```

---

## 🚀 Quick Start

### 1. Prerequisites

- **Python 3.11+**
- **Ollama** installed locally ([ollama.ai](https://ollama.ai))
- **Docker** (for infrastructure services)

### 2. Setup

```bash
# Clone and enter the project
cd intelligent-codebase-assistant

# Create virtual environment
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # macOS/Linux

# Install dependencies
pip install -r requirements.txt

# Copy environment file
copy .env.example .env
# Edit .env with your API keys
```

### 3. Pull Ollama Models

```bash
ollama pull phi3
ollama pull llama3:8b
```

### 4. Start Infrastructure

```bash
docker compose up -d
```

### 5. Start the Backend

```bash
python -m uvicorn services.api_gateway.main:app --reload --port 8000
```

### 6. Open the UI

Visit **http://localhost:8000** in your browser.

---

## 🖥️ CLI Usage

```bash
# Ask questions
python -m cli.cli ask "Explain the authentication flow" --model auto
python -m cli.cli ask "What does this function do?" --model local
python -m cli.cli ask "Analyze the architecture" --model gemini

# Debug errors
python -m cli.cli debug error.log --model groq

# Analyze dependencies
python -m cli.cli deps main.py

# Index codebase for RAG
python -m cli.cli index ./src

# Health check
python -m cli.cli health
```

---

## 🧠 Model Selection

| Mode     | Provider | Use Case                    |
|----------|----------|-----------------------------|
| `auto`   | Smart    | AI classifies and routes    |
| `local`  | Ollama   | Fast/private, on-device     |
| `groq`   | Groq     | Fast cloud, debugging       |
| `gemini` | Gemini   | Deep reasoning, complexity  |

### Auto-Classification Logic

| Query Type | → Model       |
|------------|---------------|
| Simple     | phi3 (local)  |
| RAG        | llama3 (local)|
| Debug      | Groq          |
| Complex    | Gemini        |

---

## 🔌 API Endpoints

| Method | Endpoint         | Description                |
|--------|------------------|----------------------------|
| POST   | `/chat`          | Main chat endpoint         |
| POST   | `/rag/index`     | Index codebase for RAG     |
| GET    | `/rag/status`    | RAG index status           |
| POST   | `/rag/query`     | Query with RAG context     |
| POST   | `/debug/analyze` | Analyze error logs         |
| POST   | `/graph/parse`   | Build dependency graph     |
| GET    | `/health`        | Provider health check      |

### Chat Request

```json
{
  "query": "Explain the auth flow",
  "model": "auto"
}
```

### Chat Response

```json
{
  "answer": "The authentication flow works by...",
  "model_used": "llama3:8b",
  "provider": "ollama",
  "mode": "auto",
  "fallback_used": false,
  "latency_ms": 1250.5
}
```

---

## 🔐 Environment Variables

| Variable           | Description                    | Default              |
|--------------------|--------------------------------|----------------------|
| `OLLAMA_BASE_URL`  | Ollama server URL              | http://localhost:11434|
| `GROQ_API_KEY`     | Groq API key                   | —                    |
| `GEMINI_API_KEY`   | Gemini API key                 | —                    |
| `POSTGRES_URL`     | PostgreSQL connection URL      | —                    |
| `NEO4J_URI`        | Neo4j Bolt URL                 | bolt://localhost:7687|
| `REDIS_URL`        | Redis connection URL           | redis://localhost:6379|

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.
