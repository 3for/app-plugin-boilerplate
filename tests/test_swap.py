from pathlib import Path
import sys

from ragger.backend import BackendInterface
from ragger.backend.interface import RaisePolicy
from ragger.firmware import Firmware
from ragger.navigator import Navigator

from .utils import get_appname_from_makefile
from .tron import TronClient, Errors, InsType
from .client.command_builder import CommandBuilder
from . import keychain
from .utils import check_tx_signature
'''
Tron Protobuf
'''
sys.path.append(f"{Path(__file__).parent.parent.resolve()}/proto")
from core import Contract_pb2 as contract
from core import Tron_pb2 as tron

PLUGIN_NAME = get_appname_from_makefile()

# EDIT THIS: build your own test
def test_swap_exact_eth_for_token(backend: BackendInterface,
                                  firmware: Firmware,
                                  navigator: Navigator):
    client = TronClient(backend, firmware, navigator)
    contract_address = bytes.fromhex(
        client.address_hex("TBoTZcARzWVgnNuB9SyE3S5g1RwsXoQL16"))
    selector = bytes.fromhex("a9059cbb")
    tx = client.packContract(
        tron.Transaction.Contract.TriggerSmartContract,
        contract.TriggerSmartContract(
            owner_address=bytes.fromhex(client.getAccount(0)['addressHex']),
            contract_address=contract_address,
            data=bytes.fromhex(
                "a9059cbb000000000000000000000000364b03e0815687edaf90b81ff58e496dea7383d700000000000000000000000000000000000000000000000000000000000f4240"
            )))

    cmd_builder = CommandBuilder()
    payload = bytearray()
    payload.append(len(PLUGIN_NAME))
    payload += PLUGIN_NAME.encode()
    payload += contract_address
    payload += selector
    sig = keychain.sign_data(keychain.Key.CAL, payload)
    apdu = cmd_builder.set_external_plugin(PLUGIN_NAME, contract_address,
                                           selector, sig)
    previous_policy = backend.raise_policy
    backend.raise_policy = RaisePolicy.RAISE_NOTHING
    try:
        rapdu = backend.exchange_raw(apdu)
    finally:
        backend.raise_policy = previous_policy
    assert rapdu.status in (Errors.OK, 0x6984)

    text = "Sign" if firmware.is_nano else "Hold to sign"
    resp = client.sign(client.getAccount(0)['path'],
                       tx,
                       snappath=Path("test_trx_trc20_send_clear_sign"),
                       text=text,
                       ins=InsType.CLEAR_SIGN,
                       include_tx_len=True)
    assert check_tx_signature(tx, resp.data[0:65],
                              client.getAccount(0)['publicKey'][2:])
