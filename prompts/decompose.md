# Decompose Prompt

You are an expert software architect.

## Task
Given requirements, decompose them into functions/methods.

## Rules
- Each function must be **ATOMIC** (single responsibility)
- Each function must have a **CLEAR signature** with types
- Order functions by **dependency** (dependencies first)
- Keep functions **SMALL** (< 30 lines ideally)
- Include docstring descriptions

## Output Format
JSON array of objects:
```json
[
  {
    "signature": "def function_name(arg: Type) -> ReturnType",
    "description": "What the function does",
    "dependencies": ["other_function_name"],
    "requirements": [0, 1]
  }
]
```

## Example

Requirements:
0. User can register with email and password
1. Password must have minimum 8 characters
2. Email must be unique in the system

Output:
```json
[
  {
    "signature": "def validate_password(password: str) -> bool",
    "description": "Validates password has minimum 8 characters",
    "dependencies": [],
    "requirements": [1]
  },
  {
    "signature": "def validate_email(email: str) -> bool",
    "description": "Validates email format using regex",
    "dependencies": [],
    "requirements": []
  },
  {
    "signature": "def is_email_unique(email: str, db: Database) -> bool",
    "description": "Checks if email already exists in database",
    "dependencies": [],
    "requirements": [2]
  },
  {
    "signature": "def register_user(email: str, password: str, db: Database) -> User",
    "description": "Registers new user after validating email and password",
    "dependencies": ["validate_password", "validate_email", "is_email_unique"],
    "requirements": [0]
  }
]
```

## Your Turn

Requirements:
{requirements}

Language: {language}

Decompose into functions:
