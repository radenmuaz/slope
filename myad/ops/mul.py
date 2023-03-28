from myad.ops.base import BinaryOp
class Mul(BinaryOp):
    @staticmethod
    def eval(x, y):
        return [x * y]

    @staticmethod
    def jvp(primals, tangents):
        (x, y), (x_dot, y_dot) = primals, tangents
        return [x * y], [x_dot * y + x * y_dot]

    @staticmethod
    def T(ct, x, y):
        z_bar, = ct
        assert (x is None) ^ (y is None)
        return [(z_bar * y), None] if x is None else [None, (x * z_bar)]

