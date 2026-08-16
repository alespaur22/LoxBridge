from __future__ import annotations

import json
import unittest

from loxbridge.homey.event_listener import (
    EventPayloadError,
    parse_event_payload,
)


class EventListenerTests(unittest.TestCase):
    def test_allowed_event_key(self) -> None:
        key = "led_obyvak_input_1_press_2x"

        result = parse_event_payload(
            json.dumps({"key": key}).encode("utf-8"),
            {key},
        )

        self.assertEqual(result, key)

    def test_unknown_event_key_is_rejected(self) -> None:
        with self.assertRaises(EventPayloadError):
            parse_event_payload(
                b'{"key":"unknown_event"}',
                {"known_event"},
            )

    def test_invalid_key_is_rejected(self) -> None:
        with self.assertRaises(EventPayloadError):
            parse_event_payload(
                b'{"key":"../bad"}',
                {"../bad"},
            )


if __name__ == "__main__":
    unittest.main()
