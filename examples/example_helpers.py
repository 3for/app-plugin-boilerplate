#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import hashlib
import re
import struct
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import base58
from ecdsa import SigningKey
from ecdsa.util import sigencode_der
from eth_keys import KeyAPI
from eth_keys.datatypes import PublicKey, Signature
from eth_utils import keccak
from ledgerblue.commException import CommException


ROOT_DIR = Path(__file__).resolve().parent.parent
PROTO_DIR = ROOT_DIR / "build" / "proto"

if str(PROTO_DIR) not in sys.path:
    sys.path.append(str(PROTO_DIR))

try:
    from api import api_pb2_grpc
    from core.contract import smart_contract_pb2 as smart_contract
except ModuleNotFoundError as exc:
    raise ModuleNotFoundError(
        "Missing generated protobuf modules under build/proto. Run `make proto-python` first."
    ) from exc


WalletStub = api_pb2_grpc.WalletStub


CLA = 0xE0

INS_GET_PUBLIC_KEY = 0x02
INS_SIGN_EXTERNAL_PLUGIN = 0xC4
INS_EXTERNAL_PLUGIN_SETUP = 0x12

P1_FIRST = 0x00
P1_MORE = 0x80
P1_LAST = 0x90
P1_SIGN = 0x10

MAX_APDU_DATA_LEN = 255


@dataclass
class Account:
    path: str
    public_key_hex: str
    address: str
    address_hex: str


def pack_derivation_path(path: str) -> bytes:
    cleaned = path.strip()
    if cleaned.startswith("m/"):
        cleaned = cleaned[2:]
    elements = [elem for elem in cleaned.split("/") if elem]
    data = bytearray([len(elements)])
    for elem in elements:
        if elem.endswith("'"):
            value = 0x80000000 | int(elem[:-1])
        else:
            value = int(elem)
        data += struct.pack(">I", value)
    return bytes(data)


def build_apdu(ins: int, p1: int, p2: int, cdata: bytes = b"") -> bytes:
    if len(cdata) > MAX_APDU_DATA_LEN:
        raise ValueError(f"APDU data too long: {len(cdata)} > {MAX_APDU_DATA_LEN}")
    return bytes([CLA, ins, p1, p2, len(cdata)]) + cdata


def trx_address_to_hex(address: str) -> str:
    return base58.b58decode_check(address).hex().upper()


def evm_hex_from_contract_id(contract_id: str) -> str:
    if contract_id.startswith("0x"):
        return contract_id[2:]
    if len(contract_id) == 40:
        return contract_id
    return trx_address_to_hex(contract_id)[2:]


def evm_address_bytes_from_contract_id(contract_id: str) -> bytes:
    return bytes.fromhex(evm_hex_from_contract_id(contract_id))


def tron_contract_bytes_from_contract_id(contract_id: str) -> bytes:
    if contract_id.startswith("0x"):
        contract_id = contract_id[2:]
    if len(contract_id) == 40:
        return bytes.fromhex(f"41{contract_id}")
    return base58.b58decode_check(contract_id)


def selector_from_signature(signature: str) -> bytes:
    # TRON smart contract calldata follows the Ethereum ABI selector convention.
    return keccak(text=signature)[:4]


def encode_uint256(value: int) -> bytes:
    if value < 0:
        raise ValueError("uint256 value must be non-negative")
    return value.to_bytes(32, byteorder="big")


def encode_address(value: bytes) -> bytes:
    if len(value) != 20:
        raise ValueError(f"Address must be 20 bytes, got {len(value)}")
    return value.rjust(32, b"\x00")


def encode_address_array(values: list[bytes]) -> bytes:
    return encode_uint256(len(values)) + b"".join(encode_address(value) for value in values)


def read_plugin_name(makefile_path: Path) -> str:
    pattern = re.compile(r'^\s*APPNAME\s*=\s*"?([^"\n]+)"?\s*$')
    with makefile_path.open("r", encoding="utf-8") as file:
        for line in file:
            match = pattern.match(line)
            if match:
                return match.group(1).strip()
    raise RuntimeError(f"APPNAME not found in {makefile_path}")


def sign_with_cal(cal_pem_path: Path, payload: bytes) -> bytes:
    with cal_pem_path.open("r", encoding="utf-8") as file:
        signing_key = SigningKey.from_pem(file.read(), hashlib.sha256)
    return signing_key.sign_deterministic(payload, sigencode=sigencode_der)


def _list_connected_devices():
    try:
        from ledgered.devices import Device
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Missing optional dependency `ledgered`. Install the physical-device helpers to auto-open apps."
        ) from exc
    return list(Devices())


def get_connected_device(device_name: Optional[str] = None):
    devices = _list_connected_devices()
    if not devices:
        raise RuntimeError("No Ledger device detected.")

    if device_name is None:
        if len(devices) == 1:
            return devices[0]
        available = ", ".join(device.name for device in devices)
        raise RuntimeError(f"Multiple Ledger devices detected. Pass --device. Available devices: {available}")

    for device in devices:
        if device.name == device_name:
            return device

    available = ", ".join(device.name for device in devices)
    raise RuntimeError(f"Unsupported device '{device_name}'. Available devices: {available}")


def ensure_requested_app(
    *,
    requested_app: str,
    device_name: Optional[str] = None,
    skip_open_app: bool = False,
    with_gui: bool = False,
    logger=None,
) -> None:
    if skip_open_app:
        return

    try:
        from ragger.backend import LedgerCommBackend
        from ragger.utils.misc import (exit_current_app, get_current_app_name_and_version,
                                       open_app_from_dashboard)
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Missing optional dependency `ragger`. Install it to auto-open apps from the dashboard."
        ) from exc

    device = get_connected_device(device_name)
    with LedgerCommBackend(device=device, interface="hid", with_gui=with_gui) as backend:
        app_name, version = get_current_app_name_and_version(backend)
        if logger is not None:
            logger.info("Device reports current app: %s %s", app_name, version)

        if app_name == requested_app:
            return

        if app_name != "BOLOS":
            if logger is not None:
                logger.info("Closing currently open app '%s'", app_name)
            exit_current_app(backend)
            backend.handle_usb_reset()
            app_name, version = get_current_app_name_and_version(backend)
            if logger is not None:
                logger.info("After exit: %s %s", app_name, version)

        if app_name != "BOLOS":
            raise RuntimeError(f"Unable to reach the dashboard, current app is still '{app_name}'")

        if logger is not None:
            logger.info("Opening '%s' from the dashboard", requested_app)
        open_app_from_dashboard(backend, requested_app)
        backend.handle_usb_reset()
        app_name, version = get_current_app_name_and_version(backend)
        if logger is not None:
            logger.info("Current app after open: %s %s", app_name, version)

        if app_name != requested_app:
            raise RuntimeError(f"Expected '{requested_app}', got '{app_name}'")


def get_account(dongle, path: str) -> Account:
    payload = pack_derivation_path(path)
    response = dongle.exchange(build_apdu(INS_GET_PUBLIC_KEY, 0x00, 0x00, payload))

    public_key_len = response[0]
    if public_key_len != 65:
        raise RuntimeError(f"Unexpected public key length: {public_key_len}")

    public_key = response[1:1 + public_key_len]
    offset = 1 + public_key_len

    address_len = response[offset]
    offset += 1
    address = response[offset:offset + address_len].decode("ascii")

    return Account(
        path=path,
        public_key_hex=public_key.hex(),
        address=address,
        address_hex=trx_address_to_hex(address),
    )


def build_trigger_smart_contract_tx(
    stub: WalletStub,
    owner_address_hex: str,
    contract_address: bytes,
    data: bytes,
    call_value: int = 0,
):
    tx_ext = stub.TriggerContract(
        smart_contract.TriggerSmartContract(
            owner_address=bytes.fromhex(owner_address_hex),
            contract_address=contract_address,
            call_value=call_value,
            data=data,
        )
    )
    if not tx_ext.transaction.raw_data.contract:
        raise RuntimeError(f"TriggerContract failed: {tx_ext}")
    return tx_ext


def broadcast_signed_tx(stub: WalletStub, tx_ext, signature: bytes):
    tx_ext.transaction.signature.extend([bytes(signature)])
    return stub.BroadcastTransaction(tx_ext.transaction)


def setup_external_plugin(
    dongle,
    plugin_name: str,
    contract_address: bytes,
    selector: bytes,
    cal_pem_path: Path,
) -> int:
    payload = bytearray()
    payload.append(len(plugin_name))
    payload += plugin_name.encode()
    payload += contract_address
    payload += selector

    sig = sign_with_cal(cal_pem_path, payload)
    apdu = build_apdu(INS_EXTERNAL_PLUGIN_SETUP, 0x00, 0x00, bytes(payload) + sig)

    try:
        dongle.exchange(apdu)
        return 0x9000
    except CommException as exc:
        status = getattr(exc, "sw", getattr(exc, "status", None))
        if status == 0x6A80:
            raise RuntimeError(
                "EXTERNAL_PLUGIN_SETUP was rejected with 0x6A80. "
                "These examples sign plugin metadata with the test CAL key in "
                "`tests/keychain/cal.pem`, so they require a Tron app build compiled "
                "with `use_test_keys` plus the matching plugin binary. "
                "A production Tron app installed from Ledger Live will reject this setup."
            ) from exc
        if status in (0x6984,):
            return status
        raise


def split_tx_chunks(path: str, tx_raw: bytes, include_tx_len: bool = True) -> list[bytes]:
    first = bytearray(pack_derivation_path(path))
    if include_tx_len:
        first += struct.pack(">I", len(tx_raw))

    max_first = MAX_APDU_DATA_LEN - len(first)
    if max_first < 0:
        raise RuntimeError("First chunk metadata exceeds APDU payload limit")

    chunks = [bytes(first) + tx_raw[:max_first]]
    tx_left = tx_raw[max_first:]
    while tx_left:
        chunks.append(tx_left[:MAX_APDU_DATA_LEN])
        tx_left = tx_left[MAX_APDU_DATA_LEN:]
    return chunks


def external_plugin_sign(dongle, path: str, tx_raw: bytes) -> bytes:
    chunks = split_tx_chunks(path, tx_raw, include_tx_len=True)

    if len(chunks) == 1:
        return dongle.exchange(build_apdu(INS_SIGN_EXTERNAL_PLUGIN, P1_SIGN, 0x00, chunks[0]))

    dongle.exchange(build_apdu(INS_SIGN_EXTERNAL_PLUGIN, P1_FIRST, 0x00, chunks[0]))
    for chunk in chunks[1:-1]:
        dongle.exchange(build_apdu(INS_SIGN_EXTERNAL_PLUGIN, P1_MORE, 0x00, chunk))

    return dongle.exchange(build_apdu(INS_SIGN_EXTERNAL_PLUGIN, P1_LAST, 0x00, chunks[-1]))


def verify_tx_signature(tx_raw: bytes, signature: bytes, public_key_hex_without_prefix: str) -> bool:
    tx_id = hashlib.sha256(tx_raw).digest()
    sig = Signature(signature_bytes=signature)
    pub = PublicKey(bytes.fromhex(public_key_hex_without_prefix))
    keys = KeyAPI("eth_keys.backends.NativeECCBackend")
    return keys.ecdsa_verify(tx_id, sig, pub)


def _log_prefix(tx_label: Optional[str]) -> str:
    return f"[{tx_label}] " if tx_label else ""


def sign_and_optionally_broadcast(
    *,
    logger,
    dongle,
    stub: WalletStub,
    account: Account,
    tx_ext,
    plugin_name: str,
    contract_address: bytes,
    selector: bytes,
    cal_pem_path: Path,
    no_broadcast: bool,
    tx_label: Optional[str] = None,
) -> bool:
    prefix = _log_prefix(tx_label)
    tx_raw = tx_ext.transaction.raw_data.SerializeToString()

    plugin_sw = setup_external_plugin(dongle, plugin_name, contract_address, selector, cal_pem_path)
    logger.info("%sEXTERNAL_PLUGIN_SETUP status: 0x%04X", prefix, plugin_sw)

    logger.info("%sPlease review the transaction on the Ledger device and approve it...", prefix)
    sign_resp = external_plugin_sign(dongle, account.path, tx_raw)
    signature = sign_resp[:65]

    valid = verify_tx_signature(tx_raw, signature, account.public_key_hex[2:])
    tx_id = hashlib.sha256(tx_raw).hexdigest()

    logger.info("%stxID: %s", prefix, tx_id)
    logger.info("%ssignature: %s", prefix, signature.hex())
    logger.info("%ssignature valid: %s", prefix, valid)

    if not valid:
        logger.error("%sInvalid signature", prefix)
        return False

    if no_broadcast:
        logger.info("%sBroadcast skipped by --no-broadcast", prefix)
        return True

    broadcast_resp = broadcast_signed_tx(stub, tx_ext, signature)
    logger.info("%sbroadcast response: %s", prefix, broadcast_resp)
    return True
