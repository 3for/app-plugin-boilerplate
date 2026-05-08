#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build and sign the provided TriggerSmartContract(ShieldedTRC20 transfer)
transaction on a real Ledger device:
1) Build TriggerSmartContract(transfer(bytes32[10][],bytes32[2][],bytes32[9][],bytes32[2],bytes32[21][])).
2) Send EXTERNAL_PLUGIN_SETUP for the transfer selector.
3) Send TRC20 token metadata used by the plugin display.
4) Sign with SIGN_EXTERNAL_PLUGIN and verify the signature.

Requires a Tron app build compiled with `use_test_keys` because the example
uses the test CAL key from `tests/keychain/cal.pem` to authorize metadata APDUs.
"""

import argparse
import logging
from pathlib import Path

import grpc
from ledgerblue.comm import getDongle
from example_helpers import (ROOT_DIR, TokenInformation, WalletStub,
                             build_trigger_smart_contract_tx,
                             ensure_requested_app, get_account,
                             read_plugin_name, selector_from_signature,
                             sign_and_optionally_broadcast,
                             tron_contract_bytes_from_contract_id)


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


TRANSFER_CONTRACT_B58 = "TNnFMMykZzwhPZkurKtNMyVGvgeSkCrnPi"
TRANSFER_OWNER_ADDRESS_HEX = "4119580b8D292F590D254Ab037320975Ab36789194"
TRANSFER_SIGNATURE = "transfer(bytes32[10][],bytes32[2][],bytes32[9][],bytes32[2],bytes32[21][])"
TRANSFER_SELECTOR = selector_from_signature(TRANSFER_SIGNATURE)
TRON_MAINNET_CHAIN_ID = 1151668124

TRANSFER_PARAMETER_HEX = (
    "00000000000000000000000000000000000000000000000000000000000000c000000000000000000000000000000000000000000000000000000000000002200000000000000000000000000000000000000000000000000000000000000280ce6afaf724f66efac204f6368123fcd2ef6ab565477400bab70e39ca68a581b94fc11db9de0f6951270d3fd7bea878fe4bad59f126fe446b33a66bfc8af3f70600000000000000000000000000000000000000000000000000000000000003c00000000000000000000000000000000000000000000000000000000000000001951e4c9456e7dbeed6831cd60b75d4727badc33e03bb08ab0ada011b9213747ac26c3206afaba02c8454263eb9bb6c9e2506704995b4e41989f9f47550045e5b616035300ff5e029ccdebfe596d4723f370b85e688e21aacd6083e6139af5ca175efb6b823520d481440d1474b5b6f5bc2d1d534a7763ac5a688d2d1ec529898a040447b31a528060bcc561cc2a8d7adc6f726a6f6c7d6f03bab88d21af12f3b97a48b52da15c01cd5043b32f21d3454a742654aa4985072c9cedb8934a65c30d6e373e104e428b80c966dad68d28a5440d8f09e629009e2ca43774a7307e01e112691a20dedb4f79c182531ced0a5dce04b5e78836425d5ecf45d8fe5221b6da53d6f10ea310afd1d16184e502d00e3b1c43f91a2bf21c5a003fe9f106a51fc861ef502b01e82c6df897ae4786645db8f4f6a453be039f6bfaaf501ecaacf9200000000000000000000000000000000000000000000000000000000000000016ce9d10243a28f900cf2d2b5e9bec5cb3615ce2fa36e5e16050cb81865ae43b874e74feb01c94b3d282e46e39e615431a2aed82c10dc26cfb6f6e0227c2503050000000000000000000000000000000000000000000000000000000000000001233c627d5b726522420f072681c0905e3b13bfc68605a74eee2cc9b55acb23507ae1e689515ff7301f3777ce11378b17c86ec6a443c79def76bd9eca613aa4b3b96780a9e19627cedf75b2a3c3bd3f4dda950fcec42e63f1696f12928ce1638b94f265307618c4dce68bd992e21fee80083870faca0ccbfde2b32689327d37e1564f4c58eb9aaf87777c42a238569cb7b9aeae4478650121c0913b41319b165000eb0e88da3a041242f9c5961ae8367df889dd8018053f1cea342524b606467202635eafe3eb084a530bf024151c27be783662c9d29de7ea03d2ad8d8b39fec98348addd026f862ff9d06bebf0ad75a097f9a82d5bb1965d8fc3f7ca01688bf7e3f84b206fbab3baab8f9a9bf5b240e3726bf5293d7a862bd511fc80b0e1bf380000000000000000000000000000000000000000000000000000000000000001e47864bd06637a361b0567f911da6a3d6fb1eb788b2348b90edf9d76b2906e59fc6a8923bfe76b1eb541170b85b9ff923d8da00deeefd5a2a93d1243845de4847712504f32927f792a1c81de64cc4e05d79882f80eccad69e2b0152470fdf65a5e0ee20e1d6c84e992267cb0931eb2c4f42eb95c1cdee9ee12da86f2d3e8da644df188bf81507da1409d3aef51dd7b3408bdb787acc9baaeeb91b23d11727e6e111489852685aa809d97d6b066f73c54e88540e0fadacf3a7cae30c5f94527e485a1e3249f7bc3a82f80dc815f3a9172e61bc1bdd57de58826856957e989048f185bf6dcdd2b508b5761fb34c603df7acb997ead52a5c6194c9bae77851f87fc4d0eb504e1c0b9dfd1a0f9c5593b5cf766eb00743043ca8441577c84536c7d9dc9203ff8911c1020f553c57ba34f59a7f3270eca785ca4a33c60f8df19fcbeab6c757093b4c89e186c9956d9e3ee7610537f590bfb740fa1f544d4b797a0dd8a578817c41770ac0627ff4c8b4be7061a117682275a5e38c9509c6deaa48929c908efb32d8a430c780d319157a24f020afad022494d72345ff64c3620afb6a0e670dd4641b182ac97bd79b8052b97cefb0f1f5a8c6e26f0dea53c4a79cc4965fcddf3bf7d1b726c717d5ec1eeaca9b07ba83f0cd209f59bb35ccb59127919fcf080a1c04b63683e7159d78bb419cc84df6adf1849130e602d114ff54bf6b6e11544f17959af97cc83a16aa734ff740300538739e10dac20c7c4af8ddfef14d4f8e786162b5efbe9975acfa3cf13bf17c4c1857ef12858a5db6186570570b0a33368aa026221933e96c83d173937ef3703acea5c1cde95de19fbb9b46fdb0ed9a7395caad66ad89ec3f3a5ff35d5c49decaffbb34e9d5f05275139c15dbfd4b54d5f9284afea671fc7c913ad6097dc9ff021daf4a7000000000000000000000000"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run ShieldedTRC20 transfer clear-sign flow with external plugin setup"
    )
    parser.add_argument("--device", help="Ledger device name to use when auto-opening the Tron app.")
    parser.add_argument("--app-name", default="Tron", help="Dashboard application to open.")
    parser.add_argument("--skip-open-app", action="store_true",
                        help="Do not switch apps automatically; requires the Ledger to already be unlocked in Tron.")
    parser.add_argument("--with-gui", action="store_true",
                        help="Show Ragger's helper GUI for physical-device actions.")
    parser.add_argument("--path", default="44'/195'/0'/0/0", help="BIP32 path, default: 44'/195'/0'/0/0")
    parser.add_argument(
        "--owner-address-hex",
        default=TRANSFER_OWNER_ADDRESS_HEX,
        help=f"TriggerSmartContract owner_address hex, default: {TRANSFER_OWNER_ADDRESS_HEX}",
    )
    parser.add_argument(
        "--use-ledger-owner",
        action="store_true",
        help="Use the Ledger account address as owner_address instead of --owner-address-hex.",
    )
    parser.add_argument(
        "--contract",
        default=TRANSFER_CONTRACT_B58,
        help=f"ShieldedTRC20 contract address, default: {TRANSFER_CONTRACT_B58}",
    )
    parser.add_argument(
        "--parameter-hex",
        default=TRANSFER_PARAMETER_HEX,
        help="ABI-encoded transfer parameters without the 4-byte function selector.",
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
        default=1_000_000_000,
        help="Transaction fee_limit in sun, default: 1000000000",
    )
    parser.add_argument("--call-value", type=int, default=0, help="call_value, default: 0")
    parser.add_argument("--call-token-value", type=int, default=0, help="call_token_value, default: 0")
    parser.add_argument("--token-id", type=int, default=0, help="token_id, default: 0")
    parser.add_argument("--token-ticker", default="JST", help="Display token ticker, default: JST")
    parser.add_argument("--token-decimals", type=int, default=18, help="Display token decimals, default: 18")
    parser.add_argument(
        "--chain-id",
        type=int,
        default=TRON_MAINNET_CHAIN_ID,
        help=f"TRC20 token metadata chain id, default: {TRON_MAINNET_CHAIN_ID}",
    )
    parser.add_argument(
        "--no-broadcast",
        action="store_true",
        help="Build/sign flow only, skip broadcast.",
    )
    return parser.parse_args()


def normalize_hex(value: str) -> str:
    normalized = value[2:] if value.lower().startswith("0x") else value
    if len(normalized) % 2 != 0:
        raise ValueError(f"hex value must contain an even number of characters, got {len(normalized)}")
    bytes.fromhex(normalized)
    return normalized.upper()


def normalize_tron_address_hex(value: str) -> str:
    normalized = normalize_hex(value)
    if len(normalized) != 42 or not normalized.startswith("41"):
        raise ValueError(f"TRON address hex must be 21 bytes and start with 41, got {normalized}")
    return normalized


def build_transfer_data(parameter_hex: str) -> bytes:
    normalized = normalize_hex(parameter_hex)
    parameter = bytes.fromhex(normalized)
    if len(parameter) % 32 != 0:
        raise ValueError(f"transfer parameter length must be a multiple of 32 bytes, got {len(parameter)}")
    return TRANSFER_SELECTOR + parameter


def main() -> int:
    args = parse_args()
    makefile_path = Path(args.makefile)
    cal_pem_path = Path(args.cal_key)

    plugin_name = read_plugin_name(makefile_path)
    contract_address = tron_contract_bytes_from_contract_id(args.contract)
    transfer_data = build_transfer_data(args.parameter_hex)
    token_information = TokenInformation(
        ticker=args.token_ticker,
        contract_address=contract_address,
        decimals=args.token_decimals,
        chain_id=args.chain_id,
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
        owner_address_hex = (
            account.address_hex
            if args.use_ledger_owner
            else normalize_tron_address_hex(args.owner_address_hex)
        )
        if owner_address_hex != account.address_hex:
            logger.warning(
                "Trigger owner_address (%s) differs from Ledger account (%s); "
                "broadcast may fail unless the Ledger path controls the owner address.",
                owner_address_hex,
                account.address_hex,
            )

        logger.info("Using account: %s (%s)", account.address, account.path)
        logger.info("Trigger owner_address: %s", owner_address_hex)
        logger.info("Plugin name: %s", plugin_name)
        logger.info("gRPC endpoint: %s", args.grpc_endpoint)
        logger.info("Shielded transfer contract: %s", args.contract)
        logger.info("Contract bytes: %s", contract_address.hex().upper())
        logger.info("Function selector: 0x%s", TRANSFER_SELECTOR.hex())
        logger.info("Transfer parameter length: %d bytes", len(transfer_data) - len(TRANSFER_SELECTOR))
        logger.info("Fee limit: %d", args.fee_limit)
        logger.info("Broadcast: %s", "disabled" if args.no_broadcast else "enabled")

        tx_ext = build_trigger_smart_contract_tx(
            stub=stub,
            owner_address_hex=owner_address_hex,
            contract_address=contract_address,
            data=transfer_data,
            call_value=args.call_value,
            call_token_value=args.call_token_value,
            token_id=args.token_id,
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
            selector=TRANSFER_SELECTOR,
            cal_pem_path=cal_pem_path,
            no_broadcast=args.no_broadcast,
            token_information=token_information,
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
