import errno
import json
import logging
import os.path
import re
import sys
import traceback
from io import StringIO
from socket import gaierror
from traceback import print_exception
from typing import Callable, Dict, Optional, Set, Tuple, Type

from tribler.core.components.exceptions import ComponentStartupException
from tribler.core.components.reporter.reported_error import ReportedError
from tribler.core.sentry_reporter.sentry_reporter import SentryReporter
from tribler.core.utilities.process_manager import get_global_process_manager

# There are some errors that we are ignoring.

IGNORED_ERRORS_BY_CLASS: Tuple[Type[Exception], ...] = (
    ConnectionResetError,  # Connection forcibly closed by the remote host.
    gaierror,  # all gaierror is ignored
)

IGNORED_ERRORS_BY_CODE: Set[Tuple[Type[Exception], int]] = {
    (OSError, 113),  # No route to host is non-critical since Tribler can still function when a request fails.
    # Socket block: this sometimes occurs on Windows and is non-critical.
    (BlockingIOError, 10035 if sys.platform == 'win32' else errno.EWOULDBLOCK),
    (OSError, 51),  # Could not send data: network is unreachable.
    (ConnectionAbortedError, 10053),  # An established connection was aborted by the software in your host machine.
    (OSError, 10022),  # Failed to get address info.
    (OSError, 16),  # Socket error: Device or resource busy.
    (OSError, 0)
}

IGNORED_ERRORS_BY_REGEX: Dict[Type[Exception], str] = {
    RuntimeError: r'.*invalid info-hash.*'
}


class NoCrashException(Exception):
    """Raising exceptions of this type doesn't lead to forced Tribler stop"""


class DeserializedException(Exception):
    def __init__(self, exc_type_str, exc_value_str, exc_traceback_str):
        self.original_type = exc_type_str
        self.original_traceback = exc_traceback_str
        super().__init__(f"{exc_type_str}: {exc_value_str}")

    def __str__(self):
        return f"{self.original_traceback}\n{self.original_type}: {super().__str__()}"
        # return f"{self.original_type}: {super().__str__()}"


class CoreExceptionHandler:
    """
    This class handles Python errors arising in the Core by catching them, adding necessary context,
    and sending them to the GUI through the events endpoint. It must be connected to the Asyncio loop.
    """

    def __init__(self):
        self.logger = logging.getLogger("CoreExceptionHandler")
        self.report_callback: Optional[Callable[[ReportedError], None]] = None
        self.unreported_error: Optional[ReportedError] = None
        self.sentry_reporter = SentryReporter()
        self.load_exceptions()

    @staticmethod
    def _get_long_text_from(exception: Exception):
        with StringIO() as buffer:
            print_exception(type(exception), exception, exception.__traceback__, file=buffer)
            return buffer.getvalue()

    @staticmethod
    def _is_ignored(exception: Exception):
        exception_class = exception.__class__
        error_number = exception.errno if hasattr(exception, 'errno') else None

        if isinstance(exception, IGNORED_ERRORS_BY_CLASS):
            return True

        if (exception_class, error_number) in IGNORED_ERRORS_BY_CODE:
            return True

        if exception_class not in IGNORED_ERRORS_BY_REGEX:
            return False

        pattern = IGNORED_ERRORS_BY_REGEX[exception_class]
        return re.search(pattern, str(exception)) is not None

    def _create_exception_from(self, message: str):
        text = f'Received error without exception: {message}'
        self.logger.warning(text)
        return Exception(text)

    def unhandled_system_error_observer(self, exc_type, exc_value, exc_traceback):
        print("Unhandled Exception on System Exception Handler:")
        print(f"+=" * 25)
        print(traceback.format_exc())
        print(f"ex type: {exc_type}, value: {exc_value}")
        exception = traceback.format_exception(exc_type, exc_value, exc_traceback)
        print(f"exception xxxx: {exception}")
        print(f"-=" * 25)
        exception_file = "exceptions.txt"
        with open(exception_file, 'a') as f:
            f.write(json.dumps({
                "type": exc_type.__name__,
                "message": str(exc_value),
                "traceback": "".join(exception)
            }))
            f.write("\n")
            f.flush()

    def unhandled_error_observer(self, _, context):
        """
        This method is called when an unhandled error in Tribler is observed.
        It broadcasts the tribler_exception event.
        """
        self.logger.info('Processing unhandled error...')
        self.sentry_reporter.ignore_logger(self.logger.name)
        context = context.copy()
        should_stop = context.pop('should_stop', True)
        message = context.pop('message', 'no message')
        exception = context.pop('exception', None) or self._create_exception_from(message)

        self.handle_unhandled_exceptions(exception, context, should_stop=should_stop)

    def handle_unhandled_exceptions(self, exception, context, should_stop=True):
        process_manager = get_global_process_manager()
        try:
            # Exception
            text = str(exception)
            if isinstance(exception, ComponentStartupException):
                self.logger.info('The exception is ComponentStartupException')
                should_stop = exception.component.tribler_should_stop_on_component_error
                exception = exception.__cause__
            if isinstance(exception, NoCrashException):
                self.logger.info('The exception is NoCrashException')
                should_stop = False
                exception = exception.__cause__

            if self._is_ignored(exception):
                self.logger.info('The exception will be ignored')
                self.logger.warning(exception)
                return

            long_text = self._get_long_text_from(exception)

            reported_error = ReportedError(
                type=exception.__class__.__name__,
                text=text,
                long_text=long_text,
                context=str(context),
                event=self.sentry_reporter.event_from_exception(exception) or {},
                should_stop=should_stop,
                # `additional_information` should be converted to dict
                # see: https://github.com/python/cpython/pull/32056
                additional_information=dict(self.sentry_reporter.additional_information)
            )
            self.logger.error(f"Unhandled exception occurred! {reported_error}\n{reported_error.long_text}")
            if process_manager:
                process_manager.current_process.set_error(exception)

            if self.report_callback:
                self.logger.error('Call report callback')
                self.report_callback(reported_error)  # pylint: disable=not-callable
            else:
                self.logger.error('Save the error to later report')
                if not self.unreported_error:
                    # We only remember the first unreported error,
                    # as that was probably the root cause for # the crash
                    self.unreported_error = reported_error

        except Exception as ex:
            if process_manager:
                process_manager.current_process.set_error(ex)

            self.sentry_reporter.capture_exception(ex)
            self.logger.exception(f'Error occurred during the error handling: {ex}')
            raise ex

    def handle_saved_exception(self, exception_dict):
        pass


    def save_exception(self):
        print(f"Saving exceptions")
        if self.unreported_error:
            with open("exceptions.txt", "a") as f:
                f.write(f"{json.dumps(self.unreported_error)}\n\n")

    def load_exceptions(self):
        errors = []
        exception_file = "exceptions.txt"
        if os.path.exists(exception_file):
            with open("exceptions.txt", "r") as f:
                for exception_line in f:
                    try:
                        exception = json.loads(exception_line)
                        errors.append(exception)
                        exception['should_stop'] = False

                        deserialized_exception = DeserializedException(
                            exc_type_str=exception['type'],
                            exc_value_str=exception['message'],
                            exc_traceback_str=exception['traceback']
                        )
                        self.handle_unhandled_exceptions(deserialized_exception, exception, should_stop=False)
                        # self.unhandled_error_observer(None, exception)
                        # self.unreported_error = exception
                    except json.decoder.JSONDecodeError:
                        pass


default_core_exception_handler = CoreExceptionHandler()
