#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Run the same flow as tests/test_send.py::test_sign_trc20_transfer
on a real device:
1) Build TriggerSmartContract(TRC20 transfer) payload.
2) Send EXTERNAL_PLUGIN_SETUP (set_external_plugin).
3) Sign with SIGN_EXTERNAL_PLUGIN (include tx length) and verify signature.
4) Broadcast signed transaction.

Requires a Tron app build compiled with `use_test_keys` because the example
uses the test CAL key from `tests/keychain/cal.pem` to authorize the plugin
metadata APDU.
"""

import argparse
import logging
from pathlib import Path

import grpc
from ledgerblue.comm import getDongle
from example_helpers import (ROOT_DIR, WalletStub, build_trigger_smart_contract_tx,
                             ensure_requested_app,
                             encode_address, encode_uint256,
                             evm_address_bytes_from_contract_id, get_account,
                             read_plugin_name, selector_from_signature,
                             sign_and_optionally_broadcast,
                             tron_contract_bytes_from_contract_id)


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


CLA = 0xE0

INS_GET_PUBLIC_KEY = 0x02
INS_SIGN_EXTERNAL_PLUGIN = 0xC4
INS_EXTERNAL_PLUGIN_SETUP = 0x12

P1_FIRST = 0x00
P1_MORE = 0x80
P1_LAST = 0x90
P1_SIGN = 0x10

MAX_APDU_DATA_LEN = 255

# transfer(address to, uint256 value)
TRC20_TRANSFER_SIGNATURE = "transfer(address,uint256)"
DEFAULT_TRC20_TRANSFER_RECIPIENT = "TF17BgPaZYbz8oxbjhriubPDsA7ArKoLX3"
DEFAULT_TRC20_TRANSFER_AMOUNT = 1_000_000
EXTRA_CUSTOM_DATA = (
    "TRON is an open-source public blockchain platform that supports smart contracts. Since TRON is compatible with "
    "Ethereum, you can migrate smart contracts on Ethereum to TRON directly or only with minor modifications. TRON "
    "relies on a unique consensus mechanism to realize the network's high TPS, which is far above Ethereum, bringing "
    "developers a good experience with faster transactions."
).encode()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run TRC20 clear-sign flow with external plugin setup")
    parser.add_argument("--device", help="Ledger device name to use when auto-opening the Tron app.")
    parser.add_argument("--app-name", default="Tron", help="Dashboard application to open.")
    parser.add_argument("--skip-open-app", action="store_true",
                        help="Do not try to switch to the Tron app automatically.")
    parser.add_argument("--with-gui", action="store_true",
                        help="Show Ragger's helper GUI for physical-device actions.")
    parser.add_argument("--path", default="44'/195'/0'/0/0", help="BIP32 path, default: 44'/195'/0'/0/0")
    parser.add_argument(
        "--contract",
        default="TXYZopYRdj2D9XRtbG411XZZ3kM5VkAeBf",
        help="TRC20 contract base58 address",
    )
    parser.add_argument(
        "--makefile",
        default=str(ROOT_DIR / "Makefile"),
        help="Makefile path used to read APPNAME",
    )
    parser.add_argument(
        "--cal-key",
        default=str(ROOT_DIR / "tests" / "keychain" / "cal.pem"),
        help="CAL private key PEM (tests key)",
    )
    parser.add_argument(
        "--grpc-endpoint",
        default="grpc.nile.trongrid.io:50051",
        help="Tron gRPC endpoint used for TriggerContract and BroadcastTransaction",
    )
    parser.add_argument(
        "--fee-limit",
        type=int,
        default=100_000_000,
        help="Transaction fee_limit in sun, default: 100000000",
    )
    parser.add_argument(
        "--to",
        default=DEFAULT_TRC20_TRANSFER_RECIPIENT,
        help=f"TRC20 transfer recipient, default: {DEFAULT_TRC20_TRANSFER_RECIPIENT}",
    )
    parser.add_argument(
        "--amount",
        type=int,
        default=DEFAULT_TRC20_TRANSFER_AMOUNT,
        help=f"TRC20 transfer amount in the token's smallest unit, default: {DEFAULT_TRC20_TRANSFER_AMOUNT}",
    )
    parser.add_argument(
        "--no-broadcast",
        action="store_true",
        help="Build/sign flow only, skip broadcast",
    )
    return parser.parse_args()


def build_trc20_transfer_data(to_address: str, amount: int) -> bytes:
    selector = selector_from_signature(TRC20_TRANSFER_SIGNATURE)
    recipient = evm_address_bytes_from_contract_id(to_address)
    return selector + encode_address(recipient) + encode_uint256(amount)


def main() -> int:
    args = parse_args()
    makefile_path = Path(args.makefile)
    cal_pem_path = Path(args.cal_key)

    plugin_name = read_plugin_name(makefile_path)
    contract_address = tron_contract_bytes_from_contract_id(args.contract)
    transfer_selector = selector_from_signature(TRC20_TRANSFER_SIGNATURE)
    trc20_transfer_data = build_trc20_transfer_data(
        args.to,
        args.amount,
    )

    ensure_requested_app(
        requested_app=args.app_name,
        device_name=args.device,
        skip_open_app=args.skip_open_app,
        with_gui=args.with_gui,
        logger=logger,
    )
    dongle = getDongle(True)
    channel = grpc.insecure_channel(args.grpc_endpoint)
    stub = WalletStub(channel)
    try:
        account = get_account(dongle, args.path)
        logger.info("Using account: %s (%s)", account.address, account.path)
        logger.info("Plugin name: %s", plugin_name)
        logger.info("gRPC endpoint: %s", args.grpc_endpoint)
        logger.info("Transfer recipient: %s", args.to)
        logger.info("Transfer amount: %d", args.amount)

        tx_ext = build_trigger_smart_contract_tx(
            stub=stub,
            owner_address_hex=account.address_hex,
            contract_address=contract_address,
            data=trc20_transfer_data,
        )
        tx_ext.transaction.raw_data.fee_limit = args.fee_limit
        if not sign_and_optionally_broadcast(
            logger=logger,
            dongle=dongle,
            stub=stub,
            account=account,
            tx_ext=tx_ext,
            plugin_name=plugin_name,
            contract_address=contract_address,
            selector=transfer_selector,
            cal_pem_path=cal_pem_path,
            no_broadcast=args.no_broadcast,
            tx_label="tx-1",
        ):
            return 1

        tx_ext_with_custom_data = build_trigger_smart_contract_tx(
            stub=stub,
            owner_address_hex=account.address_hex,
            contract_address=contract_address,
            data=trc20_transfer_data,
        )
        tx_ext_with_custom_data.transaction.raw_data.fee_limit = args.fee_limit
        tx_ext_with_custom_data.transaction.raw_data.data = EXTRA_CUSTOM_DATA
        logger.info(
            "[tx-2-with-custom-data] data length: %d bytes",
            len(EXTRA_CUSTOM_DATA),
        )
        if not sign_and_optionally_broadcast(
            logger=logger,
            dongle=dongle,
            stub=stub,
            account=account,
            tx_ext=tx_ext_with_custom_data,
            plugin_name=plugin_name,
            contract_address=contract_address,
            selector=transfer_selector,
            cal_pem_path=cal_pem_path,
            no_broadcast=args.no_broadcast,
            tx_label="tx-2-with-custom-data",
        ):
            return 1
        return 0
    finally:
        channel.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
