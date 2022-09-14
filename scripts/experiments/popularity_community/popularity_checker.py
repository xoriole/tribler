import csv
import time

from scripts.experiments.popularity_community.checker import TorrentChecker

filename = "popularity_community-1663063967.csv"

torrent_checker = TorrentChecker('popular-torrents')
torrent_checker.add_file(filename)
time.sleep(60)
torrent_checker.check_all_torrents()
torrent_checker.get_summary()
torrent_checker.save_results_to_file()


