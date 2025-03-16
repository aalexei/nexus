import logging
import os

LOGLEVEL = os.environ.get('LOGLEVEL', 'INFO').upper()

try:
    logging.basicConfig(format='%(levelname)s:%(message)s', level=LOGLEVEL)
except ValueError:
    logging.basicConfig(format='%(levelname)s:%(message)s', level=logging.INFO)
