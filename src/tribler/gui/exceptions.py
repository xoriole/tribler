class CoreError(Exception):
    """This is the base class for exceptions that causes GUI shutdown"""


class CoreConnectionError(CoreError):
    ...


class CoreConnectTimeoutError(CoreError):
    ...


class CoreRestAPITimeoutError(CoreConnectTimeoutError):
    """Raises in case GUI CoreManager can't obtain Core REST API port value"""


class CoreEventsEndpointTimeoutError(CoreConnectTimeoutError):
    """Raises in case GUI EventRequestManager can't connect to EventsEndpoint """


class CoreCrashedError(CoreError):
    """This error raises in case of tribler core finished with error"""


class TriblerGuiTestException(Exception):
    """Can be intentionally generated in GUI by pressing Ctrl+Alt+Shift+G"""


class UpgradeError(CoreError):
    """The error raises by UpgradeManager in GUI process and should stop Tribler"""
