from __future__ import annotations

import hashlib

GENESIS_CHAIN_HASH: str = "0" * 64


def compute_chain_hash(*, previous_chain_hash: str, ballot_hash: str) -> str:
    data = f"{previous_chain_hash}:{ballot_hash}".encode()
    return hashlib.sha256(data).hexdigest()
