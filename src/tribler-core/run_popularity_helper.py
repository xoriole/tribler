"""
This script enables you to start Tribler headless.
"""
import argparse
import os
import signal
import sys
import time
from asyncio import ensure_future, get_event_loop, sleep
from datetime import date

from ipv8.peer import Peer
from ipv8.peerdiscovery.discovery import RandomWalk
from tribler_core.config.tribler_config import TriblerConfig
from tribler_core.modules.popularity.popularity_rtt import PopularityCommunityObserver
from tribler_core.modules.process_checker import ProcessChecker
from tribler_core.session import Session
from tribler_core.utilities.path_util import Path


class TriblerService(object):

    def __init__(self):
        """
        Initialize the variables of the TriblerServiceMaker and the logger.
        """
        self.session = None
        self._stopping = False
        self.process_checker = None

    def log_incoming_remote_search(self, sock_addr, keywords):
        d = date.today()
        with open(os.path.join(self.session.config.get_state_dir(), 'incoming-searches-%s' % d.isoformat()),
                  'a') as log_file:
            log_file.write("%s %s %s %s" % (time.time(), sock_addr[0], sock_addr[1], ";".join(keywords)))

    def tribler_started(self):
        async def signal_handler(sig):
            print("Received shut down signal %s" % sig)
            if not self._stopping:
                self._stopping = True
                await self.session.shutdown()
                get_event_loop().stop()

        signal.signal(signal.SIGINT, lambda sig, _: ensure_future(signal_handler(sig)))
        signal.signal(signal.SIGTERM, lambda sig, _: ensure_future(signal_handler(sig)))

        peer = Peer(self.session.trustchain_testnet_keypair) if self.session.config.get_trustchain_testnet() \
            else Peer(self.session.trustchain_keypair)
        self.session.popularity_community = PopularityCommunityObserver(peer, self.session.ipv8.endpoint,
                                                                        self.session.ipv8.network,
                                                                        metadata_store=self.session.mds,
                                                                        torrent_checker=self.session.torrent_checker)

        self.session.ipv8.overlays.append(self.session.popularity_community)
        self.session.ipv8.strategies.append((RandomWalk(self.session.popularity_community), 20))

    async def start_tribler(self, options):
        """
        Main method to startup Tribler.
        """
        statedir = Path(options.statedir or Path('/tmp', '.Tribler'))
        print(f"state dir:{statedir}")
        config = TriblerConfig(statedir, config_file=statedir / 'triblerd.conf')

        # Check if we are already running a Tribler instance
        self.process_checker = ProcessChecker()
        if self.process_checker.already_running:
            print("Another Tribler instance is already using statedir %s" % config.get_state_dir())
            get_event_loop().stop()
            return

        print("Starting Tribler")

        if options.restapi > 0:
            config.set_api_http_enabled(True)
            config.set_api_http_port(options.restapi)

        if options.ipv8 > 0:
            config.set_ipv8_port(options.ipv8)
        elif options.ipv8 == 0:
            config.set_ipv8_enabled(False)

        if options.testnet:
            config.set_testnet(True)

        config.set_torrent_checking_enabled(True)
        config.set_tunnel_community_enabled(False)
        config.set_ipv8_enabled(True)
        config.set_libtorrent_enabled(True)
        config.set_dht_enabled(True)
        config.set_trustchain_enabled(False)
        config.set_market_community_enabled(False)
        config.set_popularity_community_enabled(False)
        config.set_chant_enabled(True)
        config.set_bootstrap_enabled(False)

        self.session = Session(config)
        try:
            await self.session.start()
        except Exception as e:
            print(str(e))
            get_event_loop().stop()
        else:
            print("Tribler started")
            self.tribler_started()


def main(argv):
    parser = argparse.ArgumentParser(add_help=False, description=('Tribler script, starts Tribler as a service'))
    parser.add_argument('--help', '-h', action='help', default=argparse.SUPPRESS,
                        help='Show this help message and exit')
    parser.add_argument('--statedir', '-s', default=None, help='Use an alternate statedir')
    parser.add_argument('--restapi', '-p', default=-1, type=int, help='Use an alternate port for REST API')
    parser.add_argument('--ipv8', '-i', default=-1, type=int, help='Use an alternate port for the IPv8')
    parser.add_argument('--testnet', '-t', action='store_const', default=False, const=True, help='Join the testnet')

    args = parser.parse_args(sys.argv[1:])
    service = TriblerService()

    loop = get_event_loop()
    coro = service.start_tribler(args)
    ensure_future(coro)

    if sys.platform == 'win32':
        # Unfortunately, this is needed on Windows for Ctrl+C to work consistently.
        # Should no longer be needed in Python 3.8.
        async def wakeup():
            while True:
                await sleep(1)

        ensure_future(wakeup())

    loop.run_forever()


if __name__ == "__main__":
    main(sys.argv[1:])
