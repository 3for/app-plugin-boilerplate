import sys
from pathlib import Path
from inspect import currentframe

import pytest
from ragger.backend import BackendInterface
from ledgered.devices import Device
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

MINT_CONTRACT_B58 = "TNnFMMykZzwhPZkurKtNMyVGvgeSkCrnPi"
MINT_CONTRACT_BYTES = tron_contract_bytes_from_contract_id(MINT_CONTRACT_B58)
TRON_MAINNET_CHAIN_ID = 1151668124

# mint(uint256 rawValue, bytes32[9] output, bytes32[2] bindingSignature, bytes32[21] c)
MINT_CALLDATA = bytes.fromhex(
    "855d175e"
    "0000000000000000000000000000000000000000000000003782dace9d900000"
    "432464fe1e9c33eaf99edad710ef11359d0291506bc81f7445f1447ba112ab18"
    "30579dd4decdd0ed38f33215375c00e1fb324f0f35892991aa0b8f5eb2a9dfcb"
    "1533ca563b77de5177a41e8ffefb2fd688334af95bcd1143470318c026b00e2e"
    "86227c50592880dd3f0c362258714e50b9b9d54eb193b0bba6cc04cf348d841d"
    "55261810658d9eeaeb2920005179f9e099c9eaf06c793ccc3ec2f30c8f52d939"
    "4d0f6084bc53f142663d713f6ef575db86b0c55abfe9aacf6515bb0a5986a0b2"
    "14bc1c48c9678906c88a4c625336b8d8a9be49d1ec75762bb60338f738ad9989"
    "1b98ce18c723e76e70f53dce7c03b247aa937354a6954feac4f8858ae5830b3c"
    "fc0466421864b2ffc5740dc19210e691d5d4fccf9a3e7d1f4ef6e2a676975dec"
    "cd63c5990d8275dc35d0922be3bd5dc7c4a81494e8276b282e61a19fbe9cca05"
    "32592b05623b7bffee09ef81fb298cbaf4ece9c42fe5ac80a716e90c7dff7f01"
    "2c1215f739c89e715ffab693eff699b5eb6368753af0c0087274db0f14c38ce7"
    "b0b36100f9a2f51cc7f6eca87eb750544f9fbe18ea79dbd8595028c4d33da6ee"
    "62afe4eca52cfe40f164f00063abe1c76e3d0fc0af2db17aad96b3f472d41f0b"
    "56d8dd4fa5b9d6de028678731425871cbf134701c351aba7edeaad07e8d40060"
    "1e245bc1751ebb514365c774e5108c348a39533e836a10338ab8ae00ceb0f819"
    "f3f45268ee88bdf9fdadf6c921269d707fe457fa25d6997a5da382ac8b4f960a"
    "381ab539c33421931569785dbe6dfa59914ca6bc597576e9e33314eb62326658"
    "c8548c22622f3a9a06b3fe40842210018bedbda8e95662a2a7bb1db9121e39bc"
    "c2f6d004c9b7cf5131d3989a32a3ade8c447d34b4244841a0cb071efdd7ed68e"
    "7c02d1aeadbda9ab1f6e5f3f2b0227e07a8d5e30418e354f000329f12f4462aa"
    "c4db0dbd034e85ed9b3dc2cac483c41bdfa690fefacfc038dd20067b1e8dc1e7"
    "72e1c719ad4e6b14c87c779b4477daa5edb47a5218ad5d4afb6983d460aa012e"
    "6415ac67135a9f9cb438ca9f9655fd2dfd44a43785d2eb7e8b4d77e81573f7f0"
    "2355f114601e9909793ec437d9d2257512c799c0ee769876bb98842995d73468"
    "e1a81ef9c8dc5e6702179d25632cfe8ec8214b76b6bceab5741ade28f5fa10ff"
    "a72abfcfaffb7e8224fc89fe65a2c440fa9a291e974f366ec5c87302e86d1df7"
    "4b73396f5e35030106dcc9ac54f20557a58dabba7975decbce146536f4a1b13d"
    "71f549e7b7d8c5e61b3c92118dbf0f6dacd09a24f3514d1642f711d02b6c29d4"
    "7f5d3f4a2b7c66dd941eb9f02ba311a72c00f449a837767c5d71e99414c84cf9"
    "e8c37ef731efaaa8266cdd309311615aea396f264389fe115abb0a1967a9af14"
    "b972f20d8bf31550d9c4e67366161b5546b58003000000000000000000000000")

MINT_SELECTOR = MINT_CALLDATA[:4]

CUSTOM_DATA = (
    "In this section of the Developer Portal, you will find the resources "
    "to build, test and submit C and Rust apps, Ethereum plugins and "
    "Cloned coins apps, compatible with all Ledger devices (Ledger Nano S+, "
    "Ledger Nano X, Ledger Stax and Ledger Flex).This is a test case for "
    "extra data.").encode()


def test_sign_long_trigger_smart_contract(backend: BackendInterface,
                                          device: Device,
                                          navigator: Navigator):
    client = TronClient(backend, device, navigator)
    force_external_plugin_reset(client)

    rapdu = setup_external_plugin(backend, PLUGIN_NAME,
                                  MINT_CONTRACT_BYTES,
                                  MINT_SELECTOR)
    if rapdu.status == PLUGIN_NOT_FOUND:
        pytest.xfail("Plugin binary is not loaded in this test environment")
    assert rapdu.status == Errors.OK

    rapdu = provide_trc20_token_information(backend, "JST",
                                            MINT_CONTRACT_BYTES,
                                            18,
                                            TRON_MAINNET_CHAIN_ID)
    assert rapdu.status == Errors.OK

    tx = client.packContract(
        tron.Transaction.Contract.TriggerSmartContract,
        contract.TriggerSmartContract(
            owner_address=bytes.fromhex(client.getAccount(0)["addressHex"]),
            contract_address=MINT_CONTRACT_BYTES,
            data=MINT_CALLDATA),
        CUSTOM_DATA)

    text = "Sign" if device.is_nano else "Hold to sign"
    resp = client.sign(client.getAccount(0)["path"],
                       tx,
                       snappath=Path(currentframe().f_code.co_name),
                       text=text,
                       ins=InsType.SIGN_EXTERNAL_PLUGIN,
                       include_tx_len=True)
    assert check_tx_signature(tx, resp.data[0:65],
                              client.getAccount(0)["publicKey"][2:])
