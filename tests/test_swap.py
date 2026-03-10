from pathlib import Path
import sys
from typing import Optional

import pytest
from ragger.backend import BackendInterface
from ragger.backend.interface import RaisePolicy
from ragger.bip import pack_derivation_path
from ragger.error import ExceptionRAPDU
from ragger.firmware import Firmware
from ragger.navigator import Navigator

from . import keychain
from .client.command_builder import CommandBuilder, InsType as BuilderInsType
from .tron import CLA, Errors, InsType, TronClient
from .utils import check_tx_signature, get_appname_from_makefile

"""
Tron Protobuf
"""
sys.path.append(f"{Path(__file__).parent.parent.resolve()}/build/proto")
from core import Tron_pb2 as tron
from core.contract import smart_contract_pb2 as contract

TRC20_CONTRACT_B58 = "TBoTZcARzWVgnNuB9SyE3S5g1RwsXoQL16"
TRC20_TRANSFER_SELECTOR = bytes.fromhex("a9059cbb")
TRC20_SWAP_SELECTOR = bytes.fromhex("7ff36ab5")
TRC20_TRANSFER_CALLDATA = bytes.fromhex(
    "a9059cbb000000000000000000000000364b03e0815687edaf90b81ff58e496dea7383d7"
    "00000000000000000000000000000000000000000000000000000000000f4240")
TRC20_TRANSFER_CALLDATA_WITH_EXTRA_PARAMETER = bytes.fromhex(
    "a9059cbb"
    "000000000000000000000000364b03e0815687edaf90b81ff58e496dea7383d7"
    "00000000000000000000000000000000000000000000000000000000000f4240"
    "0000000000000000000000000000000000000000000000000000000000000001")
PLUGIN_NOT_FOUND = 0x6984
PLUGIN_NAME = get_appname_from_makefile()
P1_FIRST = 0x00
P1_SIGN = 0x10
P1_MORE = 0x80


def _contract_address(client: TronClient) -> bytes:
    return bytes.fromhex(client.address_hex(TRC20_CONTRACT_B58))


def _build_trc20_transfer_tx(client: TronClient) -> bytes:
    return _build_trigger_tx(client, _contract_address(client),
                             TRC20_TRANSFER_CALLDATA)


def _build_trigger_tx(client: TronClient, contract_address: bytes,
                      calldata: bytes) -> bytes:
    return client.packContract(
        tron.Transaction.Contract.TriggerSmartContract,
        contract.TriggerSmartContract(
            owner_address=bytes.fromhex(client.getAccount(0)["addressHex"]),
            contract_address=contract_address,
            data=calldata))


def _force_external_plugin_reset(client: TronClient):
    # This forces the app to run clear-sign finalization and reset internal state.
    try:
        client.sign(client.getAccount(0)["path"],
                    b"",
                    navigate=False,
                    ins=InsType.SIGN_EXTERNAL_PLUGIN,
                    include_tx_len=True)
    except ExceptionRAPDU:
        pass


def _setup_external_plugin(
        backend: BackendInterface,
        plugin_name: str,
        contract_address: bytes,
        selector: bytes,
        signature: Optional[bytes] = None):
    payload = bytearray()
    payload.append(len(plugin_name))
    payload += plugin_name.encode()
    payload += contract_address
    payload += selector
    sig = signature if signature is not None else keychain.sign_data(
        keychain.Key.CAL, bytes(payload))
    apdu = CommandBuilder().set_external_plugin(plugin_name, contract_address,
                                                selector, sig)

    previous_policy = backend.raise_policy
    backend.raise_policy = RaisePolicy.RAISE_NOTHING
    try:
        return backend.exchange_raw(apdu)
    finally:
        backend.raise_policy = previous_policy


def test_set_external_plugin_rejects_short_payload(backend: BackendInterface):
    with pytest.raises(ExceptionRAPDU) as err:
        backend.exchange(CLA, BuilderInsType.EXTERNAL_PLUGIN_SETUP, 0x00, 0x00,
                         b"\x00")
    assert err.value.status == Errors.INCORRECT_DATA


def test_set_external_plugin_rejects_name_too_long(
        backend: BackendInterface, firmware: Firmware):
    client = TronClient(backend, firmware, None)
    rapdu = _setup_external_plugin(backend, "x" * 30, _contract_address(client),
                                   TRC20_TRANSFER_SELECTOR)
    assert rapdu.status == Errors.INCORRECT_DATA


def test_set_external_plugin_rejects_invalid_signature(
        backend: BackendInterface, firmware: Firmware):
    client = TronClient(backend, firmware, None)
    rapdu = _setup_external_plugin(backend,
                                   PLUGIN_NAME,
                                   _contract_address(client),
                                   TRC20_TRANSFER_SELECTOR,
                                   signature=b"\x30\x06\x02\x01\x01\x02\x01\x01")
    assert rapdu.status == Errors.INCORRECT_DATA


def test_set_external_plugin_returns_plugin_not_found(
        backend: BackendInterface, firmware: Firmware):
    client = TronClient(backend, firmware, None)
    try:
        rapdu = _setup_external_plugin(backend, "missingPlugin",
                                       _contract_address(client),
                                       TRC20_TRANSFER_SELECTOR)
        assert rapdu.status == PLUGIN_NOT_FOUND
    except Exception as err:
        if (isinstance(err, TimeoutError)
                or err.__class__.__name__ == "ChunkedEncodingError"):
            pytest.xfail(
                "Speculos crashes when checking presence of a missing external plugin"
            )
        raise


def test_external_plugin_without_external_plugin_returns_invalid_data(
        backend: BackendInterface, firmware: Firmware):
    client = TronClient(backend, firmware, None)
    _force_external_plugin_reset(client)
    tx = _build_trc20_transfer_tx(client)
    with pytest.raises(ExceptionRAPDU) as err:
        client.sign(client.getAccount(0)["path"],
                    tx,
                    navigate=False,
                    ins=InsType.SIGN_EXTERNAL_PLUGIN,
                    include_tx_len=True)
    assert err.value.status == Errors.INCORRECT_DATA


def test_external_plugin_rejects_nonzero_p2(backend: BackendInterface,
                                       firmware: Firmware):
    client = TronClient(backend, firmware, None)
    _force_external_plugin_reset(client)
    with pytest.raises(ExceptionRAPDU) as err:
        backend.exchange(CLA, InsType.SIGN_EXTERNAL_PLUGIN, P1_SIGN, 0x01, b"")
    assert err.value.status == Errors.INCORRECT_P2


def test_external_plugin_rejects_unknown_p1(backend: BackendInterface,
                                       firmware: Firmware):
    client = TronClient(backend, firmware, None)
    _force_external_plugin_reset(client)
    with pytest.raises(ExceptionRAPDU) as err:
        backend.exchange(CLA, InsType.SIGN_EXTERNAL_PLUGIN, 0x7F, 0x00, b"")
    assert err.value.status == Errors.INCORRECT_P2


def test_external_plugin_more_without_init_returns_conditions_not_satisfied(
        backend: BackendInterface, firmware: Firmware):
    client = TronClient(backend, firmware, None)
    _force_external_plugin_reset(client)
    with pytest.raises(ExceptionRAPDU) as err:
        backend.exchange(CLA, InsType.SIGN_EXTERNAL_PLUGIN, P1_MORE, 0x00, b"")
    assert err.value.status == Errors.CONDITIONS_OF_USE_NOT_SATISFIED


def test_external_plugin_rejects_invalid_bip32_path(backend: BackendInterface,
                                               firmware: Firmware):
    client = TronClient(backend, firmware, None)
    _force_external_plugin_reset(client)
    with pytest.raises(ExceptionRAPDU) as err:
        backend.exchange(CLA, InsType.SIGN_EXTERNAL_PLUGIN, P1_FIRST, 0x00, b"\x05")
    assert err.value.status == Errors.INCORRECT_BIP32_PATH
    _force_external_plugin_reset(client)


def test_external_plugin_requires_tx_len_after_path(backend: BackendInterface,
                                               firmware: Firmware):
    client = TronClient(backend, firmware, None)
    _force_external_plugin_reset(client)
    # Build only a valid derivation path payload, without the mandatory tx length field.
    with pytest.raises(ExceptionRAPDU) as err:
        backend.exchange(CLA, InsType.SIGN_EXTERNAL_PLUGIN, P1_FIRST, 0x00,
                         pack_derivation_path(client.getAccount(0)["path"]))
    assert err.value.status == Errors.INCORRECT_LENGTH
    _force_external_plugin_reset(client)


def test_external_plugin_selector_mismatch_returns_invalid_data(
        backend: BackendInterface, firmware: Firmware):
    client = TronClient(backend, firmware, None)
    _force_external_plugin_reset(client)
    rapdu = _setup_external_plugin(backend, PLUGIN_NAME, _contract_address(client),
                                   TRC20_SWAP_SELECTOR)
    if rapdu.status == PLUGIN_NOT_FOUND:
        pytest.xfail("Plugin binary is not loaded in this test environment")
    assert rapdu.status == Errors.OK

    tx = _build_trc20_transfer_tx(client)
    with pytest.raises(ExceptionRAPDU) as err:
        client.sign(client.getAccount(0)["path"],
                    tx,
                    navigate=False,
                    ins=InsType.SIGN_EXTERNAL_PLUGIN,
                    include_tx_len=True)
    assert err.value.status == Errors.INCORRECT_DATA


def test_external_plugin_contract_mismatch_returns_invalid_data(
        backend: BackendInterface, firmware: Firmware):
    client = TronClient(backend, firmware, None)
    _force_external_plugin_reset(client)
    wrong_contract = bytes.fromhex(client.getAccount(1)["addressHex"])
    rapdu = _setup_external_plugin(backend, PLUGIN_NAME, wrong_contract,
                                   TRC20_TRANSFER_SELECTOR)
    if rapdu.status == PLUGIN_NOT_FOUND:
        pytest.xfail("Plugin binary is not loaded in this test environment")
    assert rapdu.status == Errors.OK

    tx = _build_trc20_transfer_tx(client)
    with pytest.raises(ExceptionRAPDU) as err:
        client.sign(client.getAccount(0)["path"],
                    tx,
                    navigate=False,
                    ins=InsType.SIGN_EXTERNAL_PLUGIN,
                    include_tx_len=True)
    assert err.value.status == Errors.INCORRECT_DATA


def test_external_plugin_plugin_parameter_rejection_returns_conditions_not_satisfied(
        backend: BackendInterface, firmware: Firmware):
    client = TronClient(backend, firmware, None)
    _force_external_plugin_reset(client)
    rapdu = _setup_external_plugin(backend, PLUGIN_NAME, _contract_address(client),
                                   TRC20_TRANSFER_SELECTOR)
    if rapdu.status == PLUGIN_NOT_FOUND:
        pytest.xfail("Plugin binary is not loaded in this test environment")
    assert rapdu.status == Errors.OK

    tx = _build_trigger_tx(client, _contract_address(client),
                           TRC20_TRANSFER_CALLDATA_WITH_EXTRA_PARAMETER)
    with pytest.raises(ExceptionRAPDU) as err:
        client.sign(client.getAccount(0)["path"],
                    tx,
                    navigate=False,
                    ins=InsType.SIGN_EXTERNAL_PLUGIN,
                    include_tx_len=True)
    assert err.value.status == Errors.CONDITIONS_OF_USE_NOT_SATISFIED


def test_external_plugin_plugin_query_ui_failure_returns_conditions_not_satisfied(
        backend: BackendInterface, firmware: Firmware):
    client = TronClient(backend, firmware, None)
    _force_external_plugin_reset(client)
    non_tron_contract = bytes.fromhex("42" + ("11" * 20))
    rapdu = _setup_external_plugin(backend, PLUGIN_NAME, non_tron_contract,
                                   TRC20_TRANSFER_SELECTOR)
    if rapdu.status == PLUGIN_NOT_FOUND:
        pytest.xfail("Plugin binary is not loaded in this test environment")
    assert rapdu.status == Errors.OK

    tx = _build_trigger_tx(client, non_tron_contract, TRC20_TRANSFER_CALLDATA)
    with pytest.raises(ExceptionRAPDU) as err:
        client.sign(client.getAccount(0)["path"],
                    tx,
                    navigate=False,
                    ins=InsType.SIGN_EXTERNAL_PLUGIN,
                    include_tx_len=True)
    assert err.value.status == Errors.CONDITIONS_OF_USE_NOT_SATISFIED


def test_external_plugin_with_external_plugin_success(backend: BackendInterface,
                                                 firmware: Firmware,
                                                 navigator: Navigator):
    client = TronClient(backend, firmware, navigator)
    _force_external_plugin_reset(client)
    rapdu = _setup_external_plugin(backend, PLUGIN_NAME, _contract_address(client),
                                   TRC20_TRANSFER_SELECTOR)
    if rapdu.status == PLUGIN_NOT_FOUND:
        pytest.xfail("Plugin binary is not loaded in this test environment")
    assert rapdu.status == Errors.OK

    tx = _build_trc20_transfer_tx(client)
    text = "Sign" if firmware.is_nano else "Hold to sign"
    resp = client.sign(client.getAccount(0)["path"],
                       tx,
                       snappath=Path("test_trx_trc20_send_external_plugin"),
                       text=text,
                       ins=InsType.SIGN_EXTERNAL_PLUGIN,
                       include_tx_len=True)
    assert check_tx_signature(tx, resp.data[0:65],
                              client.getAccount(0)["publicKey"][2:])
