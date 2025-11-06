#!/usr/bin/env python3
"""
Advanced MCP Tools
Production-ready utility tools for data processing and analysis.
"""

import sys
import json
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))


def calculate_statistics(numbers: List[float]) -> Dict[str, float]:
    """
    Calculate statistical measures for a list of numbers.
    
    Args:
        numbers: List of numerical values
        
    Returns:
        Dictionary with mean, median, std, min, max
    """
    if not numbers:
        return {"error": "Empty list provided"}
    
    try:
        sorted_numbers = sorted(numbers)
        n = len(numbers)
        
        mean = sum(numbers) / n
        
        if n % 2 == 0:
            median = (sorted_numbers[n//2 - 1] + sorted_numbers[n//2]) / 2
        else:
            median = sorted_numbers[n//2]
        
        variance = sum((x - mean) ** 2 for x in numbers) / n
        std = variance ** 0.5
        
        return {
            "count": n,
            "mean": round(mean, 2),
            "median": round(median, 2),
            "std": round(std, 2),
            "min": min(numbers),
            "max": max(numbers),
            "range": max(numbers) - min(numbers)
        }
    except Exception as e:
        return {"error": str(e)}


def format_date(
    date_string: str,
    input_format: str = "%Y-%m-%d",
    output_format: str = "%B %d, %Y"
) -> str:
    """
    Format a date string from one format to another.
    
    Args:
        date_string: Date string to format
        input_format: Current format (strftime format)
        output_format: Desired format (strftime format)
        
    Returns:
        Formatted date string
    """
    try:
        date_obj = datetime.strptime(date_string, input_format)
        return date_obj.strftime(output_format)
    except ValueError as e:
        return f"Error: Invalid date format - {str(e)}"
    except Exception as e:
        return f"Error: {str(e)}"


def generate_password(
    length: int = 16,
    include_uppercase: bool = True,
    include_numbers: bool = True,
    include_symbols: bool = True
) -> str:
    """
    Generate a random secure password.
    
    Args:
        length: Length of the password (minimum 4)
        include_uppercase: Include uppercase letters
        include_numbers: Include numbers
        include_symbols: Include special symbols
        
    Returns:
        Generated password
    """
    import random
    import string
    
    if length < 4:
        return "Error: Password length must be at least 4 characters"
    
    characters = string.ascii_lowercase
    
    if include_uppercase:
        characters += string.ascii_uppercase
    if include_numbers:
        characters += string.digits
    if include_symbols:
        characters += "!@#$%^&*()_+-=[]{}|;:,.<>?"
    
    try:
        password = ''.join(random.choice(characters) for _ in range(length))
        return password
    except Exception as e:
        return f"Error: {str(e)}"


def validate_email(email: str) -> Dict[str, Any]:
    """
    Validate an email address format.
    
    Args:
        email: Email address to validate
        
    Returns:
        Validation result with details
    """
    import re
    
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    is_valid = bool(re.match(pattern, email))
    
    result = {
        "email": email,
        "is_valid": is_valid,
    }
    
    if is_valid:
        try:
            username, domain = email.split('@')
            result["username"] = username
            result["domain"] = domain
            result["length"] = len(email)
        except Exception:
            pass
    else:
        result["error"] = "Invalid email format"
    
    return result


def convert_units(
    value: float,
    from_unit: str,
    to_unit: str,
    category: str = "length"
) -> Dict[str, Any]:
    """
    Convert between different units of measurement.
    
    Args:
        value: Value to convert
        from_unit: Source unit
        to_unit: Target unit
        category: Category (length, weight, temperature)
        
    Returns:
        Conversion result
    """
    conversions = {
        "length": {
            "m": 1.0, "km": 0.001, "cm": 100.0, "mm": 1000.0,
            "mile": 0.000621371, "yard": 1.09361, "foot": 3.28084, "inch": 39.3701,
        },
        "weight": {
            "kg": 1.0, "g": 1000.0, "mg": 1000000.0,
            "lb": 2.20462, "oz": 35.274,
        },
    }
    
    if category not in conversions:
        return {"error": f"Unknown category: {category}"}
    
    if category == "temperature":
        if from_unit == "C" and to_unit == "F":
            result = (value * 9/5) + 32
        elif from_unit == "F" and to_unit == "C":
            result = (value - 32) * 5/9
        elif from_unit == "C" and to_unit == "K":
            result = value + 273.15
        elif from_unit == "K" and to_unit == "C":
            result = value - 273.15
        else:
            return {"error": "Unsupported temperature conversion"}
    else:
        factors = conversions[category]
        
        if from_unit not in factors or to_unit not in factors:
            return {"error": f"Unknown unit in category {category}"}
        
        base_value = value / factors[from_unit]
        result = base_value * factors[to_unit]
    
    return {
        "original_value": value,
        "original_unit": from_unit,
        "converted_value": round(result, 4),
        "converted_unit": to_unit,
        "category": category
    }


def main():
    """Run MCP server with advanced tools."""
    try:
        from polymcp_toolkit import expose_tools
        import uvicorn
        
        app = expose_tools(
            tools=[
                calculate_statistics,
                format_date,
                generate_password,
                validate_email,
                convert_units,
            ],
            title="Advanced MCP Tools Server",
            description="Production-ready utility tools for data processing",
            version="1.0.0"
        )
        
        print("\n" + "="*60)
        print("🚀 Advanced MCP Tools Server")
        print("="*60)
        print("\nAvailable tools:")
        print("  • calculate_statistics - Statistical analysis")
        print("  • format_date - Date formatting")
        print("  • generate_password - Password generation")
        print("  • validate_email - Email validation")
        print("  • convert_units - Unit conversions")
        print("\nServer: http://localhost:8001")
        print("API Docs: http://localhost:8001/docs")
        print("List tools: http://localhost:8001/mcp/list_tools")
        print("\nPress Ctrl+C to stop")
        print("="*60 + "\n")
        
        uvicorn.run(app, host="0.0.0.0", port=8001, log_level="info")
    
    except KeyboardInterrupt:
        print("\n\nServer stopped.")
    except ImportError as e:
        print(f"\nError: {e}")
        print("\nPlease install dependencies:")
        print("  pip install -r requirements.txt")
        sys.exit(1)
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
