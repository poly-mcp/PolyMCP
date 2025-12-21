# {CATEGORY_NAME} Skills

**Category:** {category}  
**Tools:** {tool_count}  
**Generated:** {generation_date}

## Description

{detailed_category_description}

This skill provides tools for {category}-related operations, including {main_capabilities}.

## Usage Patterns

**Best for:**
- {use_case_1}
- {use_case_2}
- {use_case_3}

**Avoid for:**
- {anti_pattern_1} (use `{alternative_skill}` instead)
- {anti_pattern_2}

## Trigger Examples

This skill is loaded when queries contain:
- "{trigger_phrase_1}"
- "{trigger_phrase_2}"
- "{trigger_phrase_3}"

**Example queries:**
```
✅ "Send email to John about project updates"
✅ "Create calendar event for tomorrow at 3pm"
❌ "What's the weather?" (use weather skill instead)
```

---

## Available Tools

### {tool_name}

{tool_description}

**Source:** {server_name}  
**Category Tags:** {tags}

**Parameters:**
- `param1` (type) *(required)*  
  Description of parameter 1
  
- `param2` (type) *(optional)*  
  Description of parameter 2  
  Default: `{default_value}`

**Returns:** JSON string with operation result

**Example:**
```python
import json

# Call the tool
result_json = tools.{tool_name}(param1="value1", param2="value2")

# Parse result
result = json.loads(result_json)
print(f"Result: {result}")
```

**Sample Output:**
```json
{
  "status": "success",
  "data": {
    "field1": "value1",
    "field2": "value2"
  }
}
```

---

### {tool_name_2}

{tool_description_2}

*(Repeat structure for each tool)*

---

## Multi-Step Workflows

### Workflow: {workflow_name}

Common pattern combining multiple tools:

```python
# Step 1: {step_1_description}
result1 = tools.{tool_1}(param="value")

# Step 2: {step_2_description}
data = json.loads(result1)
result2 = tools.{tool_2}(input=data["field"])

# Step 3: {step_3_description}
final = tools.{tool_3}(processed=result2)
```

---

## Best Practices

### Error Handling

Always wrap tool calls in try-except blocks:

```python
try:
    result_json = tools.{tool_name}(param="value")
    result = json.loads(result_json)
    
    if result.get("status") == "error":
        print(f"Tool error: {result.get('message')}")
    else:
        # Process successful result
        print(f"Success: {result}")
        
except Exception as e:
    print(f"Execution error: {e}")
```

### JSON Parsing

```python
import json

# Always parse JSON results
result_json = tools.{tool_name}()
result = json.loads(result_json)

# Access fields safely
value = result.get("field", "default_value")
```

### Parameter Validation

```python
# Validate before calling
def validate_params(email: str) -> bool:
    return "@" in email and "." in email

if validate_params(user_email):
    result = tools.send_email(to=user_email)
else:
    print("Invalid email format")
```

### {category_specific_practices}

---

## Security & Sandbox

**Execution Environment:**
- ✅ Runs in sandboxed environment
- ✅ Timeout protection: {timeout}s max
- ✅ Memory limit: {memory_limit}MB
- ✅ Network isolation (unless explicitly allowed)

**Safe Practices:**
```python
# ✅ GOOD: Validate inputs
if user_input.isalnum():
    result = tools.process(data=user_input)

# ❌ BAD: Unvalidated user input
result = tools.process(data=user_input)  # Potential injection
```

---

## Troubleshooting

### Problem: Tool returns error

**Symptoms:**
```json
{"status": "error", "message": "Invalid parameter"}
```

**Solutions:**
1. Verify all required parameters are provided
2. Check parameter types match the schema
3. Ensure MCP server is running and accessible
4. Review error message for specific details

**Debug example:**
```python
# Enable verbose mode
result = tools.{tool_name}(param="value", verbose=True)
print(f"Debug info: {result}")
```

### Problem: Tool timeout

**Symptoms:**
```
TimeoutError: Execution exceeded 30.0s
```

**Solutions:**
1. Increase timeout setting in agent config
2. Check network connectivity to MCP server
3. Verify server is responding (not overloaded)
4. Split large operations into smaller chunks

### Problem: JSON parsing error

**Symptoms:**
```
JSONDecodeError: Expecting value: line 1 column 1 (char 0)
```

**Solutions:**
```python
import json

result_json = tools.{tool_name}()

# Validate before parsing
if result_json and isinstance(result_json, str):
    try:
        result = json.loads(result_json)
    except json.JSONDecodeError as e:
        print(f"Invalid JSON: {result_json}")
        print(f"Error: {e}")
else:
    print(f"Unexpected result type: {type(result_json)}")
```

---

## Performance Tips

1. **Batch Operations**: Group multiple calls when possible
   ```python
   # ✅ GOOD: Single batch call
   results = tools.batch_process(items=[item1, item2, item3])
   
   # ❌ BAD: Multiple individual calls
   for item in items:
       result = tools.process(item=item)  # Slower
   ```

2. **Caching**: Cache results for repeated queries
   ```python
   cache = {}
   
   def get_data(key):
       if key not in cache:
           cache[key] = json.loads(tools.fetch(key=key))
       return cache[key]
   ```

3. **Parallel Execution**: Use async for independent operations
   ```python
   import asyncio
   
   async def parallel_tasks():
       task1 = asyncio.create_task(tools.operation1())
       task2 = asyncio.create_task(tools.operation2())
       results = await asyncio.gather(task1, task2)
   ```

---

## Related Skills

- `{related_category1}.md` - {relation_description_1}
- `{related_category2}.md` - {relation_description_2}
- `{related_category3}.md` - {relation_description_3}

**When to use each:**
- Use **{this_category}** for: {use_case}
- Use **{related_category1}** for: {alternative_use_case}

---

## Version History

- **v{version}** ({date}): {changes}
- **v1.0.0** (Initial): Generated from {server_name}

---

## References

- MCP Server: `{server_url}`
- Documentation: `{docs_url}`
- Examples: `{examples_url}`

---

*This skill was {generated_method}.*  
*For automatic generation from MCP servers, use: `polymcp skills generate --server {server_url}`*  
*For manual skill creation, copy this template and fill in the placeholders.*

---

**Skill Metadata**
```yaml
category: {category}
tags: [{tag1}, {tag2}, {tag3}]
tools_count: {tool_count}
server: {server_name}
version: {version}
requires_auth: {auth_required}
network_access: {network_required}
```
