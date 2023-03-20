from __future__ import annotations

import logging
import struct
from asyncio import DatagramProtocol, Future

from tribler.core.components.socks_servers.socks5.client import Socks5Client


class UdpSocketManager(DatagramProtocol):
    """
    The UdpSocketManager ensures that the network packets are forwarded to the right UdpTrackerSession.
    """

    def __init__(self):
        self._logger = logging.getLogger(self.__class__.__name__)
        self.tracker_sessions = {}
        self.transport = None
        self.proxy_transports = {}

    def connection_made(self, transport):
        self.transport = transport

    async def send_request(self, data, tracker_session):
        transport = self.transport
        proxy = tracker_session.proxy

        if proxy:
            transport = self.proxy_transports.get(proxy, Socks5Client(proxy, self.datagram_received))
            if not transport.associated:
                await transport.associate_udp()
            if proxy not in self.proxy_transports:
                self.proxy_transports[proxy] = transport

        host = tracker_session.ip_address or tracker_session.tracker_address[0]
        try:
            transport.sendto(data, (host, tracker_session.port))
            f = self.tracker_sessions[tracker_session.transaction_id] = Future()
            return await f
        except OSError as e:
            self._logger.warning("Unable to write data to %s:%d - %s",
                                 tracker_session.ip_address, tracker_session.port, e)
            return RuntimeError("Unable to write to socket - " + str(e))

    def datagram_received(self, data, _):
        # If the incoming data is valid, find the tracker session and give it the data
        if data and len(data) >= 4:
            transaction_id = struct.unpack_from('!i', data, 4)[0]
            if transaction_id in self.tracker_sessions:
                session = self.tracker_sessions.pop(transaction_id)
                if not session.done():
                    session.set_result(data)

