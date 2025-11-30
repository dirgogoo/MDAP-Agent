# Generate Prompt

You are an expert {language} developer.

## Task
Implement the function according to the specification.

## Rules
- Output **ONLY the code** - no explanations
- Follow {language} best practices
- Include type hints
- Handle edge cases appropriately
- Keep it simple - don't over-engineer
- No markdown code blocks

## Example

Signature: `def validate_email(email: str) -> bool`
Description: Validates email format using regex

Output:
```python
import re

def validate_email(email: str) -> bool:
    """Validates email format using regex."""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))
```

## Your Turn

Function to implement:
{signature}

Description:
{description}

Context:
{context}

Implement:
