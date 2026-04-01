"""
Graph Service — AST-based dependency extraction and Neo4j graph storage.

Capabilities:
  • Parse Python files via AST to extract imports, classes, functions
  • Build a dependency graph
  • Store and query relationships in Neo4j
"""

import ast
import os
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ── AST Parsing ────────────────────────────────────────────────────

def parse_python_file(file_path: str) -> dict:
    """Extract structural information from a Python file using AST."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    source = path.read_text(encoding="utf-8", errors="ignore")

    try:
        tree = ast.parse(source, filename=file_path)
    except SyntaxError as exc:
        logger.warning("Syntax error in %s: %s", file_path, exc)
        return {"file": file_path, "error": str(exc)}

    info = {
        "file": file_path,
        "module": path.stem,
        "imports": [],
        "from_imports": [],
        "classes": [],
        "functions": [],
        "global_variables": [],
    }

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                info["imports"].append({
                    "module": alias.name,
                    "alias": alias.asname,
                    "line": node.lineno,
                })

        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                info["from_imports"].append({
                    "module": node.module or "",
                    "name": alias.name,
                    "alias": alias.asname,
                    "line": node.lineno,
                })

        elif isinstance(node, ast.ClassDef):
            methods = [
                {
                    "name": item.name,
                    "args": [a.arg for a in item.args.args if a.arg != "self"],
                    "line": item.lineno,
                    "decorators": [_decorator_name(d) for d in item.decorator_list],
                }
                for item in node.body
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
            ]
            bases = [_node_name(b) for b in node.bases]
            info["classes"].append({
                "name": node.name,
                "bases": bases,
                "methods": methods,
                "line": node.lineno,
                "decorators": [_decorator_name(d) for d in node.decorator_list],
            })

        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Only top-level functions (not methods)
            if isinstance(getattr(node, '_parent', None), ast.Module) or not hasattr(node, '_parent'):
                info["functions"].append({
                    "name": node.name,
                    "args": [a.arg for a in node.args.args],
                    "line": node.lineno,
                    "is_async": isinstance(node, ast.AsyncFunctionDef),
                    "decorators": [_decorator_name(d) for d in node.decorator_list],
                })

    # Set parent references for top-level detection
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            child._parent = node

    # Reparse for accurate top-level functions
    info["functions"] = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            info["functions"].append({
                "name": node.name,
                "args": [a.arg for a in node.args.args],
                "line": node.lineno,
                "is_async": isinstance(node, ast.AsyncFunctionDef),
                "decorators": [_decorator_name(d) for d in node.decorator_list],
            })

    return info


def _decorator_name(node) -> str:
    if isinstance(node, ast.Name):
        return node.id
    elif isinstance(node, ast.Attribute):
        return f"{_node_name(node.value)}.{node.attr}"
    elif isinstance(node, ast.Call):
        return _decorator_name(node.func)
    return str(ast.dump(node))


def _node_name(node) -> str:
    if isinstance(node, ast.Name):
        return node.id
    elif isinstance(node, ast.Attribute):
        return f"{_node_name(node.value)}.{node.attr}"
    return str(ast.dump(node))


def parse_directory(directory: str) -> list[dict]:
    """Parse all Python files in a directory tree."""
    results = []
    skip_dirs = {".git", "__pycache__", "node_modules", ".venv", "venv", "dist", "build"}

    for root, dirs, files in os.walk(directory):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for f in files:
            if f.endswith(".py"):
                fpath = os.path.join(root, f)
                results.append(parse_python_file(fpath))

    logger.info("Parsed %d Python files in %s", len(results), directory)
    return results


# ── Dependency Graph (in-memory) ───────────────────────────────────

def build_dependency_graph(parsed_files: list[dict]) -> dict:
    """Build an in-memory dependency graph from parsed file data."""
    nodes = []
    edges = []

    module_map = {}  # module_name → file_path

    for pf in parsed_files:
        if "error" in pf:
            continue
        fpath = pf["file"]
        module = pf["module"]
        module_map[module] = fpath

        nodes.append({
            "id": fpath,
            "label": module,
            "type": "module",
            "classes": len(pf.get("classes", [])),
            "functions": len(pf.get("functions", [])),
        })

    for pf in parsed_files:
        if "error" in pf:
            continue
        source = pf["file"]

        for imp in pf.get("imports", []):
            target = module_map.get(imp["module"])
            if target:
                edges.append({
                    "source": source,
                    "target": target,
                    "type": "imports",
                    "module": imp["module"],
                })

        for imp in pf.get("from_imports", []):
            target = module_map.get(imp["module"])
            if target:
                edges.append({
                    "source": source,
                    "target": target,
                    "type": "from_import",
                    "module": imp["module"],
                    "name": imp["name"],
                })

    return {
        "nodes": nodes,
        "edges": edges,
        "total_modules": len(nodes),
        "total_dependencies": len(edges),
    }


# ── Neo4j Integration ─────────────────────────────────────────────

class Neo4jGraphStore:
    """Store and query the dependency graph in Neo4j."""

    def __init__(self, uri: str, user: str, password: str):
        self.uri = uri
        self.user = user
        self.password = password
        self._driver = None

    def _get_driver(self):
        if self._driver is None:
            from neo4j import GraphDatabase
            self._driver = GraphDatabase.driver(
                self.uri, auth=(self.user, self.password)
            )
        return self._driver

    def close(self):
        if self._driver:
            self._driver.close()
            self._driver = None

    def ingest_graph(self, graph: dict) -> dict:
        """Store the dependency graph in Neo4j."""
        driver = self._get_driver()

        with driver.session() as session:
            # Clear existing data
            session.run("MATCH (n:Module) DETACH DELETE n")

            # Create nodes
            for node in graph["nodes"]:
                session.run(
                    "CREATE (m:Module {id: $id, label: $label, classes: $classes, functions: $functions})",
                    **node,
                )

            # Create edges
            for edge in graph["edges"]:
                session.run(
                    "MATCH (a:Module {id: $source}), (b:Module {id: $target}) "
                    "CREATE (a)-[:DEPENDS_ON {type: $type, module: $module}]->(b)",
                    source=edge["source"],
                    target=edge["target"],
                    type=edge["type"],
                    module=edge["module"],
                )

        return {
            "status": "ingested",
            "nodes": len(graph["nodes"]),
            "edges": len(graph["edges"]),
        }

    def query_dependencies(self, module_id: str) -> dict:
        """Query what a module depends on and what depends on it."""
        driver = self._get_driver()

        with driver.session() as session:
            depends_on = session.run(
                "MATCH (m:Module {id: $id})-[:DEPENDS_ON]->(dep) RETURN dep.label as label, dep.id as id",
                id=module_id,
            ).data()

            depended_by = session.run(
                "MATCH (dep)-[:DEPENDS_ON]->(m:Module {id: $id}) RETURN dep.label as label, dep.id as id",
                id=module_id,
            ).data()

        return {
            "module": module_id,
            "depends_on": depends_on,
            "depended_by": depended_by,
        }

    def get_full_graph(self) -> dict:
        """Return the complete graph for visualization."""
        driver = self._get_driver()

        with driver.session() as session:
            nodes = session.run(
                "MATCH (m:Module) RETURN m.id as id, m.label as label, "
                "m.classes as classes, m.functions as functions"
            ).data()

            edges = session.run(
                "MATCH (a:Module)-[r:DEPENDS_ON]->(b:Module) "
                "RETURN a.id as source, b.id as target, r.type as type, r.module as module"
            ).data()

        return {"nodes": nodes, "edges": edges}


# ── Semantic Workflow (LLM-based) ──────────────────────────────────

async def generate_semantic_workflow(directory: str, orchestrator) -> str:
    """Generate a high-level architectural workflow using LLM analysis."""
    # 1. Get structural summary of the codebase
    parsed_files = parse_directory(directory)
    
    summary_parts = []
    for pf in parsed_files:
        if "error" in pf: continue
        fpath = pf["file"]
        module = pf["module"]
        classes = [c["name"] for c in pf.get("classes", [])]
        functions = [f["name"] for f in pf.get("functions", [])]
        
        summary_parts.append(f"Module: {module} ({fpath})")
        if classes: summary_parts.append(f"  Classes: {', '.join(classes)}")
        if functions: summary_parts.append(f"  Functions: {', '.join(functions)}")
        summary_parts.append("")

    code_summary = "\n".join(summary_parts[:50]) # Cap it to avoid context overflow

    # 2. Prompt LLM to generate Mermaid
    prompt = f"""
You are an expert system architect and visual designer. Analyze the following codebase structure and generate a HIGH-LEVEL 2D structural workflow using Mermaid (graph TD).

STYLE RULES:
1. Use distinct shapes for different components:
   - Use HEXAGONS {{{{node}}}} for entry points / API controllers.
   - Use ROUNDED (node) for core logic services.
   - Use CIRCLES ((node)) for background processes or LLM.
   - Use CYLINDERS [(node)] for databases (ChromaDB/Neo4j).
   - Use DIAMONDS {{node}} for conditional logic or routers.
2. Use EMOJIS in every label for a premium look (e.g., 🌐 API, 🧠 LLM, 📁 DB, ⚙️ Logic).
3. Group related modules into 'subgraph' blocks.
4. Keep relationships (edges) clear with labels (e.g., -->|Queries|).
5. Output ONLY the Mermaid code block starting with 'graph TD'.

Codebase Structure:
{code_summary}

Example of desired style:
graph TD
    User((👤 User)) -->|Requests| API{{{{🌐 API Gateway}}}}
    API -->|Search| RAG(📂 RAG Service)
    RAG -->|Fetch| DB[(📁 ChromaDB)]
    ... etc.
"""

    result = await orchestrator.generate_response(
        query=prompt,
        model_preference="auto",
        system_prompt="You are a system architecture visualizer that outputs Mermaid diagrams."
    )
    
    mermaid_text = result.get("answer", "")
    
    # 1. Try backticks first
    if "```mermaid" in mermaid_text:
        mermaid_text = mermaid_text.split("```mermaid")[1].split("```")[0]
    elif "```" in mermaid_text:
        mermaid_text = mermaid_text.split("```")[1].split("```")[0]
    
    # 2. If still has conversational text, find the 'graph' keyword
    if "graph TD" in mermaid_text or "graph LR" in mermaid_text:
        # Split at the first occurrence of graph and take everything after
        # But we also need to avoid text AFTER the diagram
        keyword = "graph TD" if "graph TD" in mermaid_text else "graph LR"
        parts = mermaid_text.split(keyword)
        # Take the keyword + the content
        content = parts[1]
        
        # Try to find where it ends (usually at a blank line or triple backticks)
        # For now, just take until the end but strip trailing filler if we can
        mermaid_text = keyword + content

    return mermaid_text.strip()
