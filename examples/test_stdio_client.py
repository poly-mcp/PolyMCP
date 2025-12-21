#!/usr/bin/env python3
"""
Stdio MCP Client Test
Script per testare il server stdio in modo interattivo.

Run:
    python test_stdio_client.py
"""

import subprocess
import json
import sys
import threading
import queue
from typing import Dict, Any, Optional


class StdioMCPClient:
    """Client persistente per testare server MCP stdio."""
    
    def __init__(self, server_command: str):
        """
        Inizializza client con connessione persistente.
        
        Args:
            server_command: Comando per avviare server (es: "python example_stdio_server.py")
        """
        self.server_command = server_command
        self.request_id = 0
        self.process: Optional[subprocess.Popen] = None
        self.response_queue = queue.Queue()
        self.reader_thread: Optional[threading.Thread] = None
    
    def start(self):
        """Avvia il server e la connessione."""
        print(f"\n🚀 Starting server: {self.server_command}")
        
        # Avvia processo server
        self.process = subprocess.Popen(
            self.server_command.split(),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1  # Line buffered
        )
        
        # Thread per leggere stderr (log del server)
        def read_stderr():
            """Leggi e mostra log del server."""
            for line in self.process.stderr:
                line = line.strip()
                if line:
                    print(f"   [SERVER] {line}", file=sys.stderr)
        
        stderr_thread = threading.Thread(target=read_stderr, daemon=True)
        stderr_thread.start()
        
        # Thread per leggere stdout (risposte JSON-RPC)
        def read_stdout():
            """Leggi risposte dal server."""
            for line in self.process.stdout:
                line = line.strip()
                if line:
                    try:
                        response = json.loads(line)
                        self.response_queue.put(response)
                    except json.JSONDecodeError as e:
                        print(f"   [ERROR] Invalid JSON: {e}", file=sys.stderr)
        
        self.reader_thread = threading.Thread(target=read_stdout, daemon=True)
        self.reader_thread.start()
        
        print("✅ Server started\n")
    
    def send_request(self, method: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Invia richiesta JSON-RPC al server.
        
        Args:
            method: Metodo MCP (es: "tools/list")
            params: Parametri opzionali
        
        Returns:
            Risposta del server
        """
        if not self.process:
            raise RuntimeError("Server not started. Call start() first.")
        
        self.request_id += 1
        
        request = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": method
        }
        
        if params:
            request["params"] = params
        
        # Converti in JSON
        request_json = json.dumps(request)
        
        print(f"\n📤 Sending: {method}")
        print(f"   Request: {request_json}")
        
        # Invia richiesta
        self.process.stdin.write(request_json + "\n")
        self.process.stdin.flush()
        
        # Aspetta risposta (con timeout)
        try:
            response = self.response_queue.get(timeout=5.0)
            print(f"\n📥 Response:")
            print(f"   {json.dumps(response, indent=2)}")
            return response
        except queue.Empty:
            raise TimeoutError(f"No response from server for {method}")
    
    def stop(self):
        """Ferma il server."""
        if self.process:
            print("\n🛑 Stopping server...")
            self.process.stdin.close()
            self.process.terminate()
            self.process.wait(timeout=3)
            print("✅ Server stopped")
    
    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop()


def test_stdio_server():
    """Test completo del server stdio."""
    
    print("=" * 80)
    print("STDIO MCP SERVER TEST")
    print("=" * 80)
    
    # Usa context manager per mantenere connessione persistente
    with StdioMCPClient("python example_stdio_server.py") as client:
        
        # Test 1: Initialize
        print("\n" + "=" * 80)
        print("TEST 1: Initialize")
        print("=" * 80)
        
        response = client.send_request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "clientInfo": {
                    "name": "test-client",
                    "version": "1.0.0"
                }
            }
        )
        
        assert "result" in response, "Initialize fallito"
        assert response["result"]["protocolVersion"] == "2024-11-05"
        print("✅ Initialize OK")
        
        # Test 2: List Tools
        print("\n" + "=" * 80)
        print("TEST 2: List Tools")
        print("=" * 80)
        
        response = client.send_request("tools/list")
        
        assert "result" in response, "List tools fallito"
        tools = response["result"]["tools"]
        print(f"\n✅ Found {len(tools)} tools:")
        for tool in tools:
            print(f"   • {tool['name']}: {tool['description']}")
        
        # Test 3: Call Tool - Calculate
        print("\n" + "=" * 80)
        print("TEST 3: Call Tool - calculate")
        print("=" * 80)
        
        response = client.send_request(
            "tools/call",
            {
                "name": "calculate",
                "arguments": {
                    "a": 15,
                    "b": 7,
                    "operation": "multiply"
                }
            }
        )
        
        assert "result" in response, "Call tool fallito"
        content = response["result"]["content"][0]["text"]
        print(f"\n✅ Result: {content}")
        
        # Test 4: Call Tool - Analyze Text
        print("\n" + "=" * 80)
        print("TEST 4: Call Tool - analyze_text")
        print("=" * 80)
        
        response = client.send_request(
            "tools/call",
            {
                "name": "analyze_text",
                "arguments": {
                    "text": "Hello world! This is a test message. Testing MCP stdio server."
                }
            }
        )
        
        assert "result" in response
        content = response["result"]["content"][0]["text"]
        print(f"\n✅ Result: {content}")
        
        # Test 5: Call Tool - Fibonacci
        print("\n" + "=" * 80)
        print("TEST 5: Call Tool - generate_fibonacci")
        print("=" * 80)
        
        response = client.send_request(
            "tools/call",
            {
                "name": "generate_fibonacci",
                "arguments": {
                    "n": 10
                }
            }
        )
        
        assert "result" in response
        content = response["result"]["content"][0]["text"]
        print(f"\n✅ Result: {content}")
        
        # Test 6: Call Tool - Format Data
        print("\n" + "=" * 80)
        print("TEST 6: Call Tool - format_data")
        print("=" * 80)
        
        response = client.send_request(
            "tools/call",
            {
                "name": "format_data",
                "arguments": {
                    "data": [
                        {"name": "Alice", "age": 30, "city": "NYC"},
                        {"name": "Bob", "age": 25, "city": "LA"}
                    ],
                    "format_type": "table"
                }
            }
        )
        
        assert "result" in response
        content = response["result"]["content"][0]["text"]
        print(f"\n✅ Result:\n{content}")
        
        # Test 7: Error Handling
        print("\n" + "=" * 80)
        print("TEST 7: Error Handling - Invalid Tool")
        print("=" * 80)
        
        response = client.send_request(
            "tools/call",
            {
                "name": "nonexistent_tool",
                "arguments": {}
            }
        )
        
        assert "error" in response
        print(f"\n✅ Error handled correctly: {response['error']['message']}")
        
        # Summary
        print("\n" + "=" * 80)
        print("✅ ALL TESTS PASSED!")
        print("=" * 80)
        print(f"\nTotal requests: {client.request_id}")
        print("\nServer stdio funziona correttamente! 🎉")


if __name__ == "__main__":
    try:
        test_stdio_server()
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrotto dall'utente")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Test fallito: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
