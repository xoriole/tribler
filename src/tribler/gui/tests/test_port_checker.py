import asyncio
import socket
from unittest.mock import MagicMock, Mock, patch

import pytest

from tribler.gui import port_checker
from tribler.gui.port_checker import PortChecker


@pytest.fixture
def mock_port():
    return 20100


@pytest.fixture
def process_with_no_ports():
    process = MagicMock()
    process.connections = lambda _: []
    return process


@pytest.fixture
def process_with_valid_port(mock_port):
    def mocked_connection(port):
        connection = MagicMock()
        connection.status = 'LISTEN'
        connection.type = socket.SocketKind.SOCK_STREAM
        connection.laddr = Mock()
        connection.laddr.ip = '127.0.0.1'
        connection.laddr.port = port
        return connection

    def connections(kind):
        min_port = mock_port - port_checker.MAX_PORTS_TO_CHECK
        max_port = mock_port + port_checker.MAX_PORTS_TO_CHECK
        return [mocked_connection(port) for port in range(min_port, max_port)]

    process = MagicMock()
    process.connections = connections
    return process

@pytest.fixture
def process_with_valid_port(mock_port):
    def mocked_connection(port):
        connection = MagicMock()
        connection.status = 'LISTEN'
        connection.type = socket.SocketKind.SOCK_STREAM
        connection.laddr = Mock()
        connection.laddr.ip = '127.0.0.1'
        connection.laddr.port = port
        return connection

    def connections(kind):
        min_port = mock_port - port_checker.MAX_PORTS_TO_CHECK
        max_port = mock_port + port_checker.MAX_PORTS_TO_CHECK
        return [mocked_connection(port) for port in range(min_port, max_port)]

    process = MagicMock()
    process.connections = connections
    return process

@pytest.fixture
def process_with_invalid_port(mock_port):
    def mocked_connection(con_type, ip, port, status):
        connection = MagicMock()
        connection.status = status
        connection.type = type
        connection.laddr = Mock()
        connection.laddr.ip = ip
        connection.laddr.port = port
        return connection

    def invalid_connection():
        pass

    def connections(kind):
        min_port = mock_port - port_checker.MAX_PORTS_TO_CHECK
        max_port = mock_port + port_checker.MAX_PORTS_TO_CHECK
        return [mocked_connection(port) for port in range(min_port, max_port)]

    process = MagicMock()
    process.connections = connections
    return process


@pytest.fixture
def process_with_invalid_ports(mock_port):
    connection = MagicMock()
    connection.status = 'LISTEN'
    connection.type = socket.SocketKind.SOCK_STREAM
    connection.laddr = Mock()
    connection.laddr.ip = '127.0.0.1'
    connection.laddr.port = mock_port + port_checker.MAX_PORTS_TO_CHECK

    process = MagicMock()
    process.connections = lambda kind: [connection]

    yield process

def mocker_process(mocker):
    mocker.mock_open(read_data="oracle")

async def test_detected_port(mock_port, mocker, process_with_valid_port):
    connection = MagicMock()
    connection.status = 'LISTEN'
    connection.type = socket.SocketKind.SOCK_STREAM
    connection.laddr = Mock()
    connection.laddr.ip = '127.0.0.1'
    connection.laddr.port = mock_port

    def fn_connection():
        print(f"calling connections...")
        return [connection]

    process = MagicMock()
    process.connections = lambda kind: fn_connection()

    # mocker.patch("psutil.Process", return_value=process)
    mocker.patch("psutil.Process", return_value=process_with_valid_port)

    print("patching process here...")
    # process.connections = lambda _: []
    print(f"process connections: {process.connections(None)}")

    callback = MagicMock()
    port_checker = PortChecker(mock_port, callback)

    detected_port = port_checker._detect_port_from_process()
    assert detected_port is None

    process_id = 1024
    port_checker.setup_with_pid(process_id)

    await asyncio.sleep(1.0)

    detected_port = port_checker._detect_port_from_process()
    print(f"port: {detected_port}")


