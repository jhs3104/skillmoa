"""collector 진입점: uv run python -m collector --help"""

import argparse
import logging
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

from collector.config import Settings, load_settings
from collector.pipeline.run import (
    Mode,
    Paths,
    RunOptions,
    export_site,
    reset_small_run,
    run_collection,
    run_summaries,
    run_tool_news_only,
    write_metrics,
)
from collector.sources.github import GitHubClient
from collector.summarize.base import Classifier, Summarizer
from collector.summarize.classify import ClaudeClassifier
from collector.summarize.claude import ClaudeSummarizer
from collector.summarize.mock import MockClassifier, MockSummarizer
from collector.summarize.tool_news import ClaudeToolNewsWriter

COLLECTOR_ROOT = Path(__file__).resolve().parents[2]
EXIT_USAGE = 2
FEED_TIMEOUT_SECONDS = 30.0


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="collector", description=__doc__)
    parser.add_argument("--mode", choices=[mode.value for mode in Mode], default=None)
    parser.add_argument("--limit", type=int, help="N개만 처리하고 build/에만 결과를 쓴다")
    parser.add_argument(
        "--repo-cap", type=int, help="저장소당 상한을 낮춰 표본을 넓힌다 (--limit 전용)"
    )
    parser.add_argument(
        "--mock-summary", action="store_true", help="API 없이 자리표시 요약을 쓴다 (--limit 전용)"
    )
    parser.add_argument("--skip-summary", action="store_true", help="수집과 내보내기만 한다")
    parser.add_argument(
        "--tool-news",
        action="store_true",
        help="스킬 수집 없이 도구 업데이트만 가져와 요약한다 (ADR-0022)",
    )
    parser.add_argument(
        "--refresh-prompt", action="store_true", help="이전 프롬프트 버전의 요약도 다시 만든다"
    )
    arguments = parser.parse_args()
    if arguments.mock_summary and arguments.limit is None:
        parser.error("--mock-summary는 --limit과 함께만 쓸 수 있습니다")
    if arguments.repo_cap is not None and arguments.limit is None:
        parser.error("--repo-cap은 --limit과 함께만 쓸 수 있습니다")
    if arguments.tool_news and (arguments.skip_summary or arguments.mock_summary):
        parser.error("--tool-news는 Claude API로 요약하므로 요약을 끄는 옵션과 함께 쓸 수 없습니다")
    return arguments


def build_summarizer(arguments: argparse.Namespace, settings: Settings) -> Summarizer | None:
    if arguments.skip_summary:
        return None
    if arguments.mock_summary:
        return MockSummarizer()
    return ClaudeSummarizer(settings.summary)


def build_classifier(arguments: argparse.Namespace, settings: Settings) -> Classifier | None:
    if arguments.skip_summary:
        return None
    if arguments.mock_summary:
        return MockClassifier()
    return ClaudeClassifier(settings.classify)


def main() -> int:
    arguments = parse_arguments()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s", stream=sys.stderr)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    settings = load_settings()
    if arguments.repo_cap is not None:
        ranking = settings.ranking.model_copy(update={"per_repository_cap": arguments.repo_cap})
        settings = settings.model_copy(update={"ranking": ranking})
    needs_api_key = not (arguments.skip_summary or arguments.mock_summary)
    if needs_api_key and not os.environ.get("ANTHROPIC_API_KEY"):
        logging.error("ANTHROPIC_API_KEY가 없습니다. --mock-summary나 --skip-summary를 쓰세요")
        return EXIT_USAGE
    summarizer = build_summarizer(arguments, settings)
    classifier = build_classifier(arguments, settings)

    small = arguments.limit is not None
    paths = Paths.small(COLLECTOR_ROOT) if small else Paths.production(COLLECTOR_ROOT)
    if small:
        reset_small_run(paths)

    token = os.environ.get("GH_SEARCH_TOKEN")
    limits = settings.github
    max_wait = limits.max_wait_seconds_with_token if token else limits.max_wait_seconds_anonymous
    github = GitHubClient(token, max_wait_seconds=max_wait)
    # Cursor 변경 기록 RSS용. 요청은 sources.tool_releases가 보낸다.
    feeds = httpx.Client(timeout=FEED_TIMEOUT_SECONDS, follow_redirects=True)
    started_at = time.monotonic()
    options = RunOptions(
        mode=Mode(arguments.mode) if arguments.mode else None,
        limit=arguments.limit,
        today=datetime.now(UTC).date(),
    )
    try:
        if arguments.tool_news:
            writer = ClaudeToolNewsWriter(settings.news)
            context = run_tool_news_only(settings, github, feeds, writer, paths, options.today)
            return 0
        context, _ = run_collection(settings, github, paths, options)
        if summarizer is not None:
            run_summaries(
                context,
                summarizer,
                paths,
                arguments.limit,
                classifier=classifier,
                refresh_prompt=arguments.refresh_prompt,
            )
        export_site(context, paths)
    finally:
        github.close()
        feeds.close()
        if "context" in locals():
            write_metrics(context.metrics, paths, started_at)
    return 0


if __name__ == "__main__":
    sys.exit(main())
