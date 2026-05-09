import sys
from inspect import currentframe
from pathlib import Path

import pytest
from ledgered.devices import Device
from ragger.backend import BackendInterface
from ragger.navigator import Navigator

from .external_plugin_helpers import (PLUGIN_NAME, PLUGIN_NOT_FOUND,
                                      force_external_plugin_reset,
                                      provide_trc20_token_information,
                                      setup_external_plugin,
                                      tron_contract_bytes_from_contract_id)
from .tron import Errors, InsType, TronClient
from .utils import check_tx_signature

sys.path.append(f"{Path(__file__).parent.parent.resolve()}/build/proto")
from core import Tron_pb2 as tron
from core.contract import smart_contract_pb2 as contract


TRON_MAINNET_CHAIN_ID = 1151668124
SHIELDED_TRANSFER_SELECTOR = bytes.fromhex("9110a55b")
SHIELDED_TRANSFER_CONTRACT_B58 = "TNnFMMykZzwhPZkurKtNMyVGvgeSkCrnPi"
SHIELDED_TRANSFER_CONTRACT_BYTES = tron_contract_bytes_from_contract_id(
    SHIELDED_TRANSFER_CONTRACT_B58)
SHIELDED_TRANSFER_PARAMETER_HEX = (
    "00000000000000000000000000000000000000000000000000000000000000c0000000000000000000000000"
    "0000000000000000000000000000000000000220000000000000000000000000000000000000000000000000"
    "0000000000000280ce6afaf724f66efac204f6368123fcd2ef6ab565477400bab70e39ca68a581b94fc11db9"
    "de0f6951270d3fd7bea878fe4bad59f126fe446b33a66bfc8af3f70600000000000000000000000000000000"
    "000000000000000000000000000003c000000000000000000000000000000000000000000000000000000000"
    "00000001951e4c9456e7dbeed6831cd60b75d4727badc33e03bb08ab0ada011b9213747ac26c3206afaba02c"
    "8454263eb9bb6c9e2506704995b4e41989f9f47550045e5b616035300ff5e029ccdebfe596d4723f370b85e6"
    "88e21aacd6083e6139af5ca175efb6b823520d481440d1474b5b6f5bc2d1d534a7763ac5a688d2d1ec529898"
    "a040447b31a528060bcc561cc2a8d7adc6f726a6f6c7d6f03bab88d21af12f3b97a48b52da15c01cd5043b32"
    "f21d3454a742654aa4985072c9cedb8934a65c30d6e373e104e428b80c966dad68d28a5440d8f09e629009e2"
    "ca43774a7307e01e112691a20dedb4f79c182531ced0a5dce04b5e78836425d5ecf45d8fe5221b6da53d6f10"
    "ea310afd1d16184e502d00e3b1c43f91a2bf21c5a003fe9f106a51fc861ef502b01e82c6df897ae4786645db"
    "8f4f6a453be039f6bfaaf501ecaacf9200000000000000000000000000000000000000000000000000000000"
    "000000016ce9d10243a28f900cf2d2b5e9bec5cb3615ce2fa36e5e16050cb81865ae43b874e74feb01c94b3d"
    "282e46e39e615431a2aed82c10dc26cfb6f6e0227c2503050000000000000000000000000000000000000000"
    "000000000000000000000001233c627d5b726522420f072681c0905e3b13bfc68605a74eee2cc9b55acb2350"
    "7ae1e689515ff7301f3777ce11378b17c86ec6a443c79def76bd9eca613aa4b3b96780a9e19627cedf75b2a3"
    "c3bd3f4dda950fcec42e63f1696f12928ce1638b94f265307618c4dce68bd992e21fee80083870faca0ccbfd"
    "e2b32689327d37e1564f4c58eb9aaf87777c42a238569cb7b9aeae4478650121c0913b41319b165000eb0e88"
    "da3a041242f9c5961ae8367df889dd8018053f1cea342524b606467202635eafe3eb084a530bf024151c27be"
    "783662c9d29de7ea03d2ad8d8b39fec98348addd026f862ff9d06bebf0ad75a097f9a82d5bb1965d8fc3f7ca"
    "01688bf7e3f84b206fbab3baab8f9a9bf5b240e3726bf5293d7a862bd511fc80b0e1bf380000000000000000"
    "000000000000000000000000000000000000000000000001e47864bd06637a361b0567f911da6a3d6fb1eb78"
    "8b2348b90edf9d76b2906e59fc6a8923bfe76b1eb541170b85b9ff923d8da00deeefd5a2a93d1243845de484"
    "7712504f32927f792a1c81de64cc4e05d79882f80eccad69e2b0152470fdf65a5e0ee20e1d6c84e992267cb0"
    "931eb2c4f42eb95c1cdee9ee12da86f2d3e8da644df188bf81507da1409d3aef51dd7b3408bdb787acc9baae"
    "eb91b23d11727e6e111489852685aa809d97d6b066f73c54e88540e0fadacf3a7cae30c5f94527e485a1e324"
    "9f7bc3a82f80dc815f3a9172e61bc1bdd57de58826856957e989048f185bf6dcdd2b508b5761fb34c603df7a"
    "cb997ead52a5c6194c9bae77851f87fc4d0eb504e1c0b9dfd1a0f9c5593b5cf766eb00743043ca8441577c84"
    "536c7d9dc9203ff8911c1020f553c57ba34f59a7f3270eca785ca4a33c60f8df19fcbeab6c757093b4c89e18"
    "6c9956d9e3ee7610537f590bfb740fa1f544d4b797a0dd8a578817c41770ac0627ff4c8b4be7061a11768227"
    "5a5e38c9509c6deaa48929c908efb32d8a430c780d319157a24f020afad022494d72345ff64c3620afb6a0e6"
    "70dd4641b182ac97bd79b8052b97cefb0f1f5a8c6e26f0dea53c4a79cc4965fcddf3bf7d1b726c717d5ec1ee"
    "aca9b07ba83f0cd209f59bb35ccb59127919fcf080a1c04b63683e7159d78bb419cc84df6adf1849130e602d"
    "114ff54bf6b6e11544f17959af97cc83a16aa734ff740300538739e10dac20c7c4af8ddfef14d4f8e786162b"
    "5efbe9975acfa3cf13bf17c4c1857ef12858a5db6186570570b0a33368aa026221933e96c83d173937ef3703"
    "acea5c1cde95de19fbb9b46fdb0ed9a7395caad66ad89ec3f3a5ff35d5c49decaffbb34e9d5f05275139c15d"
    "bfd4b54d5f9284afea671fc7c913ad6097dc9ff021daf4a7000000000000000000000000"
)
SHIELDED_TRANSFER_CALLDATA = (SHIELDED_TRANSFER_SELECTOR +
                              bytes.fromhex(SHIELDED_TRANSFER_PARAMETER_HEX))


def test_sign_long_shielded_transfer(backend: BackendInterface,
                                                  device: Device,
                                                  navigator: Navigator):
    client = TronClient(backend, device, navigator)
    force_external_plugin_reset(client)

    rapdu = setup_external_plugin(backend,
                                  PLUGIN_NAME,
                                  SHIELDED_TRANSFER_CONTRACT_BYTES,
                                  SHIELDED_TRANSFER_SELECTOR)
    if rapdu.status == PLUGIN_NOT_FOUND:
        pytest.xfail("Plugin binary is not loaded in this test environment")
    assert rapdu.status == Errors.OK

    rapdu = provide_trc20_token_information(backend,
                                            "JST",
                                            SHIELDED_TRANSFER_CONTRACT_BYTES,
                                            18,
                                            TRON_MAINNET_CHAIN_ID)
    assert rapdu.status == Errors.OK

    tx = client.packContract(
        tron.Transaction.Contract.TriggerSmartContract,
        contract.TriggerSmartContract(
            owner_address=bytes.fromhex(client.getAccount(0)["addressHex"]),
            contract_address=SHIELDED_TRANSFER_CONTRACT_BYTES,
            data=SHIELDED_TRANSFER_CALLDATA))

    text = "Sign" if device.is_nano else "Hold to sign"
    resp = client.sign(client.getAccount(0)["path"],
                       tx,
                       snappath=Path(currentframe().f_code.co_name),
                       text=text,
                       ins=InsType.SIGN_EXTERNAL_PLUGIN,
                       include_tx_len=True)
    assert check_tx_signature(tx, resp.data[0:65],
                              client.getAccount(0)["publicKey"][2:])
