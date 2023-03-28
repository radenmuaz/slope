from myad.ops.base import ShapeOp
import numpy as np


class Reshape(ShapeOp):
    @staticmethod
    def eval(x, *, perm):
        return [np.reshape(x, perm)]
