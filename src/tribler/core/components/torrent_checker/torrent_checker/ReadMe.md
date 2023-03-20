# Torrent Checker 

Torrent Checker component is responsible for persisting and returning the health information of a torrent 
given an infohash.

There are two sub-components on Torrent Checker.
1. DB Component
2. Checker Component

Torrent Checker is also responsible for periodically checking the torrents and trackers so that health information 
remains up to date.

## DB Component
DB Component is responsible for persisting newly received health information of a torrent and returning the last saved 
information of the torrent.

## Checker Component
Checker component is responsible for checking the health of torrent using the trackers or DHT. This component returns 
the health information after checking it immediately. This component does not persist anything on the disk or the 
database and uses RAM storage only.

Checker component includes the following checkers:
1. UDP Tracker 
2. HTTP Tracker 
3. DHT Tracker