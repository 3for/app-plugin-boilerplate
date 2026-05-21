#!/usr/bin/env python3
"""Generate a hand-crafted seed corpus and libFuzzer dictionary for fuzz_plugin.c.

Harness input layout (see fuzz_plugin.c):
  data[0..4)                                  selector hint (only data[0] is used:
                                              SELECTORS[data[0] % SELECTOR_COUNT])
  data[4..4+SIZEOF_TX_CONTENT)                memcpy'd into txContent_t
                                              (harness then forces contractAddress[0] = 0x41)
  data[...]                                   32-byte ABI words streamed into
                                              handle_provide_parameter
  tail (<= 2 * SIZEOF_EXTRA_INFO)             extraInfo_t entries for token lookups

The loop reads ABI words while `size - cursor >= 32 + 2*sizeof(extraInfo_t) = 216`,
so to make the last ABI word consumed, leave exactly 0..184 trailing bytes.
"""

from pathlib import Path

SELECTOR_SIZE = 4
PARAMETER_LENGTH = 32
SIZEOF_TX_CONTENT = 544           # verified via sizeof() probe
SIZEOF_EXTRA_INFO = 92            # tokenDefinition_t (21 + 51 + 1 = 73, padded to 92 by nftInfo)
TAIL_RESERVE = PARAMETER_LENGTH + 2 * SIZEOF_EXTRA_INFO  # 216

# Selector enum order in plugin.h drives data[0] % 6 mapping
SEL_TRANSFER  = 0   # 0xa9059cbb
SEL_SWAP      = 1   # 0x1cf4401e
SEL_DUMMY     = 2   # 0x13374242
SEL_MINT      = 3   # 0x855d175e
SEL_XFER      = 4   # 0x9110a55b (shielded transfer)
SEL_BURN      = 5   # 0xcc105875

OUT_DIR = Path(__file__).resolve().parent / "corpus"
DICT_PATH = Path(__file__).resolve().parent / "plugin.dict"


def w(*chunks):
    """Concatenate 32-byte ABI words / arbitrary blobs."""
    return b"".join(chunks)


def u256(value):
    return value.to_bytes(32, "big")


def addr_word(addr20):
    """ABI-encode a 20-byte address as a left-padded 32-byte word."""
    assert len(addr20) == 20
    return b"\x00" * 12 + addr20


def make_token_extra(addr21, ticker, decimals):
    """Build an extraInfo_t (tokenDefinition_t) blob of exactly 92 bytes."""
    assert len(addr21) == 21
    blob = bytearray(SIZEOF_EXTRA_INFO)
    blob[0:21] = addr21
    enc = ticker.encode("ascii")
    assert len(enc) < 51
    blob[21:21 + len(enc)] = enc
    # ticker[50] is forced to NUL by the harness; intermediate bytes are already 0.
    blob[21 + 50] = decimals
    return bytes(blob)


def make_tx_content(contract_addr21=None):
    """All zeros (harness will overwrite contractAddress[0] anyway) but we can pre-set fields."""
    buf = bytearray(SIZEOF_TX_CONTENT)
    if contract_addr21 is not None:
        # contractAddress lives at offset 66 (verified via offsetof() probe).
        buf[66:66 + 21] = contract_addr21
    return bytes(buf)


def make_seed(selector_index, abi_body, extras):
    """Assemble: selector_hint (4B) + txContent (544B) + abi_body + extras."""
    sel_hint = bytes([selector_index % 6]) + b"\x00\x00\x00"
    return sel_hint + make_tx_content() + abi_body + b"".join(extras)


# ----------------------------------------------------------------------------
# Seed 1: TRC20 transfer(address,uint256) — exactly 2 ABI words consumed.
# Anything past word 2 trips UNEXPECTED_PARAMETER, so don't pad more ABI words.
# ----------------------------------------------------------------------------
RECIPIENT_EVM = bytes.fromhex("dd" * 20)
USDT_CONTRACT_21 = b"\x41" + b"\xab" * 20

seed_transfer = make_seed(
    SEL_TRANSFER,
    w(
        addr_word(RECIPIENT_EVM),       # to
        u256(1_000_000),                # value (1 USDT at 6 decimals)
    ),
    [make_token_extra(USDT_CONTRACT_21, "USDT", 6),
     b"\x00" * SIZEOF_EXTRA_INFO],      # unused item2 padding so loop boundary lines up
)

# ----------------------------------------------------------------------------
# Seed 2: swapExactTRXForTokens(uint256, address[], address, uint256).
# Must reach word 6 (path[1] = TOKEN_RECEIVED) for the full code path.
# ----------------------------------------------------------------------------
SWAP_BENEFICIARY_EVM = bytes.fromhex("cc" * 20)
SWAP_PATH0_EVM = bytes.fromhex("11" * 20)   # input token (TRX wrapped)
SWAP_PATH1_EVM = bytes.fromhex("22" * 20)   # output token
SWAP_TOKEN_OUT_21 = b"\x41" + SWAP_PATH1_EVM

seed_swap = make_seed(
    SEL_SWAP,
    w(
        u256(500),                          # word 0: amountOutMin
        u256(0x80),                         # word 1: path offset (4 words from data start)
        addr_word(SWAP_BENEFICIARY_EVM),    # word 2: to
        u256(0xFFFFFFFF),                   # word 3: deadline (skipped via go_to_offset)
        u256(2),                            # word 4: path length
        addr_word(SWAP_PATH0_EVM),          # word 5: path[0]
        addr_word(SWAP_PATH1_EVM),          # word 6: path[1] -> TOKEN_RECEIVED
    ),
    [make_token_extra(SWAP_TOKEN_OUT_21, "WTRX", 6),
     b"\x00" * SIZEOF_EXTRA_INFO],
)

# ----------------------------------------------------------------------------
# Seed 3: BOILERPLATE_DUMMY_2 — finalize returns ERROR, harness early-exits.
# Still exercises init_contract + handle_provide_parameter for this selector.
# ----------------------------------------------------------------------------
seed_dummy = make_seed(
    SEL_DUMMY,
    w(u256(0xDEADBEEF), u256(0x13374242), u256(0)),
    [b"\x00" * SIZEOF_EXTRA_INFO, b"\x00" * SIZEOF_EXTRA_INFO],
)

# ----------------------------------------------------------------------------
# Seed 4: shielded mint(uint256 rawValue, ...). Word 0 is the raw amount.
# Remaining words are MINT_SKIP no-ops, so we add a small handful.
# ----------------------------------------------------------------------------
JST_CONTRACT_21 = b"\x41" + bytes.fromhex("9d2b58a86e1f3d77f5f29b9b4d09c3a8716eb002")
MINT_RAW_VALUE = 4_000_000_000_000_000_000  # 4 JST at 18 decimals

seed_mint = make_seed(
    SEL_MINT,
    w(
        u256(MINT_RAW_VALUE),       # rawValue
        u256(0),                    # MINT_SKIP padding (output[0])
        u256(0),
        u256(0),
        u256(0),
    ),
    [make_token_extra(JST_CONTRACT_21, "JST", 18),
     b"\x00" * SIZEOF_EXTRA_INFO],
)

# ----------------------------------------------------------------------------
# Seed 5: shielded transfer. Handler accepts every word; just feed a few.
# ----------------------------------------------------------------------------
seed_xfer = make_seed(
    SEL_XFER,
    w(
        u256(0xc0),                 # mimics the offsets seen in test_long_transfer.py
        u256(0x220),
        u256(0x280),
        u256(1),
        u256(0),
    ),
    [make_token_extra(JST_CONTRACT_21, "JST", 18),
     b"\x00" * SIZEOF_EXTRA_INFO],
)

# ----------------------------------------------------------------------------
# Seed 6: shielded burn. BURN_RAW_VALUE is only consumed at parameterOffset
# == SELECTOR_SIZE + 12 * PARAMETER_LENGTH (=388), i.e., word index 12.
# Need at least 13 ABI words so the raw value is captured.
# ----------------------------------------------------------------------------
BURN_RAW_VALUE = 3_000_000_000_000_000_000  # 3 JST

seed_burn_words = [u256(0)] * 12 + [u256(BURN_RAW_VALUE)] + [u256(0)] * 3
seed_burn = make_seed(
    SEL_BURN,
    w(*seed_burn_words),
    [make_token_extra(JST_CONTRACT_21, "JST", 18),
     b"\x00" * SIZEOF_EXTRA_INFO],
)

SEEDS = {
    "seed_transfer":           seed_transfer,
    "seed_swap":               seed_swap,
    "seed_dummy":              seed_dummy,
    "seed_shielded_mint":      seed_mint,
    "seed_shielded_transfer":  seed_xfer,
    "seed_shielded_burn":      seed_burn,
}


# ----------------------------------------------------------------------------
# libFuzzer dictionary.
# Tokens are 32-byte aligned where they represent ABI words, so the mutator
# can substitute them at any word boundary in the corpus.
# ----------------------------------------------------------------------------
def dict_entry(name, blob):
    encoded = "".join(f"\\x{b:02x}" for b in blob)
    return f'{name}="{encoded}"'


DICT_LINES = [
    "# libFuzzer dictionary for fuzz_plugin (TRON plugin boilerplate)",
    "# Auto-generated by seed_corpus_gen.py",
    "",
    "# --- TRON-specific magic bytes ---",
    dict_entry("tron_addr_prefix", b"\x41"),
    "",
    "# --- ticker strings observed in tests ---",
    dict_entry("ticker_usdt", b"USDT\x00"),
    dict_entry("ticker_jst",  b"JST\x00"),
    dict_entry("ticker_trx",  b"TRX\x00"),
    dict_entry("ticker_wtrx", b"WTRX\x00"),
    "",
    "# --- uint256 boundary values (full 32-byte ABI words) ---",
    dict_entry("u256_zero",      u256(0)),
    dict_entry("u256_one",       u256(1)),
    dict_entry("u256_max",       b"\xff" * 32),
    dict_entry("u256_2pow63",    u256(1 << 63)),
    dict_entry("u256_2pow64",    u256(1 << 64)),
    dict_entry("u256_2pow128",   u256(1 << 128)),
    "",
    "# --- common ABI structural offsets (right-aligned 32-byte words) ---",
    dict_entry("abi_off_0x20",  u256(0x20)),
    dict_entry("abi_off_0x40",  u256(0x40)),
    dict_entry("abi_off_0x60",  u256(0x60)),
    dict_entry("abi_off_0x80",  u256(0x80)),
    dict_entry("abi_off_0xa0",  u256(0xa0)),
    dict_entry("abi_off_0xc0",  u256(0xc0)),
    dict_entry("abi_len_2",     u256(2)),
    "",
    "# --- BURN_RAW_VALUE trigger offset (parameterOffset == 388 = 4 + 12*32) ---",
    dict_entry("burn_offset_marker", (388).to_bytes(4, "big")),
    "",
    "# --- selectors (handy when fuzzer mutates beyond the harness's selector_hint) ---",
    dict_entry("sel_transfer", bytes.fromhex("a9059cbb")),
    dict_entry("sel_swap",     bytes.fromhex("1cf4401e")),
    dict_entry("sel_dummy",    bytes.fromhex("13374242")),
    dict_entry("sel_mint",     bytes.fromhex("855d175e")),
    dict_entry("sel_xfer",     bytes.fromhex("9110a55b")),
    dict_entry("sel_burn",     bytes.fromhex("cc105875")),
    "",
    "# --- amount magnitudes from existing test fixtures ---",
    dict_entry("amt_1e6",   u256(1_000_000)),
    dict_entry("amt_4e18",  u256(4_000_000_000_000_000_000)),
    dict_entry("amt_3e18",  u256(3_000_000_000_000_000_000)),
]


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, blob in SEEDS.items():
        path = OUT_DIR / name
        path.write_bytes(blob)
        print(f"wrote {path} ({len(blob)} bytes)")
    DICT_PATH.write_text("\n".join(DICT_LINES) + "\n")
    print(f"wrote {DICT_PATH}")


if __name__ == "__main__":
    main()
