#!/usr/bin/env python3
"""
Stdio MCP Server Example
Esempio completo di server stdio con tools di test.

Run:
    python example_stdio_server.py

Test (in altra shell):
    echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05"}}' | python example_stdio_server.py
    echo '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' | python example_stdio_server.py
    echo '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"calculate","arguments":{"a":10,"b":5,"operation":"multiply"}}}' | python example_stdio_server.py
"""

from polymcp import expose_tools_stdio
from typing import List, Dict, Any
import sys


# ============================================================================
# TOOLS DI ESEMPIO
# ============================================================================

def calculate(a: float, b: float, operation: str = "add") -> Dict[str, Any]:
    """
    Esegue operazioni matematiche.
    
    Args:
        a: Primo numero
        b: Secondo numero
        operation: Operazione (add, subtract, multiply, divide)
    
    Returns:
        Risultato con dettagli operazione
    """
    operations = {
        "add": a + b,
        "subtract": a - b,
        "multiply": a * b,
        "divide": a / b if b != 0 else float('inf')
    }
    
    if operation not in operations:
        raise ValueError(f"Operazione non valida: {operation}")
    
    result = operations[operation]
    
    return {
        "operation": operation,
        "a": a,
        "b": b,
        "result": result,
        "formula": f"{a} {operation} {b} = {result}"
    }


def analyze_text(text: str) -> Dict[str, Any]:
    """
    Analizza un testo e ritorna statistiche.
    
    Args:
        text: Testo da analizzare
    
    Returns:
        Statistiche del testo
    """
    words = text.split()
    sentences = text.split('.')
    
    return {
        "characters": len(text),
        "words": len(words),
        "unique_words": len(set(words)),
        "sentences": len(sentences),
        "avg_word_length": sum(len(w) for w in words) / len(words) if words else 0,
        "longest_word": max(words, key=len) if words else ""
    }


def generate_fibonacci(n: int) -> List[int]:
    """
    Genera sequenza di Fibonacci.
    
    Args:
        n: Numero di elementi (1-50)
    
    Returns:
        Lista con sequenza di Fibonacci
    """
    if n < 1 or n > 50:
        raise ValueError("n deve essere tra 1 e 50")
    
    if n == 1:
        return [0]
    if n == 2:
        return [0, 1]
    
    fib = [0, 1]
    for i in range(2, n):
        fib.append(fib[-1] + fib[-2])
    
    return fib


def format_data(data: list, format_type: str = "json") -> str:
    """
    Formatta dati in vari formati.
    
    Args:
        data: Lista di dizionari
        format_type: Formato (json, csv, table)
    
    Returns:
        Dati formattati
    """
    import json
    
    if format_type == "json":
        return json.dumps(data, indent=2)
    
    elif format_type == "csv":
        if not data:
            return ""
        headers = list(data[0].keys())
        lines = [",".join(headers)]
        for item in data:
            values = [str(item.get(h, "")) for h in headers]
            lines.append(",".join(values))
        return "\n".join(lines)
    
    elif format_type == "table":
        if not data:
            return ""
        headers = list(data[0].keys())
        lines = ["| " + " | ".join(headers) + " |"]
        lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
        for item in data:
            values = [str(item.get(h, "")) for h in headers]
            lines.append("| " + " | ".join(values) + " |")
        return "\n".join(lines)
    
    else:
        raise ValueError(f"Formato non valido: {format_type}")


# ============================================================================
# SERVER
# ============================================================================

def main():
    """Avvia il server stdio."""
    
    # Log su stderr (stdout è per JSON-RPC)
    print("=" * 60, file=sys.stderr)
    print("PolyMCP Stdio Server - Example", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    print("", file=sys.stderr)
    print("Tools disponibili:", file=sys.stderr)
    print("  • calculate - Operazioni matematiche", file=sys.stderr)
    print("  • analyze_text - Analisi testo", file=sys.stderr)
    print("  • generate_fibonacci - Sequenza Fibonacci", file=sys.stderr)
    print("  • format_data - Formattazione dati", file=sys.stderr)
    print("", file=sys.stderr)
    print("Server in ascolto su stdin/stdout...", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    print("", file=sys.stderr)
    
    # Crea e avvia server
    server = expose_tools_stdio(
        tools=[
            calculate,
            analyze_text,
            generate_fibonacci,
            format_data
        ],
        server_name="Example Stdio MCP Server",
        server_version="1.0.0",
        verbose=True  # Log dettagliati su stderr
    )
    
    # Run (blocca finché non viene fermato)
    server.run()


if __name__ == "__main__":
    main()
