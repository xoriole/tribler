import logging
import psutil
import requests
import time
from operator import itemgetter

from bs4 import BeautifulSoup


HOUR = 3600
MB = 1204 * 1024


class MiningState(object):
    """
    Represents the credit mining state for the torrent.
    """
    DOWNLOAD_STATE_1 = 0
    SEEDING_STATE_1 = 1
    DOWNLOAD_STATE_2 = 2
    SEEDING_STATE_2 = 3
    DOWNLOAD_STATE_3 = 4
    SEEDING_STATE_3 = 5

    def __init__(self, state, max_torrents, bandwidth_limit, wait_time, promotion_ratio=1, promotion_interval=5 * 60, upload_mode=False):
        self.state = state
        self.max_torrents = max_torrents
        self.num_torrents = 0
        self.bandwidth_limit = bandwidth_limit
        self.wait_time = wait_time
        self.upload_mode = upload_mode

        self.promotion_ratio = promotion_ratio
        self.promotion_interval = promotion_interval
        self.promotion_candidates = {}
        self.last_promotion_ts = None

    def add_torrent(self):
        if self.num_torrents > self.max_torrents:
            return False
        self.num_torrents += 1
        return True

    def remove_torrent(self):
        if self.num_torrents > 0:
            self.num_torrents -= 1
            return True
        return False

    def add_promotion_candidate(self, infohash, score):
        self.promotion_candidates[infohash] = score

    def pop_best_candidate(self, count=1):
        sorted_candidates = sorted(self.promotion_candidates.items(), key=itemgetter(1), reverse=True)
        return [candidate[0] for candidate in sorted_candidates[:count]]


class BaseMiningPolicy(object):
    """
    Base class for determining what swarm selection policy will be applied
    """
    def __init__(self, url, output_file, session, mining_states, scrape_interval=10 * 60):
        self.url = url
        self.session = session
        self.output_file = output_file
        self.mining_states = mining_states
        self.scrape_interval = scrape_interval

        self.magnets = []
        self.last_scrape_ts = 0

        self.stopped = []

        self.logger = logging.getLogger(__name__)

    def scrape_torrents(self, base_url, num_torrents=30):
        """
        Scrapes magnet links from the url page
        :param base_url: Base url of the torrent website containing magnet links
        :param num_torrents: Number of torrents to extract
        :return: [magnet_links] list of magnet links
        """
        self.last_scrape_ts = time.time()

        # Assuming there are 30 magnet links in a page
        num_pages_to_scrape = num_torrents/30 + 1

        torrent_list = []
        for i in xrange(num_pages_to_scrape):
            # Assuming the pages have url of the following format
            # https://something.com/recent/{page_num}
            webpage_url = "%s/%s" % (base_url, i)
            request = requests.get(webpage_url)

            html_content = request.text
            soup = BeautifulSoup(html_content, "html.parser")

            for link in soup.find_all('a'):
                url = link.get('href')
                if 'magnet:?' in url and url not in torrent_list:
                    torrent_list.append(url)

        print "Extracted %s torrent links" % len(torrent_list)
        return torrent_list

    def execute(self):
        raise NotImplementedError()


class FreshScrapePolicy(BaseMiningPolicy):
    """ Fresh scrape policy """
    def __init__(self, url, output_file, session, mining_states, scrape_interval=10 * 60):
        super(FreshScrapePolicy, self).__init__(url, output_file, session, mining_states, scrape_interval=scrape_interval)

    def execute(self):
        """
        Execute the policy periodically.
        """
        # Add torrents; check if scraping is necessary and add new torrents
        if time.time() - self.last_scrape_ts > self.scrape_interval and self.mining_states[0].add_torrent():
            scraped = self.scrape_torrents(self.url)
            self.logger.info("Scraped %s magnet links", len(scraped))
            for magnet in scraped:
                if magnet not in self.magnets and self.mining_states[0].add_torrent():
                    self.magnets.append(magnet)
                    self.session.start_download_from_uri(magnet)

        # Check and update the states for all torrents
        for infohash, (torrentdl, handle) in self.session.lm.ltmgr.torrents.iteritems():
            # state information
            lt_status = torrentdl.get_state().lt_status
            downloaded = lt_status.all_time_download if lt_status else 0
            uploaded = lt_status.all_time_upload if lt_status else 0
            upload_mode = torrentdl.get_upload_mode() or False
            share_mode = torrentdl.get_share_mode() or False
            timestamp = time.time()

            output = "%s, %s, %s, %s, %s, %s" % (infohash, timestamp, downloaded, uploaded, share_mode, upload_mode)
            self.output_file.write(output + "\n")
            print output

            mining_state = self.mining_states[torrentdl.mining_state]
            if mining_state.upload_mode:
                diff = timestamp - torrentdl.get_upload_start_time()
                if diff > mining_state.time:
                    if uploaded > mining_state.bandwidth_limit:
                        if mining_state.add_torrent():
                            torrentdl.set_upload_mode(False)
                            torrentdl.mining_state += 1
            else:
                if downloaded > mining_state.bandwidth_limit:
                    print "upgrading state: downloaded:%s, limit:%s" % (downloaded, mining_state.bandwidth_limit)
                    torrentdl.set_upload_mode(True)
                    torrentdl.set_upload_start_time(timestamp)
                    torrentdl.mining_state += 1


class TimeConstraintFullDownloadPolicy(BaseMiningPolicy):
    """ Time constrained limited full download policy """

    def __init__(self, url, output_file, session, mining_states, scrape_interval=5 *60):
        super(TimeConstraintFullDownloadPolicy, self).__init__(url, output_file, session, mining_states, scrape_interval=scrape_interval)

    def execute(self):
        """
        Execute the policy periodically.
        """
        self.logger.info("\n\n")
        # Add torrents; check if scraping is necessary and add new torrents
        if time.time() - self.last_scrape_ts > self.scrape_interval and self.mining_states[0].add_torrent():
            scraped = self.scrape_torrents(self.url)
            self.logger.info("Scraped %s magnet links", len(scraped))
            for magnet in scraped:
                if magnet not in self.magnets and self.mining_states[0].add_torrent():
                    self.magnets.append(magnet)
                    self.session.start_download_from_uri(magnet)

        # Check and update the states for all torrents
        for infohash, (torrentdl, handle) in self.session.lm.ltmgr.torrents.iteritems():
            # state information
            lt_status = torrentdl.get_state().lt_status
            downloaded = lt_status.all_time_download if lt_status else 0
            uploaded = lt_status.all_time_upload if lt_status else 0
            upload_mode = torrentdl.get_upload_mode() or False
            share_mode = torrentdl.get_share_mode() or False
            timestamp = time.time()
            num_peers = len(torrentdl.get_peerlist()) or 0

            output = "%s, %s, %s, %s, %s, %s, %s, %s" % (infohash, timestamp, downloaded, uploaded, num_peers,
                                                         share_mode, upload_mode, torrentdl.mining_state)
            self.output_file.write(output + "\n")
            print output

            if infohash in self.stopped:
                continue

            mining_state = self.mining_states[torrentdl.mining_state]

            if torrentdl.mining_state == MiningState.DOWNLOAD_STATE_1:
                if downloaded > mining_state.bandwidth_limit:
                    torrentdl.set_upload_mode(True)
                    torrentdl.set_upload_start_time(timestamp)
                    torrentdl.mining_state += 1
                else:
                    diff = time.time() - torrentdl.add_time
                    if diff > mining_state.wait_time and infohash not in self.stopped:
                        print "Removing torrent [%s]; Too low download; downloaded: %s in %s seconds" % (infohash, downloaded, diff)
                        torrentdl.stop_remove(removestate=False, removecontent=False)
                        self.stopped.append(infohash)

            elif torrentdl.mining_state == MiningState.SEEDING_STATE_1:
                    diff = timestamp - torrentdl.get_upload_start_time()
                    if diff > mining_state.wait_time:
                        if uploaded < mining_state.bandwidth_limit:
                            print "Removing torrent [%s]; Too low upload; uploaded: %s in %s seconds" % (infohash, uploaded, diff)
                            torrentdl.stop_remove(removestate=False, removecontent=False)
                            self.stopped.append(infohash)
                        else:
                            ratio = uploaded / diff
                            mining_state.add_promotion_candidate(infohash, ratio)

            elif torrentdl.mining_state == MiningState.DOWNLOAD_STATE_2:
                if torrentdl.get_state().get_progress() == 1:
                    torrentdl.mining_state += 1
                    torrentdl.set_upload_mode(True)

        # Check for promotions
        print "***" * 10, "Checking promotion states ", "***" * 10
        for mining_state in self.mining_states:
            print "state[%s]-> %s candidates, upload_mode:%s" % (mining_state.state, len(mining_state.promotion_candidates), mining_state.upload_mode)

            if mining_state == self.mining_states[-1]:
                break

            if not mining_state.last_promotion_ts:
                mining_state.last_promotion_ts = time.time()
                continue

            diff = time.time() - mining_state.last_promotion_ts
            should_promote = diff >= mining_state.promotion_interval
            print "last promotion:%s, diff:%s, interval:%s, should_promote:%s" % (mining_state.last_promotion_ts, diff, mining_state.promotion_interval, should_promote)
            if mining_state.upload_mode and should_promote:

                mining_state.last_promotion_ts = time.time()
                best_candidates = mining_state.pop_best_candidate()
                print "promotion candidate:%s" % best_candidates
                next_mining_state = self.mining_states[mining_state.state + 1] \
                    if len(self.mining_states) > mining_state.state else None

                if next_mining_state and best_candidates:

                    (torrentdl, handle) = self.session.lm.ltmgr.torrents[best_candidates[0]]
                    print "promotion torrent:%s, %s" % (torrentdl, handle)
                    if next_mining_state and next_mining_state.add_torrent():

                        print "promoted %s", best_candidates[0]
                        torrentdl.set_upload_mode(False)
                        torrentdl.mining_state += 1
                        del mining_state.promotion_candidates[best_candidates[0]]

        self.logger.info("\n\n")


class FreshScrapeWithFairComparePolicy(BaseMiningPolicy):
    """ Fresh scrape policy with fair compare """
    def __init__(self, url, output_file, session, mining_states, scrape_interval=10 * 60):
        super(FreshScrapeWithFairComparePolicy, self).__init__(url, output_file, session, mining_states,
                                                               scrape_interval=scrape_interval)

    def should_add_torrent(self):
        state2_slot_available = self.mining_states[MiningState.DOWNLOAD_STATE_2].num_torrents < self.mining_states[MiningState.DOWNLOAD_STATE_2].max_torrents
        state3_slot_available = self.mining_states[MiningState.DOWNLOAD_STATE_3].num_torrents < self.mining_states[MiningState.DOWNLOAD_STATE_3].max_torrents
        if state2_slot_available or state3_slot_available:
            return True
        return False

    def execute(self):
        """
        Execute the policy periodically.
        """
        self.logger.info("\n\n")
        # Add torrents; check if scraping is necessary and add new torrents
        if time.time() - self.last_scrape_ts > self.scrape_interval and self.mining_states[0].add_torrent() and self.should_add_torrent():
            scraped = self.scrape_torrents(self.url)
            print "Scraped %s magnet links" % len(scraped)
            for magnet in scraped:
                if magnet not in self.magnets and self.mining_states[0].add_torrent():
                    self.magnets.append(magnet)
                    self.session.start_download_from_uri(magnet)

        # Check and update the states for all torrents
        for infohash, (torrentdl, handle) in self.session.lm.ltmgr.torrents.iteritems():
            # state information
            lt_status = torrentdl.get_state().lt_status
            downloaded = lt_status.total_payload_download if lt_status else 0
            uploaded = lt_status.total_payload_upload if lt_status else 0
            upload_mode = torrentdl.get_upload_mode() or False
            share_mode = torrentdl.get_share_mode() or False
            timestamp = time.time()
            num_peers = len(torrentdl.get_peerlist()) or 0

            output = "%s, %s, %s, %s, %s, %s, %s, %s" % (infohash, timestamp, downloaded, uploaded, num_peers,
                                                         share_mode, upload_mode, torrentdl.mining_state)
            self.output_file.write(output + "\n")
            self.logger.info(output)
            print output

            mining_state = self.mining_states[torrentdl.mining_state]
            if mining_state.upload_mode:
                diff = timestamp - torrentdl.get_upload_start_time()
                if diff > mining_state.wait_time:
                    if uploaded > mining_state.bandwidth_limit:
                        ratio = uploaded/diff
                        mining_state.add_promotion_candidate(infohash, ratio)
            else:
                if downloaded > mining_state.bandwidth_limit:
                    torrentdl.set_upload_mode(True)
                    torrentdl.set_upload_start_time(timestamp)
                    torrentdl.mining_state += 1

        # Check for promotions
        print "***" * 10, "Checking promotion states ", "***" * 10
        for mining_state in self.mining_states:
            print "state[%s]-> %s candidates, upload_mode:%s" % (mining_state.state, len(mining_state.promotion_candidates), mining_state.upload_mode)
            if mining_state == self.mining_states[-1]:
                break
            if not mining_state.last_promotion_ts:
                mining_state.last_promotion_ts = time.time()
                continue
            diff = time.time() - mining_state.last_promotion_ts
            should_promote = diff >= mining_state.promotion_interval
            print "last promotion:%s, diff:%s, interval:%s, should_promote:%s" % (mining_state.last_promotion_ts, diff, mining_state.promotion_interval, should_promote)
            if mining_state.upload_mode and should_promote:
                mining_state.last_promotion_ts = time.time()
                best_candidates = mining_state.pop_best_candidate()
                print "promotion candidate:%s" % best_candidates
                next_mining_state = self.mining_states[mining_state.state + 1] \
                    if len(self.mining_states) > mining_state.state else None
                if next_mining_state and best_candidates:
                    (torrentdl, handle) = self.session.lm.ltmgr.torrents[best_candidates[0]]
                    print "promotion torrent:%s, %s" % (torrentdl, handle)
                    if next_mining_state and next_mining_state.add_torrent():
                        print "promoted %s", best_candidates[0]
                        torrentdl.set_upload_mode(False)
                        torrentdl.mining_state += 1
                        del mining_state.promotion_candidates[best_candidates[0]]

        self.logger.info("\n\n")


class MultiLevelInvestmentPolicy(BaseMiningPolicy):
    """
    Multi level investment policy.
    Multiple investment levels are set and when a torrent downloads a specific bandwidth limit of the level, it is
    set to upload mode and keeps waiting until the same amount is uploaded, in which case it is promoted to the next
    level.
    """

    def __init__(self, session, mining_states, settings):
        super(MultiLevelInvestmentPolicy, self).__init__(settings["url"], settings["output_file"],
                                                         session, mining_states,
                                                         scrape_interval=settings["scrape_interval"])

        self.settings = settings
        self.round_counter = 0
        self.active_torrents = 0

        self.last_download_sum = 0
        self.last_reserve_sum = 0

    def get_stats(self, torrent_download):
        timestamp = time.time()
        lt_status = torrent_download.get_state().lt_status
        downloaded = lt_status.total_payload_download if lt_status else 0
        uploaded = lt_status.total_payload_upload if lt_status else 0
        upload_mode = torrent_download.get_upload_mode() or False
        share_mode = torrent_download.get_share_mode() or False
        num_peers = len(torrent_download.get_peerlist()) or 0
        return timestamp, downloaded, uploaded, num_peers, share_mode, upload_mode

    def fill_new_torrents(self):
        # Add torrents; check if scraping is necessary and add new torrents
        if time.time() - self.last_scrape_ts > self.scrape_interval \
                and self.active_torrents < self.settings["max_torrents"]:

            scraped = self.scrape_torrents(self.url)
            print "Scraped %s magnet links" % len(scraped)

            for magnet in scraped:
                if self.active_torrents >= self.settings["max_torrents"]:
                    break
                if magnet not in self.magnets:
                    self.active_torrents += 1
                    self.magnets.append(magnet)
                    self.session.start_download_from_uri(magnet)

    def execute(self):
        self.logger.info("\n\n")
        self.round_counter += 1

        # Add torrents; check if scraping is necessary and add new torrents
        self.fill_new_torrents()

        # Check and update the states for all torrents
        download_sum = 0
        reserve_sum = 0
        new_reserve_sum = 0
        index = 0
        for infohash, (torrentdl, handle) in self.session.lm.ltmgr.torrents.iteritems():
            # state information
            timestamp, downloaded, uploaded, num_peers, share_mode, upload_mode = self.get_stats(torrentdl)
            download_sum += downloaded
            index += 1

            output = "%s, %s, %s, %s, %s, %s, %s, %s, %s, %s" % (self.round_counter, index, infohash, timestamp,
                                                                 downloaded, uploaded, num_peers, share_mode,
                                                                 upload_mode, torrentdl.mining_state)
            self.output_file.write(output + "\n")
            self.logger.info(output)
            print output

            mining_state = self.mining_states[torrentdl.mining_state]
            if mining_state == self.mining_states[-1]:
                continue
            if mining_state.upload_mode:
                next_mining_state = self.mining_states[mining_state.state + 1]
                if next_mining_state and uploaded > mining_state.bandwidth_limit:
                    if self.last_download_sum + self.last_reserve_sum + new_reserve_sum < self.settings["max_storage"]:
                        torrentdl.set_upload_mode(False)
                        torrentdl.mining_state += 1
                        new_reserve_sum += next_mining_state.bandwidth_limit - downloaded
            else:
                diff = mining_state.bandwidth_limit - downloaded
                if diff > 0:
                    reserve_sum += diff
                else:
                    torrentdl.set_upload_mode(True)
                    torrentdl.mining_state += 1

        # update the sum states
        self.last_download_sum = download_sum
        self.last_reserve_sum = reserve_sum

        self.logger.info("\n\n")


class MultiLevelGreedySpacePolicy(BaseMiningPolicy):
    """
    Aggressive multilevel investment policy  with periodic deletion
    Level limit download follows the progression: a, a + a/2, ...
    Level limit upload follows in times of download limit: 2, 3, 4, 5, 6, ...

    Deletion policy:
       delete if
        - Time: 1H, Upload: < 5MB
        - Time: 12H, Upload: < 50MB
        - Time: 24H, Upload: < 100MB
        - Time: 48H, Upload: < 250MB
        - Time: 72H, Delete anyway

    Torrents are replaced every 72hours even if they were performing well.
    """

    def __init__(self, session, mining_states, settings):
        super(MultiLevelGreedySpacePolicy, self).__init__(settings["url"], settings["output_file"],
                                                          session, mining_states,
                                                          scrape_interval=settings["scrape_interval"])

        self.settings = settings
        self.round_counter = 0
        self.active_torrents = 0

        self.last_download_sum = 0
        self.last_reserve_sum = 0

    def get_stats(self, torrent_download):
        timestamp = time.time()
        lt_status = torrent_download.get_state().lt_status
        downloaded = lt_status.total_payload_download if lt_status else 0
        uploaded = lt_status.total_payload_upload if lt_status else 0
        upload_mode = torrent_download.get_upload_mode() or False
        share_mode = torrent_download.get_share_mode() or False
        num_peers = len(torrent_download.get_peerlist()) or 0
        return timestamp, downloaded, uploaded, num_peers, share_mode, upload_mode

    def fill_new_torrents(self):
        # Add torrents; check if scraping is necessary and add new torrents
        if time.time() - self.last_scrape_ts > self.scrape_interval \
                and self.active_torrents < self.settings["max_torrents"]:

            scraped = self.scrape_torrents(self.url)
            print "Scraped %s magnet links" % len(scraped)

            for magnet in scraped:
                if self.active_torrents >= self.settings["max_torrents"]:
                    break
                if magnet not in self.magnets:
                    self.active_torrents += 1
                    self.magnets.append(magnet)
                    self.session.start_download_from_uri(magnet)

    def execute(self):
        self.logger.info("\n\n")
        self.round_counter += 1

        # Add torrents; check if scraping is necessary and add new torrents
        self.fill_new_torrents()

        # Check and update the states for all torrents
        download_sum = 0
        reserve_sum = 0
        new_reserve_sum = 0
        index = 0

        for infohash, (torrentdl, handle) in self.session.lm.ltmgr.torrents.iteritems():
            # state information
            timestamp, downloaded, uploaded, num_peers, share_mode, upload_mode = self.get_stats(torrentdl)
            download_sum += downloaded
            index += 1

            # Check for potential deletion
            diff_time = timestamp - torrentdl.add_time
            should_remove = diff_time > HOUR and uploaded < 5 * MB \
                or diff_time > 12 * HOUR and uploaded < 50 * MB \
                or diff_time > 24 * HOUR and uploaded < 100 * MB \
                or diff_time > 48 * HOUR and uploaded < 250 * MB \
                or diff_time > 72 * HOUR

            output = "%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s" % (self.round_counter, index, infohash, timestamp,
                                                                 downloaded, uploaded, num_peers, share_mode,
                                                                 upload_mode, torrentdl.mining_state, should_remove)
            self.output_file.write(output + "\n")
            self.logger.info(output)
            print output

            # Remove the state and download if the torrent is eligible for deletion
            if should_remove:
                torrentdl.stop_remove(removestate=True, removecontent=True)
                self.active_torrents -= 1
                continue

            mining_state = self.mining_states[torrentdl.mining_state]
            if mining_state == self.mining_states[-1]:
                continue
            if mining_state.upload_mode:
                next_mining_state = self.mining_states[mining_state.state + 1]
                if next_mining_state and uploaded > mining_state.promotion_ratio * mining_state.bandwidth_limit:
                    if self.last_download_sum + self.last_reserve_sum + new_reserve_sum < self.settings["max_storage"]:
                        torrentdl.set_upload_mode(False)
                        torrentdl.mining_state += 1
                        new_reserve_sum += next_mining_state.bandwidth_limit - downloaded
            else:
                diff = mining_state.bandwidth_limit - downloaded
                if diff > 0:
                    reserve_sum += diff
                else:
                    torrentdl.set_upload_mode(True)
                    torrentdl.mining_state += 1

        # update the sum states
        self.last_download_sum = download_sum
        self.last_reserve_sum = reserve_sum

        self.logger.info("\n\n")
