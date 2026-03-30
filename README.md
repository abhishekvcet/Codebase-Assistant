# 🧠 Intelligent Codebase Assistant

AI-powered code understanding, debugging, and documentation — powered by a hybrid LLM system (Ollama / Groq / Gemini) with RAG-based retrieval using ChromaDB.

---

## ✨ Features

- **RAG-Powered Code Chat** — Strict RAG-first pipeline indexing code into ChromaDB for context-aware answers.
- **Hybrid LLM System** — Fallback orchestration: `Local (Ollama) → Groq → Gemini` with 3x retry logic.
- **Interactive CLI (`cb`)** — Menu-driven mode selection (Chat / Debug / Dependency) with dynamic model listing.
- **Web UI** — Real-time chat with model selection, context source display, and markdown rendering.
- **Debug Mode** — Root cause analysis from error logs with fix recommendations based on indexed code.
- **Dependency Analysis** — Parse AST imports/classes/functions and analyze cross-module impact.

---

## 🏗️ Architecture

```
User (CLI / Web UI)
       │
       ▼
  API Gateway (FastAPI :8000)
       │
       ├── /chat ──→ RAG (ChromaDB) ──→ LLM Orchestrator ──→ Response
       ├── /index ─→ Chunk + Embed ──→ ChromaDB (persistent)
       ├── /debug ─→ Parse Logs ────→ LLM Analysis
       ├── /deps ──→ AST Parsing ──→ Dependency Info
       └── /health → Provider Status
```

### Project Structure

```
Codebase-Assistant/
├── cli/
│   └── cli.py                  # Interactive CLI (cb index / cb run)
├── frontend/
│   ├── index.html              # Web UI
│   ├── app.js                  # Frontend logic
│   └── style.css               # Styles
├── services/
│   ├── api_gateway/
│   │   └── main.py             # FastAPI server (all endpoints)
│   ├── rag_service/
│   │   └── rag_service.py      # ChromaDB indexing & retrieval
│   ├── debug_service/
│   │   └── debug_service.py    # Error log analysis
│   ├── graph_service/          # Dependency graph parsing
│   └── llm_orchestrator/
├── shared/
│   ├── config.py               # Central configuration
│   └── llm/
│       ├── base.py             # LLM abstract interface
│       ├── ollama_client.py    # Ollama (local)
│       ├── groq_client.py      # Groq (cloud, with retry)
│       ├── gemini_client.py    # Gemini (cloud, with retry)
│       └── orchestrator.py     # Model selection + fallback chain
├── requirements.txt            # Python dependencies
├── .env                        # Environment variables (gitignored)
└── .env.example                # Template for .env
```

---

## 🚀 Quick Start

### Prerequisites

- **Python 3.11+**
- **Ollama** installed locally ([ollama.com](https://ollama.com)) with at least one model pulled

### 1. Clone & Setup

```bash
git clone <repo-url>
cd Codebase-Assistant

# Create virtual environment
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/Mac:
# source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
# Copy the example env file
cp .env.example .env
```

Edit `.env` with your API keys:

```env
# Required for cloud LLMs (optional if using Ollama only)
GROQ_API_KEY=your_groq_api_key_here
GEMINI_API_KEY=your_gemini_api_key_here

# Ollama (runs locally)
OLLAMA_BASE_URL=http://localhost:11434
```

### 3. Start Ollama (Local LLM)

```bash
# Pull a model
ollama pull llama3:8b
ollama pull phi3

# Ollama runs automatically as a service, or start it:
ollama serve
```

### 4. Start the API Server

```bash
python -m services.api_gateway.main
```

The server starts at **http://localhost:8000**

### 5. Index Your Codebase (Required)

The assistant uses a strict RAG-first pipeline. You **must** index your project before chatting.

```bash
# Via CLI (ensure server is running)
cb index ./path/to/your/project
```

### 6. Start Chatting!

**Interactive CLI:**
```bash
cb run
```

**Web UI:**
Open [http://localhost:8000](http://localhost:8000) in your browser.

---

## 💻 CLI Usage

The project includes a `cb` shortcut for a streamlined experience.

### Index a Codebase
```bash
cb index ./your-project
```

### Interactive Mode
```bash
cb run
```

The interactive flow allows you to:
1. **Select Mode** → Chat (General), Debug (Log analysis), or Dependency (Graph analysis).
2. **Select Model** → Choose between local (Ollama) or API-based (Groq/Gemini).
3. **Start Working** → Enter an interactive loop (type `quit` to exit).

### Health Check
Check connection status and configured providers:
```bash
cb health
```

---

## 🌐 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/chat` | Chat with RAG context (main endpoint) |
| `POST` | `/index` | Index a directory into ChromaDB |
| `POST` | `/debug` | Analyze error logs |
| `POST` | `/deps` | Dependency analysis |
| `GET` | `/rag/status` | ChromaDB index status |
| `GET` | `/health` | Provider health check |
| `GET` | `/` | Web UI |

### Example: Chat

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"query": "How does the RAG service work?", "model": "auto"}'
```

### Response Format

```json
{
  "answer": "The RAG service works by...",
  "model_used": "llama3:8b",
  "provider": "ollama",
  "mode": "chat",
  "fallback_used": false,
  "latency_ms": 1234.5,
  "context_used": [
    {"file": "services/rag_service/rag_service.py", "lines": "10-25", "scope": "search", "score": 0.89}
  ],
  "context_chunks": 5
}
```

---

## ⚙️ Configuration

All settings are in `.env` (see `.env.example` for template):

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_MODEL_FAST` | `phi3` | Fast model for simple queries |
| `OLLAMA_MODEL_COMPLEX` | `llama3:8b` | Complex model for detailed analysis |
| `GROQ_API_KEY` | — | Groq API key ([console.groq.com](https://console.groq.com)) |
| `GROQ_MODEL` | `llama-3.1-8b-instant` | Groq model |
| `GEMINI_API_KEY` | — | Google Gemini API key ([aistudio.google.com](https://aistudio.google.com)) |
| `GEMINI_MODEL` | `gemini-2.0-flash` | Gemini model |
| `CHROMA_PERSIST_DIR` | `./chroma_db` | ChromaDB storage directory |
| `CHROMA_COLLECTION_NAME` | `codebase` | ChromaDB collection name |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Sentence transformer model |
| `CHUNK_SIZE` | `512` | Characters per code chunk |
| `TOP_K_RESULTS` | `5` | Number of RAG results to retrieve |
| `API_PORT` | `8000` | Server port |
| `LOG_LEVEL` | `INFO` | Logging level |

---

## 🔄 LLM Fallback Chain

The system automatically falls back if a provider fails:

```
Primary Provider (user-selected or auto-detected)
       │ fails
       ▼
  Local (Ollama) → Groq → Gemini
```

Each provider retries **3 times** with exponential backoff before failing over.

### Auto-Classification

When model is set to `auto`, queries are classified:

| Category | Provider | Trigger Words |
|----------|----------|---------------|
| Simple | Ollama (phi3) | Short, basic questions |
| RAG | Ollama (llama3) | "explain", "how does", "function", "class" |
| Debug | Groq | "error", "bug", "traceback", "fix" |
| Complex | Gemini | "architecture", "refactor", "optimize" |

---

## 📁 Supported File Types

The RAG indexer supports: `.py`, `.js`, `.ts`, `.jsx`, `.tsx`, `.java`, `.go`, `.rs`, `.c`, `.cpp`, `.cs`, `.rb`, `.php`, `.swift`, `.kt`, `.scala`, `.sh`, `.yaml`, `.json`, `.toml`, `.md`, `.html`, `.css`, `.sql`

---

## 🛠️ Troubleshooting

| Problem | Solution |
|---------|----------|
| `Cannot connect to backend` | Start the server: `python -m services.api_gateway.main` |
| `No Ollama models found` | Run `ollama pull llama3:8b` and ensure Ollama is running |
| `Groq/Gemini not working` | Set valid API keys in `.env` |
| `No code context found` | Index your codebase first: `cb index ./project` |
| `ChromaDB error` | Delete `./chroma_db/` and re-index |

---

## 📄 License

MIT
