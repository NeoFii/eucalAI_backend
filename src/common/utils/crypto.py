# -*- coding: utf-8 -*-
"""
AES-256-GCM 对称加密工具
用于存储探针 API Key，密文落库，读时仅返回掩码

使用方式：
    from common.utils.crypto import encrypt_api_key, decrypt_api_key, mask_api_key
"""

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def validate_master_key(master_key_hex: str) -> bytes:
    """
    校验主密钥格式：必须为 64 位十六进制字符串（= 32 字节 AES-256）。
    返回原始字节。
    """
    if not master_key_hex or len(master_key_hex) != 64:
        raise ValueError(
            "TESTING_SECRET_MASTER_KEY 必须为 64 位十六进制字符串（32 字节）"
        )
    try:
        return bytes.fromhex(master_key_hex)
    except ValueError:
        raise ValueError(
            "TESTING_SECRET_MASTER_KEY 包含非法十六进制字符"
        )


def encrypt_api_key(plaintext: str, master_key_hex: str) -> dict:
    """
    加密明文 API Key。

    Returns:
        {"ciphertext": str, "iv": str, "tag": str}  —— 均为 Base64 编码
    """
    key = validate_master_key(master_key_hex)
    iv = os.urandom(12)  # 96-bit nonce
    aesgcm = AESGCM(key)
    ct_with_tag = aesgcm.encrypt(iv, plaintext.encode("utf-8"), None)
    # AESGCM.encrypt 返回 ciphertext || tag（16 字节）
    ct = ct_with_tag[:-16]
    tag = ct_with_tag[-16:]
    return {
        "ciphertext": base64.b64encode(ct).decode("ascii"),
        "iv": base64.b64encode(iv).decode("ascii"),
        "tag": base64.b64encode(tag).decode("ascii"),
    }


def decrypt_api_key(
    ciphertext_b64: str,
    iv_b64: str,
    tag_b64: str,
    master_key_hex: str,
) -> str:
    """
    解密 API Key，返回明文字符串。
    """
    key = validate_master_key(master_key_hex)
    iv = base64.b64decode(iv_b64)
    ct = base64.b64decode(ciphertext_b64)
    tag = base64.b64decode(tag_b64)
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(iv, ct + tag, None).decode("utf-8")


def mask_api_key(plaintext: str) -> str:
    """
    生成掩码：前 4 位 + **** + 后 4 位。
    长度不足 8 位时返回 "****"。
    """
    if len(plaintext) <= 8:
        return "****"
    return plaintext[:4] + "****" + plaintext[-4:]
