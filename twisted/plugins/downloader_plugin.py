"""
This twistd plugin enables to start Tribler headless using the twistd command.
"""
from socket import inet_aton
from datetime import date
import os
import signal
import time

import re
from twisted.application.service import MultiService, IServiceMaker
from twisted.conch import manhole_tap
from twisted.internet import reactor
from twisted.internet.task import LoopingCall
from twisted.plugin import IPlugin
from twisted.python import usage
from twisted.python.log import msg
from zope.interface import implements

from Tribler.Core.Config.tribler_config import TriblerConfig
from Tribler.Core.Modules.process_checker import ProcessChecker
from Tribler.Core.Session import Session

# Register yappi profiler
from Tribler.community.allchannel.community import AllChannelCommunity
from Tribler.community.search.community import SearchCommunity
from Tribler.dispersy.utils import twistd_yappi

LOG_TIME = 1
DOWNLOAD_LIMIT = 25 * 1024 * 1024 # 25MB
WAIT_TIME = 30 # 3 min
GATE_THRESHOLD = 0


def check_ipv8_bootstrap_override(val):
    parsed = re.match(r"^([\d\.]+)\:(\d+)$", val)
    if not parsed:
        raise ValueError("Invalid bootstrap address:port")

    ip, port = parsed.group(1), int(parsed.group(2))
    try:
        inet_aton(ip)
    except:
        raise ValueError("Invalid bootstrap server address")

    if port < 0 or port > 65535:
        raise ValueError("Invalid bootstrap server port")
    return ip, port
check_ipv8_bootstrap_override.coerceDoc = "IPv8 bootstrap server address must be in ipv4_addr:port format"


class Options(usage.Options):
    optParameters = [
        ["manhole", "m", 0, "Enable manhole telnet service listening at the specified port", int],
        ["statedir", "s", None, "Use an alternate statedir", str],
        ["restapi", "p", -1, "Use an alternate port for the REST API", int],
        ["dispersy", "d", -1, "Use an alternate port for Dispersy", int],
        ["libtorrent", "l", -1, "Use an alternate port for libtorrent", int],
        ["ipv8_bootstrap_override", "b", None, "Force the usage of specific IPv8 bootstrap server (ip:port)",
         check_ipv8_bootstrap_override],
        ["input_filename", "f", None, "File containing magnet links", str],
        ["output_filename", "o", None, "Output file", str]
    ]
    optFlags = [
        ["auto-join-channel", "a", "Automatically join a channel when discovered"],
        ["log-incoming-searches", "i", "Write information about incoming remote searches to a file"],
        ["testnet", "t", "Join the testnet"]
    ]


class TriblerDownloaderServiceMaker(object):
    implements(IServiceMaker, IPlugin)
    tapname = "downloader"
    description = "Tribler twistd plugin, starts Tribler as a service"
    options = Options

    def __init__(self):
        """
        Initialize the variables of the TriblerServiceMaker and the logger.
        """
        self.session = None
        self._stopping = False
        self.process_checker = None
        self.download_loop = None
        self.output_file = None

    def log_incoming_remote_search(self, sock_addr, keywords):
        d = date.today()
        with open(os.path.join(self.session.config.get_state_dir(), 'incoming-searches-%s' % d.isoformat()), 'a') as log_file:
            log_file.write("%s %s %s %s" % (time.time(), sock_addr[0], sock_addr[1], ";".join(keywords)))

    def shutdown_process(self, shutdown_message, code=1):
        self.download_loop = None
        if self.output_file:
            self.output_file.close()
        msg(shutdown_message)
        reactor.addSystemEventTrigger('after', 'shutdown', os._exit, code)
        reactor.stop()

    def start_tribler(self, options):
        """
        Main method to startup Tribler.
        """
        def on_tribler_shutdown(_):
            msg("Tribler shut down")
            reactor.stop()
            self.process_checker.remove_lock_file()

        def signal_handler(sig, _):
            msg("Received shut down signal %s" % sig)
            if not self._stopping:
                self._stopping = True
                self.session.shutdown().addCallback(on_tribler_shutdown)

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        config = TriblerConfig()

        # Check if we are already running a Tribler instance
        self.process_checker = ProcessChecker()
        if self.process_checker.already_running:
            self.shutdown_process("Another Tribler instance is already using statedir %s" % config.get_state_dir())
            return

        msg("Starting Tribler")

        if options["statedir"]:
            config.set_state_dir(options["statedir"])

        if options["restapi"] > 0:
            config.set_http_api_enabled(True)
            config.set_http_api_port(options["restapi"])

        if options["dispersy"] > 0:
            config.set_dispersy_port(options["dispersy"])
        elif options["dispersy"] == 0:
            config.set_dispersy_enabled(False)

        if options["libtorrent"] != -1 and options["libtorrent"] > 0:
            config.set_libtorrent_port(options["libtorrent"])

        if options["ipv8_bootstrap_override"] is not None:
            config.set_ipv8_bootstrap_override(options["ipv8_bootstrap_override"])

        if "testnet" in options and options["testnet"]:
            config.set_testnet(True)

        input_filename = None
        if options["input_filename"]:
            input_filename = options["input_filename"]

        output_filename = "output.csv"
        if options["output_filename"]:
            output_filename = options["output_filename"]

        config.set_libtorrent_enabled(True)
        config.set_trustchain_enabled(True)
        config.set_credit_mining_enabled(False)
        config.set_popularity_community_enabled(False)

        self.session = Session(config)
        self.session.start().addErrback(lambda failure: self.shutdown_process(failure.getErrorMessage()))
        msg("Tribler started")
        msg("state directory:", config.get_state_dir())

        # If magnet file in provided
        if input_filename and os.path.exists(input_filename):
            magnets = []
            with open(input_filename, 'r') as file:
                magnets = file.readlines()
                msg("lines:%s" % magnets)

            for magnet in magnets:
                msg("Initiated downloading %s" % magnet)
                self.session.start_download_from_uri(magnet)

            self.output_file = open(output_filename, 'a')

            self.download_loop = LoopingCall(self.start_mining)
            self.download_loop.start(LOG_TIME, now=True)

        else:
            msg("No input file provided")

        if "auto-join-channel" in options and options["auto-join-channel"]:
            msg("Enabling auto-joining of channels")
            for community in self.session.get_dispersy_instance().get_communities():
                if isinstance(community, AllChannelCommunity):
                    community.auto_join_channel = True

        if "log-incoming-searches" in options and options["log-incoming-searches"]:
            msg("Logging incoming remote searches")
            for community in self.session.get_dispersy_instance().get_communities():
                if isinstance(community, SearchCommunity):
                    community.log_incoming_searches = self.log_incoming_remote_search

    def start_mining(self):
        msg("=" * 80)

        mining_candidates = {}

        torrent_items = self.session.lm.ltmgr.torrents.iteritems()
        for infohash, (torrentdl, handle) in torrent_items:
            lt_status = torrentdl.get_state().lt_status
            downloaded = lt_status.all_time_download if lt_status else 0
            uploaded = lt_status.all_time_upload if lt_status else 0
            upload_mode = torrentdl.get_upload_mode() or False
            share_mode = torrentdl.get_share_mode() or False
            timestamp = time.time()

            output = "%s, %s, %s, %s, %s, %s" % (infohash, timestamp, downloaded, uploaded, share_mode, upload_mode)
            if self.output_file:
                self.output_file.write(output + "\n")

            msg(output)

            if torrentdl.mining_state == 1:
                if downloaded > DOWNLOAD_LIMIT:
                    torrentdl.set_upload_mode(True)
                    torrentdl.set_upload_start_time(timestamp)
                    torrentdl.mining_state = 2
            elif torrentdl.mining_state == 2:
                if upload_mode:
                    diff = timestamp - torrentdl.get_upload_start_time()
                    if diff > WAIT_TIME:
                        # if uploaded >= GATE_THRESHOLD:
                        #     mining_candidates[infohash] = uploaded

                        torrentdl.set_upload_mode(False)
                        torrentdl.mining_state = 3
            elif torrentdl.mining_state == 3:
                if torrentdl.get_state().get_progress() == 1:
                    torrentdl.mining_state = 4
                    torrentdl.set_upload_mode(True)

        msg("=" * 80)

    def makeService(self, options):
        """
        Construct a Tribler service.
        """
        tribler_service = MultiService()
        tribler_service.setName("Downloader")

        manhole_namespace = {}
        if options["manhole"] > 0:
            port = options["manhole"]
            manhole = manhole_tap.makeService({
                'namespace': manhole_namespace,
                'telnetPort': 'tcp:%d:interface=127.0.0.1' % port,
                'sshPort': None,
                'passwd': os.path.join(os.path.dirname(__file__), 'passwd'),
            })
            tribler_service.addService(manhole)

        reactor.callWhenRunning(self.start_tribler, options)

        return tribler_service

service_maker = TriblerDownloaderServiceMaker()
