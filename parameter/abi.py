from __future__ import annotations

from typing import Any

from parameter.models import ZERO_ADDRESS

PANCAKE_V2_FACTORY = "0xca143ce32fe78f1f7019d7d551a6402fc5350c73"
PANCAKE_V3_FACTORY = "0x0bfbcf9fa4f9c56b0f40a671ad40e0805a091865"

PANCAKE_V2_SWAP_TOPIC = "0xd78ad95fa46c994b6551d0da85fc275fe613ce37657fb8d5e3d130840159d822"
PANCAKE_V3_SWAP_TOPIC = "0x19b47279256b2a23a1665c810c8d55a1758940ee09377d4f8d26497a3577dc83"

SELECTOR_DECIMALS = "0x313ce567"
SELECTOR_TOKEN0 = "0x0dfe1681"
SELECTOR_TOKEN1 = "0xd21220a7"
SELECTOR_GET_PAIR = "0xe6a43905"
SELECTOR_GET_POOL = "0x1698ee82"


def normalize_address(value: str) -> str:
    text = value.strip().lower()
    if not text.startswith("0x"):
        text = f"0x{text}"
    if len(text) != 42:
        raise ValueError(f"invalid EVM address: {value}")
    return text


def encode_address(value: str) -> str:
    return normalize_address(value)[2:].rjust(64, "0")


def encode_uint(value: int) -> str:
    if value < 0:
        raise ValueError("uint cannot be negative")
    return f"{value:064x}"


def encode_get_pair(token_a: str, token_b: str) -> str:
    return SELECTOR_GET_PAIR + encode_address(token_a) + encode_address(token_b)


def encode_get_pool(token_a: str, token_b: str, fee: int) -> str:
    return SELECTOR_GET_POOL + encode_address(token_a) + encode_address(token_b) + encode_uint(fee)


def decode_address_output(data: str) -> str:
    word = _strip_0x(data).rjust(64, "0")[-64:]
    address = f"0x{word[-40:]}"
    return normalize_address(address)


def decode_uint_output(data: str) -> int:
    words = split_words(data)
    return int(words[0], 16) if words else 0


def split_words(data: str) -> list[str]:
    text = _strip_0x(data)
    return [text[index : index + 64].rjust(64, "0") for index in range(0, len(text), 64) if text]


def word_to_uint(word: str) -> int:
    return int(word, 16)


def word_to_int(word: str) -> int:
    value = int(word, 16)
    if value >= 1 << 255:
        value -= 1 << 256
    return value


def log_block_number(log: dict[str, Any]) -> int:
    return int(str(log["blockNumber"]), 16)


def log_index(log: dict[str, Any]) -> int:
    return int(str(log.get("logIndex", "0x0")), 16)


def is_zero_address(value: str) -> bool:
    return normalize_address(value) == ZERO_ADDRESS


def _strip_0x(value: str) -> str:
    text = value[2:] if value.startswith("0x") else value
    return text.lower()
