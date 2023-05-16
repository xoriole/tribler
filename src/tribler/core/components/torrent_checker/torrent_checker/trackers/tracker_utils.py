import socket
from asyncio import get_event_loop

from tribler.core.components.torrent_checker.torrent_checker.trackers import TrackerException


async def resolve_ip(tracker_address):
    try:
        infos = await get_event_loop().getaddrinfo(tracker_address[0], 0, family=socket.AF_INET)
        ip_address = infos[0][-1][0]
        return ip_address
    except socket.gaierror as e:
        raise TrackerException("Socket error resolving tracker ip") from e
