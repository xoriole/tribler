# pylint: disable=wrong-import-position

import logging
logger = logging.getLogger(__name__)

from .patch import patch_asyncio
from .watching_thread import start_watching_thread


SLOW_CORO_REPORT_FILENAME = 'slow_coro_report.txt'
