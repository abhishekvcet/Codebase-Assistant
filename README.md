# 🧠 Intelligent Codebase Assistant

AI-powered code understanding, debugging, and documentation — powered by a hybrid LLM system (Ollama / Groq / Gemini) with RAG-based retrieval using ChromaDB.

---

## ✨ Features

-   **RAG-Powered Code Chat** — Strict RAG-first pipeline indexing code into ChromaDB for context-aware answers.
-   **Hybrid LLM System** — Fallback orchestration: `Local (Ollama) → Groq → Gemini` with 3x retry logic.
-   **Automated Startup** — One-click `start_all.bat` to launch the API server, Web UI, and Interactive CLI.
-   **Interactive CLI (`cb`)** — Menu-driven mode selection (Chat / Debug / Dependency) with shorthand commands.
-   **Web UI** — Real-time chat with model selection, context source display, and markdown rendering.
-   **External Database** — ChromaDB data is stored outside the repository for cleaner commits.
-   **Debug Mode** — Root cause analysis from error logs with fix recommendations based on indexed code.
-   **Dependency Analysis** — Parse AST imports/classes/functions and analyze cross-module impact.

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

---

## 🚀 Quick Start (Windows)

The fastest way to get started is using our automated scripts.

### 1. Initial Setup

```powershell
git clone <repo-url>
cd Codebase-Assistant

# Create & activate virtual environment
python -m venv .venv
.venv\Scripts\activate

# Install all requirements (including sentence-transformers)
pip install -r requirements.txt

# Create your .env file
copy .env.example .env
```

### 2. Configure API Keys
Edit your `.env` file to add your `GROQ_API_KEY` or `GEMINI_API_KEY` if you want to use cloud models.

### 3. One-Click Launch 🚀
Start the server, open the browser, and enter interactive chat all at once:
```powershell
.\start_all.bat
```

### 4. Index Your Codebase (Required First Step)
The assistant uses a strict RAG-first pipeline. You **must** index your project folder before chatting:
```powershell
# Open a new terminal (while server is running) and run:
.\cb index C:\path\to\your\codebase
```

---

## 💻 CLI Commands (`cb`)

We provide a `cb` shortcut for a streamlined terminal experience.

| Command | Description |
| :--- | :--- |
| `.\cb index <path>` | Index a folder or file into the database |
| `.\cb run` | Launch Interactive Mode (Chat/Debug/Deps) |
| `.\cb web` | Open the Web UI in your default browser |
| `.\cb health` | Check if providers (Ollama, Groq, etc.) are reachable |

---

## 🌐 API & Web UI

-   **Dashboard**: Access the Web UI at [http://localhost:8000](http://localhost:8000)
-   **API Base**: [http://localhost:8000](http://localhost:8000)
-   **Health**: [http://localhost:8000/health](http://localhost:8000/health)

---

## ⚙️ Configuration

Settings are managed in `.env`. Key options:

| Variable | Default | Description |
| :--- | :--- | :--- |
| `CHROMA_PERSIST_DIR` | `../chroma_db` | **Now stored outside the repo** for cleanliness |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Requires `sentence-transformers` (installed via pip) |
| `GROQ_API_KEY` | — | Required for high-speed cloud inference |
| `GEMINI_API_KEY` | — | Required for deep architectural reasoning |

---

## 🔄 LLM Fallback Chain

The system automatically falls back if a provider fails or API keys are missing:
`Primary Provider → Local (Ollama) → Groq → Gemini`

Each provider retries **3 times** with exponential backoff before failing over.

---

## 🛠️ Troubleshooting

| Problem | Solution |
| :--- | :--- |
| `Cannot connect to backend` | Ensure you ran `.\start_all.bat` or the server main script. |
| `ChromaDB error (missing package)` | Run `pip install sentence-transformers`. |
| `Interactive CLI busy` | Open a second terminal to run `cb index` while chatting. |
| `No code context found` | You must index your codebase first using the `cb index` command. |

---

## 📄 License

MIT
 the server: `python -m services.api_gateway.main` |
| `No Ollama models found` | Run `ollama pull llama3:8b` and ensure Ollama is running |
| `Groq/Gemini not working` | Set valid API keys in `.env` |
| `No code context found` | Index your codebase first: `cb index ./project` |
| `ChromaDB error` | Delete `./chroma_db/` and re-index |

---

## 📄 License

MIT
