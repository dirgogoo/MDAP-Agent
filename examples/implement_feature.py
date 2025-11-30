"""
Example: Implement a Feature using MDAP Agent

This example shows how to use the MDAP Agent to implement
a complete feature from a natural language description.
"""
import asyncio
import os
import logging

# Ensure API key is set
if not os.environ.get("ANTHROPIC_API_KEY"):
    print("Please set ANTHROPIC_API_KEY environment variable")
    exit(1)

from mdap import Language, MDAPConfig
from mdap.agent import AgentLoop, agent_loop


async def main():
    """Run the MDAP Agent to implement a feature."""

    # Task description
    task = """
    Create a simple JWT authentication module with:
    - Token generation with expiration
    - Token validation
    - Token refresh functionality
    """

    # Configuration
    config = MDAPConfig(
        k=3,                          # votes needed to win
        max_samples=10,               # max candidates per step
        max_tokens_response=500,      # response limit
        temperature=0.1,              # low for consistency
        model="claude-3-haiku-20240307",  # fast model for experiments
    )

    print("=" * 60)
    print("MDAP Agent - Feature Implementation")
    print("=" * 60)
    print(f"\nTask: {task.strip()}")
    print("\nStarting agent loop...\n")

    # Run agent
    result = await agent_loop(
        task=task,
        language=Language.PYTHON,
        config=config,
        max_steps=30,
    )

    # Print results
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)

    print("\n### Requirements Expanded ###")
    for i, req in enumerate(result.get("requirements", []), 1):
        print(f"  {i}. {req}")

    print("\n### Functions Generated ###")
    for func in result.get("functions", []):
        print(f"  - {func['signature']}")

    print("\n### Generated Code ###")
    for step_id, code in result.get("code", {}).items():
        print(f"\n# {step_id}")
        print(code)

    print("\n### Metrics ###")
    metrics = result.get("metrics", {})
    print(f"  Steps total: {metrics.get('steps_total', 0)}")
    print(f"  Tokens used: {metrics.get('tokens', {}).get('total', 0)}")
    print(f"  Duration: {metrics.get('duration_seconds', 0):.1f}s")

    # Estimate cost
    tokens = metrics.get('tokens', {})
    input_cost = tokens.get('input', 0) * 0.25 / 1_000_000
    output_cost = tokens.get('output', 0) * 1.25 / 1_000_000
    total_cost = input_cost + output_cost
    print(f"  Estimated cost: ${total_cost:.4f}")


async def main_interactive():
    """Run with step-by-step confirmation."""
    task = input("Enter task description: ")

    agent = AgentLoop()

    async def on_step_start(step):
        print(f"\n>>> Starting: {step.type.value} - {step.description}")

    async def on_step_end(step, success):
        status = "OK" if success else "FAILED"
        print(f"<<< Finished: [{status}]")

    agent.on_step_start(on_step_start)
    agent.on_step_end(on_step_end)

    context = await agent.run_interactive(task)

    print("\n\nFinal result:")
    print(context.to_json())

    await agent.close()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # Run basic example
    asyncio.run(main())

    # Or run interactive:
    # asyncio.run(main_interactive())
