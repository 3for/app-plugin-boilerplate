#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

from web3 import Web3

from ledgered.devices import Device, Devices

from ledger_app_clients.ethereum.client import EthAppClient
import ledger_app_clients.ethereum.response_parser as ResponseParser
from ledger_app_clients.ethereum.status_word import StatusWord
from ledger_app_clients.ethereum.utils import get_selector_from_data, recover_transaction

from ragger.backend import LedgerCommBackend, LedgerWalletBackend
from ragger.error import ExceptionRAPDU
from ragger.utils.misc import exit_current_app, get_current_app_name_and_version, open_app_from_dashboard


ROOT_DIR = Path(__file__).resolve().parents[1]
ABI_PATH = ROOT_DIR / "tests" / "abis" / "0x000102030405060708090a0b0c0d0e0f10111213.abi.json"
DEFAULT_DERIVATION_PATH = "m/44'/60'/0'/0/0"
DEFAULT_SWAP_PATH = (
    "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
    "0x6B3595068778DD592e39A122f4f5a5cF09C90fE2",
)
DEFAULT_RECIPIENT = "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"
APPNAME_PATTERN = r'.*APPNAME.*=.*'
STRIP_CHARS = " \t\n\r\x0b\x0c"
WEI_EXPONENTS = {
    "ether": 18,
    "gwei": 9,
}


def get_appname_from_makefile() -> str:
    app_name = None
    with (ROOT_DIR / "Makefile").open(encoding="utf-8") as file:
        for line in file:
            if re.search(APPNAME_PATTERN, line):
                _, value = line.partition("=")[::2]
                app_name = value.strip(STRIP_CHARS + '"')

    if app_name is None:
        raise RuntimeError("Unable to find APPNAME in Makefile")
    return app_name


PLUGIN_NAME = get_appname_from_makefile()


def load_contract():
    with ABI_PATH.open(encoding="utf-8") as file:
        return Web3().eth.contract(
            abi=json.load(file),
            address=bytes.fromhex(ABI_PATH.name.split(".")[0].split("x")[-1]),
        )


CONTRACT = load_contract()


def device_names() -> list[str]:
    return [device.name for device in Devices()]


def get_device(device_name: str) -> Device:
    for device in Devices():
        if device.name == device_name:
            return device
    raise ValueError(f"Unsupported device '{device_name}'")


def parse_address(value: str) -> bytes:
    raw = value[2:] if value.lower().startswith("0x") else value
    if len(raw) != 40:
        raise argparse.ArgumentTypeError(f"Address must be 20 bytes: '{value}'")
    try:
        return bytes.fromhex(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Invalid hex address: '{value}'") from exc


def format_address(value: bytes) -> str:
    return Web3.to_checksum_address(f"0x{value.hex()}")


def decimal_to_wei(value: str, unit: str) -> int:
    try:
        amount = Decimal(value)
    except InvalidOperation as exc:
        raise argparse.ArgumentTypeError(f"Invalid decimal amount '{value}'") from exc

    exponent = WEI_EXPONENTS[unit]
    scaled = amount * (Decimal(10) ** exponent)
    if scaled != scaled.to_integral_value():
        raise argparse.ArgumentTypeError(f"Amount '{value}' has too many decimals for {unit}")
    return int(scaled)


def default_deadline() -> int:
    return int((dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=1)).timestamp())


def format_deadline(deadline: int) -> str:
    return dt.datetime.fromtimestamp(deadline, tz=dt.timezone.utc).isoformat()


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sign a swapExactETHForTokens transaction with a physical Ledger device."
    )
    parser.add_argument("--backend", choices=("ledgercomm", "ledgerwallet"), default="ledgercomm")
    parser.add_argument("--device", choices=device_names(), required=True)
    parser.add_argument("--app-name", default="Ethereum", help="Dashboard application to open.")
    parser.add_argument("--skip-open-app", action="store_true",
                        help="Do not try to switch to the Ethereum app automatically.")
    parser.add_argument("--with-gui", action="store_true",
                        help="Show Ragger's helper GUI for physical-device actions.")
    parser.add_argument("--derivation-path", default=DEFAULT_DERIVATION_PATH)
    parser.add_argument("--nonce", type=int, default=20)
    parser.add_argument("--chain-id", type=int, default=1)
    parser.add_argument("--gas-limit", type=int, default=173290)
    parser.add_argument("--max-fee-per-gas-gwei", default="145")
    parser.add_argument("--max-priority-fee-per-gas-gwei", default="1.5")
    parser.add_argument("--value-eth", default="0.1",
                        help="ETH value sent with the swap transaction.")
    parser.add_argument("--amount-out-min-eth", default="28.5",
                        help="Minimum output amount encoded in the calldata.")
    parser.add_argument("--path", nargs="+", type=parse_address, default=[parse_address(addr) for addr in DEFAULT_SWAP_PATH],
                        help="Swap path addresses, for example WETH tokenOut.")
    parser.add_argument("--recipient", type=parse_address, default=parse_address(DEFAULT_RECIPIENT))
    parser.add_argument("--deadline", type=int, default=default_deadline(),
                        help="Unix timestamp. Defaults to now + 1 hour.")
    return parser


def create_backend(args: argparse.Namespace, device: Device):
    if args.backend == "ledgerwallet":
        return LedgerWalletBackend(device=device, with_gui=args.with_gui)
    return LedgerCommBackend(device=device, interface="hid", with_gui=args.with_gui)


def ensure_requested_app(backend, requested_app: str, skip_open_app: bool) -> None:
    app_name, version = get_current_app_name_and_version(backend)
    print(f"Device reports current app: {app_name} {version}")

    if skip_open_app or app_name == requested_app:
        return

    if app_name != "BOLOS":
        print(f"Closing currently open app '{app_name}'")
        exit_current_app(backend)
        backend.handle_usb_reset()
        app_name, version = get_current_app_name_and_version(backend)
        print(f"After exit: {app_name} {version}")

    if app_name != "BOLOS":
        raise RuntimeError(f"Unable to reach the dashboard, current app is still '{app_name}'")

    print(f"Opening '{requested_app}' from the dashboard")
    open_app_from_dashboard(backend, requested_app)
    backend.handle_usb_reset()
    app_name, version = get_current_app_name_and_version(backend)
    print(f"Current app after open: {app_name} {version}")

    if app_name != requested_app:
        raise RuntimeError(f"Expected '{requested_app}', got '{app_name}'")


def get_wallet_address(client: EthAppClient, derivation_path: str) -> bytes:
    with client.get_public_addr(display=False, bip32_path=derivation_path):
        pass
    wallet = ResponseParser.pk_addr(client.response().data)
    if wallet is None:
        raise RuntimeError("Unable to parse wallet address from Ledger response")
    return wallet[1]


def build_tx_params(args: argparse.Namespace) -> tuple[dict, str]:
    calldata = CONTRACT.encode_abi(
        "swapExactETHForTokens",
        [
            decimal_to_wei(args.amount_out_min_eth, "ether"),
            args.path,
            args.recipient,
            args.deadline,
        ],
    )

    tx_params = {
        "nonce": args.nonce,
        "maxFeePerGas": decimal_to_wei(args.max_fee_per_gas_gwei, "gwei"),
        "maxPriorityFeePerGas": decimal_to_wei(args.max_priority_fee_per_gas_gwei, "gwei"),
        "gas": args.gas_limit,
        "to": CONTRACT.address,
        "value": decimal_to_wei(args.value_eth, "ether"),
        "chainId": args.chain_id,
        "data": calldata,
    }
    return tx_params, calldata


def describe_plugin_error(exc: ExceptionRAPDU) -> str:
    hints = {
        StatusWord.CONDITION_NOT_SATISFIED: (
            "Device rejected the external plugin metadata. On a production Ethereum app this "
            "usually means the example's local test signature is not accepted."
        ),
        StatusWord.INVALID_DATA: (
            "External plugin payload was rejected as invalid. Check the installed plugin, "
            "contract address, selector and chain context."
        ),
        StatusWord.REF_DATA_NOT_FOUND: (
            "Referenced plugin data was not found. Make sure this plugin is installed on the device."
        ),
    }
    hint = hints.get(StatusWord(exc.status), "See the APDU status and Ethereum app logs for details.") \
        if exc.status in set(item.value for item in StatusWord) else \
        "See the APDU status and Ethereum app logs for details."
    return f"External plugin setup failed with status 0x{exc.status:04x}. {hint}"


def sign_transaction(client: EthAppClient, derivation_path: str, tx_params: dict) -> tuple[int, int, int]:
    print("Review the transaction on the Ledger device, then approve it.")
    try:
        with client.sign(derivation_path, tx_params):
            input("Press Enter after the Ledger device finishes the signing flow. ")
    except ExceptionRAPDU as exc:
        raise RuntimeError(f"Transaction signing failed with status 0x{exc.status:04x}") from exc

    response = client.response()
    if response is None:
        raise RuntimeError("No signature response received from the Ledger device")
    return ResponseParser.signature(response.data)


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()

    device = get_device(args.device)
    tx_params, calldata = build_tx_params(args)

    print(f"Connecting with backend={args.backend} device={device.name}")
    print(f"Plugin name: {PLUGIN_NAME}")
    print(f"Contract: {format_address(CONTRACT.address)}")
    print(f"Selector: 0x{get_selector_from_data(calldata).hex()}")
    print(f"Deadline: {args.deadline} ({format_deadline(args.deadline)})")

    with create_backend(args, device) as backend:
        ensure_requested_app(backend, args.app_name, args.skip_open_app)
        client = EthAppClient(backend)

        # GET_PUBLIC_ADDR resets Ethereum app context (including pluginType). Resolve the wallet
        # first, then set the external plugin immediately before SIGN.
        wallet_addr = get_wallet_address(client, args.derivation_path)
        print(f"Signing address: {format_address(wallet_addr)}")

        try:
            response = client.set_external_plugin(
                PLUGIN_NAME,
                CONTRACT.address,
                get_selector_from_data(calldata),
            )
            if response.status != StatusWord.OK:
                raise RuntimeError(f"Unexpected plugin setup status 0x{response.status:04x}")
            print("External plugin metadata accepted by the Ethereum app.")
        except ExceptionRAPDU as exc:
            raise RuntimeError(describe_plugin_error(exc)) from exc

        encoded_tx, _ = client.serialize_tx(tx_params)
        print(f"Unsigned transaction payload: 0x{encoded_tx.hex()}")

        vrs = sign_transaction(client, args.derivation_path, tx_params)
        print(f"Signature v={vrs[0]} r=0x{vrs[1]:064x} s=0x{vrs[2]:064x}")

        recovered_addr = recover_transaction(tx_params, vrs)
        print(f"Recovered address: {format_address(recovered_addr)}")

        if recovered_addr != wallet_addr:
            raise RuntimeError("Recovered address does not match the Ledger wallet address")

    print("Signature verified successfully.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nInterrupted by user.", file=sys.stderr)
        raise SystemExit(130)
    except (RuntimeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
