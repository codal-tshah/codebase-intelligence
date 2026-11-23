"""Files written for newer Pythons must still be analysed by the 3.12 runtime."""

from ci_parsers.files import DEFAULT_SKIP_DIRS
from ci_parsers.python_parser import parenthesize_bare_except, parse_python_source

PEP758 = '''import requests


def fetch(url):
    try:
        return requests.get(url)
    except ValueError, TypeError:
        return None
    except (KeyError, IndexError):
        return None
    except OSError as exc:
        raise RuntimeError(url) from exc


def other():
    return fetch("x")
'''


def test_unparenthesised_except_is_parsed_with_exact_lines():
    result = parse_python_source(PEP758, "svc")
    assert result.error is None
    names = {s.name: s for s in result.symbols}
    assert {"fetch", "other"} <= set(names)
    assert names["other"].start_line == 15  # line numbers unchanged by the rewrite
    assert any(c.callee.endswith("fetch") for c in result.calls)


def test_rewrite_only_touches_bare_tuples():
    fixed = parenthesize_bare_except(PEP758)
    assert fixed is not None
    assert "except (ValueError, TypeError):" in fixed
    assert "except (KeyError, IndexError):" in fixed  # already parenthesised: unchanged
    assert "except OSError as exc:" in fixed
    assert fixed.count("\n") == PEP758.count("\n")
    assert parenthesize_bare_except("x = 1\n") is None


def test_real_syntax_errors_still_reported():
    assert parse_python_source("def broken(:\n    pass\n", "m").error


def test_generated_report_dirs_are_skipped():
    assert {"htmlcov", "coverage", ".next"} <= DEFAULT_SKIP_DIRS
