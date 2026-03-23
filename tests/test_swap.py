import datetime
from pathlib import Path

from web3 import Web3

import pytest
from ragger.backend import BackendInterface
from ragger.firmware import Firmware
from ragger.navigator import Navigator
from pathlib import Path
from inspect import currentframe

from .external_plugin_helpers import (PLUGIN_NAME, PLUGIN_NOT_FOUND,
                                      abi_hex_to_bytes, build_trigger_tx,
                                      force_external_plugin_reset,
                                      load_contract_from_abi_fixture,
                                      setup_external_plugin,
                                      tron_contract_bytes_from_contract_id)
from .tron import Errors, InsType, TronClient
from .utils import check_tx_signature

SWAP_CONTRACT_B58 = "T9yED5xMV5ARV98BexN97aLZ1UUq7eKSxm"
SWAP_ABI_FILENAME = f"{SWAP_CONTRACT_B58}.abi.json"
contract = load_contract_from_abi_fixture(SWAP_ABI_FILENAME)
SWAP_CONTRACT_TRON_BYTES = tron_contract_bytes_from_contract_id(SWAP_CONTRACT_B58)

def test_swap_exact_eth_for_token(backend: BackendInterface,
                                  firmware: Firmware,
                                  navigator: Navigator):
    client = TronClient(backend, firmware, navigator)
    force_external_plugin_reset(client)

    data = abi_hex_to_bytes(contract.encode_abi("swapExactETHForTokens", [
        Web3.to_wei(28.5, "ether"),
        [
            bytes.fromhex("C02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"),
            bytes.fromhex("6B3595068778DD592e39A122f4f5a5cF09C90fE2")
        ],
        bytes.fromhex("d8dA6BF26964aF9D7eEd9e03E53415D37aA96045"),
        int(datetime.datetime(2023, 12, 25, 0, 0).timestamp())
    ]))

    rapdu = setup_external_plugin(backend, PLUGIN_NAME, SWAP_CONTRACT_TRON_BYTES,
                                  data[:4])
    if rapdu.status == PLUGIN_NOT_FOUND:
        pytest.xfail("Plugin binary is not loaded in this test environment")
    assert rapdu.status == Errors.OK

    tx = build_trigger_tx(client, SWAP_CONTRACT_TRON_BYTES, data)
    text = "Sign" if firmware.is_nano else "Hold to sign"
    resp = client.sign(client.getAccount(0)["path"],
                       tx,
                       snappath=Path(currentframe().f_code.co_name),
                       text=text,
                       ins=InsType.SIGN_EXTERNAL_PLUGIN,
                       include_tx_len=True)

    assert check_tx_signature(tx, resp.data[0:65],
                              client.getAccount(0)["publicKey"][2:])
