import logging
import sys


logger = logging.getLogger("LoxBridge")

logger.setLevel(logging.INFO)

handler = logging.StreamHandler(sys.stdout)

formatter = logging.Formatter(
    "%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S",
)

handler.setFormatter(formatter)

logger.addHandler(handler)

logger.propagate = False