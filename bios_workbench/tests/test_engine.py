import pandas as pd
import pytest
from bios_workbench.core.engine import BIOSProcessEngine
from bios_workbench.core.contract import HEADERS


def make_df(rows):
    df = pd.DataFrame(rows, columns=HEADERS)
    return df


def test_missing_headers():
    engine = BIOSProcessEngine()
    df = pd.DataFrame({'foo': [1]})
    with pytest.raises(Exception):
        engine.load(df)


def test_unknown_next_step():
    rows = [
        ['O','','','','','T1','start','A','','human:X','','','','','', 'T2'],
    ]
    df = make_df(rows)
    engine = BIOSProcessEngine()
    engine.load(df)
    issues = engine.validate()
    assert any(i['code']=='unknown_next' for i in issues)


def test_dead_end_task():
    rows = [
        ['','','','','','T1','task','A','','human:X','','','','','', ''],
    ]
    df = make_df(rows)
    engine = BIOSProcessEngine()
    engine.load(df)
    issues = engine.validate()
    assert any(i['code']=='dead_end' for i in issues)


def test_decision_single_branch():
    rows = [
        ['','','','','','T1','decision','A','','human:X','','','','','', 'T2'],
        ['','','','','','T2','end','B','','human:X','','','','','', ''],
    ]
    df = make_df(rows)
    engine = BIOSProcessEngine()
    engine.load(df)
    issues = engine.validate()
    assert any(i['code']=='decision_branches' for i in issues)


def test_cycle_detection():
    rows = [
        ['','','','','','T1','start','A','','human:X','','','','','', 'T2'],
        ['','','','','','T2','task','B','','human:X','','','','','', 'T1'],
    ]
    df = make_df(rows)
    engine = BIOSProcessEngine()
    engine.load(df)
    issues = engine.validate()
    assert any(i['code']=='cycle' for i in issues)
