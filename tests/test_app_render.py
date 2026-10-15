"""Render tests -- NEED A LIVE DATABASE. The only check that catches UI-only errors.

    $env:PYTHONPATH="."; .venv\\Scripts\\python.exe tests\\test_app_render.py

Never imports app.py; Streamlit's AppTest runs it as a script.
"""
from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

from streamlit.testing.v1 import AppTest

TIMEOUT = 120
APP = str(Path(__file__).resolve().parent.parent / "app.py")


def _app() -> AppTest:
    at = AppTest.from_file(APP, default_timeout=TIMEOUT)
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def test_renders_all_tabs():
    at = _app()
    assert len(at.tabs) == 7
    assert at.title[0].value == "CHRO External Recognition"
    assert not at.error, [e.value for e in at.error]


def test_overview_counts_multi_source_leaders():
    at = _app()
    labels = {m.label: m.value for m in at.metric}
    # Workbook facts: Breitfelder, Ola Snow, Donna Morris are each recognized by 2 orgs.
    assert int(labels["Recognized by 2+ organizations"]) >= 3, labels


def test_profiles_render_for_varied_executives():
    at = _app()
    sb = at.selectbox(key="prof_exec")
    want = {"Matthew Breitfelder", "Rob Ployhart", "Paul Gregory", "Paige Ross", "Riya Sood"}
    # `options` holds the format_func LABELS; the values are ids, so select by index.
    picked = [o for o in sb.options if o in want]
    assert len(picked) == len(want), f"missing executives: {want - set(picked)}"
    for name in picked:
        at.selectbox(key="prof_exec").select_index(sb.options.index(name))
        at.run()
        assert not at.exception, (name, [e.value for e in at.exception])


def test_compare_filters_do_not_crash():
    at = _app()
    at.checkbox(key="cmp_sec").check()
    at.checkbox(key="cmp_acad").check()
    at.selectbox(key="cmp_year").set_value("2026")
    at.selectbox(key="cmp_mb").set_value(2)
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    at.checkbox(key="cmp_ad").check()
    at.run()
    assert not at.exception, [e.value for e in at.exception]


def test_peer_sets_and_review_render():
    at = _app()
    sb = at.selectbox(key="peer_set")
    for i in range(len(sb.options)):
        at.selectbox(key="peer_set").select_index(i)
        at.run()
        assert not at.exception, [e.value for e in at.exception]
    # Review renders its editor only when drafts exist; filtering must not crash.
    if any(m.key == "rv_conf" for m in at.multiselect):
        at.multiselect(key="rv_conf").set_value(["high"])
        at.run()
        assert not at.exception, [e.value for e in at.exception]


def test_password_gate_blocks_until_correct():
    os.environ["APP_PASSWORD"] = "test-pw"
    try:
        at = AppTest.from_file(APP, default_timeout=TIMEOUT)
        at.run()
        assert len(at.tabs) == 0, "content rendered without a password"
        at.text_input(key="pw").input("wrong")
        at.run()
        assert at.error and len(at.tabs) == 0
        at.text_input(key="pw").input("test-pw")
        at.run()
        assert not at.exception and len(at.tabs) == 7
    finally:
        os.environ.pop("APP_PASSWORD", None)


def main() -> int:
    tests = [(n, f) for n, f in globals().items() if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS {name}")
        except Exception:
            failed += 1
            print(f"FAIL {name}")
            traceback.print_exc()
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
