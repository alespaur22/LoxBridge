import socket


def send_value(
    ip: str,
    port: int,
    value: bool | int | float | str,
    key: str = "value",
) -> None:
    message = f"{key}={value}"

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.sendto(message.encode("utf-8"), (ip, port))

    print(f"Odesláno do Loxone: {message}")