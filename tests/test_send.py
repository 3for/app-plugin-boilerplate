from pathlib import Path

import pytest
from ragger.backend import BackendInterface
from ragger.bip import pack_derivation_path
from ragger.error import ExceptionRAPDU
from ragger.firmware import Firmware
from ragger.navigator import Navigator
from inspect import currentframe

from .client.command_builder import InsType as BuilderInsType
from .external_plugin_helpers import (PLUGIN_NAME, PLUGIN_NOT_FOUND,
                                      abi_hex_to_bytes, build_trigger_tx,
                                      evm_hex_from_contract_id,
                                      force_external_plugin_reset,
                                      load_contract_from_abi_fixture,
                                      provide_trc20_token_information,
                                      setup_external_plugin,
                                      tron_contract_bytes_from_contract_id)
from .tron import CLA, Errors, InsType, TronClient
from .utils import check_tx_signature

TRC20_CONTRACT_B58 = "TXYZopYRdj2D9XRtbG411XZZ3kM5VkAeBf"
TRC20_ABI_FILENAME = f"{TRC20_CONTRACT_B58}.abi.json"
TRC20_CONTRACT_BYTES = tron_contract_bytes_from_contract_id(TRC20_CONTRACT_B58)
TRC20_TRANSFER_RECIPIENT_B58 = "TEvHMZWyfjCAdDJEKYxYVL8rRpigddLC1R"
TRC20_TRANSFER_RECIPIENT_HEX = evm_hex_from_contract_id(TRC20_TRANSFER_RECIPIENT_B58)
TRC20_TRANSFER_AMOUNT = 1_000_000
TRC20_EXTRA_PARAMETER = (1).to_bytes(32, byteorder="big")
TRC20_SWAP_SELECTOR = bytes.fromhex("7ff36ab5")
TRC20_CONTRACT = load_contract_from_abi_fixture(TRC20_ABI_FILENAME)
TRC20_TRANSFER_CALLDATA = abi_hex_to_bytes(
    TRC20_CONTRACT.encode_abi(
        "transfer",
        [bytes.fromhex(TRC20_TRANSFER_RECIPIENT_HEX), TRC20_TRANSFER_AMOUNT]))
TRC20_TRANSFER_SELECTOR = TRC20_TRANSFER_CALLDATA[:4]
TRC20_TRANSFER_CALLDATA_WITH_EXTRA_PARAMETER = (TRC20_TRANSFER_CALLDATA +
                                                TRC20_EXTRA_PARAMETER)
TRC20_TOKEN_TICKER = "USDT"
TRC20_TOKEN_DECIMALS = 6
TRON_MAINNET_CHAIN_ID = 1151668124

P1_FIRST = 0x00
P1_SIGN = 0x10
P1_MORE = 0x80


def contract_address() -> bytes:
    return TRC20_CONTRACT_BYTES


def build_trc20_transfer_tx(client: TronClient) -> bytes:
    return build_trigger_tx(client, contract_address(), TRC20_TRANSFER_CALLDATA)

def test_setup_rejects_short_payload(backend: BackendInterface):
    with pytest.raises(ExceptionRAPDU) as err:
        backend.exchange(CLA, BuilderInsType.EXTERNAL_PLUGIN_SETUP, 0x00, 0x00,
                         b"\x00")
    assert err.value.status == Errors.INCORRECT_DATA


def test_setup_rejects_name_too_long(
        backend: BackendInterface, firmware: Firmware):
    client = TronClient(backend, firmware, None)
    rapdu = setup_external_plugin(backend, "x" * 30, contract_address(),
                                  TRC20_TRANSFER_SELECTOR)
    assert rapdu.status == Errors.INCORRECT_DATA


def test_setup_rejects_invalid_signature(
        backend: BackendInterface, firmware: Firmware):
    client = TronClient(backend, firmware, None)
    rapdu = setup_external_plugin(backend,
                                  PLUGIN_NAME,
                                  contract_address(),
                                  TRC20_TRANSFER_SELECTOR,
                                  signature=b"\x30\x06\x02\x01\x01\x02\x01\x01")
    assert rapdu.status == Errors.INCORRECT_DATA


def test_setup_returns_plugin_not_found(
        backend: BackendInterface, firmware: Firmware):
    client = TronClient(backend, firmware, None)
    try:
        rapdu = setup_external_plugin(backend, "missingPlugin",
                                      contract_address(),
                                      TRC20_TRANSFER_SELECTOR)
        assert rapdu.status == PLUGIN_NOT_FOUND
    except Exception as err:
        if (isinstance(err, TimeoutError)
                or err.__class__.__name__ == "ChunkedEncodingError"):
            pytest.xfail(
                "Speculos crashes when checking presence of a missing external plugin"
            )
        raise


def test_sign_rejects_when_plugin_not_configured(
        backend: BackendInterface, firmware: Firmware):
    client = TronClient(backend, firmware, None)
    force_external_plugin_reset(client)
    tx = build_trc20_transfer_tx(client)
    with pytest.raises(ExceptionRAPDU) as err:
        client.sign(client.getAccount(0)["path"],
                    tx,
                    navigate=False,
                    ins=InsType.SIGN_EXTERNAL_PLUGIN,
                    include_tx_len=True)
    assert err.value.status == Errors.INCORRECT_DATA


def test_sign_rejects_nonzero_p2(backend: BackendInterface,
                                                 firmware: Firmware):
    client = TronClient(backend, firmware, None)
    force_external_plugin_reset(client)
    with pytest.raises(ExceptionRAPDU) as err:
        backend.exchange(CLA, InsType.SIGN_EXTERNAL_PLUGIN, P1_SIGN, 0x01, b"")
    assert err.value.status == Errors.INCORRECT_P2


def test_sign_rejects_unknown_p1(backend: BackendInterface,
                                                 firmware: Firmware):
    client = TronClient(backend, firmware, None)
    force_external_plugin_reset(client)
    with pytest.raises(ExceptionRAPDU) as err:
        backend.exchange(CLA, InsType.SIGN_EXTERNAL_PLUGIN, 0x7F, 0x00, b"")
    assert err.value.status == Errors.INCORRECT_P2


def test_sign_rejects_more_without_init(
        backend: BackendInterface, firmware: Firmware):
    client = TronClient(backend, firmware, None)
    force_external_plugin_reset(client)
    with pytest.raises(ExceptionRAPDU) as err:
        backend.exchange(CLA, InsType.SIGN_EXTERNAL_PLUGIN, P1_MORE, 0x00, b"")
    assert err.value.status == Errors.CONDITIONS_OF_USE_NOT_SATISFIED


def test_sign_rejects_invalid_bip32_path(
        backend: BackendInterface, firmware: Firmware):
    client = TronClient(backend, firmware, None)
    force_external_plugin_reset(client)
    with pytest.raises(ExceptionRAPDU) as err:
        backend.exchange(CLA, InsType.SIGN_EXTERNAL_PLUGIN, P1_FIRST, 0x00, b"\x05")
    assert err.value.status == Errors.INCORRECT_BIP32_PATH
    force_external_plugin_reset(client)


def test_sign_requires_tx_len_after_path(
        backend: BackendInterface, firmware: Firmware):
    client = TronClient(backend, firmware, None)
    force_external_plugin_reset(client)
    # Build only a valid derivation path payload, without the mandatory tx length field.
    with pytest.raises(ExceptionRAPDU) as err:
        backend.exchange(CLA, InsType.SIGN_EXTERNAL_PLUGIN, P1_FIRST, 0x00,
                         pack_derivation_path(client.getAccount(0)["path"]))
    assert err.value.status == Errors.INCORRECT_LENGTH
    force_external_plugin_reset(client)


def test_sign_rejects_selector_mismatch(
        backend: BackendInterface, firmware: Firmware):
    client = TronClient(backend, firmware, None)
    force_external_plugin_reset(client)
    rapdu = setup_external_plugin(backend, PLUGIN_NAME, contract_address(),
                                  TRC20_SWAP_SELECTOR)
    if rapdu.status == PLUGIN_NOT_FOUND:
        pytest.xfail("Plugin binary is not loaded in this test environment")
    assert rapdu.status == Errors.OK

    tx = build_trc20_transfer_tx(client)
    with pytest.raises(ExceptionRAPDU) as err:
        client.sign(client.getAccount(0)["path"],
                    tx,
                    navigate=False,
                    ins=InsType.SIGN_EXTERNAL_PLUGIN,
                    include_tx_len=True)
    assert err.value.status == Errors.INCORRECT_DATA


def test_sign_rejects_contract_mismatch(
        backend: BackendInterface, firmware: Firmware):
    client = TronClient(backend, firmware, None)
    force_external_plugin_reset(client)
    wrong_contract = bytes.fromhex(client.getAccount(1)["addressHex"])
    rapdu = setup_external_plugin(backend, PLUGIN_NAME, wrong_contract,
                                  TRC20_TRANSFER_SELECTOR)
    if rapdu.status == PLUGIN_NOT_FOUND:
        pytest.xfail("Plugin binary is not loaded in this test environment")
    assert rapdu.status == Errors.OK

    tx = build_trc20_transfer_tx(client)
    with pytest.raises(ExceptionRAPDU) as err:
        client.sign(client.getAccount(0)["path"],
                    tx,
                    navigate=False,
                    ins=InsType.SIGN_EXTERNAL_PLUGIN,
                    include_tx_len=True)
    assert err.value.status == Errors.INCORRECT_DATA


def test_sign_rejects_extra_parameter(
        backend: BackendInterface, firmware: Firmware):
    client = TronClient(backend, firmware, None)
    force_external_plugin_reset(client)
    rapdu = setup_external_plugin(backend, PLUGIN_NAME, contract_address(),
                                  TRC20_TRANSFER_SELECTOR)
    if rapdu.status == PLUGIN_NOT_FOUND:
        pytest.xfail("Plugin binary is not loaded in this test environment")
    assert rapdu.status == Errors.OK

    tx = build_trigger_tx(client,
                          contract_address(),
                          TRC20_TRANSFER_CALLDATA_WITH_EXTRA_PARAMETER)
    with pytest.raises(ExceptionRAPDU) as err:
        client.sign(client.getAccount(0)["path"],
                    tx,
                    navigate=False,
                    ins=InsType.SIGN_EXTERNAL_PLUGIN,
                    include_tx_len=True)
    assert err.value.status == Errors.CONDITIONS_OF_USE_NOT_SATISFIED


def test_sign_rejects_non_tron_contract(
        backend: BackendInterface, firmware: Firmware):
    client = TronClient(backend, firmware, None)
    force_external_plugin_reset(client)
    non_tron_contract = bytes.fromhex("42" + ("11" * 20))
    rapdu = setup_external_plugin(backend, PLUGIN_NAME, non_tron_contract,
                                  TRC20_TRANSFER_SELECTOR)
    if rapdu.status == PLUGIN_NOT_FOUND:
        pytest.xfail("Plugin binary is not loaded in this test environment")
    assert rapdu.status == Errors.OK

    tx = build_trigger_tx(client, non_tron_contract, TRC20_TRANSFER_CALLDATA)
    with pytest.raises(ExceptionRAPDU) as err:
        client.sign(client.getAccount(0)["path"],
                    tx,
                    navigate=False,
                    ins=InsType.SIGN_EXTERNAL_PLUGIN,
                    include_tx_len=True)
    assert err.value.status == Errors.CONDITIONS_OF_USE_NOT_SATISFIED


def test_sign_trc20_transfer(backend: BackendInterface,
                                              firmware: Firmware,
                                              navigator: Navigator):
    client = TronClient(backend, firmware, navigator)
    force_external_plugin_reset(client)
    rapdu = setup_external_plugin(backend, PLUGIN_NAME, contract_address(),
                                  TRC20_TRANSFER_SELECTOR)
    if rapdu.status == PLUGIN_NOT_FOUND:
        pytest.xfail("Plugin binary is not loaded in this test environment")
    assert rapdu.status == Errors.OK
    # For testing purposes only; in production, it should be signed by Ledger. 
    rapdu = provide_trc20_token_information(backend,
                                            TRC20_TOKEN_TICKER,
                                            tron_contract_bytes_from_contract_id(
                                                TRC20_CONTRACT_B58),
                                            TRC20_TOKEN_DECIMALS,
                                            TRON_MAINNET_CHAIN_ID)
    assert rapdu.status == Errors.OK

    tx = build_trc20_transfer_tx(client)
    text = "Sign" if firmware.is_nano else "Hold to sign"
    resp = client.sign(client.getAccount(0)["path"],
                       tx,
                       snappath=Path(currentframe().f_code.co_name),
                       text=text,
                       ins=InsType.SIGN_EXTERNAL_PLUGIN,
                       include_tx_len=True)
    assert check_tx_signature(tx, resp.data[0:65],
                              client.getAccount(0)["publicKey"][2:])
