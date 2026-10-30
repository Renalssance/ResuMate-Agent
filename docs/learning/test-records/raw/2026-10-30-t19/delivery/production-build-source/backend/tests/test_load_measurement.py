"""Load reports must keep failures and distinguish commit latency from missing delivery."""
import importlib.util
from pathlib import Path

import pytest


def load_module():
    spec = importlib.util.spec_from_file_location('load_api_sse', Path(__file__).resolve().parents[2] / 'tests/load/api_sse.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_api_percentile_keeps_timeouts_and_non_success_samples():
    report = load_module().summarize_api([
        {'endpoint': 'jobs', 'elapsed_ms': n, 'status': 200, 'valid': True} for n in range(1, 20)
    ] + [{'endpoint': 'jobs', 'elapsed_ms': 800, 'status': 0, 'valid': False}])
    assert report['overall']['p95_ms'] == 19
    assert report['overall']['max_ms'] == 800
    assert report['overall']['samples'] == 20
    assert report['overall']['errors'] == 1
    assert report['passed'] is False


def test_empty_load_cannot_pass():
    report = load_module().summarize_api([])
    assert not report['passed'] and report['overall']['samples'] == 0


def test_sse_missing_or_duplicate_delivery_cannot_pass_fast_latency():
    check = load_module().summarize_delivery
    commits = [{'run_id': 'r1', 'seq': 3, 'committed_ns': 1_000_000_000}]
    receives = [{'subscriber': 0, 'run_id': 'r1', 'seq': 3, 'received_ns': 1_100_000_000}]
    result = check(commits, receives, {0: 'r1', 1: 'r1'})
    assert result['missing'] == 1 and result['p95_ms'] == 100
    assert result['passed'] is False
    duplicate = check(commits, receives * 2, {0: 'r1'})
    assert duplicate['duplicates'] == 1 and duplicate['passed'] is False


def test_sse_out_of_order_frames_cannot_pass_complete_delivery():
    commits = [{'run_id': 'r1', 'seq': n, 'committed_ns': 1_000_000_000} for n in (1, 2)]
    receives = [{'subscriber': 0, 'run_id': 'r1', 'seq': n, 'received_ns': 1_100_000_000} for n in (2, 1)]
    result = load_module().summarize_delivery(commits, receives, {0: 'r1'})
    assert result['passed'] is False
    assert result['out_of_order'] == 1
