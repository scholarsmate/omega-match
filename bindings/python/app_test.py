import logging

logging.basicConfig(level=logging.DEBUG)

from omega_match.omega_match import get_version

logging.info("Library version:", get_version())
