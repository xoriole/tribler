"""
This script runs Tribler popularity community and saves the torrents
received to a database so that it can be analyzed. It does not propagate
any torrents to other nodes. It is just an observer node.
"""

import argparse
import asyncio
import inspect
import logging
import os
import time
from binascii import hexlify
from json import dumps
from pathlib import Path
from types import SimpleNamespace

import libtorrent
import sentry_sdk
from pony import orm
from pony.orm import db_session, Database
from pydantic import BaseSettings, Field

from ipv8.lazy_community import lazy_wrapper
from ipv8.taskmanager import TaskManager
from scripts.experiments.popularity_community.component import CustomPopularityComponent
from tribler.core.components.gigachannel.gigachannel_component import GigaChannelComponent
from tribler.core.components.gigachannel_manager.gigachannel_manager_component import GigachannelManagerComponent
from tribler.core.components.ipv8.ipv8_component import Ipv8Component
from tribler.core.components.libtorrent.libtorrent_component import LibtorrentComponent
from tribler.core.components.key.key_component import KeyComponent
from tribler.core.components.metadata_store.db.orm_bindings.channel_node import NEW
from tribler.core.components.metadata_store.metadata_store_component import MetadataStoreComponent
from tribler.core.components.popularity.community.payload import TorrentsHealthPayload
from tribler.core.components.popularity.popularity_component import PopularityComponent
from tribler.core.components.restapi.restapi_component import RESTComponent
from tribler.core.components.socks_servers.socks_servers_component import SocksServersComponent
from tribler.core.components.torrent_checker.torrent_checker_component import TorrentCheckerComponent
from tribler.core.config.tribler_config import TriblerConfig
from tribler.core.components.libtorrent.torrentdef import TorrentDef
from tribler.core.utilities.tiny_tribler_service import TinyTriblerService

# fmt: off
# flake8: noqa

_logger = logging.getLogger('TorrentLogger')

sentry_sdk.init(
    os.environ.get('SENTRY_URL'),
    traces_sample_rate=1.0
)


def parse_args():
    parser = argparse.ArgumentParser(description='Log popular torrents on the Tribler network')
    parser.add_argument('-t', '--tribler_dir', type=str, help='path to data folder', default='/tmp/tribler3')
    parser.add_argument('-v', '--verbosity', help='increase output verbosity', action='store_true')

    return parser.parse_args()


def setup_logger(verbosity):
    logging_level = logging.DEBUG if verbosity else logging.INFO
    logging.basicConfig(level=logging_level)


class Service(TinyTriblerService, TaskManager):
    def __init__(self, config):
        super().__init__(config,
                         working_dir=config.state_dir,
                         components=[RESTComponent(), KeyComponent(), SocksServersComponent(),
                                     LibtorrentComponent(), Ipv8Component(), MetadataStoreComponent(),
                                     GigachannelManagerComponent(), GigaChannelComponent(),
                                     TorrentCheckerComponent(), CustomPopularityComponent()])
        TaskManager.__init__(self)

        # Let the experiment run forever
        # self.register_task('_graceful_shutdown', self._graceful_shutdown, delay=3600)

    def _graceful_shutdown(self):
        task = asyncio.create_task(self.on_tribler_shutdown())
        task.add_done_callback(lambda result: TinyTriblerService._graceful_shutdown(self))

    # async def on_tribler_started(self):
        # self.download_manager = LibtorrentComponent.instance().download_manager

    async def on_tribler_shutdown(self):
        await self.shutdown_task_manager()


def run_tribler(arguments):
    working_dir = Path(arguments.tribler_dir)
    config = TriblerConfig(state_dir=working_dir)
    config.dht.enabled = True
    service = Service(config)

    loop = asyncio.get_event_loop()
    loop.create_task(service.start_tribler())
    try:
        loop.run_forever()
    finally:
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()


if __name__ == "__main__":
    _arguments = parse_args()
    print(f"Arguments: {_arguments}")

    setup_logger(_arguments.verbosity)
    run_tribler(_arguments)
