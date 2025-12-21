#!/usr/bin/env python3
"""
WASM MCP Server Example
Esempio completo per compilare tools in WASM.

Run:
    python example_wasm_builder.py
    
Then test:
    cd wasm_output
    python -m http.server 8000
    Open: http://localhost:8000/demo.html
"""

from polymcp import expose_tools_wasm
import math


# ============================================================================
# TOOLS DI ESEMPIO
# ============================================================================

def calculate_stats(numbers) -> dict:
    """
    Calcola statistiche per una lista di numeri.
    
    Args:
        numbers: Lista di numeri o stringa (es: "1, 2, 3, 4, 5")
    
    Returns:
        Dizionario con statistiche (mean, median, std, min, max)
    """
    # Convert string to list if needed (from HTML form)
    if isinstance(numbers, str):
        numbers = [float(x.strip()) for x in numbers.split(',') if x.strip()]
    else:
        # Convert all elements to float
        numbers = [float(x) for x in numbers]
    
    if not numbers:
        return {"error": "Lista vuota"}
    
    n = len(numbers)
    mean = sum(numbers) / n
    
    sorted_nums = sorted(numbers)
    if n % 2 == 0:
        median = (sorted_nums[n // 2 - 1] + sorted_nums[n // 2]) / 2
    else:
        median = sorted_nums[n // 2]
    
    variance = sum((x - mean) ** 2 for x in numbers) / n
    std = math.sqrt(variance)
    
    return {
        "count": n,
        "sum": sum(numbers),
        "mean": round(mean, 3),
        "median": median,
        "std": round(std, 3),
        "min": min(numbers),
        "max": max(numbers),
        "range": max(numbers) - min(numbers)
    }


def prime_factors(n) -> dict:
    """
    Trova i fattori primi di un numero.
    
    Args:
        n: Numero da fattorizzare (2-10000)
    
    Returns:
        Dizionario con fattori primi
    """
    # Convert to int (from HTML form)
    n = int(n)
    
    if n < 2 or n > 10000:
        raise ValueError("n deve essere tra 2 e 10000")
    
    factors = []
    d = 2
    original = n
    
    while d * d <= n:
        while n % d == 0:
            factors.append(d)
            n //= d
        d += 1
    
    if n > 1:
        factors.append(n)
    
    # Conta occorrenze
    unique_factors = list(set(factors))
    factor_counts = {f: factors.count(f) for f in unique_factors}
    
    return {
        "number": original,
        "factors": factors,
        "unique_factors": unique_factors,
        "factor_counts": factor_counts,
        "is_prime": len(factors) == 1
    }


def text_processor(text: str, operations) -> dict:
    """
    Processa testo con multiple operazioni.
    
    Args:
        text: Testo da processare
        operations: Lista di operazioni o stringa separata da virgole
    
    Returns:
        Dizionario con risultati di ogni operazione
    """
    # Convert string to list if needed (from HTML form)
    if isinstance(operations, str):
        operations = [op.strip() for op in operations.split(',') if op.strip()]
    
    results = {"original": text}
    
    for op in operations:
        if op == "uppercase":
            results[op] = text.upper()
        elif op == "lowercase":
            results[op] = text.lower()
        elif op == "reverse":
            results[op] = text[::-1]
        elif op == "capitalize":
            results[op] = text.capitalize()
        elif op == "title":
            results[op] = text.title()
        elif op == "length":
            results[op] = str(len(text))
        elif op == "words":
            results[op] = str(len(text.split()))
        else:
            results[op] = f"Unknown operation: {op}"
    
    return results


def unit_converter(value, from_unit: str, to_unit: str) -> dict:
    """
    Converte tra unità di misura.
    
    Args:
        value: Valore da convertire
        from_unit: Unità di origine (km, mi, kg, lb, c, f)
        to_unit: Unità di destinazione
    
    Returns:
        Dizionario con risultato conversione
    """
    # Convert value to float (from HTML form)
    value = float(value)
    
    conversions = {
        ("km", "mi"): 0.621371,
        ("mi", "km"): 1.60934,
        ("kg", "lb"): 2.20462,
        ("lb", "kg"): 0.453592,
        ("c", "f"): lambda x: x * 9/5 + 32,
        ("f", "c"): lambda x: (x - 32) * 5/9,
        ("m", "ft"): 3.28084,
        ("ft", "m"): 0.3048
    }
    
    key = (from_unit.lower(), to_unit.lower())
    
    if key not in conversions:
        return {
            "error": f"Conversione {from_unit} -> {to_unit} non supportata",
            "supported": list(set(f"{k[0]}->{k[1]}" for k in conversions.keys()))
        }
    
    converter = conversions[key]
    
    if callable(converter):
        result = converter(value)
    else:
        result = value * converter
    
    return {
        "input_value": value,
        "input_unit": from_unit,
        "output_value": round(result, 4),
        "output_unit": to_unit,
        "formula": f"{value} {from_unit} = {round(result, 4)} {to_unit}"
    }


def compound_interest(
    principal,
    rate,
    years,
    compounds_per_year = 12
) -> dict:
    """
    Calcola interesse composto.
    
    Args:
        principal: Capitale iniziale
        rate: Tasso annuale (es: 0.05 per 5%)
        years: Anni di investimento
        compounds_per_year: Frequenza composizione (12=mensile, 4=trimestrale, 1=annuale)
    
    Returns:
        Calcoli interesse composto
    """
    # Convert to correct types (from HTML form)
    principal = float(principal)
    rate = float(rate)
    years = int(years)
    compounds_per_year = int(compounds_per_year)
    
    if principal <= 0 or rate < 0 or years <= 0:
        raise ValueError("Valori devono essere positivi")
    
    amount = principal * (1 + rate / compounds_per_year) ** (compounds_per_year * years)
    interest = amount - principal
    
    # Calcola anno per anno
    yearly_breakdown = []
    for year in range(1, years + 1):
        year_amount = principal * (1 + rate / compounds_per_year) ** (compounds_per_year * year)
        yearly_breakdown.append({
            "year": year,
            "amount": round(year_amount, 2),
            "interest_earned": round(year_amount - principal, 2)
        })
    
    return {
        "principal": round(principal, 2),
        "rate_percent": f"{rate * 100}%",
        "years": years,
        "compounds_per_year": compounds_per_year,
        "final_amount": round(amount, 2),
        "total_interest": round(interest, 2),
        "roi_percent": f"{(interest / principal * 100):.2f}%",
        "yearly_breakdown": yearly_breakdown
    }


# ============================================================================
# BUILDER
# ============================================================================

def main():
    """Compila i tools in WASM."""
    
    print("\n" + "=" * 80)
    print("WASM MCP Server Builder")
    print("=" * 80)
    print()
    
    tools = [
        calculate_stats,
        prime_factors,
        text_processor,
        unit_converter,
        compound_interest
    ]
    
    print(f"📦 Compiling {len(tools)} tools to WASM...")
    print()
    print("Tools:")
    for tool in tools:
        doc = tool.__doc__.strip().split('\n')[0] if tool.__doc__ else "No description"
        print(f"  • {tool.__name__} - {doc}")
    print()
    
    # Crea compiler
    compiler = expose_tools_wasm(
        tools=tools,
        server_name="Example WASM MCP Server",
        server_version="1.0.0",
        pyodide_version="0.26.4",
        verbose=True
    )
    
    # Compila
    print("🔨 Compiling...")
    print()
    
    bundle = compiler.compile(output_dir="./wasm_output")
    
    print()
    print("=" * 80)
    print("✅ Compilation Complete!")
    print("=" * 80)
    print()
    print("Generated files:")
    for name, path in bundle.items():
        print(f"  ✓ {name:20s} → {path}")
    print()
    print("=" * 80)
    print("Next Steps:")
    print("=" * 80)
    print()
    print("1. Test locally:")
    print("   cd wasm_output")
    print("   python -m http.server 8000")
    print()
    print("2. Open in browser:")
    print("   http://localhost:8000/demo.html")
    print()
    print("3. Deploy:")
    print("   - GitHub Pages: push wasm_output/ to gh-pages branch")
    print("   - Vercel/Netlify: deploy wasm_output/ folder")
    print("   - NPM: cd wasm_output && npm publish")
    print()
    print("=" * 80)
    print()


if __name__ == "__main__":
    main()
