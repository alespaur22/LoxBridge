import socket


def send_value(ip: str, port: int, value: str) -> None:
    message = f"value={value}"

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.sendto(
            message.encode("utf-8"),
            (ip, port),
        )

    print(f"Odesláno do Loxone: {message}")