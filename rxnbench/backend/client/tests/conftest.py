"""Shared test fakes for instrument wrapper tests."""


class FakeSubscription:
    def __init__(self, value):
        self._value = value

    def __next__(self):
        return self._value

    def cancel(self):
        pass
