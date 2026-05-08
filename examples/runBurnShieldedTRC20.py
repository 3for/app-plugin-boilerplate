#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build and sign the provided TriggerSmartContract(burn) transaction on a real
Ledger device:
1) Build TriggerSmartContract(burn(bytes32[10],bytes32[2],uint256,bytes32[2],address,bytes32[3],bytes32[9][],bytes32[21][])).
2) Send EXTERNAL_PLUGIN_SETUP for the burn selector.
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


BURN_CONTRACT_HEX = "418C8705769E5ec53F5F9C42A3bc3305624AD37192"
BURN_OWNER_ADDRESS_HEX = "4119580b8D292F590D254Ab037320975Ab36789194"
BURN_SIGNATURE = "burn(bytes32[10],bytes32[2],uint256,bytes32[2],address,bytes32[3],bytes32[9][],bytes32[21][])"
BURN_SELECTOR = selector_from_signature(BURN_SIGNATURE)
TRON_MAINNET_CHAIN_ID = 1151668124

BURN_PARAMETER_HEX = (
    "411fcd54cea8939bd45b9ad7b2c0001872eb50903f8e6e063bd6d46aff890206afa8e0e221d5997d57547d7666a7c2f776317b2a2906c58055551972622a7d6fc9074c2907d279a4e6cf6d5c7098516b338564c55401087605e2b1f554f146d83c71fc1792c27f464fc1c5a7dfe0a6806cc6921cef46a41008de6a18e78dfee7a0e0f3ece3fd4d7a3db027e11c3fa8f58346539502eb9dd17db76fd60f79657303b95dcfa2e2e8bc069a793fc71d501da737ff5deee54e1f659f1fda4ce5428c18b3cca5f816ef3308dd3d2bf323de1bd361183d829ebd21b3198c306d30176506efba80a1a341ea8eae32d3f263294b5cd48e16a7f481230c83cb0fa198718fba949736aba6e1b7cfcffbb7aca62624867e948c97cda7e4e4b0038bd51933bed2d56ff884d4ac7c12e8fb3a84ccddb6f3830b36424ac2f1c09b2ed784d2208cb8dfa7a9aa61016cc74876572938c48edd9ae4e9061501db182991030596aca5791900aba9c4dfb97f1ebb328f27b7d470e90aa4d7c56ad2184abb4c45b1f40800000000000000000000000000000000000000000000000029a2241af62c00000423e07a9c2e1f4bc5192f5dc42e413e508cc85bbd4bdfb51022c626e890cadedf7737598997f77d9639ca3764f56e54950f6e4dc3148c3bf585135af1108f0200000000000000000000004119580b8d292f590d254ab037320975ab367891945d4188e801642649a5d69f6ba4a174aa57b97410d5a2ba17c7dae76462b3e1e23e3007946b5f21510ed860e048e638a6dbd76c5670b753b83383962eb486e693e92fbbdc97a835c02a93c33030a888f50000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000002a000000000000000000000000000000000000000000000000000000000000003e00000000000000000000000000000000000000000000000000000000000000001f4f835357d8ca230e33488f80c83bacc79bc234333d60b5a73c1a8e5255b336263861fb9e1882c9be89afe4f7c5529c87e38c8aa5da2a663dddce5d620f786247ff151f8bcca7cc3c968a18fab7ea8f291263356ad18a45ab37d6235689be33aa7a0d63bb0247c9b8fa870f496ced81c1096e7a35f171d10b704f098e91d6be554f8248b86566c5a6f66af4cca0b9557a1a11a6aaa8d054f644dbcba9a77ada5e245870d23f1ee4e29c1063507bbba526a596b93930fb5d8ae6895bace0818430e75585a8a655b342c2c9239675c95a54cabdd83d1590aa62acf3b4786648d94084084484f19496a722eb387b24599a688126cfc46dc75a8872e923add73763c74369413a73b9ce20c44bfba051ebfd43bd075b1ca5d1eb11568a0721b8a63280000000000000000000000000000000000000000000000000000000000000001ff387be3765524f0b6ebb5552402188980d16e63559fc62f7b7e89720b213121ba385494a87c778d5c2ccd745888321f882658c2e26687ead9b21f46f3c7364388ed7c63ecb1aa66fe86e036ad2b40d2a1df90fa0c7a81aa24bd9e6010231e2d94a874954245fd48bbe6521933fef5f8bd78ae07dea625ebb2c0273cde2b1acf7f07883e5f4f05fb70b3f1b45735addcdf9410c81444d0575d177c5a5676b44c666948ce09cac6a1ea0d5710652f0ce31d372648b874f64ba487579a0045b4b44949a9fa1a22fc949c3cad5da1c334ee25d5357ae41dad9ed54e6433c5ba2d31101f652e992c7e922e1fd40ba9221a0c53c54eb89c49c68395eb61e1b489882759a788a4ea383167950e3adc80ebd3bbea11b490d402a64634006cd10170ad84cbb34c6c4a239df33b962fb4dedd62fefc1c03089a5481da96f6e09c47c5197ea58dfd3193cde8e9e3acf4fa74beefca94df5bf9c99dacfc298e14cab2360a10f7d76a77ecc4471d513be5262a7ffe52177c11ba24e626cbc33e12cddbf02bb42d80aabcd86e03fd4f733ede78a9682842803605a924b99cd1048984a4131780935d70975f99c5685445e1d3345cb4848e4fc68df984049cf5abd02abb5525c8df5870797d8a0905ecff4f37b9f0e1d25ae99c6d311749830208f7c2cb47043afc1dc44c9f2dbdbeeb54e352d77ab5b629917b659f7e69e91521577ae1b3c7aff99ed31848ea7302e07cff9851213bda670cd6c895bbeb37a991ca09d2debe034fb37e1a0aa791323217790f72cde2d41c1f5e32878253d8b0f5db896a22a6ab2437c5f8d126e7505412a109939ccdd634cc04993a197725d0b8e2f4350f3d041199c9b6d7756a863afa9793293b25ff17d2472499b64f321c4e9fecf4fcee7e79ba7e62fe2c3dc034d381f7d65c9d310349a8e4000000000000000000000000"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run ShieldedTRC20 burn clear-sign flow with external plugin setup"
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
        default=BURN_OWNER_ADDRESS_HEX,
        help=f"TriggerSmartContract owner_address hex, default: {BURN_OWNER_ADDRESS_HEX}",
    )
    parser.add_argument(
        "--use-ledger-owner",
        action="store_true",
        help="Use the Ledger account address as owner_address instead of --owner-address-hex.",
    )
    parser.add_argument(
        "--contract",
        default=BURN_CONTRACT_HEX,
        help=f"ShieldedTRC20 contract address, default: {BURN_CONTRACT_HEX}",
    )
    parser.add_argument(
        "--parameter-hex",
        default=BURN_PARAMETER_HEX,
        help="ABI-encoded burn parameters without the 4-byte function selector.",
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


def build_burn_data(parameter_hex: str) -> bytes:
    normalized = normalize_hex(parameter_hex)
    parameter = bytes.fromhex(normalized)
    if len(parameter) % 32 != 0:
        raise ValueError(f"burn parameter length must be a multiple of 32 bytes, got {len(parameter)}")
    return BURN_SELECTOR + parameter


def main() -> int:
    args = parse_args()
    makefile_path = Path(args.makefile)
    cal_pem_path = Path(args.cal_key)

    plugin_name = read_plugin_name(makefile_path)
    contract_address = tron_contract_bytes_from_contract_id(args.contract)
    burn_data = build_burn_data(args.parameter_hex)
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
        logger.info("Shielded burn contract: %s", args.contract)
        logger.info("Contract bytes: %s", contract_address.hex().upper())
        logger.info("Function selector: 0x%s", BURN_SELECTOR.hex())
        logger.info("Burn parameter length: %d bytes", len(burn_data) - len(BURN_SELECTOR))
        logger.info("Fee limit: %d", args.fee_limit)
        logger.info("Broadcast: %s", "disabled" if args.no_broadcast else "enabled")

        tx_ext = build_trigger_smart_contract_tx(
            stub=stub,
            owner_address_hex=owner_address_hex,
            contract_address=contract_address,
            data=burn_data,
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
            selector=BURN_SELECTOR,
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
