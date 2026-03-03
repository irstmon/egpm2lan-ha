"""Constants for the Energenie EG-PM2-LAN integration."""

DOMAIN = "egpm2lan"

CONF_IP = "ip"
CONF_PASSWORD = "password"
CONF_SCAN_INTERVAL = "scan_interval"

DEFAULT_SCAN_INTERVAL = 30  # seconds between status polls
DEFAULT_TIMEOUT = 8  # seconds per HTTP request
NUMBER_OF_SOCKETS = 4

DEFAULT_INTER_OP_DELAY = 5  # seconds between operations
