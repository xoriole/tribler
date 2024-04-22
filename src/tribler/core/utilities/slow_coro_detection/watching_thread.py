from __future__ import annotations

import time
from asyncio import Handle
from pathlib import Path
from threading import Event, Lock, Thread

from typing import Optional

from tribler.core.utilities.slow_coro_detection import logger
from tribler.core.utilities.slow_coro_detection.utils import format_info

# How long (in seconds) a coroutine can run before we generate an error.
# Reduce if you want stricter limits for maximum coroutine step duration.
SLOW_CORO_DURATION_THRESHOLD = 1.0

# How long (in seconds) the debug thread waits before checks.
# Reduce if you want a better precision at the expense of a minor performance hit.
WATCHING_THREAD_INTERVAL = 1.0


class DebugInfo:
    def __init__(self):
        self.handle: Optional[Handle] = None
        self.start_time: Optional[float] = None

        self.coro_info: Optional[str] = None
        self.slowest_coro_info: Optional[str] = None
        self.slowest_coro_duration: float = 0.0


current = DebugInfo()
lock = Lock()
_thread: Optional[SlowCoroWatchingThread] = None


def start_watching_thread(slow_coro_report_filepath: Optional[Path] = None):
    """
    Starts separate thread that detects and reports slow coroutines.
    """
    global _thread  # pylint: disable=global-statement
    with lock:
        if _thread is not None:
            return  # the thread is already created

        _thread = SlowCoroWatchingThread(daemon=True)
        _thread.slow_coro_report_filepath = slow_coro_report_filepath

    _thread.start()


class SlowCoroWatchingThread(Thread):
    """
    A thread that detects and reports slow coroutines.
    """
    def __init__(self, group=None, target=None, name=None, args=(), kwargs=None, *, daemon=None):
        super().__init__(group=group, target=target, name=name, args=args, kwargs=kwargs, daemon=daemon)
        self.stop_event = Event()
        self.slow_coro_report_filepath: Optional[Path] = None

    def run(self):
        # SlowCoroWatchingThread.run() checks periodically that we are not currently in the coroutine step that already
        # took too much time but is not finished yet. This way, we can detect a freezer coroutine that never finished
        # or a coroutine that freezes the loop until the GUI process decides to kill the Core process. In contrast to
        # patched_handle_run(), it is not guaranteed that SlowCoroWatchingThread.run() is triggered for each coroutine,
        # a coroutine that was just slightly longer than the limit may be missed by SlowCoroWatchingThread.run().
        #
        # Also, SlowCoroWatchingThread.run() displays the current main stack (as we are inside a running coroutine)
        # while patched_handle_run() does not display the stack (as the coroutine step is already finished).

        self.remove_previous_slow_coro_report()

        prev_reported_handle = None  # to detect in the loop when we have the second report of the same slow coroutine
        while not self.stop_event.is_set():
            time.sleep(WATCHING_THREAD_INTERVAL)
            with lock:
                handle, start_time = current.handle, current.start_time

            new_reported_handle = None
            if handle is not None:
                duration = time.time() - start_time
                if duration > SLOW_CORO_DURATION_THRESHOLD:
                    _report_freeze(handle, duration, first_report=prev_reported_handle is not handle,
                                   slow_coro_report_filepath=self.slow_coro_report_filepath)
                    new_reported_handle = handle
            prev_reported_handle = new_reported_handle

    def remove_previous_slow_coro_report(self):
        try:
            self.slow_coro_report_filepath.unlink(missing_ok=True)
        except Exception as exc:
            logger.exception(f'Exception while removing previous slow coro report: {exc.__class__.__name__}: {exc}')

    def stop(self):
        # We actually do not use it, as the thread is started as daemonic, that is, it runs till the very end
        # and does not prevent the process exiting
        self.stop_event.set()


def _report_freeze(handle: Handle, duration: float, first_report: bool,
                   slow_coro_report_filepath: Optional[Path] = None):
    # When printing the stack, we only want to show the stack frames executing long enough,
    # as displaying the entire stack can confuse the reader and mislead him regarding what function should be optimized
    stack_cut_duration = duration * 0.8
    info_str = format_info(handle, include_stack=True, stack_cut_duration=stack_cut_duration)
    with lock:
        current.coro_info = info_str

    logger.error(f"A slow coroutine step is {'still ' if not first_report else ''}occupying the loop "
                 f"for {duration:.3f} seconds already: {info_str}")
    update_slowest_coro_info(duration, slow_coro_report_filepath)


def update_slowest_coro_info(duration, slow_coro_report_filepath: Optional[Path] = None):
    new_coro_info_to_write = None
    with lock:
        if duration > current.slowest_coro_duration :
            current.slowest_coro_duration = duration

            if current.slowest_coro_info != current.coro_info:
                current.slowest_coro_info = current.coro_info

            new_coro_info_to_write = current.coro_info

    if new_coro_info_to_write and slow_coro_report_filepath is not None:
        write_slowest_coro_info_to_file(new_coro_info_to_write, duration, slow_coro_report_filepath)


def write_slowest_coro_info_to_file(coro_info: str, duration: float, slow_coro_report_filepath: Path):
    text = f'Slow coroutine execution: {duration:.3f} seconds\n{coro_info}'
    try:
        slow_coro_report_filepath.write_text(text, encoding='utf-8')
    except Exception as exc:
        logger.exception(f'Exception while reading slow coro report: {exc.__class__.__name__}: {exc}')
