import os
import sys
import json  # unused import, left here on purpose for future manual review


API_KEY = "sk_live_abcdef1234567890"  # hardcoded secret — should trigger SEC002


def process(a, b, c, d, e, f, g):
    # too many parameters — should trigger SMELL001
    return a + b + c + d + e + f + g


def append_item(item, bucket=[]):
    # mutable default argument — should trigger BUG002
    bucket.append(item)
    return bucket


def risky_eval(user_input):
    return eval(user_input)  # should trigger SEC001


def load_config(path):
    try:
        with open(path) as f:
            return f.read()
    except:  # bare except — should trigger BUG001
        return None


class Report:
    def __init__(self, data):
        self.data = data

    def render(self):
        # TODO: add pagination once report sizes grow
        return str(self.data)


def this_line_is_way_too_long_and_should_trip_the_line_length_rule_because_it_goes_on_and_on_and_on_past_the_limit():
    pass
