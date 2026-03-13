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


TRC20_CONTRACT_B58 = "TBoTZcARzWVgnNuB9SyE3S5g1RwsXoQL16"
TRC20_ABI_FOLDER = Path(__file__).parent / "abis"
TRC20_TRANSFER_RECIPIENT_HEX = "364b03e0815687edaf90b81ff58e496dea7383d7"
TRC20_TRANSFER_AMOUNT = 1_000_000
TRC20_EXTRA_PARAMETER = (1).to_bytes(32, byteorder="big")
TRC20_SWAP_SELECTOR = bytes.fromhex("7ff36ab5")
PLUGIN_NOT_FOUND = 0x6984
PLUGIN_NAME = get_appname_from_makefile()


def _load_contract_from_abi(abi_path: Path):
    with abi_path.open(encoding="utf-8") as file:
        return Web3().eth.contract(abi=json.load(file),
                                   address=bytes.fromhex(TRC20_CONTRACT_EVM_HEX))


def _abi_hex_to_bytes(data: str) -> bytes:
    return bytes.fromhex(data[2:] if data.startswith("0x") else data)


def _tron_b58_to_evm_hex(address: str) -> str:
    tron_hex = base58.b58decode_check(address).hex()
    return tron_hex[2:]


TRC20_CONTRACT_EVM_HEX = _tron_b58_to_evm_hex(TRC20_CONTRACT_B58)
TRC20_CONTRACT = _load_contract_from_abi(
    TRC20_ABI_FOLDER / f"0x{TRC20_CONTRACT_EVM_HEX}.abi.json")
TRC20_TRANSFER_CALLDATA = _abi_hex_to_bytes(
    TRC20_CONTRACT.encode_abi(
        "transfer",
        [bytes.fromhex(TRC20_TRANSFER_RECIPIENT_HEX), TRC20_TRANSFER_AMOUNT]))
TRC20_TRANSFER_SELECTOR = TRC20_TRANSFER_CALLDATA[:4]
TRC20_TRANSFER_CALLDATA_WITH_EXTRA_PARAMETER = (TRC20_TRANSFER_CALLDATA +
                                                TRC20_EXTRA_PARAMETER)


def contract_address(client: TronClient) -> bytes:
    return bytes.fromhex(client.address_hex(TRC20_CONTRACT_B58))


def build_trc20_transfer_tx(client: TronClient) -> bytes:
    return build_trigger_tx(client, contract_address(client), TRC20_TRANSFER_CALLDATA)


def build_trigger_tx(client: TronClient, contract_address_bytes: bytes,
                     calldata: bytes) -> bytes:
    return client.packContract(
        tron.Transaction.Contract.TriggerSmartContract,
        contract.TriggerSmartContract(
            owner_address=bytes.fromhex(client.getAccount(0)["addressHex"]),
            contract_address=contract_address_bytes,
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
