import unittest

import slope
from slope import ad
from slope.base_array import BaseArray
from slope.array import Array
import numpy as np
import os
from typing import NamedTuple
from functools import partial

DEBUG = os.environ.get("SLOPE_DEBUG", 0)


class TestJit(unittest.TestCase):
    def test_add(self):
        # @slope.ad.jit
        def f(x, **kwargs):
            # breakpoint()
            out = x + x
            out = x + Array([4., 5., 6.])
            return out

        res = f(Array([1.0, 2.0, 3.0]))
        print(res)


if __name__ == "__main__":
    unittest.main()
