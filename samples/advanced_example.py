"""Intentionally flawed sample for demonstrating advanced analyzer rules."""

import hashlib
import json  # unused import for MAINT002 demo
import subprocess

access_token = "replace-with-a-real-token"  # placeholder intentionally ignored
client_secret = "hardcoded-demo-secret-value"  # SEC002


def inspect_request(user_command, cursor, user_id):
    subprocess.run(user_command, shell=True)  # SEC003
    digest = hashlib.md5(str(user_id).encode()).hexdigest()  # SEC004
    cursor.execute(f"SELECT * FROM users WHERE id={user_id}")  # SEC005
    return digest


def deeply_nested(a, b, c, d, e):
    if a:
        for item in b:
            while c:
                try:
                    with d:
                        if e:
                            return item
                except Exception:
                    return None
    return None


def many_decisions(value):
    if value == 1:
        pass
    if value == 2:
        pass
    if value == 3:
        pass
    if value == 4:
        pass
    if value == 5:
        pass
    if value == 6:
        pass
    if value == 7:
        pass
    if value == 8:
        pass
    if value == 9:
        pass
    if value == 10:
        pass
    return value
