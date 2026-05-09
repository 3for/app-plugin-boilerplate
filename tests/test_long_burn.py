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
                                      setup_external_plugin)
from .tron import Errors, InsType, TronClient
from .utils import check_tx_signature

sys.path.append(f"{Path(__file__).parent.parent.resolve()}/build/proto")
from core import Tron_pb2 as tron
from core.contract import smart_contract_pb2 as contract


TRON_MAINNET_CHAIN_ID = 1151668124
SHIELDED_BURN_SELECTOR = bytes.fromhex("cc105875")
SHIELDED_BURN_CONTRACT_HEX = "418C8705769E5ec53F5F9C42A3bc3305624AD37192"
SHIELDED_BURN_CONTRACT_BYTES = bytes.fromhex(SHIELDED_BURN_CONTRACT_HEX)
SHIELDED_BURN_PARAMETER_HEX = (
    "411fcd54cea8939bd45b9ad7b2c0001872eb50903f8e6e063bd6d46aff890206afa8e0e221d5997d57547d76"
    "66a7c2f776317b2a2906c58055551972622a7d6fc9074c2907d279a4e6cf6d5c7098516b338564c554010876"
    "05e2b1f554f146d83c71fc1792c27f464fc1c5a7dfe0a6806cc6921cef46a41008de6a18e78dfee7a0e0f3ec"
    "e3fd4d7a3db027e11c3fa8f58346539502eb9dd17db76fd60f79657303b95dcfa2e2e8bc069a793fc71d501d"
    "a737ff5deee54e1f659f1fda4ce5428c18b3cca5f816ef3308dd3d2bf323de1bd361183d829ebd21b3198c30"
    "6d30176506efba80a1a341ea8eae32d3f263294b5cd48e16a7f481230c83cb0fa198718fba949736aba6e1b7"
    "cfcffbb7aca62624867e948c97cda7e4e4b0038bd51933bed2d56ff884d4ac7c12e8fb3a84ccddb6f3830b36"
    "424ac2f1c09b2ed784d2208cb8dfa7a9aa61016cc74876572938c48edd9ae4e9061501db182991030596aca5"
    "791900aba9c4dfb97f1ebb328f27b7d470e90aa4d7c56ad2184abb4c45b1f408000000000000000000000000"
    "00000000000000000000000029a2241af62c00000423e07a9c2e1f4bc5192f5dc42e413e508cc85bbd4bdfb5"
    "1022c626e890cadedf7737598997f77d9639ca3764f56e54950f6e4dc3148c3bf585135af1108f0200000000"
    "000000000000004119580b8d292f590d254ab037320975ab367891945d4188e801642649a5d69f6ba4a174aa"
    "57b97410d5a2ba17c7dae76462b3e1e23e3007946b5f21510ed860e048e638a6dbd76c5670b753b83383962e"
    "b486e693e92fbbdc97a835c02a93c33030a888f5000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000002a00000000000000000000000000000000000000000"
    "0000000000000000000003e00000000000000000000000000000000000000000000000000000000000000001"
    "f4f835357d8ca230e33488f80c83bacc79bc234333d60b5a73c1a8e5255b336263861fb9e1882c9be89afe4f"
    "7c5529c87e38c8aa5da2a663dddce5d620f786247ff151f8bcca7cc3c968a18fab7ea8f291263356ad18a45a"
    "b37d6235689be33aa7a0d63bb0247c9b8fa870f496ced81c1096e7a35f171d10b704f098e91d6be554f8248b"
    "86566c5a6f66af4cca0b9557a1a11a6aaa8d054f644dbcba9a77ada5e245870d23f1ee4e29c1063507bbba52"
    "6a596b93930fb5d8ae6895bace0818430e75585a8a655b342c2c9239675c95a54cabdd83d1590aa62acf3b47"
    "86648d94084084484f19496a722eb387b24599a688126cfc46dc75a8872e923add73763c74369413a73b9ce2"
    "0c44bfba051ebfd43bd075b1ca5d1eb11568a0721b8a63280000000000000000000000000000000000000000"
    "000000000000000000000001ff387be3765524f0b6ebb5552402188980d16e63559fc62f7b7e89720b213121"
    "ba385494a87c778d5c2ccd745888321f882658c2e26687ead9b21f46f3c7364388ed7c63ecb1aa66fe86e036"
    "ad2b40d2a1df90fa0c7a81aa24bd9e6010231e2d94a874954245fd48bbe6521933fef5f8bd78ae07dea625eb"
    "b2c0273cde2b1acf7f07883e5f4f05fb70b3f1b45735addcdf9410c81444d0575d177c5a5676b44c666948ce"
    "09cac6a1ea0d5710652f0ce31d372648b874f64ba487579a0045b4b44949a9fa1a22fc949c3cad5da1c334ee"
    "25d5357ae41dad9ed54e6433c5ba2d31101f652e992c7e922e1fd40ba9221a0c53c54eb89c49c68395eb61e1"
    "b489882759a788a4ea383167950e3adc80ebd3bbea11b490d402a64634006cd10170ad84cbb34c6c4a239df3"
    "3b962fb4dedd62fefc1c03089a5481da96f6e09c47c5197ea58dfd3193cde8e9e3acf4fa74beefca94df5bf9"
    "c99dacfc298e14cab2360a10f7d76a77ecc4471d513be5262a7ffe52177c11ba24e626cbc33e12cddbf02bb4"
    "2d80aabcd86e03fd4f733ede78a9682842803605a924b99cd1048984a4131780935d70975f99c5685445e1d3"
    "345cb4848e4fc68df984049cf5abd02abb5525c8df5870797d8a0905ecff4f37b9f0e1d25ae99c6d31174983"
    "0208f7c2cb47043afc1dc44c9f2dbdbeeb54e352d77ab5b629917b659f7e69e91521577ae1b3c7aff99ed318"
    "48ea7302e07cff9851213bda670cd6c895bbeb37a991ca09d2debe034fb37e1a0aa791323217790f72cde2d4"
    "1c1f5e32878253d8b0f5db896a22a6ab2437c5f8d126e7505412a109939ccdd634cc04993a197725d0b8e2f4"
    "350f3d041199c9b6d7756a863afa9793293b25ff17d2472499b64f321c4e9fecf4fcee7e79ba7e62fe2c3dc0"
    "34d381f7d65c9d310349a8e4000000000000000000000000"
)
SHIELDED_BURN_CALLDATA = (SHIELDED_BURN_SELECTOR +
                          bytes.fromhex(SHIELDED_BURN_PARAMETER_HEX))


def test_sign_long_shielded_burn(backend: BackendInterface,
                                 device: Device,
                                 navigator: Navigator):
    client = TronClient(backend, device, navigator)
    force_external_plugin_reset(client)

    rapdu = setup_external_plugin(backend,
                                  PLUGIN_NAME,
                                  SHIELDED_BURN_CONTRACT_BYTES,
                                  SHIELDED_BURN_SELECTOR)
    if rapdu.status == PLUGIN_NOT_FOUND:
        pytest.xfail("Plugin binary is not loaded in this test environment")
    assert rapdu.status == Errors.OK

    rapdu = provide_trc20_token_information(backend,
                                            "JST",
                                            SHIELDED_BURN_CONTRACT_BYTES,
                                            18,
                                            TRON_MAINNET_CHAIN_ID)
    assert rapdu.status == Errors.OK

    tx = client.packContract(
        tron.Transaction.Contract.TriggerSmartContract,
        contract.TriggerSmartContract(
            owner_address=bytes.fromhex(client.getAccount(0)["addressHex"]),
            contract_address=SHIELDED_BURN_CONTRACT_BYTES,
            data=SHIELDED_BURN_CALLDATA))

    text = "Sign" if device.is_nano else "Hold to sign"
    resp = client.sign(client.getAccount(0)["path"],
                       tx,
                       snappath=Path(currentframe().f_code.co_name),
                       text=text,
                       ins=InsType.SIGN_EXTERNAL_PLUGIN,
                       include_tx_len=True)
    assert check_tx_signature(tx, resp.data[0:65],
                              client.getAccount(0)["publicKey"][2:])
