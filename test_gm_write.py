#!/usr/bin/env python3
"""Manual live GM write utility.

This is intentionally not an automated test. It writes to myUplink parameter
40940 and can affect the real heat pump. Use only during supervised debugging.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.abspath('src'))


CONFIRM_FLAG = "--i-understand-this-writes-live-gm"
CONFIRM_ENV = "ALLOW_LIVE_GM_WRITE_TEST"


def parse_args():
    parser = argparse.ArgumentParser(description="Manually write one live GM value to parameter 40940.")
    parser.add_argument("--value", type=int, required=True, help="GM value to write once.")
    parser.add_argument(
        CONFIRM_FLAG,
        action="store_true",
        dest="confirmed",
        help="Required confirmation that this writes to the live heat pump.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    if not args.confirmed or os.getenv(CONFIRM_ENV) != "1":
        raise SystemExit(
            "Refusing live GM write. This utility writes to parameter 40940. "
            f"Pass `{CONFIRM_FLAG}` and set `{CONFIRM_ENV}=1` to run it manually."
        )

    if not -2000 <= args.value <= 200:
        raise SystemExit("Refusing value outside GM safety bounds [-2000, 200].")

    from loguru import logger
    from integrations.auth import MyUplinkAuth
    from integrations.api_client import MyUplinkClient

    auth = MyUplinkAuth()
    client = MyUplinkClient(auth)

    systems = client.get_systems()
    devices = systems[0].get('devices', [])
    if not devices:
        raise SystemExit("No devices found")

    device_id = devices[0]['id']
    current_gm_value = client.get_point_data(device_id, '40940')['value']
    logger.warning(f"Live GM write requested: current 40940={current_gm_value}, new={args.value}")

    response = client.set_point_value(device_id, '40940', args.value)
    logger.info(f"API response: {response}")


if __name__ == "__main__":
    main()
