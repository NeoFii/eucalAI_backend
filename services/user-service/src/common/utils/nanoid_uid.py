from nanoid import generate

_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
_SIZE = 10


def generate_nanoid_uid() -> str:
    return generate(_ALPHABET, _SIZE)
