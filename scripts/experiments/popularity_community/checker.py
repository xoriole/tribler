import csv
import json
import os
import time

import urllib3

CHECKER_BASE_URL = os.environ.get("CHECKER_BASE_URL", None)


class TorrentChecker:

    def __init__(self, name, base_url=None):
        self.name = name
        self.base_url = base_url or CHECKER_BASE_URL
        self.http = urllib3.PoolManager()
        self.torrents = {}

        ts = int(time.time())
        tsmod = ts // 86400
        self.output_file = f"{self.name}-{tsmod}-{ts}.csv"
        print(f"output filename:{self.output_file}")
        self.output_dir = "checked-data"

    def add_file(self, csv_file):
        torrent_dict = {}
        with open(csv_file, 'r') as infile:
            reader = csv.DictReader(infile)
            for row in reader:
                infohash = row['infohash']
                torrent_dict[infohash] = row

        sorted_torrents = dict(sorted(torrent_dict.items(), key=lambda item: -int(item[1]['seeders'])))
        print(f"Adding file: {len(torrent_dict)}")
        num_torrents = 1
        for infohash in torrent_dict:
            print(infohash)
            self.add(infohash, torrent_dict[infohash])
            start_ts = time.time()
            while time.time() - start_ts < 60:
                self.check(infohash)
                time.sleep(5)
            num_torrents += 1
            if num_torrents > 25:
                break

    def add(self, infohash, extra_info=None):
        checker_url = f"{self.base_url}/{infohash}"
        response = self.http.request("POST", checker_url)
        if response.status == 200:
            print(f">> Added {infohash}, {extra_info}")
            self.torrents[infohash] = extra_info or {}

    def is_finished(self, infohash):
        return not self.torrents[infohash].get('keep_checking', True)

    def check(self, infohash):
        if infohash not in self.torrents:
            return
        if self.is_finished(infohash):
            return

        checker_url = f"{self.base_url}/{infohash}"
        response = self.http.request("GET", checker_url)
        # print(f"send check request for {infohash}")
        if response.status == 200:
            json_data = json.loads(response.data)
            payload = json_data['payload']
            for _ih in payload:
                data = payload[_ih]
                max_seeders = data['max_seeders']
                max_leechers = data['max_leechers']
                last_checked = data['last_checked']
                keep_checking = data['keep_checking']
                self.torrents[infohash]['checked_seeders'] = max_seeders
                self.torrents[infohash]['checked_leechers'] = max_leechers
                self.torrents[infohash]['last_checked'] = last_checked
                self.torrents[infohash]['keep_checking'] = keep_checking
                print(f">> {infohash}  seeders:{max_seeders}  leechers:{max_leechers}")

    def keep_checking_until_finished(self):
        finished = False
        start_ts = time.time()
        max_check_time = 60

        print(f"{start_ts}: Check started")
        while not finished and time.time() - start_ts < max_check_time:
            finished = False
            for infohash in self.torrents:
                self.check(infohash)
                # finished |= self.is_finished(infohash)
                time.sleep(0.1)
            print(f">> {int(time.time())}: Check completed; Waiting 1 second")
            time.sleep(1)
        print(f"{int(time.time())}: Check finished")

    def check_all_torrents(self):
        print("==" * 50)
        for infohash in self.torrents:
            self.check(infohash)
        print("==" * 50)

    def get_summary(self):
        for infohash in self.torrents:
            tdata = self.torrents[infohash]
            print(f"{infohash},"
                  f"{tdata['seeders']},"
                  f"{tdata['leechers']},"
                  f"{tdata['checked_seeders']},"
                  f"{tdata['checked_leechers']},"
                  f"{tdata['last_checked']}")

    def save_results_to_file(self):
        filename = f"{self.output_file}"
        with open(filename, 'w+') as outfile:
            for infohash in self.torrents:
                tdata = self.torrents[infohash]
                row = f"{infohash},{tdata['seeders']},{tdata['leechers']},{tdata['checked_seeders']},{tdata['checked_leechers']},{tdata['last_checked']}\n"
                outfile.write(row)
