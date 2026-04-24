#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build and sign the provided TriggerSmartContract(mint) transaction on a real
Ledger device:
1) Build TriggerSmartContract(mint(uint256,bytes32[9],bytes32[2],bytes32[21])).
2) Send EXTERNAL_PLUGIN_SETUP for the mint selector.
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


MINT_CONTRACT_B58 = "TNnFMMykZzwhPZkurKtNMyVGvgeSkCrnPi"
MINT_SIGNATURE = "mint(uint256,bytes32[9],bytes32[2],bytes32[21])"
MINT_SELECTOR = selector_from_signature(MINT_SIGNATURE)
TRON_MAINNET_CHAIN_ID = 1151668124

MINT_PARAMETER_HEX = (
    "00000000000000000000000000000000000000000000000053444835ec580000ef7bd6fc77820fe29eb61a243373c97411dbc91b9c78397815b8682aa6cf920f1d295363722a8abfe0c6562bbddf6654c3a27dede76a89b2d938369229a89faf4d2eda91b230ebcc8a1c2bf478aae2f44b9f5ed0b35f28a2c453430fef4f71678bf508df306cee0e3c427af5f4498178a1edf7f316c73e7321c28ad0340d30c9664a9d5aa6d6e0bd7b680312282ffbf2afe19549c8ce46de29236082af8f2f4830a3dfc6447a13fadc976de3eb1536f314b59d74fee1e3e2d8e3bf83a3d47f8f09f5a002dd5c210b2d6ffd99f38e0d4d0194f153f0a99cf6162ed5fb5ee1e008892c2462dea465eecd14f118e95ceddf920736ed577954feef6c1fe3891f6d750585761ab87d1c499b4ad32cb56fe79fc8551c6f90900d07fa3df42594028ffad4d9dc789628d39b9d23c3852186682acfeae2eeb36bb92c442902179eb5bae6adf58d3dfaa2a6b10d2f2e6bc8f9d2c5da5b9c15779f3da789ffdaeab8cbbf038e96406dec3bc055a0ce6a9f7ab302dbfbf58e7e3774c347c22d4ee9e96a70ddd2b731fb963ea2b882f62d0da7cc9f2f4de2a0a46f868b8730d1d31b65925368ada0c824761e71d89bac2a3811050dfc638fda90672e653baef3abd20d6130117888892da81d270afaa5d15ab820904d3799313c715b800bc62dca4487cf26baa1b2bd004d8ba299af9b604980aa060a8e6261ddd1dcbc26a33728c03cc6e322f7fc6a2a9140873eaacc2b05a78adecf865f83225498a8b22678a773d5e2b3fb9d0ea356486255308fc53b3c405d4d3f10317a451bc00d8c1f7cc94bb497275310bd023b9c33231c361c5353b771b3c62986f8d1444a2bfb61b49c4e5785b2bba0d306c2e98759d3f01d76da4d543300e3def65a15097a38fd395c63360fea47f2663524272fba031083c55e5832b75ede98398cc11bbf8408a325053b6c92c992ce11b2a721ce510fc0fa4dac4eaec0b0dda2cd4e440b9689f0d5008294edeb72b62040e17e15f014a3bae029de843ecc38b9d033f8f86580f80a05453b5d55ac8d016726c85725b41e5ea88c57b159c995558870eb215cbc42700a60a744ea29b5423f78a462105245632a697c4a1e32727db5d7e35058ee778eee773b5370faf6617345e42d5f29770e0f76814c3c55399a4c1b8c9e5f70259dfc72edda8b886bb8590a85c01d5132ac499ba664926b0f635369d9026188f4fed499a1327501f15d485f525bd88b1c21c87c096da777c93ccf78c841a9ad4b3136cd74529bb50fed7950e3f6b174af43c5e5e41bcded0f8b0463844f230efa5058e9ceb41481bf99808b5671eecb120a17da89009eacf0074706b83484ea7887e218ef4258b3f661d7477d3ab361450f0cc44f376fdbf513938d854606b58e63d3569d9c4884d82d37dc9057562ad5a4c5b34e0d09eccd4870000000000000000000000000"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run ShieldedTRC20 mint clear-sign flow with external plugin setup"
    )
    parser.add_argument("--device", help="Ledger device name to use when auto-opening the Tron app.")
    parser.add_argument("--app-name", default="Tron", help="Dashboard application to open.")
    parser.add_argument("--skip-open-app", action="store_true",
                        help="Do not switch apps automatically; requires the Ledger to already be unlocked in Tron.")
    parser.add_argument("--with-gui", action="store_true",
                        help="Show Ragger's helper GUI for physical-device actions.")
    parser.add_argument("--path", default="44'/195'/0'/0/0", help="BIP32 path, default: 44'/195'/0'/0/0")
    parser.add_argument(
        "--contract",
        default=MINT_CONTRACT_B58,
        help=f"ShieldedTRC20 contract address, default: {MINT_CONTRACT_B58}",
    )
    parser.add_argument(
        "--parameter-hex",
        default=MINT_PARAMETER_HEX,
        help="ABI-encoded mint parameters without the 4-byte function selector.",
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


def build_mint_data(parameter_hex: str) -> bytes:
    normalized = parameter_hex.removeprefix("0x")
    parameter = bytes.fromhex(normalized)
    if len(parameter) % 32 != 0:
        raise ValueError(f"mint parameter length must be a multiple of 32 bytes, got {len(parameter)}")
    return MINT_SELECTOR + parameter


def main() -> int:
    args = parse_args()
    makefile_path = Path(args.makefile)
    cal_pem_path = Path(args.cal_key)

    plugin_name = read_plugin_name(makefile_path)
    contract_address = tron_contract_bytes_from_contract_id(args.contract)
    mint_data = build_mint_data(args.parameter_hex)
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
        logger.info("Using account: %s (%s)", account.address, account.path)
        logger.info("Plugin name: %s", plugin_name)
        logger.info("gRPC endpoint: %s", args.grpc_endpoint)
        logger.info("Mint contract: %s", args.contract)
        logger.info("Contract bytes: %s", contract_address.hex().upper())
        logger.info("Function selector: 0x%s", MINT_SELECTOR.hex())
        logger.info("Mint parameter length: %d bytes", len(mint_data) - len(MINT_SELECTOR))
        logger.info("Fee limit: %d", args.fee_limit)
        logger.info("Broadcast: %s", "disabled" if args.no_broadcast else "enabled")

        tx_ext = build_trigger_smart_contract_tx(
            stub=stub,
            owner_address_hex=account.address_hex,
            contract_address=contract_address,
            data=mint_data,
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
            selector=MINT_SELECTOR,
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
