from __future__ import absolute_import

import logging
import os
import shutil
from pathlib import Path

from pony.orm import db_session

from six.moves.configparser import MissingSectionHeaderError, ParsingError

from twisted.internet.defer import succeed

from Tribler.Core import version
from Tribler.Core.Category.l2_filter import is_forbidden
from Tribler.Core.Modules.MetadataStore.OrmBindings.channel_metadata import CHANNEL_DIR_NAME_LENGTH
from Tribler.Core.Modules.MetadataStore.store import MetadataStore
from Tribler.Core.Upgrade.config_converter import convert_config_to_tribler71, convert_config_to_tribler74
from Tribler.Core.Upgrade.db72_to_pony import DispersyToPonyMigration, cleanup_pony_experimental_db, should_upgrade
from Tribler.Core.Utilities.configparser import CallbackConfigParser
from Tribler.Core.osutils import dir_copy
from Tribler.Core.simpledefs import NTFY_FINISHED, NTFY_STARTED, NTFY_UPGRADER, NTFY_UPGRADER_TICK, \
    STATEDIR_CHANNELS_DIR, STATEDIR_CHECKPOINT_DIR, STATEDIR_DB_DIR, STATEDIR_WALLET_DIR


def cleanup_noncompliant_channel_torrents(state_dir):
    logger = logging.getLogger(__name__)
    channels_dir = os.path.join(state_dir, "channels")
    # Remove torrents contents
    if os.path.exists(channels_dir):
        for d in os.listdir(channels_dir):
            if len(os.path.splitext(d)[0]) != CHANNEL_DIR_NAME_LENGTH:
                dir_path = os.path.join(channels_dir, d)
                # We remove both malformed channel dirs and .torrent and .mdblob files for personal channel
                if os.path.isdir(dir_path):
                    shutil.rmtree(dir_path, ignore_errors=True)
                elif os.path.isfile(dir_path):
                    os.unlink(dir_path)

    # Remove .state torrent resume files
    resume_dir = os.path.join(state_dir, "dlcheckpoints")
    if os.path.exists(resume_dir):
        for f in os.listdir(resume_dir):
            if not f.endswith('.state'):
                continue
            file_path = os.path.join(resume_dir, f)
            pstate = CallbackConfigParser()
            try:
                pstate.read_file(file_path)
            except (ParsingError, MissingSectionHeaderError):
                logger.warning("Parsing channel torrent resume file %s failed, deleting", file_path)
                os.unlink(file_path)
                continue

            if pstate and pstate.has_option('download_defaults', 'channel_download') and \
                    pstate.get('download_defaults', 'channel_download'):
                try:
                    name = pstate.get('state', 'metainfo')['info']['name']
                    if name and len(name) != CHANNEL_DIR_NAME_LENGTH:
                        os.unlink(file_path)
                except (TypeError, KeyError, ValueError):
                    logger.debug("Malfored .pstate file %s found during cleanup of non-compliant channel torrents.",
                                 file_path)


class TriblerUpgrader(object):

    def __init__(self, session):
        self._logger = logging.getLogger(self.__class__.__name__)
        self.session = session

        self.notified = False
        self.is_done = False
        self.failed = True

        self.current_status = u"Initializing"
        self._dtp72 = None
        self.skip_upgrade_called = False

    def skip(self):
        self.skip_upgrade_called = True
        if self._dtp72:
            self._dtp72.shutting_down = True

    def run(self):
        """
        Run the upgrader if it is enabled in the config.

        Note that by default, upgrading is enabled in the config. It is then disabled
        after upgrading to Tribler 7.
        """
        d = self.upgrade_72_to_pony()
        d.addCallback(self.upgrade_pony_db_6to7)
        self.backup_state_directory()
        self.upgrade_config_to_74()
        return d

    def upgrade_pony_db_6to7(self, _):
        """
        Upgrade GigaChannel DB from version 6 (7.3.0) to version 7 (7.3.1).
        Migration should be relatively fast, so we do it in the foreground, without notifying the user
        and breaking it in smaller chunks as we do with 72_to_pony.
        """
        # We have to create the Metadata Store object because the LaunchManyCore has not been started yet
        database_path = os.path.join(self.session.config.get_state_dir(), 'sqlite', 'metadata.db')
        channels_dir = os.path.join(self.session.config.get_chant_channels_dir())
        if not os.path.exists(database_path):
            return succeed(None)
        mds = MetadataStore(database_path, channels_dir, self.session.trustchain_keypair, disable_sync=True)
        with db_session:
            db_version = mds.MiscData.get(name="db_version")
            if int(db_version.value) != 6:
                return succeed(None)
            for c in mds.ChannelMetadata.select():
                if is_forbidden(c.title+c.tags):
                    c.contents.delete()
                    c.delete()
                    # The channel torrent will be removed by GigaChannel manager during the cruft cleanup

        # The process is broken down into batches to limit memory usage
        batch_size = 10000
        with db_session:
            total_entries = mds.TorrentMetadata.select().count()
            page_num = total_entries // batch_size
        while page_num >= 0:
            with db_session:
                for t in mds.TorrentMetadata.select().page(page_num, pagesize=batch_size):
                    if is_forbidden(t.title+t.tags):
                        t.delete()
            page_num -= 1
        with db_session:
            db_version = mds.MiscData.get(name="db_version")
            db_version.value = str(7)
        mds.shutdown()
        return succeed(None)

    def update_status(self, status_text):
        self.session.notifier.notify(NTFY_UPGRADER_TICK, NTFY_STARTED, None, status_text)
        self.current_status = status_text

    def upgrade_72_to_pony(self):
        old_database_path = os.path.join(self.session.config.get_state_dir(), 'sqlite', 'tribler.sdb')
        new_database_path = os.path.join(self.session.config.get_state_dir(), 'sqlite', 'metadata.db')
        channels_dir = os.path.join(self.session.config.get_chant_channels_dir())

        if os.path.exists(new_database_path):
            cleanup_pony_experimental_db(new_database_path)
            cleanup_noncompliant_channel_torrents(self.session.config.get_state_dir())

        self._dtp72 = DispersyToPonyMigration(old_database_path, self.update_status, logger=self._logger)
        if not should_upgrade(old_database_path, new_database_path, logger=self._logger):
            self._dtp72 = None
            return succeed(None)
        # This thing is here mostly for the skip upgrade test to work...
        self._dtp72.shutting_down = self.skip_upgrade_called
        self.notify_starting()
        # We have to create the Metadata Store object because the LaunchManyCore has not been started yet
        mds = MetadataStore(new_database_path, channels_dir, self.session.trustchain_keypair, disable_sync=True)
        self._dtp72.initialize(mds)

        def finish_migration(_):
            mds.shutdown()
            self.notify_done()

        def log_error(failure):
            self._logger.error("Error in Upgrader callback chain: %s", failure)
        return self._dtp72.do_migration().addCallbacks(finish_migration, log_error)

    def upgrade_config_to_74(self):
        """
        This method performs actions necessary to upgrade the configuration files to Tribler 7.4.
        """
        convert_config_to_tribler74()

    def upgrade_config_to_71(self):
        """
        This method performs actions necessary to upgrade the configuration files to Tribler 7.1.
        """
        self.session.config = convert_config_to_tribler71(self.session.config)
        self.session.config.write()

    def backup_state_directory(self):
        """
        Backs up the current state directory if the version in the state directory and in the code is different.
        """
        if not self.session.config.get_version_backup_enabled():
            return

        current_version = self.get_tribler_version()
        if current_version != version.version_id:
            # If current version is None, then the code is pre 7.4, so use .Tribler (root dir) as the state directory
            # instead of versioned directory inside the .Tribler.
            current_state_dir = Path(self.session.config.get_state_dir(version_id=current_version)
                                     if current_version else self.session.config.get_root_state_dir())
            new_state_dir = Path(self.session.config.get_state_dir(version_id=version.version_id))

            # If only there is no tribler config already in the new state directory,
            # then we assume that this is a new version so we copy the last state directory and upgrade it.
            new_conf_path = new_state_dir / 'triblerd.conf'
            if not new_conf_path.exists():
                # Copy the selected directories from the current state directory to the new one.
                upgrade_dirs = [STATEDIR_DB_DIR, STATEDIR_CHECKPOINT_DIR, STATEDIR_WALLET_DIR, STATEDIR_CHANNELS_DIR]
                src_sub_dirs = os.listdir(current_state_dir)
                for upgrade_dir in upgrade_dirs:
                    if upgrade_dir in src_sub_dirs:
                        dir_copy(current_state_dir / upgrade_dir, new_state_dir / upgrade_dir)

                # Copy other important files: keys and config
                extra_files = ['ec_multichain.pem', 'ecpub_multichain.pem', 'ec_trustchain_testnet.pem',
                               'ecpub_trustchain_testnet.pem', 'triblerd.conf']
                for extra_file in extra_files:
                    if os.path.exists(current_state_dir / extra_file):
                        shutil.copy(current_state_dir / extra_file, new_state_dir / extra_file)

            # Update the current version to version_id
            self.set_tribler_version(version.version_id)

    def get_tribler_version(self):
        """
        Returns the last version recorded in .version file else None.
        """
        version_file = Path(self.session.config.get_root_state_dir(), ".version")
        if version_file.exists():
            return version_file.read_text().strip()
        return None

    def set_tribler_version(self, new_version):
        """
        Updates the version to .version file in the state directory.
        """
        Path(self.session.config.get_root_state_dir(), ".version").write_text(new_version)

    def notify_starting(self):
        """
        Broadcast a notification (event) that the upgrader is starting doing work
        after a check has established work on the db is required.
        Will only fire once.
        """
        if not self.notified:
            self.notified = True
            self.session.notifier.notify(NTFY_UPGRADER, NTFY_STARTED, None)

    def notify_done(self):
        """
        Broadcast a notification (event) that the upgrader is done.
        """
        self.session.notifier.notify(NTFY_UPGRADER, NTFY_FINISHED, None)
