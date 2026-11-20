from ci_parsers.python_parser import parse_python_source


def test_plain_type_checking_block():
    src = """
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from other import Thing

from real import Runtime
"""
    imps = {i.module: i for i in parse_python_source(src, "m").imports if i.module}
    assert imps["other"].type_only is True and not imps["other"].lazy
    assert not imps["real"].type_only


def test_else_branch_imports_stay_runtime():
    src = """
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ghost import Ghost
else:
    from real import Runtime
"""
    imps = {i.module: i for i in parse_python_source(src, "m").imports if i.module}
    assert imps["ghost"].type_only is True
    assert not imps["real"].type_only


def test_not_type_checking_puts_type_only_on_else():
    src = """
from typing import TYPE_CHECKING
if not TYPE_CHECKING:
    from real import Runtime
else:
    from ghost import Ghost
"""
    imps = {i.module: i for i in parse_python_source(src, "m").imports if i.module}
    assert not imps["real"].type_only
    assert imps["ghost"].type_only


def test_type_checking_alias():
    src = """
from typing import TYPE_CHECKING as TC
if TC:
    from other import Thing
"""
    (imp,) = [i for i in parse_python_source(src, "m").imports if i.module == "other"]
    assert imp.type_only is True


def test_type_checking_or_stays_runtime():
    src = """
from typing import TYPE_CHECKING
DEBUG = True
if TYPE_CHECKING or DEBUG:
    from other import Thing
"""
    (imp,) = [i for i in parse_python_source(src, "m").imports if i.module == "other"]
    assert not imp.type_only


def test_class_body_import_is_runtime():
    src = """
class Container:
    from inner import helper
"""
    (imp,) = [i for i in parse_python_source(src, "m").imports if i.module == "inner"]
    assert not imp.lazy and not imp.type_only


def test_function_local_imports_are_lazy():
    src = """
def load():
    from deferred import x
"""
    (imp,) = [i for i in parse_python_source(src, "m").imports if i.module == "deferred"]
    assert imp.lazy and not imp.type_only


def test_module_level_try_except_import_is_runtime():
    src = """
try:
    from fast import x
except ImportError:
    from slow import x
"""
    imps = {i.module: i for i in parse_python_source(src, "m").imports if i.module}
    assert not any(i.type_only or i.lazy for i in imps.values())
