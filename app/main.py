import socket
import sys

LOXONE_IP = "192.168.68.118"
LOXONE_PORT = 7001


def send_value(value: str) -> None:
    message = f"value={value}"

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.sendto(
            message.encode("utf-8"),
            (LOXONE_IP, LOXONE_PORT),
        )

    print(f"Odesláno do Loxone: {message}")


def main() -> None:
    if len(sys.argv) != 2:
        print("Použití: python3 app/main.py <hodnota>")
        print("Příklad: python3 app/main.py 1")
        sys.exit(1)

    send_value(sys.argv[1])


if __name__ == "__main__":
    main()