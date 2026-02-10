#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Run the same flow as tests/test_swap.py::test_swap_exact_eth_for_token
on a real device:
1) Build TriggerSmartContract(TRC20 transfer) payload.
2) Send EXTERNAL_PLUGIN_SETUP (set_external_plugin).
3) Sign with CLEAR_SIGN (include tx length) and verify signature.
4) Broadcast signed transaction.
"""

import argparse
import hashlib
import logging
import re
import struct
import sys
from dataclasses import dataclass
from pathlib import Path

import base58
import grpc
from ecdsa import SigningKey
from ecdsa.util import sigencode_der
from eth_keys import KeyAPI
from eth_keys.datatypes import PublicKey, Signature
from ledgerblue.comm import getDongle
from ledgerblue.commException import CommException
from tron_sdk_py.proto.api.api_pb2_grpc import WalletStub
from tron_sdk_py.proto.core.contract import smart_contract_pb2 as smart_contract


ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT_DIR / "proto"))


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


CLA = 0xE0

INS_GET_PUBLIC_KEY = 0x02
INS_CLEAR_SIGN = 0xC4
INS_EXTERNAL_PLUGIN_SETUP = 0x12

P1_FIRST = 0x00
P1_MORE = 0x80
P1_LAST = 0x90
P1_SIGN = 0x10

MAX_APDU_DATA_LEN = 255

SELECTOR = bytes.fromhex("a9059cbb")
TRC20_TRANSFER_DATA = bytes.fromhex(
    "a9059cbb"
    "000000000000000000000000364b03e0815687edaf90b81ff58e496dea7383d7"
    "00000000000000000000000000000000000000000000000000000000000f4240"
)


@dataclass
class Account:
    path: str
    public_key_hex: str
    address: str
    address_hex: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run TRC20 clear-sign flow with external plugin setup")
    parser.add_argument("--path", default="44'/195'/0'/0/0", help="BIP32 path, default: 44'/195'/0'/0/0")
    parser.add_argument(
        "--contract",
        default="TXYZopYRdj2D9XRtbG411XZZ3kM5VkAeBf",
        help="TRC20 contract base58 address",
    )
    parser.add_argument(
        "--makefile",
        default=str(ROOT_DIR / "Makefile"),
        help="Makefile path used to read APPNAME",
    )
    parser.add_argument(
        "--cal-key",
        default=str(ROOT_DIR / "tests" / "keychain" / "cal.pem"),
        help="CAL private key PEM (tests key)",
    )
    parser.add_argument(
        "--grpc-endpoint",
        default="grpc.nile.trongrid.io:50051",
        help="Tron gRPC endpoint used for TriggerContract and BroadcastTransaction",
    )
    parser.add_argument(
        "--no-broadcast",
        action="store_true",
        help="Build/sign flow only, skip broadcast",
    )
    return parser.parse_args()


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


def read_plugin_name(makefile_path: Path) -> str:
    pattern = re.compile(r'^\s*APPNAME\s*=\s*"?([^"\n]+)"?\s*$')
    with makefile_path.open("r", encoding="utf-8") as f:
        for line in f:
            match = pattern.match(line)
            if match:
                return match.group(1).strip()
    raise RuntimeError(f"APPNAME not found in {makefile_path}")


def sign_with_cal(cal_pem_path: Path, payload: bytes) -> bytes:
    with cal_pem_path.open("r", encoding="utf-8") as f:
        signing_key = SigningKey.from_pem(f.read(), hashlib.sha256)
    return signing_key.sign_deterministic(payload, sigencode=sigencode_der)


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


def build_trigger_smart_contract_tx(stub: WalletStub, owner_address_hex: str, contract_address: bytes,
                                    data: bytes):
    tx_ext = stub.TriggerContract(
        smart_contract.TriggerSmartContract(
            owner_address=bytes.fromhex(owner_address_hex),
            contract_address=contract_address,
            data=data,
        ))
    if not tx_ext.transaction.raw_data.contract:
        raise RuntimeError(f"TriggerContract failed: {tx_ext}")
    return tx_ext


def broadcast_signed_tx(stub: WalletStub, tx_ext, signature: bytes):
    tx_ext.transaction.signature.extend([bytes(signature)])
    return stub.BroadcastTransaction(tx_ext.transaction)


def setup_external_plugin(dongle, plugin_name: str, contract_address: bytes, selector: bytes, cal_pem_path: Path) -> int:
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
        if status in (0x6984,):
            return status
        raise


def split_clear_sign_chunks(path: str, tx_raw: bytes, include_tx_len: bool = True) -> list[bytes]:
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


def clear_sign(dongle, path: str, tx_raw: bytes) -> bytes:
    chunks = split_clear_sign_chunks(path, tx_raw, include_tx_len=True)

    if len(chunks) == 1:
        return dongle.exchange(build_apdu(INS_CLEAR_SIGN, P1_SIGN, 0x00, chunks[0]))

    dongle.exchange(build_apdu(INS_CLEAR_SIGN, P1_FIRST, 0x00, chunks[0]))
    for chunk in chunks[1:-1]:
        dongle.exchange(build_apdu(INS_CLEAR_SIGN, P1_MORE, 0x00, chunk))

    return dongle.exchange(build_apdu(INS_CLEAR_SIGN, P1_LAST, 0x00, chunks[-1]))


def verify_tx_signature(tx_raw: bytes, signature: bytes, public_key_hex_without_prefix: str) -> bool:
    tx_id = hashlib.sha256(tx_raw).digest()
    sig = Signature(signature_bytes=signature)
    pub = PublicKey(bytes.fromhex(public_key_hex_without_prefix))
    keys = KeyAPI("eth_keys.backends.NativeECCBackend")
    return keys.ecdsa_verify(tx_id, sig, pub)


def main() -> int:
    args = parse_args()
    makefile_path = Path(args.makefile)
    cal_pem_path = Path(args.cal_key)

    plugin_name = read_plugin_name(makefile_path)
    contract_address = bytes.fromhex(trx_address_to_hex(args.contract))

    dongle = getDongle(True)
    channel = grpc.insecure_channel(args.grpc_endpoint)
    stub = WalletStub(channel)
    try:
        account = get_account(dongle, args.path)
        logger.info("Using account: %s (%s)", account.address, account.path)
        logger.info("Plugin name: %s", plugin_name)
        logger.info("gRPC endpoint: %s", args.grpc_endpoint)

        tx_ext = build_trigger_smart_contract_tx(
            stub=stub,
            owner_address_hex=account.address_hex,
            contract_address=contract_address,
            data=TRC20_TRANSFER_DATA,
        )
        tx_raw = tx_ext.transaction.raw_data.SerializeToString()

        plugin_sw = setup_external_plugin(dongle, plugin_name, contract_address, SELECTOR, cal_pem_path)
        logger.info("EXTERNAL_PLUGIN_SETUP status: 0x%04X", plugin_sw)

        logger.info("Please review the transaction on the Ledger device and approve it...")
        sign_resp = clear_sign(dongle, account.path, tx_raw)
        signature = sign_resp[:65]

        valid = verify_tx_signature(tx_raw, signature, account.public_key_hex[2:])
        tx_id = hashlib.sha256(tx_raw).hexdigest()

        logger.info("txID: %s", tx_id)
        logger.info("signature: %s", signature.hex())
        logger.info("signature valid: %s", valid)

        if not valid:
            logger.error("Invalid signature")
            return 1

        if args.no_broadcast:
            logger.info("Broadcast skipped by --no-broadcast")
            return 0

        broadcast_resp = broadcast_signed_tx(stub, tx_ext, signature)
        logger.info("broadcast response: %s", broadcast_resp)
        return 0
    finally:
        channel.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
