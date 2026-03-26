#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Run the same flow as tests/test_swap.py::test_swap_exact_trx_for_token
on a real device:
1) Build TriggerSmartContract(swapExactTRXForTokens) payload.
2) Send EXTERNAL_PLUGIN_SETUP (set_external_plugin).
3) Sign with SIGN_EXTERNAL_PLUGIN (include tx length) and verify signature.
4) Broadcast signed transaction.
"""

import argparse
import logging
import time
from pathlib import Path

import grpc
from ledgerblue.comm import getDongle
from example_helpers import (ROOT_DIR, WalletStub, build_trigger_smart_contract_tx,
                             encode_address, encode_address_array,
                             encode_uint256, evm_address_bytes_from_contract_id,
                             get_account, read_plugin_name,
                             selector_from_signature,
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

DEFAULT_SWAP_CONTRACT = "TM2dkGswmejM9FbKGWkjtugN34c6ZBxjzJ"
DEFAULT_CALL_VALUE = 100_000
DEFAULT_AMOUNT_OUT_MIN = 28_500_000
DEFAULT_PATH = "TTVHrJWLPEMpsRJLs14bAZTpfXB5HBmNRa,TKk5VY5HxbYJFc3nTr6XjV42n5LXdorkoB"
DEFAULT_TO = "TVjpchRyV9wdpj6kmwqVsBDWY1J8PaFtnb"
DEFAULT_DEADLINE_OFFSET = 20 * 60
SWAP_SIGNATURE = "swapExactTRXForTokens(uint256,address[],address,uint256)"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run swapExactTRXForTokens clear-sign flow with external plugin setup"
    )
    parser.add_argument("--path", default="44'/195'/0'/0/0", help="BIP32 path, default: 44'/195'/0'/0/0")
    parser.add_argument(
        "--contract",
        default=DEFAULT_SWAP_CONTRACT,
        help=f"Swap router contract base58 address, default: {DEFAULT_SWAP_CONTRACT}",
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
        "--call-value",
        type=int,
        default=DEFAULT_CALL_VALUE,
        help=f"TRX amount sent with the swap in sun, default: {DEFAULT_CALL_VALUE}",
    )
    parser.add_argument(
        "--amount-out-min",
        type=int,
        default=DEFAULT_AMOUNT_OUT_MIN,
        help=f"Minimum output amount in token smallest unit, default: {DEFAULT_AMOUNT_OUT_MIN}",
    )
    parser.add_argument(
        "--path-addresses",
        default=DEFAULT_PATH,
        help=f"Comma-separated TRON addresses for swap path, default: {DEFAULT_PATH}",
    )
    parser.add_argument(
        "--to",
        default=DEFAULT_TO,
        help=f"Recipient TRON address, default: {DEFAULT_TO}",
    )
    parser.add_argument(
        "--deadline",
        type=int,
        default=int(time.time()) + DEFAULT_DEADLINE_OFFSET,
        help="Unix timestamp deadline. Default: now + 20 minutes",
    )
    parser.add_argument(
        "--no-broadcast",
        action="store_true",
        help="Build/sign flow only, skip broadcast",
    )
    return parser.parse_args()


def parse_path_addresses(raw_value: str) -> list[str]:
    path_addresses = [item.strip() for item in raw_value.split(",") if item.strip()]
    if len(path_addresses) < 2:
        raise ValueError("swap path must contain at least two addresses")
    return path_addresses


def build_swap_data(
    *,
    amount_out_min: int,
    path_addresses: list[str],
    to_address: str,
    deadline: int,
) -> bytes:
    selector = selector_from_signature(SWAP_SIGNATURE)
    path_values = [evm_address_bytes_from_contract_id(address) for address in path_addresses]
    to_value = evm_address_bytes_from_contract_id(to_address)
    path_offset = 32 * 4
    head = b"".join(
        [
            encode_uint256(amount_out_min),
            encode_uint256(path_offset),
            encode_address(to_value),
            encode_uint256(deadline),
        ]
    )
    tail = encode_address_array(path_values)
    return selector + head + tail


def main() -> int:
    args = parse_args()
    makefile_path = Path(args.makefile)
    cal_pem_path = Path(args.cal_key)

    plugin_name = read_plugin_name(makefile_path)
    contract_address = tron_contract_bytes_from_contract_id(args.contract)
    path_addresses = parse_path_addresses(args.path_addresses)
    swap_data = build_swap_data(
        amount_out_min=args.amount_out_min,
        path_addresses=path_addresses,
        to_address=args.to,
        deadline=args.deadline,
    )
    selector = swap_data[:4]

    dongle = getDongle(True)
    channel = grpc.insecure_channel(args.grpc_endpoint)
    stub = WalletStub(channel)
    try:
        account = get_account(dongle, args.path)
        logger.info("Using account: %s (%s)", account.address, account.path)
        logger.info("Plugin name: %s", plugin_name)
        logger.info("gRPC endpoint: %s", args.grpc_endpoint)
        logger.info("Swap contract: %s", args.contract)
        logger.info("Call value: %d sun", args.call_value)
        logger.info("Amount out min: %d", args.amount_out_min)
        logger.info("Path: %s", ",".join(path_addresses))
        logger.info("Recipient: %s", args.to)
        logger.info("Deadline: %d", args.deadline)
        logger.info("Selector: 0x%s", selector.hex())

        tx_ext = build_trigger_smart_contract_tx(
            stub=stub,
            owner_address_hex=account.address_hex,
            contract_address=contract_address,
            data=swap_data,
            call_value=args.call_value,
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
            selector=selector,
            cal_pem_path=cal_pem_path,
            no_broadcast=args.no_broadcast,
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
