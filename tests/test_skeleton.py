# -*- coding: utf-8 -*-

import pytest
from dumpling.skeleton import fib

__author__ = "Manuel Eggimann"
__copyright__ = "Manuel Eggimann"
__license__ = "apache"


def test_fib():
    assert fib(1) == 1
    assert fib(2) == 1
    assert fib(7) == 13
    with pytest.raises(AssertionError):
        fib(-10)
