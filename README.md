# 🧠 Intelligent Codebase Assistant — v1.0

AI-powered code understanding, debugging, and high-level architectural visualization. Built with a **Hybrid LLM Orchestrator** and a **Semantic RAG Pipeline** to give you deep insights into any codebase within seconds.

---

## 🔥 Key Innovations

### 1. 🎨 Visual Architecture (Adaptive Workflow)
Unlike traditional tools that only show file lists, our assistant generates a **2D Semantic Workflow**. It identifies your entry points, core logic providers, and storage layers, then visualizes them with professional icons and distinct shapes (Hexagons, Diamonds, Cylinders) using Mermaid.

### 2. 🧠 Smart Context Injection (Strict RAG)
We enforce a **Context-Only** response policy. The assistant retrieves relevant AST chunks from a persistent **ChromaDB** store and uses them to anchor every answer. No hallucinated code.

### 3. ⛓️ Hybrid LLM Orchestrator
A robust fallback chain with exponential backoff and 3x retries:
`Local (Ollama) → Cloud (Groq) → Deep Reasoning (Gemini)`

### 4. 🗄️ External Persistence
ChromaDB data is stored **outside the repository** (`../chromadb`) by default, ensuring your project directory stays clean and your vector database persists across multiple project versions.

---

## 📊 Comparison: Standard RAG vs. Our Assistant

| Feature | Standard RAG | **Our Intelligent Assistant** |
| :--- | :--- | :--- |
| **Indexing** | Basic text chunking | **AST-Aware Chunking** (Functions/Classes) |
| **Logic Recovery** | None | **Semantic Architecture Workflows** |
| **Model Choice** | Single Model | **Hybrid Fallback Orchestrator** |
| **Reliability** | Fails on API errors | **3x Retry Logic + Provider Failover** |
| **Visuals** | Static file trees | **Dynamic 2D Mermaid Flowcharts** |
| **Storage** | Local/Temporary | **Persistent External Database** |

---

## 🏗️ System Workflow

```mermaid
graph TD
    User((👤 Developer)) -->|Input| CLI{{⌨️ CLI / Web UI}}
    
    subgraph Processing Layer
        CLI -->|Query| Gateway{{🌐 API Gateway}}
        Gateway -->|Retrieve| RAG(📂 RAG Service)
        RAG -->|Metadata| DB[(📁 ChromaDB)]
    end
    
    subgraph Reasoning Layer
        Gateway -->|Context| Brain{🧠 LLM Orchestrator}
        Brain -->|Strategy| Local(🏠 Ollama)
        Brain -->|Fallback| Groq(⚡ Groq)
        Brain -->|Deep Logic| Gemini(🔮 Gemini)
    end
    
    subgraph Visualization Layer
        Gateway -->|AST Analysis| Graph(🎨 Visual Workflow)
        Graph -->|Mermaid| Visual[📊 2D Architecture]
    end

    Gemini -->|Answer| User
    Visual -->|Diagram| User
```

---

## 🚀 Setup & Installation (Windows)

### 1. Prerequisites
- **Python 3.10+**
- **Ollama** (for local models like `llama3:8b`)
- **Groq/Gemini API Keys** (Optional, for cloud fallback)

### 2. Initial Setup
```powershell
git clone <repo-url>
cd Codebase-Assistant

# Create & activate virtual environment
python -m venv .venv
.venv\Scripts\activate

# Install requirements
pip install -r requirements.txt

# Configure environment
copy .env.example .env
```
*Edit `.env` to add your Groq/Gemini keys for the best experience.*

### 3. Launching the Assistant
```powershell
# Start the unified server (API + Web UI)
python main.py
```

---

## 💻 Working with the CLI (`cb`)

The `cb` shortcut provides a "premium" terminal experience with a high-fidelity ASCII banner and specialized menu styles.

| Command | Description |
| :--- | :--- |
| `.\cb cli` | **Full Interactive Mode** (Chat, Debug, Architecture) |
| `.\cb index <dir>` | Index a project folder into ChromaDB (Required) |
| `.\cb web` | Instantly open the Web UI in your browser |
| `.\cb stop` | Safely shutdown the background server |
| `.\cb health` | Check reachability of Ollama, Groq, and Gemini |

---

## 📂 Project Structure

-   `cli/` : Interactive terminal interface with `rich` and `questionary`.
-   `services/`
    - `api_gateway/` : FastAPI entry point and endpoint routing.
    - `rag_service/` : ChromaDB management and AST chunking.
    - `graph_service/` : Visual architecture and logic flow generator.
    - `debug_service/` : Log analysis and fix advisor.
-   `shared/`
    - `llm/` : Clients and the Orchestrator brain.
    - `config.py` : Pydantic-based settings management.

---

## 📄 License

MIT — Build something great.
