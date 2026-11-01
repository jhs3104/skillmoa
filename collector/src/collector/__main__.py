"""collector 진입점: uv run python -m collector --help"""

import argparse
import logging
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from collector.config import load_settings
from collector.pipeline.run import (
    Mode,
    Paths,
    RunOptions,
    reset_small_run,
    run_collection,
    write_metrics,
)
from collector.sources.github import GitHubClient

COLLECTOR_ROOT = Path(__file__).resolve().parents[2]


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="collector", description=__doc__)
    parser.add_argument("--mode", choices=[mode.value for mode in Mode], default=None)
    parser.add_argument("--limit", type=int, help="N개만 처리하고 build/에만 결과를 쓴다")
    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s", stream=sys.stderr)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    settings = load_settings()
    small = arguments.limit is not None
    paths = Paths.small(COLLECTOR_ROOT) if small else Paths.production(COLLECTOR_ROOT)
    if small:
        reset_small_run(paths)

    token = os.environ.get("GH_SEARCH_TOKEN")
    limits = settings.github
    max_wait = limits.max_wait_seconds_with_token if token else limits.max_wait_seconds_anonymous
    github = GitHubClient(token, max_wait_seconds=max_wait)
    started_at = time.monotonic()
    options = RunOptions(
        mode=Mode(arguments.mode) if arguments.mode else None,
        limit=arguments.limit,
        today=datetime.now(UTC).date(),
    )
    try:
        context, _ = run_collection(settings, github, paths, options)
    finally:
        github.close()
    write_metrics(context.metrics, paths, started_at)
    return 0


if __name__ == "__main__":
    sys.exit(main())
