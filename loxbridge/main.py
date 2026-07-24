import sys

from loxone.udp import send_value


LOXONE_IP = "192.168.68.118"
LOXONE_PORT = 7001


def main() -> None:
    if len(sys.argv) != 2:
        print("Použití: python3 app/main.py <hodnota>")
        print("Příklad: python3 app/main.py 1")
        sys.exit(1)

    send_value(
        ip=LOXONE_IP,
        port=LOXONE_PORT,
        value=sys.argv[1],
    )


if __name__ == "__main__":
    main()