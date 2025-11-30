"""
Example: Compare MDAP vs Single-Shot Generation

This experiment compares:
1. Single-shot: Generate code once (k=1, no voting)
2. MDAP: Generate with voting (k=3)

Measures:
- Success rate (syntax valid)
- Quality (validation pass rate)
- Token usage
- Time
"""
import asyncio
import os
import json
from datetime import datetime

if not os.environ.get("ANTHROPIC_API_KEY"):
    print("Please set ANTHROPIC_API_KEY environment variable")
    exit(1)

from mdap import Step, StepType, Language, MDAPConfig
from mdap.llm.client import ClaudeClient
from mdap.decision.generator import Generator
from mdap.decision.validator import Validator


# Test cases
TEST_CASES = [
    {
        "signature": "def is_palindrome(s: str) -> bool",
        "description": "Check if a string is a palindrome, ignoring case and non-alphanumeric characters",
    },
    {
        "signature": "def find_duplicates(lst: list) -> list",
        "description": "Find all duplicate elements in a list, return each duplicate once",
    },
    {
        "signature": "def merge_sorted_lists(list1: list, list2: list) -> list",
        "description": "Merge two sorted lists into one sorted list",
    },
    {
        "signature": "def validate_brackets(s: str) -> bool",
        "description": "Check if brackets (), [], {} are balanced in a string",
    },
    {
        "signature": "def deep_flatten(nested: list) -> list",
        "description": "Flatten a deeply nested list into a single-level list",
    },
]


async def run_experiment():
    """Run comparison experiment."""

    # Config for single-shot
    config_single = MDAPConfig(
        k=1,
        max_samples=1,
        temperature=0.1,
        model="claude-3-haiku-20240307",
    )

    # Config for MDAP
    config_mdap = MDAPConfig(
        k=3,
        max_samples=15,
        temperature=0.1,
        model="claude-3-haiku-20240307",
    )

    client = ClaudeClient(config_single)

    results = {
        "timestamp": datetime.now().isoformat(),
        "test_cases": len(TEST_CASES),
        "single_shot": {
            "successes": 0,
            "failures": 0,
            "tokens": 0,
            "details": [],
        },
        "mdap": {
            "successes": 0,
            "failures": 0,
            "tokens": 0,
            "details": [],
        },
    }

    print("=" * 60)
    print("MDAP vs Single-Shot Comparison")
    print("=" * 60)

    for i, test in enumerate(TEST_CASES, 1):
        print(f"\n[{i}/{len(TEST_CASES)}] {test['signature']}")

        step = Step(
            type=StepType.GENERATE,
            signature=test["signature"],
            description=test["description"],
        )

        # --- Single-shot ---
        print("  Single-shot: ", end="", flush=True)
        generator_single = Generator(client, config_single)
        validator_single = Validator(client, config_single)

        try:
            code_single = await generator_single.generate(
                step=step,
                language=Language.PYTHON,
                use_mdap=False,
            )

            validation_single = await validator_single.validate(
                code=code_single,
                step=step,
                language=Language.PYTHON,
            )

            if validation_single.passed:
                results["single_shot"]["successes"] += 1
                print("PASS")
            else:
                results["single_shot"]["failures"] += 1
                print(f"FAIL - {validation_single.errors}")

            results["single_shot"]["details"].append({
                "test": test["signature"],
                "passed": validation_single.passed,
                "code": code_single[:200],
                "errors": validation_single.errors,
            })

        except Exception as e:
            results["single_shot"]["failures"] += 1
            print(f"ERROR - {e}")

        # --- MDAP ---
        print("  MDAP (k=3):  ", end="", flush=True)
        generator_mdap = Generator(client, config_mdap)
        validator_mdap = Validator(client, config_mdap)

        try:
            code_mdap = await generator_mdap.generate(
                step=step,
                language=Language.PYTHON,
                use_mdap=True,
            )

            validation_mdap = await validator_mdap.validate(
                code=code_mdap,
                step=step,
                language=Language.PYTHON,
            )

            if validation_mdap.passed:
                results["mdap"]["successes"] += 1
                print("PASS")
            else:
                results["mdap"]["failures"] += 1
                print(f"FAIL - {validation_mdap.errors}")

            results["mdap"]["details"].append({
                "test": test["signature"],
                "passed": validation_mdap.passed,
                "code": code_mdap[:200],
                "errors": validation_mdap.errors,
            })

        except Exception as e:
            results["mdap"]["failures"] += 1
            print(f"ERROR - {e}")

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    single_rate = results["single_shot"]["successes"] / len(TEST_CASES) * 100
    mdap_rate = results["mdap"]["successes"] / len(TEST_CASES) * 100

    print(f"\nSingle-shot: {results['single_shot']['successes']}/{len(TEST_CASES)} ({single_rate:.0f}%)")
    print(f"MDAP (k=3):  {results['mdap']['successes']}/{len(TEST_CASES)} ({mdap_rate:.0f}%)")

    improvement = mdap_rate - single_rate
    print(f"\nImprovement: {improvement:+.0f}%")

    # Save results
    output_file = f"results/comparison_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    os.makedirs("results", exist_ok=True)
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to: {output_file}")

    await client.close()


if __name__ == "__main__":
    asyncio.run(run_experiment())
