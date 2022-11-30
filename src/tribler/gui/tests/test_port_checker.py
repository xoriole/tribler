import asyncio
from unittest.mock import Mock

import pytest
from PyQt5 import QtTest
from PyQt5.QtWidgets import QMainWindow
from pytestqt.exceptions import capture_exceptions
from pytestqt.qtbot import QtBot

from tribler.gui.port_checker import PortChecker


@pytest.fixture(scope="module")
def qtbot_session(qapp):
    print("  SETUP qtbot")
    result = QtBot(qapp)
    with capture_exceptions() as exceptions:
        yield result
    print("  TEARDOWN qtbot")


@pytest.fixture(scope="module")
def dummy_window(qtbot_session):
    print("  SETUP GUI")
    app = QMainWindow()
    bot = QtBot(QMainWindow())
    QtTest.QTest.qWait(2000)

    return app, bot


async def test_port_checker(qapp):
    pid = 100
    port = 20100
    success_callback = Mock()
    timeout_callback = Mock()
    check_interval_in_sec = 0.01
    check_timeout_in_sec = 0.1

    PortChecker.get_process_from_pid = lambda pid: Mock()

    def mock_port_detected(port_checker):
        print(f"calling mock port detected")
        port_checker.detected_port = port

    def mock_port_not_detected(port_checker):
        print(f"calling port not detected")
        port_checker.detected_port = None

    port_checker = PortChecker(pid, port, on_success=success_callback,
                               on_timeout=timeout_callback,
                               check_interval_in_sec=check_interval_in_sec,
                               check_timeout_in_sec=check_timeout_in_sec)
    port_checker._detect_port_from_process = lambda: mock_port_detected(port_checker)
    port_checker.start()
    await asyncio.sleep(check_timeout_in_sec)
    assert success_callback.assert_called_once()
    QtTest.QTest.qWait(2000)
