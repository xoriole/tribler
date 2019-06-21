import time

import psutil


def pp_seconds(seconds):
    minutes, seconds = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    years, days = divmod(days, 365)
    out = ""
    if years > 0:
        out = str(years) + (" years" if years > 1 else " year")
    if days > 0:
        if out:
            out += ", "
        out += str(days) + (" days"  if days > 1 else " day")
    if hours > 0:
        if out:
            out += ", "
        out += str(hours) + (" hours" if hours > 1 else " hour")
    if minutes > 0:
        if out:
            out += ", "
        out += str(minutes) + (" minutes" if minutes > 1 else " minute")
    if seconds > 0:
        if out:
            out += ", "
        out += str(seconds) + (" seconds"  if seconds > 1 else " second")
    return out


def get_uptime():
    for pid in psutil.pids():
        p = psutil.Process(pid)
        cmd = p.cmdline()
        if (len(cmd) > 1) and (cmd[0].endswith('python')) and (cmd[1] == 'ipv8_service.py'):
            return pp_seconds(time.time() - p.create_time())
    return ""
