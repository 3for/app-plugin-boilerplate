import json
from pathlib import Path
import sys
from typing import Optional

import base58
from ragger.backend import BackendInterface
from ragger.backend.interface import RaisePolicy
from ragger.error import ExceptionRAPDU
from web3 import Web3

from . import keychain
from .client.command_builder import CommandBuilder
from .tron import InsType, TronClient
from .utils import get_appname_from_makefile

sys.path.append(f"{Path(__file__).parent.parent.resolve()}/build/proto")
from core import Tron_pb2 as tron
from core.contract import smart_contract_pb2 as contract


PLUGIN_NOT_FOUND = 0x6984
PLUGIN_NAME = get_appname_from_makefile()
ABIS_FOLDER = Path(__file__).parent / "abis"

def _tron_b58_to_evm_hex(address: str) -> str:
    tron_hex = base58.b58decode_check(address).hex()
    return tron_hex[2:]


def abi_hex_to_bytes(data: str) -> bytes:
    return bytes.fromhex(data[2:] if data.startswith("0x") else data)


def evm_hex_from_contract_id(contract_id: str) -> str:
    if contract_id.startswith("0x"):
        return contract_id[2:]
    if len(contract_id) == 40:
        return contract_id
    return _tron_b58_to_evm_hex(contract_id)


def tron_contract_bytes_from_contract_id(contract_id: str) -> bytes:
    if contract_id.startswith("0x"):
        contract_id = contract_id[2:]
    if len(contract_id) == 40:
        return bytes.fromhex(f"41{contract_id}")
    return base58.b58decode_check(contract_id)


def load_contract_from_abi_fixture(abi_filename: str):
    abi_path = ABIS_FOLDER / abi_filename
    contract_id = abi_filename.split(".")[0]
    with abi_path.open(encoding="utf-8") as file:
        return Web3().eth.contract(abi=json.load(file),
                                   address=bytes.fromhex(
                                       evm_hex_from_contract_id(contract_id)))


def build_trigger_tx(client: TronClient,
                     contract_address_bytes: bytes,
                     calldata: bytes,
                     call_value: int = 0) -> bytes:
    return client.packContract(
        tron.Transaction.Contract.TriggerSmartContract,
        contract.TriggerSmartContract(
            owner_address=bytes.fromhex(client.getAccount(0)["addressHex"]),
            contract_address=contract_address_bytes,
            call_value=call_value,
            data=calldata))


def force_external_plugin_reset(client: TronClient):
    # This forces the app to run clear-sign finalization and reset internal state.
    try:
        client.sign(client.getAccount(0)["path"],
                    b"",
                    navigate=False,
                    ins=InsType.SIGN_EXTERNAL_PLUGIN,
                    include_tx_len=True)
    except ExceptionRAPDU:
        pass


def setup_external_plugin(backend: BackendInterface,
                          plugin_name: str,
                          contract_address_bytes: bytes,
                          selector: bytes,
                          signature: Optional[bytes] = None):
    payload = bytearray()
    payload.append(len(plugin_name))
    payload += plugin_name.encode()
    payload += contract_address_bytes
    payload += selector
    sig = signature if signature is not None else keychain.sign_data(
        keychain.Key.CAL, bytes(payload))
    apdu = CommandBuilder().set_external_plugin(plugin_name, contract_address_bytes,
                                                selector, sig)

    previous_policy = backend.raise_policy
    backend.raise_policy = RaisePolicy.RAISE_NOTHING
    try:
        return backend.exchange_raw(apdu)
    finally:
        backend.raise_policy = previous_policy


def provide_trc20_token_information(backend: BackendInterface,
                                    ticker: str,
                                    contract_address_bytes: bytes,
                                    decimals: int,
                                    chain_id: int,
                                    signature: Optional[bytes] = None):
    if signature is None:
        # Mirror the main app test helper: build the APDU with an empty signature,
        # then sign the token metadata payload that follows the APDU header.
        tmp = CommandBuilder().provide_trc20_token_information(ticker,
                                                               contract_address_bytes,
                                                               decimals,
                                                               chain_id,
                                                               bytes())
        signature = keychain.sign_data(keychain.Key.CAL, tmp[6:])

    apdu = CommandBuilder().provide_trc20_token_information(ticker,
                                                            contract_address_bytes,
                                                            decimals,
                                                            chain_id,
                                                            signature)

    previous_policy = backend.raise_policy
    backend.raise_policy = RaisePolicy.RAISE_NOTHING
    try:
        return backend.exchange_raw(apdu)
    finally:
        backend.raise_policy = previous_policy
