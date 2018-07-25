"""
This twistd plugin enables to start Tribler headless using the twistd command.
"""
import os
import re
import shutil
import signal
import time
from Tribler.Core.DownloadConfig import DefaultDownloadStartupConfig
from socket import inet_aton
from twisted.application.service import MultiService, IServiceMaker
from twisted.conch import manhole_tap
from twisted.internet import reactor
from twisted.internet.task import LoopingCall
from twisted.plugin import IPlugin
from twisted.python import usage
from twisted.python.log import msg
from zope.interface import implements

from Tribler.Core.Config.tribler_config import TriblerConfig
from Tribler.Core.CreditMining.LiveCreditMiningPolicy import MiningState, FreshScrapeWithFairComparePolicy, \
    FreshScrapePolicy, TimeConstraintFullDownloadPolicy
from Tribler.Core.Modules.process_checker import ProcessChecker
from Tribler.Core.Session import Session
from Tribler.community.allchannel.community import AllChannelCommunity
from check_os import enable_fault_handler

LOG_TIME = 5
INITIAL_INVESTMENT_DOWNLOAD_LIMIT = 25 * 1024 * 1024  # 25MB
SECONDARY_INVESTMENT_DOWNLOAD_LIMIT = 500 * 1024 * 1024  # 500MB
INITIAL_INVESTMENT_DOWNLOAD_TIME = 3 * 60  # 3 mins to download gate download amount
WAIT_TIME = 3 * 60  # 3 min
MINIMUM_UPLOAD_THRESHOLD = 1 * 1024 * 1024
MAX_FULL_DOWNLOADS = 10
SCRAPE_INTERVAL = 10 * 60  # 10 Minutes
MAX_TORRENTS = 200

INITIAL_INVESTMENT_DOWNLOAD = 1
INITIAL_INVESTMENT_SEEDING = 2
SECONDARY_INVESTMENT_DOWNLOAD = 3
SECONDARY_INVESTMENT_SEEDING = 4

# Enable fault handler to check for segfaults
enable_fault_handler()


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
        ["output-file", "o", None, "Output file", str],
        ["input-url", "u", '', "Input URL", str]
    ]
    optFlags = [
        ["auto-join-channel", "a", "Automatically join a channel when discovered"]
    ]


class TriblerLiveDownloaderServiceMaker(object):
    implements(IServiceMaker, IPlugin)
    tapname = "live_download"
    description = "Tribler twistd plugin, starts Tribler as a service"
    options = Options

    def __init__(self):
        """
        Initialize the variables of the TriblerServiceMaker and the logger.
        """
        self.session = None
        self._stopping = False
        self.process_checker = None
        self.mining_loop = None
        self.output_file = None
        self.url = None

    def shutdown_process(self, shutdown_message, code=1):
        self.mining_loop = None
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

        shutil.rmtree(config.get_state_dir())
        download_dir = DefaultDownloadStartupConfig.getInstance().get_dest_dir()
        shutil.rmtree(download_dir)

        if not options["input-url"]:
            msg("No input url found")
            exit(1)
        else:
            self.url = options["input-url"]

        output_filename = "output.csv"
        if options["output-file"]:
            output_filename = options["output-file"]
        # Add timestamp prefix to output file
        output_filename = "%s.%s" % (int(time.time()), output_filename)
        self.output_file = open(output_filename, 'a')

        config.set_libtorrent_enabled(True)
        config.set_trustchain_enabled(True)
        config.set_credit_mining_enabled(False)
        config.set_popularity_community_enabled(False)

        self.session = Session(config)
        self.session.start().addErrback(lambda failure: self.shutdown_process(failure.getErrorMessage()))
        msg("Tribler started")
        msg("state directory:", config.get_state_dir())

        # Setup credit mining policy
        policy = self.create_policy_1_or_2()

        self.mining_loop = LoopingCall(policy.execute)
        self.mining_loop.start(LOG_TIME, now=True)

        if "auto-join-channel" in options and options["auto-join-channel"]:
            msg("Enabling auto-joining of channels")
            for community in self.session.get_dispersy_instance().get_communities():
                if isinstance(community, AllChannelCommunity):
                    community.auto_join_channel = True

    def create_policy_1_or_2(self):
        # Setup credit mining policy 1 or 2, the difference lies on the input whether popular torrents or recent ones
        # are used.
        mining_states = [MiningState(MiningState.DOWNLOAD_STATE_1, 100, 25 * 1024 * 1024, 10 * 60),  # 25MB, no time limit
                         MiningState(MiningState.SEEDING_STATE_1, -1, 1 * 1024 * 1024, 10 * 60, promotion_interval = 10, upload_mode=True),  # 1MB, 5MIN limit
                         MiningState(MiningState.DOWNLOAD_STATE_2, 10, -1, -1),  # full download, no time limit
                         MiningState(MiningState.SEEDING_STATE_2, -1, -1, -1, upload_mode=True)]  # no limit, no time limit

        return TimeConstraintFullDownloadPolicy(self.url, self.output_file, self.session, mining_states, scrape_interval=10)

    def create_policy_3(self):
        # Setup credit mining policy 3
        mining_states = [MiningState(MiningState.DOWNLOAD_STATE_1, 200, 25 * 1024 * 1024, -1),  # 25MB, no time limit
                         MiningState(MiningState.SEEDING_STATE_1, -1, 1 * 1024 * 1024, 5 * 60, upload_mode=True),  # 1MB, 5MIN limit
                         MiningState(MiningState.DOWNLOAD_STATE_2, 190, 500 * 1024 * 1024, -1),  # 500MB, no time limit
                         MiningState(MiningState.SEEDING_STATE_2, -1, -1, -1, upload_mode=True)]  # no limit, no time limit

        return FreshScrapePolicy(self.url, self.output_file, self.session, mining_states,
                                 scrape_interval=10*60)

    def create_policy_4(self):
        # Setup credit mining policy 4
        mining_states = [MiningState(MiningState.DOWNLOAD_STATE_1, 1000, 25 * 1024 * 1024, -1),  # 1000 torrents, 25MB, no time limit
                         MiningState(MiningState.SEEDING_STATE_1, -1, 1 * 1024 * 1024, 5 * 60, upload_mode=True),  # 1MB, 5MIN limit
                         MiningState(MiningState.DOWNLOAD_STATE_2, 100, 250 * 1024 * 1024, -1),  # 100 torrents, 500MB, no time limit
                         MiningState(MiningState.SEEDING_STATE_2, -1, 25 * 1024 * 1024, 5 * 60, upload_mode=True),  # 1MB, 5MIN limit
                         MiningState(MiningState.DOWNLOAD_STATE_3, 25, 1024 * 1024 * 1024, -1),  # 25 torrents, 1GB, no time limit
                         MiningState(MiningState.SEEDING_STATE_3, -1, -1, -1, upload_mode=True)]  # no limit, no time limit

        return FreshScrapeWithFairComparePolicy(self.url, self.output_file, self.session, mining_states,
                                                scrape_interval=15 * 60)

    def makeService(self, options):
        """
        Construct a Tribler service.
        """
        tribler_service = MultiService()
        tribler_service.setName("Live Downloader")

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


service_maker = TriblerLiveDownloaderServiceMaker()
