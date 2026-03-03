import pytest
import subprocess
from pathlib import Path

from ragger.conftest import configuration
from .utils import WalletAddr


def _ensure_tron_proto_python() -> None:
    repo_root = Path(__file__).parent.parent.resolve()
    required_pb2 = [
        repo_root / "build" / "proto" / "core" / "Tron_pb2.py",
        repo_root / "build" / "proto" / "core" / "contract" / "smart_contract_pb2.py",
        repo_root / "build" / "proto" / "api" / "api_pb2_grpc.py",
    ]
    if all(path.exists() for path in required_pb2):
        return

    try:
        subprocess.run(["make", "proto-python"], cwd=repo_root, check=True)
    except FileNotFoundError as err:
        raise RuntimeError("`make` is required to generate protobuf python files.") from err
    except subprocess.CalledProcessError as err:
        raise RuntimeError(
            "Failed to generate protobuf python files. "
            "Run `make proto-python` and ensure `grpcio-tools` is installed."
        ) from err


_ensure_tron_proto_python()

###########################
### CONFIGURATION START ###
###########################
MNEMONIC = "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"

configuration.OPTIONAL.BACKEND_SCOPE = "class"
configuration.OPTIONAL.CUSTOM_SEED = MNEMONIC

###########################
### CONFIGURATION START ###
###########################

# You can configure optional parameters by overriding the value of ragger.configuration.OPTIONAL_CONFIGURATION
# Please refer to ragger/conftest/configuration.py for their descriptions and accepted values

configuration.OPTIONAL.MAIN_APP_DIR = "tests/.test_dependencies/"

configuration.OPTIONAL.BACKEND_SCOPE = "class"


#########################
### CONFIGURATION END ###
#########################

# Pull all features from the base ragger conftest using the overridden configuration
pytest_plugins = ("ragger.conftest.base_conftest", )

@pytest.fixture
def wallet_addr(backend):
    return WalletAddr(backend)
