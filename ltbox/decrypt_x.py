#!/usr/bin/env python

import hashlib
from binascii import hexlify, unhexlify
import sys
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
import struct

PASSWORD = "OSD"

def PBKDF1(s, salt, lenout, hashfunc, iter_):
    m = hashfunc
    digest = m(s.encode("utf-8") + salt).digest()
    for i in range(iter_-1):
        digest = m(digest).digest()
    return digest[:lenout]

def generate(salt):
    return PBKDF1(PASSWORD, salt, 32, hashlib.sha256, 1000)

def decrypt_file(fi_path, fo_path):
    try:
        buf = open(fi_path, "rb").read()
        iv = buf[0:16]
        salt = buf[16:32]

        # Test
        # assert(hexlify(generate(unhexlify('bb90a93499fc85018520604da0843829'))) == b'70c1dbf7b3c9e056901a7d0478c3c21f996276c81844e4d18eb962062c74a4ef')

        key = generate(salt)

        cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
        decryptor = cipher.decryptor()
        plain = decryptor.update(buf[32:]) + decryptor.finalize()

        original_size = struct.unpack('<q', plain[0:8])[0]
        signature = plain[8:16]
        if signature != b'\xcf\x06\x05\x04\x03\x02\x01\xfc':
            print("Broken file.")
            return False

        body = plain[16:16 + original_size]
        digest = hashlib.sha256(body).digest()
        if digest != plain[16 + original_size:16 + original_size + 32]:
            print("Broken file.")
            return False

        open(fo_path, "wb").write(body)
        print("Successfully decrypted.", original_size, "bytes")
        return True

    except Exception as e:
        print(f"Error decrypting {fi_path}: {e}", file=sys.stderr)
        return False

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python decrypt_x.py <input_file> <output_file>")
        sys.exit(1)
        
    fi = sys.argv[1]
    fo = sys.argv[2]
    
    if not decrypt_file(fi, fo):
        sys.exit(1)