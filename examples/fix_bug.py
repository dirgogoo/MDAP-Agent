"""
Example: Fix a Bug using MDAP Agent

This example shows how to use the MDAP Agent to analyze
and fix a bug in existing code.
"""
import asyncio
import os

if not os.environ.get("ANTHROPIC_API_KEY"):
    print("Please set ANTHROPIC_API_KEY environment variable")
    exit(1)

from mdap import Language, MDAPConfig, Step, StepType
from mdap.llm.client import ClaudeClient
from mdap.decision.generator import Generator
from mdap.decision.validator import Validator


# Buggy code to fix
BUGGY_CODE = '''
def binary_search(arr, target):
    """Find target in sorted array, return index or -1."""
    left = 0
    right = len(arr)  # BUG: should be len(arr) - 1

    while left < right:  # BUG: should be left <= right
        mid = (left + right) / 2  # BUG: should use // for integer division
        if arr[mid] == target:
            return mid
        elif arr[mid] < target:
            left = mid  # BUG: should be mid + 1
        else:
            right = mid  # BUG: should be mid - 1

    return -1
'''

BUG_REPORT = """
The binary_search function has multiple bugs:
1. It sometimes goes into infinite loop
2. It misses elements at array boundaries
3. It throws TypeError for float indices

Please fix all bugs while maintaining the same interface.
"""


async def main():
    """Fix the buggy code using MDAP."""

    config = MDAPConfig(
        k=3,
        max_samples=10,
        temperature=0.1,
        model="claude-3-haiku-20240307",
    )

    client = ClaudeClient(config)
    generator = Generator(client, config)
    validator = Validator(client, config)

    print("=" * 60)
    print("MDAP Agent - Bug Fix")
    print("=" * 60)

    print("\n### Original Buggy Code ###")
    print(BUGGY_CODE)

    print("\n### Bug Report ###")
    print(BUG_REPORT)

    # Create step for fix
    step = Step(
        type=StepType.GENERATE,
        signature="def binary_search(arr, target) -> int",
        description=f"""Fix the bugs in this binary search implementation.
Bug report: {BUG_REPORT}

Original code:
{BUGGY_CODE}

Provide the FIXED version.""",
    )

    print("\n### Generating Fix with MDAP (k=3) ###")

    # Generate fix with MDAP
    fixed_code = await generator.generate(
        step=step,
        language=Language.PYTHON,
        use_mdap=True,
    )

    print("\n### Fixed Code ###")
    print(fixed_code)

    # Validate fix
    print("\n### Validating Fix ###")
    validation = await validator.validate(
        code=fixed_code,
        step=step,
        language=Language.PYTHON,
    )

    if validation.passed:
        print("Validation: PASSED")
    else:
        print(f"Validation: FAILED")
        print(f"Errors: {validation.errors}")

    if validation.warnings:
        print(f"Warnings: {validation.warnings}")

    if validation.suggestions:
        print(f"Suggestions: {validation.suggestions}")

    # Test the fix
    print("\n### Testing Fix ###")
    test_code = f'''
{fixed_code}

# Test cases
test_arr = [1, 3, 5, 7, 9, 11, 13]

# Should find
assert binary_search(test_arr, 1) == 0, "Should find first element"
assert binary_search(test_arr, 13) == 6, "Should find last element"
assert binary_search(test_arr, 7) == 3, "Should find middle element"

# Should not find
assert binary_search(test_arr, 0) == -1, "Should return -1 for missing"
assert binary_search(test_arr, 14) == -1, "Should return -1 for missing"
assert binary_search(test_arr, 6) == -1, "Should return -1 for missing"

# Edge cases
assert binary_search([], 5) == -1, "Empty array"
assert binary_search([1], 1) == 0, "Single element found"
assert binary_search([1], 2) == -1, "Single element not found"

print("All tests passed!")
'''

    try:
        exec(test_code)
        print("FIX VERIFIED: All tests passed!")
    except AssertionError as e:
        print(f"FIX INCOMPLETE: {e}")
    except Exception as e:
        print(f"FIX ERROR: {e}")

    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
