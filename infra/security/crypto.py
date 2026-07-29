"""AES-256-GCM 密码加解密(详设§2.19.6)。

§2.19.6：密码**不存明文**，以 AES-256 加密后落库；密钥经 Docker Secrets / 环境变量
注入(等价密钥外部托管)；校验时解密比对。密钥不入库(§2.19.1)。

采用 AES-256-GCM(认证加密，防篡改)：nonce 随机，密文 = nonce(12B)+ciphertext+tag，
整体 base64 编码落库。
"""

from __future__ import annotations

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from config.settings import settings

#: nonce 长度(GCM 推荐 12 字节)。
_NONCE_LEN = 12


def _key() -> bytes:
    """从 settings 取 32 字节 AES 密钥(hex 解码)。"""
    raw = settings.aes_key
    try:
        key = bytes.fromhex(raw)
    except ValueError as exc:
        raise ValueError("AES_KEY 必须为 64 字符 hex(32 字节)") from exc
    if len(key) != 32:
        raise ValueError(f"AES_KEY 长度需 32 字节，当前 {len(key)} 字节")
    return key


def encrypt(plaintext: str) -> str:
    """加密明文密码 -> base64 字符串(落库)。

    Args:
        plaintext: 明文密码。
    Returns:
        base64(nonce + ciphertext + tag)。
    """
    key = _key()
    nonce = os.urandom(_NONCE_LEN)
    aesgcm = AESGCM(key)
    ct = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    return base64.b64encode(nonce + ct).decode("ascii")


def decrypt(token: str) -> str:
    """解密落库密文 -> 明文(校验比对用)。

    Args:
        token: encrypt() 产出的 base64 字符串。
    Returns:
        明文。
    Raises:
        ValueError: 密文损坏或密钥不匹配。
    """
    key = _key()
    raw = base64.b64decode(token)
    if len(raw) < _NONCE_LEN + 16:  # nonce + 至少 tag(16B)
        raise ValueError("密文长度异常")
    nonce = raw[:_NONCE_LEN]
    ct = raw[_NONCE_LEN:]
    aesgcm = AESGCM(key)
    pt = aesgcm.decrypt(nonce, ct, None)
    return pt.decode("utf-8")


def verify(plaintext: str, token: str) -> bool:
    """校验明文是否与密文匹配(常量时间比较由 GCM 认证保证)。"""
    try:
        return decrypt(token) == plaintext
    except Exception:  # noqa: BLE001  密文损坏/密钥不符均视为校验失败
        return False


__all__: list[str] = ["encrypt", "decrypt", "verify"]
