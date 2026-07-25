from loxbridge.bridge.bridge import Bridge
from loxbridge.config.loader import ConfigLoader


def main():
    config = ConfigLoader().load()
    Bridge(config).run()


if __name__ == "__main__":
    main()