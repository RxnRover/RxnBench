"""Tests for bench.devices auto-discovery.

No network/mDNS: discover_sila_clients()/DeviceNamespace._scan() are
monkeypatched to return fake discovered clients. Mirrors test_client.py's
fake-based style.
"""
import pytest

import rxn_bench_client.devices as devices_module
from rxn_bench_client.client import RxnBenchClient


class _FakeServerNameProp:
    def __init__(self, value):
        self._value = value

    def get(self):
        return self._value


class _FakeSiLAService:
    def __init__(self, server_name):
        self.ServerName = _FakeServerNameProp(server_name)


class _FakeDiscoveredClient:
    """Stand-in for a sila2.client.SilaClient returned by discover_sila_clients().

    Advertised features are plain attributes (matching hasattr(client, feature),
    exactly like the real SilaClient's setattr(self, feature._identifier, feature)).
    """

    def __init__(self, *, address="1.2.3.4", port=50051, features=(), server_name="fake"):
        self.address = address
        self.port = port
        self.closed = False
        self.SiLAService = _FakeSiLAService(server_name)
        for f in features:
            setattr(self, f, object())

    def close(self):
        self.closed = True


class _LockCapableInstrument:
    def __init__(self, sila):
        self.sila = sila
        self.lock_acquired = False

    def acquire_experiment_lock(self):
        self.lock_acquired = True


class _PlainInstrument:
    def __init__(self, sila):
        self.sila = sila


@pytest.fixture
def fake_registry(monkeypatch):
    """Route bench.devices.gantry/ph through fake wrapper classes, not the real ones."""
    registry = {
        "gantry": (_LockCapableInstrument, "Gantry"),
        "ph": (_PlainInstrument, "PHSensor"),
    }
    monkeypatch.setattr(devices_module, "DEVICE_REGISTRY", registry)
    return registry


@pytest.fixture
def bench():
    return RxnBenchClient()


def _scan_returning(bench, clients):
    bench.devices._scan = lambda: clients


# __getattr__ - registry lookup, zero/one/many matches

def test_unregistered_name_raises_attribute_error(bench, fake_registry):
    with pytest.raises(AttributeError, match="No built-in device"):
        bench.devices.nonexistent


def test_single_match_attaches_and_wraps(bench, fake_registry):
    client = _FakeDiscoveredClient(features=["PHSensor"])
    _scan_returning(bench, [client])

    instrument = bench.devices.ph

    assert isinstance(instrument, _PlainInstrument)
    assert instrument.sila is client
    assert bench.ph is instrument  # _attach() still does setattr(bench, name, ...)


def test_repeated_access_reuses_the_same_instrument(bench, fake_registry):
    """A second bench.devices.ph must not reconnect/rewrap - same instrument,
    same underlying sila client, no second scan needed."""
    client = _FakeDiscoveredClient(features=["PHSensor"])
    _scan_returning(bench, [client])

    first = bench.devices.ph
    second = bench.devices.ph

    assert first is second
    assert bench.ph is first


def test_devices_reuses_an_instrument_attached_via_explicit_connect(bench, fake_registry):
    """bench.connect(...) first, then bench.devices.<name> - must reuse, not
    reconnect via discovery."""
    bench._attach("ph", _PlainInstrument, "explicit-sila-client")
    assert bench.devices.ph is bench.ph


def test_zero_matches_raises_helpful_error(bench, fake_registry):
    _scan_returning(bench, [])
    with pytest.raises(RuntimeError, match="No server advertising"):
        bench.devices.ph


def test_multiple_matches_raises_and_lists_candidates(bench, fake_registry):
    c1 = _FakeDiscoveredClient(features=["PHSensor"], server_name="ph-1", address="10.0.0.1")
    c2 = _FakeDiscoveredClient(features=["PHSensor"], server_name="ph-2", address="10.0.0.2")
    _scan_returning(bench, [c1, c2])

    with pytest.raises(RuntimeError, match="Multiple servers advertise") as exc:
        bench.devices.ph
    assert "ph-1" in str(exc.value) and "ph-2" in str(exc.value)


def test_scan_result_is_cached_across_attribute_accesses(bench, fake_registry, monkeypatch):
    calls = {"n": 0}

    def fake_discover(timeout=5.0):
        calls["n"] += 1
        return [_FakeDiscoveredClient(features=["Gantry", "PHSensor"])]

    monkeypatch.setattr(devices_module, "discover_sila_clients", fake_discover)

    bench.devices.gantry
    bench.devices.ph

    assert calls["n"] == 1


def test_lock_acquisition_goes_through_attach(bench, fake_registry):
    client = _FakeDiscoveredClient(features=["Gantry"])
    _scan_returning(bench, [client])

    instrument = bench.devices.gantry

    assert instrument.lock_acquired
    assert bench._lock_holder is instrument


# raw() - unwrapped escape hatch for anything not in the registry

def test_raw_returns_unwrapped_feature_and_tracks_channel(bench):
    client = _FakeDiscoveredClient(features=["Spectrometer"])
    _scan_returning(bench, [client])

    feature = bench.devices.raw("Spectrometer")

    assert feature is client.Spectrometer
    assert client in bench._instrument_clients


def test_raw_zero_matches_raises(bench):
    _scan_returning(bench, [])
    with pytest.raises(RuntimeError, match="No server advertising"):
        bench.devices.raw("Spectrometer")


def test_raw_multiple_matches_raises(bench):
    c1 = _FakeDiscoveredClient(features=["Spectrometer"], address="10.0.0.1")
    c2 = _FakeDiscoveredClient(features=["Spectrometer"], address="10.0.0.2")
    _scan_returning(bench, [c1, c2])
    with pytest.raises(RuntimeError, match="Multiple servers advertise"):
        bench.devices.raw("Spectrometer")


# __dir__ - tab-completable registry names

def test_dir_lists_registry_names(bench, fake_registry):
    assert dir(bench.devices) == sorted(fake_registry)


# discover_sila_clients() itself

def test_discover_sila_clients_scans_then_returns_browser_clients(monkeypatch):
    """Confirms the real function shape - browse for `timeout` seconds, then
    read back whatever the browser collected. The browser class itself is
    faked; this isn't a real-network test."""
    sleeps = []

    class _FakeBrowser:
        clients = ["client-a", "client-b"]

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr("sila2.discovery.browser.SilaDiscoveryBrowser", lambda **kw: _FakeBrowser())
    monkeypatch.setattr(devices_module.time, "sleep", lambda s: sleeps.append(s))

    result = devices_module.discover_sila_clients(timeout=2.5)

    assert result == ["client-a", "client-b"]
    assert sleeps == [2.5]
