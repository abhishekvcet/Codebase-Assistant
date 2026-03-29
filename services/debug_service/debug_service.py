"""
Debug Service — Error log parsing, pattern extraction, and root cause analysis.

Capabilities:
  • Parse log files (Python tracebacks, generic error patterns)
  • Extract error signatures
  • Use RAG context + LLM for root cause analysis
"""

import re
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ── Error Pattern Definitions ──────────────────────────────────────

PYTHON_TRACEBACK = re.compile(
    r'Traceback \(most recent call last\):.*?(?=\n\S|\Z)',
    re.DOTALL,
)

GENERIC_ERROR = re.compile(
    r'^.*(?:Error|Exception|FATAL|CRITICAL|Panic|FAIL).*$',
    re.MULTILINE | re.IGNORECASE,
)

STACK_TRACE_JAVA = re.compile(
    r'(?:Exception|Error).*?\n(?:\s+at\s+.*\n)+',
    re.MULTILINE,
)

JS_ERROR = re.compile(
    r'(?:TypeError|ReferenceError|SyntaxError|RangeError|URIError):\s*.+',
    re.MULTILINE,
)


# ── Log Parsing ────────────────────────────────────────────────────

def parse_log_file(file_path: str) -> dict:
    """Parse a log/error file and extract structured error information."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Log file not found: {file_path}")

    content = path.read_text(encoding="utf-8", errors="ignore")
    return parse_log_content(content, source=file_path)


def parse_log_content(content: str, source: str = "input") -> dict:
    """Parse raw log text and extract errors."""
    errors = []

    # Python tracebacks
    for match in PYTHON_TRACEBACK.finditer(content):
        errors.append({
            "type": "python_traceback",
            "text": match.group().strip(),
            "source": source,
        })

    # Java stack traces
    for match in STACK_TRACE_JAVA.finditer(content):
        errors.append({
            "type": "java_stacktrace",
            "text": match.group().strip(),
            "source": source,
        })

    # JavaScript errors
    for match in JS_ERROR.finditer(content):
        errors.append({
            "type": "js_error",
            "text": match.group().strip(),
            "source": source,
        })

    # Generic error lines (dedup against already-captured text)
    captured_text = {e["text"] for e in errors}
    for match in GENERIC_ERROR.finditer(content):
        line = match.group().strip()
        if line and line not in captured_text and len(line) > 10:
            errors.append({
                "type": "generic_error",
                "text": line,
                "source": source,
            })
            captured_text.add(line)

    return {
        "source": source,
        "total_lines": content.count("\n") + 1,
        "errors_found": len(errors),
        "errors": errors,
    }


# ── Error Summarization ───────────────────────────────────────────

def summarize_errors(parsed: dict) -> str:
    """Create a concise summary of parsed errors for LLM context."""
    if not parsed["errors"]:
        return "No errors were found in the provided log content."

    summary_parts = [
        f"Found {parsed['errors_found']} error(s) in {parsed['source']}:\n"
    ]

    for i, err in enumerate(parsed["errors"][:10], 1):  # Cap at 10
        summary_parts.append(f"### Error {i} ({err['type']})\n```\n{err['text'][:500]}\n```\n")

    return "\n".join(summary_parts)


# ── Root Cause Analysis via LLM ───────────────────────────────────

async def analyze_errors(
    log_content: str,
    orchestrator,
    model_preference: str = "groq",
    additional_context: str = "",
) -> dict:
    """
    Full debug pipeline:
      1. Parse log content for errors
      2. Compose analysis prompt
      3. Call LLM for root cause analysis
    """
    parsed = parse_log_content(log_content)
    error_summary = summarize_errors(parsed)

    system_prompt = (
        "You are a senior software engineer specializing in debugging and root cause analysis. "
        "Analyze the errors provided and give:\n"
        "1. A clear summary of each error\n"
        "2. The most likely root cause\n"
        "3. Step-by-step fix recommendations\n"
        "4. Prevention strategies\n"
        "Be specific and reference the actual error messages and stack traces."
    )

    prompt = f"## Error Report\n\n{error_summary}"

    if additional_context:
        prompt += f"\n\n## Additional Context\n\n{additional_context}"

    prompt += (
        "\n\n## Instructions\n\n"
        "Provide a thorough root cause analysis with actionable fix recommendations."
    )

    response = await orchestrator.generate_response(
        prompt,
        model_preference=model_preference,
        system_prompt=system_prompt,
    )

    response["parsed_errors"] = parsed["errors_found"]
    response["error_types"] = list({e["type"] for e in parsed["errors"]})
    return response
