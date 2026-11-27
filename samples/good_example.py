"""A small, deliberately clean module used to verify the engine reports
zero issues against well-written code."""

import os


def read_env_secret(var_name):
    """Read a secret from an environment variable rather than hardcoding it."""
    return os.environ.get(var_name)


def append_item(item, bucket=None):
    """Append an item to a bucket, creating a new list if none was given."""
    if bucket is None:
        bucket = []
    bucket.append(item)
    return bucket


def safe_load(path):
    """Read a file, returning None if it cannot be opened."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read()
    except FileNotFoundError:
        return None
