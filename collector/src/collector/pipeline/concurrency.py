"""API 호출만 작업 스레드에서 동시에 보낸다.

요청 만들기와 결과 기록은 호출한 스레드에서 하므로 상태에 잠금이 필요 없다.
"""

from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait


def run_concurrently[RequestT, ResultT](
    next_request: Callable[[], tuple[str, RequestT] | None],
    send: Callable[[RequestT], ResultT],
    record: Callable[[str, Future[ResultT]], bool],
    *,
    concurrency: int,
    on_recorded: Callable[[], None] = lambda: None,
) -> None:
    """보낼 요청이 없거나 record가 False를 돌려줄 때까지 concurrency개씩 보낸다.

    next_request가 None을 돌려주면 더 보내지 않는다. 상한 확인도 여기서 한다.
    record가 False를 돌려주면 새 요청을 멈추고, 이미 보낸 호출은 끝까지 받아 기록한다.
    """
    running: dict[Future[ResultT], str] = {}
    sending = True
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        while True:
            while sending and len(running) < concurrency:
                item = next_request()
                if item is None:
                    sending = False
                    break
                key, request = item
                running[pool.submit(send, request)] = key
            if not running:
                return
            done, _ = wait(running, return_when=FIRST_COMPLETED)
            for future in done:
                key = running.pop(future)
                if not record(key, future):
                    sending = False
                on_recorded()
