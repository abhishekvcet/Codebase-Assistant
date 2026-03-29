"""
Intelligent Codebase Assistant — CLI Tool

Commands:
  code-assist ask    "question"    --model local|groq|gemini|auto
  code-assist debug  error.log     --model groq
  code-assist deps   file.py
  code-assist index  ./src
  code-assist health
"""

import sys
import asyncio
import time
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.table import Table
from rich import print as rprint

# Ensure project root on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

app = typer.Typer(
    name="code-assist",
    help="🧠 Intelligent Codebase Assistant — AI-powered code understanding",
    add_completion=False,
    rich_markup_mode="rich",
)
console = Console()


def _run_async(coro):
    """Run an async coroutine from sync CLI context."""
    return asyncio.get_event_loop().run_until_complete(coro)


def _get_orchestrator():
    from shared.llm.orchestrator import LLMOrchestrator
    return LLMOrchestrator()


# ── ask ────────────────────────────────────────────────────────────

@app.command()
def ask(
    query: str = typer.Argument(..., help="Your question about the codebase"),
    model: str = typer.Option("auto", "--model", "-m", help="Model: auto | local | groq | gemini"),
    temperature: float = typer.Option(0.7, "--temp", "-t", help="Temperature (0.0 – 2.0)"),
    max_tokens: int = typer.Option(2048, "--max-tokens", help="Maximum response tokens"),
):
    """Ask a question about your codebase."""
    console.print(f"\n[bold cyan]🧠 Asking ({model}):[/] {query}\n")

    orchestrator = _get_orchestrator()

    with console.status("[bold green]Thinking...", spinner="dots"):
        start = time.perf_counter()
        result = _run_async(
            orchestrator.generate_response(
                query=query,
                model_preference=model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        )
        total_ms = round((time.perf_counter() - start) * 1000)

    # Display result
    console.print(Panel(
        Markdown(result["answer"]),
        title=f"[bold green]Response[/] — {result['model_used']} ({result['provider']})",
        subtitle=f"⏱ {result['latency_ms']:.0f}ms | Fallback: {'Yes' if result['fallback_used'] else 'No'}",
        border_style="green",
    ))


# ── debug ──────────────────────────────────────────────────────────

@app.command()
def debug(
    log_file: str = typer.Argument(..., help="Path to error log file"),
    model: str = typer.Option("groq", "--model", "-m", help="Model: auto | local | groq | gemini"),
    context: str = typer.Option("", "--context", "-c", help="Additional context"),
):
    """Analyze an error log for root cause."""
    path = Path(log_file)
    if not path.exists():
        console.print(f"[bold red]Error:[/] File not found: {log_file}")
        raise typer.Exit(1)

    content = path.read_text(encoding="utf-8", errors="ignore")
    console.print(f"\n[bold yellow]🔍 Analyzing:[/] {log_file} ({len(content)} bytes)\n")

    from services.debug_service import debug_service as dbg

    orchestrator = _get_orchestrator()

    with console.status("[bold green]Analyzing errors...", spinner="dots"):
        result = _run_async(
            dbg.analyze_errors(
                log_content=content,
                orchestrator=orchestrator,
                model_preference=model,
                additional_context=context,
            )
        )

    console.print(Panel(
        Markdown(result["answer"]),
        title=f"[bold red]Root Cause Analysis[/] — {result['model_used']}",
        subtitle=f"⏱ {result['latency_ms']:.0f}ms | Errors found: {result.get('parsed_errors', '?')}",
        border_style="red",
    ))


# ── deps ───────────────────────────────────────────────────────────

@app.command()
def deps(
    file_path: str = typer.Argument(..., help="Python file to analyze dependencies for"),
):
    """Show dependencies for a Python file."""
    path = Path(file_path)
    if not path.exists():
        console.print(f"[bold red]Error:[/] File not found: {file_path}")
        raise typer.Exit(1)

    from services.graph_service import graph_service as gs

    console.print(f"\n[bold magenta]📊 Parsing:[/] {file_path}\n")

    info = gs.parse_python_file(str(path.resolve()))

    if "error" in info:
        console.print(f"[bold red]Parse error:[/] {info['error']}")
        raise typer.Exit(1)

    # Imports table
    table = Table(title="Imports", border_style="cyan")
    table.add_column("Type", style="dim")
    table.add_column("Module", style="cyan")
    table.add_column("Name", style="green")
    table.add_column("Line", justify="right")

    for imp in info.get("imports", []):
        table.add_row("import", imp["module"], "", str(imp["line"]))
    for imp in info.get("from_imports", []):
        table.add_row("from", imp["module"], imp["name"], str(imp["line"]))

    console.print(table)

    # Classes
    if info.get("classes"):
        cls_table = Table(title="Classes", border_style="yellow")
        cls_table.add_column("Class", style="yellow bold")
        cls_table.add_column("Bases", style="dim")
        cls_table.add_column("Methods", justify="right")
        cls_table.add_column("Line", justify="right")

        for cls in info["classes"]:
            cls_table.add_row(
                cls["name"],
                ", ".join(cls["bases"]) or "—",
                str(len(cls["methods"])),
                str(cls["line"]),
            )
        console.print(cls_table)

    # Functions
    if info.get("functions"):
        fn_table = Table(title="Functions", border_style="green")
        fn_table.add_column("Function", style="green bold")
        fn_table.add_column("Args", style="dim")
        fn_table.add_column("Async", justify="center")
        fn_table.add_column("Line", justify="right")

        for fn in info["functions"]:
            fn_table.add_row(
                fn["name"],
                ", ".join(fn["args"]) or "—",
                "✓" if fn["is_async"] else "",
                str(fn["line"]),
            )
        console.print(fn_table)

    console.print()


# ── index ──────────────────────────────────────────────────────────

@app.command()
def index(
    directory: str = typer.Argument(".", help="Directory to index for RAG"),
):
    """Index a codebase directory for RAG-powered queries."""
    dir_path = Path(directory).resolve()
    if not dir_path.is_dir():
        console.print(f"[bold red]Error:[/] Not a directory: {directory}")
        raise typer.Exit(1)

    from services.rag_service import rag_service as rag

    console.print(f"\n[bold blue]📁 Indexing:[/] {dir_path}\n")

    with console.status("[bold green]Chunking and embedding...", spinner="dots"):
        chunks = rag.chunk_directory(str(dir_path))
        if not chunks:
            console.print("[bold yellow]No supported files found.[/]")
            raise typer.Exit(0)
        rag.build_index(chunks)

    status = rag.index_status()
    console.print(Panel(
        f"[green]✅ Indexed {status['total_chunks']} chunks "
        f"({status['total_vectors']} vectors)[/]",
        title="RAG Index Ready",
        border_style="blue",
    ))


# ── health ─────────────────────────────────────────────────────────

@app.command()
def health():
    """Check the health of all LLM providers."""
    console.print("\n[bold]🏥 Health Check\n")

    orchestrator = _get_orchestrator()

    table = Table(border_style="blue")
    table.add_column("Provider", style="bold")
    table.add_column("Status")
    table.add_column("Details", style="dim")

    # Ollama
    ollama_ok = _run_async(orchestrator.ollama.is_available())
    models = _run_async(orchestrator.ollama.list_models()) if ollama_ok else []
    table.add_row(
        "Ollama (Local)",
        "[green]✅ Available[/]" if ollama_ok else "[red]❌ Unavailable[/]",
        ", ".join(models[:5]) if models else "No models",
    )

    # Groq
    from shared.config import settings
    table.add_row(
        "Groq (Cloud)",
        "[green]✅ Configured[/]" if settings.GROQ_API_KEY else "[yellow]⚠ No API key[/]",
        f"Model: {settings.GROQ_MODEL}",
    )

    # Gemini
    table.add_row(
        "Gemini (Cloud)",
        "[green]✅ Configured[/]" if settings.GEMINI_API_KEY else "[yellow]⚠ No API key[/]",
        f"Model: {settings.GEMINI_MODEL}",
    )

    console.print(table)
    console.print()


# ── Entry point ────────────────────────────────────────────────────

def main():
    app()


if __name__ == "__main__":
    main()
