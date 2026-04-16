import datetime
from decimal import Decimal
from pathlib import Path

import pytest
from ragger.backend import BackendInterface
from ledgered.devices import Device
from ragger.navigator import Navigator
from pathlib import Path
from inspect import currentframe

from .external_plugin_helpers import (PLUGIN_NAME, PLUGIN_NOT_FOUND,
                                      abi_hex_to_bytes, build_trigger_tx,
                                      evm_hex_from_contract_id,
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
TRX_DECIMALS = 6
SWAP_CALL_VALUE = int(Decimal("0.1") * 10**TRX_DECIMALS)
PATH_ADDR_0_B58 = "TTVHrJWLPEMpsRJLs14bAZTpfXB5HBmNRa"
PATH_ADDR_1_B58 = "TKk5VY5HxbYJFc3nTr6XjV42n5LXdorkoB"
TO_ADDR_B58 = "TVjpchRyV9wdpj6kmwqVsBDWY1J8PaFtnb"
AMOUNT_OUT_MIN = int(Decimal("28.5") * 10**TRX_DECIMALS)
def test_swap_exact_trx_for_token(backend: BackendInterface,
                                  device: Device,
                                  navigator: Navigator):
    client = TronClient(backend, device, navigator)
    force_external_plugin_reset(client)

    data = abi_hex_to_bytes(contract.encode_abi("swapExactTRXForTokens", [
        AMOUNT_OUT_MIN,
        [
            bytes.fromhex(evm_hex_from_contract_id(PATH_ADDR_0_B58)),
            bytes.fromhex(evm_hex_from_contract_id(PATH_ADDR_1_B58))
        ],
        bytes.fromhex(evm_hex_from_contract_id(TO_ADDR_B58)),
        int(datetime.datetime(2023, 12, 25, 0, 0).timestamp())
    ]))

    rapdu = setup_external_plugin(backend, PLUGIN_NAME, SWAP_CONTRACT_TRON_BYTES,
                                  data[:4])
    if rapdu.status == PLUGIN_NOT_FOUND:
        pytest.xfail("Plugin binary is not loaded in this test environment")
    assert rapdu.status == Errors.OK

    tx = build_trigger_tx(client,
                          SWAP_CONTRACT_TRON_BYTES,
                          data,
                          call_value=SWAP_CALL_VALUE)
    text = "Sign" if device.is_nano else "Hold to sign"
    resp = client.sign(client.getAccount(0)["path"],
                       tx,
                       snappath=Path(currentframe().f_code.co_name),
                       text=text,
                       ins=InsType.SIGN_EXTERNAL_PLUGIN,
                       include_tx_len=True)

    assert check_tx_signature(tx, resp.data[0:65],
                              client.getAccount(0)["publicKey"][2:])
