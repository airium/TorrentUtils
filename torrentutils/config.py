__all__ = [
    'CHECK_URL_FORMAT',
    'RAISE_MALFORMED_URL',
    'URL_UNIQUE_IN_TIERS',
    'KEEP_EMPTY_TIER',
    'URL_PATH_CASE_SENSITIVE',
    'SIMPLE_URL_REGEX',
    'TRACKER_URL_REGEX',
    ]

CHECK_URL_FORMAT: bool = True
RAISE_MALFORMED_URL: bool = False
URL_UNIQUE_IN_TIERS: bool = True
KEEP_EMPTY_TIER: bool = False
URL_PATH_CASE_SENSITIVE: bool = True

import re


SIMPLE_URL_REGEX = re.compile(
    r'^(?P<scheme_host_port>([a-z0-9+.-]+:\/\/)?[a-z0-9.-]+(:[0-9]+)?)'
    r'(?P<leftover>.*)$', re.IGNORECASE
    )

TRACKER_URL_REGEX = re.compile(
    r'^(?P<scheme>udp|http|https):\/\/'
    r'(?P<host>[a-zA-Z0-9\-\.]+)(?::(?P<port>[0-9]+))?'
    r'(?P<path>\/[a-zA-Z0-9\-\.]+)*'
    r'(?P<announce>\/announce)?'
    r'(?P<scrape>\/scrape)?'
    r'(?:\?[a-zA-Z0-9\-\._\?=%&]+)?$',
    re.IGNORECASE
    )

del re
