"""
Intelligent Codebase Assistant — Interactive CLI Tool

Commands:
  cb index <folder_or_file>    Index code into ChromaDB
  cb run                       Interactive mode selection & chat
  cb web                       Open the Web UI in browser
  cb health                    Check provider health
"""

import os
import sys
import time
import asyncio
import webbrowser
from pathlib import Path
from typing import Optional

import typer
import httpx
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.table import Table
from rich.prompt import Prompt
from rich import print as rprint
import questionary

# Ensure project root on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

app = typer.Typer(
    name="cb",
    help="🧠 Intelligent Codebase Assistant — AI-powered code understanding",
    add_completion=False,
    rich_markup_mode="rich",
)
console = Console()

# Default API base URL
API_BASE = "http://localhost:8000"

# Custom style for Questionary
custom_style = questionary.Style([
    ('pointer', 'fg:#C06A49 bold'),
    ('highlighted', 'fg:#C06A49 bold'),
    ('question', 'bold'),
    ('answer', 'fg:#C06A49 bold'),
])


def _run_async(coro):
    """Run an async coroutine from sync CLI context."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, coro).result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


async def _api_call(method: str, endpoint: str, **kwargs) -> dict:
    """Make an API call to the backend."""
    url = f"{API_BASE}{endpoint}"
    async with httpx.AsyncClient(timeout=180) as client:
        if method == "GET":
            resp = await client.get(url, **kwargs)
        else:
            resp = await client.post(url, **kwargs)
        resp.raise_for_status()
        return resp.json()


async def _get_ollama_models() -> list[str]:
    """Fetch installed Ollama models dynamically."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get("http://localhost:11434/api/tags")
            if resp.status_code == 200:
                return [m["name"] for m in resp.json().get("models", [])]
    except Exception:
        pass
    return []


def _display_response(result: dict):
    """Display a formatted response from the API."""
    answer = result.get("answer", "No response")
    model_used = result.get("model_used", "unknown")
    provider = result.get("provider", "unknown")
    latency = result.get("latency_ms", 0)
    fallback = result.get("fallback_used", False)
    context_chunks = result.get("context_chunks", 0)
    context_used = result.get("context_used", [])
    mode = result.get("mode", "chat")

    # Build subtitle
    parts = [f"⏱ {latency:.0f}ms"]
    if fallback:
        parts.append("⚠ Fallback used")
    parts.append(f"📄 {context_chunks} context chunks")
    subtitle = " │ ".join(parts)

    console.print(Panel(
        Markdown(answer),
        title=f"[bold green]Response[/] — {model_used} ({provider})",
        subtitle=subtitle,
        border_style="green",
    ))

    # Show context sources
    if context_used:
        ctx_table = Table(title="📎 Context Sources", border_style="blue", show_lines=False)
        ctx_table.add_column("File", style="cyan", no_wrap=True)
        ctx_table.add_column("Lines", style="dim")
        ctx_table.add_column("Scope", style="yellow")
        ctx_table.add_column("Score", justify="right", style="green")

        for ctx in context_used:
            ctx_table.add_row(
                str(Path(ctx.get("file", "")).name),
                ctx.get("lines", ""),
                ctx.get("scope", "") or "—",
                f"{ctx.get('score', 0):.3f}",
            )
        console.print(ctx_table)


# ── index ──────────────────────────────────────────────────────────

@app.command()
def index(
    path: str = typer.Argument(..., help="Directory or file to index into ChromaDB"),
):
    """Index code into ChromaDB for RAG-powered queries."""
    target = Path(path).resolve()

    if target.is_file():
        directory = str(target.parent)
        console.print(f"\n[bold blue]📁 Indexing file's directory:[/] {directory}\n")
    elif target.is_dir():
        directory = str(target)
        console.print(f"\n[bold blue]📁 Indexing:[/] {directory}\n")
    else:
        console.print(f"[bold red]Error:[/] Path not found: {path}")
        raise typer.Exit(1)

    try:
        with console.status("[bold green]Chunking and embedding...", spinner="dots"):
            result = _run_async(
                _api_call("POST", "/index", json={"directory": directory})
            )

        console.print(Panel(
            f"[green]✅ Indexed {result.get('total_chunks', 0)} chunks "
            f"({result.get('total_vectors', 0)} vectors)[/]\n"
            f"Collection: {result.get('collection_name', 'codebase')}\n"
            f"Persist Dir: {result.get('persist_directory', './chroma_db')}",
            title="RAG Index Ready",
            border_style="blue",
        ))
    except httpx.ConnectError:
        console.print(
            "[bold red]Error:[/] Cannot connect to backend. "
            f"Make sure the server is running at {API_BASE}\n"
            "Start it with: [cyan]python -m services.api_gateway.main[/]"
        )
        raise typer.Exit(1)
    except httpx.HTTPStatusError as exc:
        detail = exc.response.json().get("detail", str(exc)) if exc.response else str(exc)
        console.print(f"[bold red]Error:[/] {detail}")
        raise typer.Exit(1)


# ── cli / run ───────────────────────────────────────────────────────

@app.command(name="cli")
def cli_command():
    """Interactive mode — select mode, model, and start working."""
    run()

@app.command()
def run():
    """Interactive mode — select mode, model, and start working."""
    # Custom ASCII Banner
    banner = """
[#C06A49] ██████  ██████  ██████  ███████ ██████   █████  ██████  ███████    ██████ ██      ██ 
██      ██    ██ ██   ██ ██      ██   ██ ██   ██ ██      ██         ██      ██      ██ 
██      ██    ██ ██   ██ █████   ██████  ███████ ███████ █████      ██      ██      ██ 
██      ██    ██ ██   ██ ██      ██   ██ ██   ██      ██ ██         ██      ██      ██ 
 ██████  ██████  ██████  ███████ ██████  ██   ██ ███████ ███████     ██████ ███████ ██ [/]

[#C06A49] codebase CLI v 1.0 [/]
"""
    console.print(banner)

    # 1. Select Mode
    mode_display = questionary.select(
        "Select Mode:",
        choices=[
            "💬 Chat — Ask questions about your codebase",
            "🔍 Debug — Analyze error logs",
            "📊 Dependency Analysis — Explore code dependencies",
            "🎨 Visual Architecture — Generate 2D workflow",
        ],
        pointer=">",
        style=custom_style,
    ).ask()

    if not mode_display:
        return

    mode_map = {
        "💬 Chat — Ask questions about your codebase": "chat",
        "🔍 Debug — Analyze error logs": "debug",
        "📊 Dependency Analysis — Explore code dependencies": "deps",
        "🎨 Visual Architecture — Generate 2D workflow": "architecture"
    }
    mode = mode_map[mode_display]

    # 2. Select Model Type
    type_display = questionary.select(
        "Select Model Type:",
        choices=[
            "🏠 Local (Ollama)",
            "☁️  API (Cloud)",
        ],
        pointer=">",
        style=custom_style,
    ).ask()

    if not type_display:
        return

    model_preference = "auto"

    if "Local" in type_display:
        # Local — fetch models dynamically
        console.print("\n[dim]Fetching installed Ollama models...[/]")
        models = _run_async(_get_ollama_models())

        if not models:
            console.print(
                "[bold yellow]⚠ No Ollama models found.[/] "
                "Make sure Ollama is running.\n"
                "Falling back to [cyan]auto[/] mode."
            )
            model_preference = "auto"
        else:
            selected_model = questionary.select(
                "Choose Local Model:",
                choices=models,
                pointer=">",
                style=custom_style,
            ).ask()

            if not selected_model:
                return

            model_preference = "local"
            console.print(f"\n[green]✓ Using local model:[/] {selected_model}")

    elif "API" in type_display:
        # API — choose provider
        api_display = questionary.select(
            "Select API Provider:",
            choices=[
                "⚡ Groq (Fast inference)",
                "🧠 Gemini (Deep reasoning)",
            ],
            pointer=">",
            style=custom_style,
        ).ask()

        if not api_display:
            return

        model_preference = "groq" if "Groq" in api_display else "gemini"
        console.print(f"\n[green]✓ Using:[/] {model_preference}")

    console.print()

    # 3. Enter mode-specific loop
    if mode == "chat":
        _chat_mode(model_preference)
    elif mode == "debug":
        _debug_mode(model_preference)
    elif mode == "deps":
        _deps_mode(model_preference)
    elif mode == "architecture":
        _architecture_mode(model_preference)


def _architecture_mode(model_preference: str):
    """Visual Architecture mode — generate 2D workflow."""
    console.print(Panel(
        "[bold cyan]🎨 Architecture Mode[/] — Generate 2D workflow diagram\n"
        "Analyzes codebase structure and generates a Mermaid diagram.\n"
        "Type [cyan]quit[/] to stop.",
        border_style="cyan",
    ))

    while True:
        try:
            with console.status("[bold green]Analyzing semantic architecture...", spinner="dots"):
                result = _run_async(
                    _api_call("POST", "/graph/workflow", json={
                        "directory": ".",  # Backend will fallback to last indexed dir
                    })
                )

            if "error" in result:
                console.print(f"[bold red]Error:[/] {result['error']}")
                break

            mermaid_str = result.get("mermaid", "graph TD\n    A[Empty Diagram]")
            _display_semantic_workflow(mermaid_str, "Indexed Codebase")
            
            break # Run once and return to menu

        except httpx.ConnectError:
            console.print(
                f"[bold red]Error:[/] Cannot connect to backend at {API_BASE}"
            )
        except Exception as exc:
            console.print(f"[bold red]Error:[/] {exc}")


def _display_semantic_workflow(mermaid_str: str, path: str):
    """Display the semantic Mermaid diagram."""
    console.print(f"\n[bold cyan]📊 Semantic Architecture Workflow for:[/] {path}\n")
    
    console.print("\n[bold]Mermaid Diagram (2D Semantic Flow):[/]")
    console.print(Panel(
        mermaid_str,
        title="Copy into Mermaid Live Editor or VS Code extension",
        subtitle="[dim]https://mermaid.live/[/]",
        border_style="cyan"
    ))
    
    console.print("\n[green]✅ Generated semantic 2D workflow based on codebase logic.[/]")


def _chat_mode(model_preference: str):
    """Interactive chat loop."""
    console.print(Panel(
        "[bold green]💬 Chat Mode[/] — Ask questions about your codebase\n"
        "Type [cyan]quit[/] or [cyan]exit[/] to stop.",
        border_style="green",
    ))

    while True:
        try:
            query = Prompt.ask("\n[bold cyan]You[/]")
        except (KeyboardInterrupt, EOFError):
            break

        if query.strip().lower() in ("quit", "exit", "q"):
            console.print("[dim]Goodbye! 👋[/]")
            break

        if not query.strip():
            continue

        try:
            with console.status("[bold green]Thinking...", spinner="dots"):
                result = _run_async(
                    _api_call("POST", "/chat", json={
                        "query": query,
                        "model": model_preference,
                        "mode": "chat",
                    })
                )
            _display_response(result)
        except httpx.ConnectError:
            console.print(
                f"[bold red]Error:[/] Cannot connect to backend at {API_BASE}"
            )
        except httpx.HTTPStatusError as exc:
            detail = exc.response.json().get("detail", str(exc)) if exc.response else str(exc)
            console.print(f"[bold red]Error:[/] {detail}")
        except Exception as exc:
            console.print(f"[bold red]Error:[/] {exc}")


def _debug_mode(model_preference: str):
    """Debug mode — analyze error logs."""
    console.print(Panel(
        "[bold red]🔍 Debug Mode[/] — Analyze error logs\n"
        "Type [cyan]quit[/] to stop.",
        border_style="red",
    ))

    while True:
        log_path = Prompt.ask(
            "\n[bold yellow]Enter log file path[/] (or 'quit')"
        )

        if log_path.strip().lower() in ("quit", "exit", "q"):
            console.print("[dim]Goodbye! 👋[/]")
            break

        path = Path(log_path.strip())
        if not path.exists():
            console.print(f"[bold red]Error:[/] File not found: {log_path}")
            continue

        content = path.read_text(encoding="utf-8", errors="ignore")
        console.print(f"\n[bold yellow]🔍 Analyzing:[/] {log_path} ({len(content)} bytes)\n")

        try:
            with console.status("[bold green]Analyzing errors...", spinner="dots"):
                result = _run_async(
                    _api_call("POST", "/debug", json={
                        "log_content": content,
                        "model": model_preference,
                    })
                )

            # Display root cause analysis
            answer = result.get("answer", "No analysis available")
            model_used = result.get("model_used", "unknown")
            parsed_errors = result.get("parsed_errors", 0)
            error_types = result.get("error_types", [])

            console.print(Panel(
                Markdown(answer),
                title=f"[bold red]Root Cause Analysis[/] — {model_used}",
                subtitle=f"Errors found: {parsed_errors} │ Types: {', '.join(error_types) if error_types else 'N/A'}",
                border_style="red",
            ))
        except httpx.ConnectError:
            console.print(
                f"[bold red]Error:[/] Cannot connect to backend at {API_BASE}"
            )
        except Exception as exc:
            console.print(f"[bold red]Error:[/] {exc}")


def _deps_mode(model_preference: str):
    """Dependency analysis mode."""
    console.print(Panel(
        "[bold magenta]📊 Dependency Mode[/] — Analyze code dependencies\n"
        "Enter a file path to parse, or ask impact queries.\n"
        "Type [cyan]quit[/] to stop.",
        border_style="magenta",
    ))

    while True:
        query = Prompt.ask(
            "\n[bold magenta]Enter file path or impact query[/] (or 'quit')"
        )

        if query.strip().lower() in ("quit", "exit", "q"):
            console.print("[dim]Goodbye! 👋[/]")
            break

        if not query.strip():
            continue

        # Check if it looks like a file path
        is_file = Path(query.strip()).exists() and Path(query.strip()).is_file()

        try:
            if is_file:
                with console.status("[bold green]Parsing dependencies...", spinner="dots"):
                    result = _run_async(
                        _api_call("POST", "/deps", json={
                            "file_path": str(Path(query.strip()).resolve()),
                            "model": model_preference,
                        })
                    )

                # Display parsed info
                if "error" in result:
                    console.print(f"[bold red]Parse error:[/] {result['error']}")
                    continue

                _display_dependency_info(result, query.strip())

            else:
                # Treat as impact query
                with console.status("[bold green]Analyzing impact...", spinner="dots"):
                    result = _run_async(
                        _api_call("POST", "/deps", json={
                            "query": query,
                            "model": model_preference,
                        })
                    )
                _display_response(result)

        except httpx.ConnectError:
            console.print(
                f"[bold red]Error:[/] Cannot connect to backend at {API_BASE}"
            )
        except Exception as exc:
            console.print(f"[bold red]Error:[/] {exc}")


def _display_dependency_info(info: dict, file_path: str):
    """Display parsed dependency information."""
    console.print(f"\n[bold magenta]📊 Dependencies for:[/] {file_path}\n")

    # Imports table
    imports = info.get("imports", [])
    from_imports = info.get("from_imports", [])

    if imports or from_imports:
        table = Table(title="Imports", border_style="cyan")
        table.add_column("Type", style="dim")
        table.add_column("Module", style="cyan")
        table.add_column("Name", style="green")
        table.add_column("Line", justify="right")

        for imp in imports:
            table.add_row("import", imp.get("module", ""), "", str(imp.get("line", "")))
        for imp in from_imports:
            table.add_row("from", imp.get("module", ""), imp.get("name", ""), str(imp.get("line", "")))

        console.print(table)

    # Classes
    classes = info.get("classes", [])
    if classes:
        cls_table = Table(title="Classes", border_style="yellow")
        cls_table.add_column("Class", style="yellow bold")
        cls_table.add_column("Bases", style="dim")
        cls_table.add_column("Methods", justify="right")
        cls_table.add_column("Line", justify="right")

        for cls in classes:
            cls_table.add_row(
                cls.get("name", ""),
                ", ".join(cls.get("bases", [])) or "—",
                str(len(cls.get("methods", []))),
                str(cls.get("line", "")),
            )
        console.print(cls_table)

    # Functions
    functions = info.get("functions", [])
    if functions:
        fn_table = Table(title="Functions", border_style="green")
        fn_table.add_column("Function", style="green bold")
        fn_table.add_column("Args", style="dim")
        fn_table.add_column("Async", justify="center")
        fn_table.add_column("Line", justify="right")

        for fn in functions:
            fn_table.add_row(
                fn.get("name", ""),
                ", ".join(fn.get("args", [])) or "—",
                "✓" if fn.get("is_async") else "",
                str(fn.get("line", "")),
            )
        console.print(fn_table)

# ── web ────────────────────────────────────────────────────────────

@app.command()
def web():
    """Open the Intelligent Codebase Assistant Web UI in your browser."""
    console.print(f"\n[bold green]🌐 Opening Web UI:[/] {API_BASE}\n")
    webbrowser.open(API_BASE)


# ── stop ───────────────────────────────────────────────────────────

@app.command()
def stop():
    """Shutdown the Intelligent Codebase Assistant server."""
    console.print("\n[bold yellow]🛑 Stopping Codebase Assistant server...[/]")
    try:
        result = _run_async(_api_call("POST", "/shutdown"))
        console.print(f"[green]✓ {result.get('message', 'Stopping...')}[/]")
    except httpx.ConnectError:
        console.print("[dim]Server is already stopped.[/]")
    except Exception as exc:
        # Check if it's a 503 or 500 because the server is closing
        if "503" in str(exc) or "Read error" in str(exc) or "RemoteProtocolError" in str(exc):
             console.print("[green]✓ Stopped.[/]")
        else:
             console.print(f"[bold red]Error:[/] {exc}")


# ── health ─────────────────────────────────────────────────────────


@app.command()
def health():
    """Check the health of all services."""
    console.print("\n[bold]🏥 Health Check\n")

    try:
        result = _run_async(_api_call("GET", "/health"))
    except httpx.ConnectError:
        console.print(f"[bold red]Error:[/] Cannot connect to backend at {API_BASE}")
        console.print("Start the server with: [cyan]python -m services.api_gateway.main[/]")
        raise typer.Exit(1)

    table = Table(border_style="blue")
    table.add_column("Service", style="bold")
    table.add_column("Status")
    table.add_column("Details", style="dim")

    providers = result.get("providers", {})

    # Ollama
    ollama_status = providers.get("ollama", "unknown")
    table.add_row(
        "Ollama (Local)",
        "[green]✅ Available[/]" if ollama_status == "available" else "[red]❌ Unavailable[/]",
        "",
    )

    # Groq
    groq_status = providers.get("groq", "unknown")
    table.add_row(
        "Groq (Cloud)",
        "[green]✅ Configured[/]" if groq_status == "configured" else "[yellow]⚠ Not configured[/]",
        "",
    )

    # Gemini
    gemini_status = providers.get("gemini", "unknown")
    table.add_row(
        "Gemini (Cloud)",
        "[green]✅ Configured[/]" if gemini_status == "configured" else "[yellow]⚠ Not configured[/]",
        "",
    )

    # RAG
    rag = result.get("rag", {})
    table.add_row(
        "RAG (ChromaDB)",
        "[green]✅ Indexed[/]" if rag.get("indexed") else "[yellow]⚠ Not indexed[/]",
        f"{rag.get('total_chunks', 0)} chunks",
    )

    console.print(table)
    console.print()


# ── Entry point ────────────────────────────────────────────────────

def main():
    app()


if __name__ == "__main__":
    main()
