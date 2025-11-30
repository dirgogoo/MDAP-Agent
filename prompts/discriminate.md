# Discriminate Prompt

You are a code analysis expert.

## Task
Determine if two code snippets are **SEMANTICALLY EQUIVALENT**.

## Definition
Two codes are equivalent if they produce the **same output for all valid inputs**.

## What Doesn't Matter
- Formatting differences
- Variable names
- Minor implementation details
- Comment differences
- Import order

## What Does Matter
- Different algorithms that produce different results
- Missing edge case handling
- Different error behavior
- Different return types

## Output
Answer **ONLY** "YES" or "NO"

## Examples

### Example 1: EQUIVALENT
Code A:
```python
def add(a, b):
    return a + b
```

Code B:
```python
def add(x, y):
    result = x + y
    return result
```

Answer: YES

### Example 2: NOT EQUIVALENT
Code A:
```python
def divide(a, b):
    return a / b
```

Code B:
```python
def divide(a, b):
    if b == 0:
        return None
    return a / b
```

Answer: NO (different behavior when b=0)

## Your Turn

Context: {context}

Code A:
```
{code_a}
```

Code B:
```
{code_b}
```

Are these semantically equivalent? (YES/NO)
