"""Offline API-contract checks; fixtures are synthetic, never research evidence."""
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from eightk.webull_src import WebullPriceClient


def row(day, close=101):
    return dict(time=f"{day}T00:00:00+0000", open="100", high="103", low="99",
                close=str(close), volume="200")


class API:
    def __init__(self, records=None, status=200):
        self.calls = []
        self.records = records
        self.status = status
        self.market_data = self

    def get_history_bar(self, **kwargs):
        self.calls.append(kwargs)
        records = self.records
        if records is None:
            day = datetime.fromtimestamp(kwargs['start_time']/1000, timezone.utc).date()
            records = [row(str(day))]
        return SimpleNamespace(status_code=self.status,
                               json=lambda: [{"symbol": kwargs['symbol'], "result": records}])


def test_date_windows_cache_and_offline(tmp_path, monkeypatch):
    monkeypatch.setattr('eightk.webull_src.time.sleep', lambda _: None)
    api = API()
    client = WebullPriceClient(tmp_path, client=api)
    bars = client.daily_bars('ABC', '2024-01-01', '2024-03-01')
    assert len(api.calls) == 2
    assert [str(b.day) for b in bars] == ['2024-01-01', '2024-02-01']
    assert all(c['timespan'] == 'D' and c['count'] == '100' for c in api.calls)
    replay = WebullPriceClient(tmp_path, offline=True)
    assert replay.daily_bars('ABC', '2024-01-01', '2024-03-01') == bars
    assert client.option_contracts('ABC', as_of='2024-01-01') == []


def test_offline_miss_is_fatal(tmp_path):
    with pytest.raises(RuntimeError, match='offline cache miss'):
        WebullPriceClient(tmp_path, offline=True).daily_bars('ABC', '2024-01-01', '2024-02-01')


@pytest.mark.parametrize('status, records, message', [
    (401, None, 'HTTP 401'),
    (200, [], 'No Webull history'),
    (200, [row('2025-01-01')], 'inside requested window'),
    (200, [row('2024-01-02', float('nan'))], 'Invalid Webull OHLCV'),
])
def test_failures_never_become_successful_empty_backtests(tmp_path, monkeypatch, status, records, message):
    monkeypatch.setattr('eightk.webull_src.time.sleep', lambda _: None)
    client = WebullPriceClient(tmp_path, client=API(records, status))
    with pytest.raises((RuntimeError, ValueError), match=message):
        client.daily_bars('ABC', '2024-01-01', '2024-01-31')


def test_deduplicate_and_sort(tmp_path, monkeypatch):
    monkeypatch.setattr('eightk.webull_src.time.sleep', lambda _: None)
    client = WebullPriceClient(tmp_path, client=API([row('2024-01-03'), row('2024-01-02'), row('2024-01-03')]))
    assert [str(b.day) for b in client.daily_bars('ABC', '2024-01-01', '2024-01-31')] == ['2024-01-02', '2024-01-03']


def test_unadjusted_and_options_are_rejected(tmp_path):
    client = WebullPriceClient(tmp_path, offline=True)
    with pytest.raises(ValueError, match='adjusted stock'):
        client.daily_bars('O:ABC', '2024-01-01', '2024-01-31')
    with pytest.raises(ValueError, match='adjusted stock'):
        client.daily_bars('ABC', '2024-01-01', '2024-01-31', adjusted=False)
