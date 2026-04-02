"""CLI entry point for finnote pipeline."""

import asyncio
import sys

from finnote.workflow.pipeline import Pipeline


def main():
    args = sys.argv[1:]
    subcommand = args[0] if args else "run"
    dry_run = "--dry-run" in args
    pipeline = Pipeline()

    match subcommand:
        case "run":
            asyncio.run(pipeline.run_full(dry_run=dry_run))
        case "collect":
            asyncio.run(pipeline.run_phase("data_collection"))
        case "debate":
            asyncio.run(pipeline.run_phase("data_science_analysis"))
        case "visualize":
            asyncio.run(pipeline.run_phase("editorial_production"))
        case _:
            print(f"Unknown command: {subcommand}")
            print("Usage: python -m finnote [run|collect|debate|visualize] [--dry-run]")
            sys.exit(1)


if __name__ == "__main__":
    main()
