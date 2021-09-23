import asyncio
import logging
import logging.config
import os
import signal
import sys
from typing import List

import tribler_core
from tribler_common.sentry_reporter.sentry_reporter import SentryReporter, SentryStrategy
from tribler_common.simpledefs import NTFY
from tribler_common.version_manager import VersionHistory
from tribler_core.check_os import check_and_enable_code_tracing, set_process_priority
from tribler_core.components.base import Component, Session
from tribler_core.components.implementation.bandwidth_accounting import BandwidthAccountingComponent, \
    BandwidthAccountingComponent
from tribler_core.components.implementation.gigachannel import GigaChannelComponent, GigaChannelComponent
from tribler_core.components.implementation.gigachannel_manager import GigachannelManagerComponent, \
    GigachannelManagerComponent
from tribler_core.components.implementation.ipv8 import Ipv8Component, Ipv8Component
from tribler_core.components.implementation.libtorrent import LibtorrentComponent, LibtorrentComponent
from tribler_core.components.implementation.masterkey import MasterKeyComponent, MasterKeyComponent
from tribler_core.components.implementation.metadata_store import MetadataStoreComponent, MetadataStoreComponent
from tribler_core.components.implementation.payout import PayoutComponent, PayoutComponent
from tribler_core.components.implementation.popularity import PopularityComponent, PopularityComponent
from tribler_core.components.implementation.reporter import ReporterComponent, ReporterComponent
from tribler_core.components.implementation.resource_monitor import ResourceMonitorComponent, \
    ResourceMonitorComponent
from tribler_core.components.implementation.restapi import RESTComponent, RESTComponent
from tribler_core.components.implementation.socks_configurator import SocksServersComponent, SocksServersComponent
from tribler_core.components.implementation.torrent_checker import TorrentCheckerComponent, TorrentCheckerComponent
from tribler_core.components.implementation.tunnels import TunnelsComponent, TunnelsComponent
from tribler_core.components.implementation.upgrade import UpgradeComponent, UpgradeComponent
from tribler_core.components.implementation.version_check import VersionCheckComponent, VersionCheckComponent
from tribler_core.components.implementation.watch_folder import WatchFolderComponent, WatchFolderComponent
from tribler_core.config.tribler_config import TriblerConfig
from tribler_core.dependencies import check_for_missing_dependencies
from tribler_core.exception_handler import CoreExceptionHandler
from tribler_core.modules.process_checker import ProcessChecker

logger = logging.getLogger(__name__)
CONFIG_FILE_NAME = 'triblerd.conf'


# pylint: disable=import-outside-toplevel


def components_gen(config: TriblerConfig):
    """This function defines components that will be used in Tibler
    """
    yield ReporterComponent()
    if config.api.http_enabled or config.api.https_enabled:
        yield RESTComponent()
    if config.chant.enabled or config.torrent_checking.enabled:
        yield MetadataStoreComponent()
    if config.ipv8.enabled:
        yield Ipv8Component()
    yield MasterKeyComponent()
    if config.libtorrent.enabled:
        yield LibtorrentComponent()
    if config.ipv8.enabled and config.chant.enabled:
        yield GigaChannelComponent()
    if config.ipv8.enabled and config.popularity_community.enabled:
        yield PopularityComponent()
    if config.ipv8.enabled:
        yield BandwidthAccountingComponent()
    if config.resource_monitor.enabled:
        yield ResourceMonitorComponent()

    # The components below are skipped if config.gui_test_mode == True
    if config.gui_test_mode:
        return

    if config.libtorrent.enabled:
        yield SocksServersComponent()
    if config.upgrader_enabled:
        yield UpgradeComponent()
    if config.ipv8.enabled and config.tunnel_community.enabled:
        yield TunnelsComponent()
    if config.ipv8.enabled:
        yield PayoutComponent()
    if config.torrent_checking.enabled:
        yield TorrentCheckerComponent()
    if config.watch_folder.enabled:
        yield WatchFolderComponent()
    if config.general.version_checker_enabled:
        yield VersionCheckComponent()
    if config.chant.enabled and config.chant.manager_enabled and config.libtorrent.enabled:
        yield GigachannelManagerComponent()


async def core_session(config: TriblerConfig, components: List[Component]):
    session = Session(config, components)
    signal.signal(signal.SIGTERM, lambda signum, stack: session.shutdown_event.set)
    session.set_as_default()

    await session.start()

    session.notifier.notify(NTFY.TRIBLER_STARTED, MasterKeyComponent.instance().keypair.key.pk)

    # If there is a config error, report to the user via GUI notifier
    if config.error:
        session.notifier.notify(NTFY.REPORT_CONFIG_ERROR, config.error)

    # SHUTDOWN
    await session.shutdown_event.wait()

    # Indicates we are shutting down core. With this environment variable set
    # to 'TRUE', RESTManager will no longer accept any new requests.
    os.environ['TRIBLER_SHUTTING_DOWN'] = "TRUE"

    await session.shutdown()

    if not config.gui_test_mode:
        session.notifier.notify_shutdown_state("Saving configuration...")
        config.write()


def start_tribler_core(base_path, api_port, api_key, root_state_dir, gui_test_mode=False):
    """
    This method will start a new Tribler session.
    Note that there is no direct communication between the GUI process and the core: all communication is performed
    through the HTTP API.
    """
    # Check for missing Core dependencies
    check_for_missing_dependencies(scope='core')

    logger.info(f'Start tribler core. Base path: "{base_path}". API port: "{api_port}". '
                f'API key: "{api_key}". Root state dir: "{root_state_dir}". '
                f'Core test mode: "{gui_test_mode}"')

    tribler_core.load_logger_config(root_state_dir)

    sys.path.insert(0, base_path)

    # Check if we are already running a Tribler instance
    process_checker = ProcessChecker(root_state_dir)
    if process_checker.already_running:
        return
    process_checker.create_lock_file()

    # Before any upgrade, prepare a separate state directory for the update version so it does not
    # affect the older version state directory. This allows for safe rollback.
    version_history = VersionHistory(root_state_dir)
    version_history.fork_state_directory_if_necessary()
    version_history.save_if_necessary()
    state_dir = version_history.code_version.directory

    config = TriblerConfig.load(file=state_dir / CONFIG_FILE_NAME, state_dir=state_dir, reset_config_on_error=True)
    config.gui_test_mode = gui_test_mode

    if not config.error_handling.core_error_reporting_requires_user_consent:
        SentryReporter.global_strategy = SentryStrategy.SEND_ALLOWED

    config.api.http_port = int(api_port)
    # If the API key is set to an empty string, it will remain disabled
    if config.api.key not in ('', api_key):
        config.api.key = api_key
        config.write()  # Immediately write the API key so other applications can use it
    config.api.http_enabled = True

    priority_order = config.resource_monitor.cpu_priority
    set_process_priority(pid=os.getpid(), priority_order=priority_order)

    # Enable tracer if --trace-debug or --trace-exceptions flag is present in sys.argv
    log_dir = config.general.get_path_as_absolute('log_dir', config.state_dir)
    trace_logger = check_and_enable_code_tracing('core', log_dir)

    logging.getLogger('asyncio').setLevel(logging.WARNING)

    if sys.platform.startswith('win'):
        # TODO for the moment being, we use the SelectorEventLoop on Windows, since with the ProactorEventLoop, ipv8
        # peer discovery becomes unstable. Also see issue #5485.
        asyncio.set_event_loop(asyncio.SelectorEventLoop())

    loop = asyncio.get_event_loop()
    loop.set_exception_handler(CoreExceptionHandler.unhandled_error_observer)

    loop.run_until_complete(core_session(config, components=list(components_gen(config))))

    if trace_logger:
        trace_logger.close()

    process_checker.remove_lock_file()
    # Flush the logs to the file before exiting
    for handler in logging.getLogger().handlers:
        handler.flush()
