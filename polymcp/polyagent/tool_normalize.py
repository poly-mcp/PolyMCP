"""
Tool Metadata Normalization
Handles camelCase/snake_case conversions.
"""

from typing import Any, Dict


def normalize_tool_metadata(tool: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize tool metadata to snake_case.
    
    Converts inputSchema → input_schema, outputSchema → output_schema.
    Ensures schemas are never null.
    """
    result = dict(tool or {})
    
    # Convert camelCase to snake_case
    if "input_schema" not in result and "inputSchema" in result:
        result["input_schema"] = result.get("inputSchema")
    
    if "output_schema" not in result and "outputSchema" in result:
        result["output_schema"] = result.get("outputSchema")
    
    # Ensure schemas exist
    if result.get("input_schema") is None:
        result["input_schema"] = {}
    
    if result.get("output_schema") is None:
        result["output_schema"] = {}
    
    return result
