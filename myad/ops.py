import myad
import numpy as np
from myad.array_shape import ArrayShape
from typing import List, Tuple, Sequence, Any
from abc import ABC, abstractmethod

class Op(ABC):
    @classmethod
    def do(cls, *args):
        return myad.RT.bind1(cls, *args)

    @classmethod
    @abstractmethod
    def eval(cls, *args):
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def vmap(cls, *args):
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def jvp(cls, *args):
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def shape_eval(cls, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def pprint(cls):
        return None

    @classmethod
    @abstractmethod
    def mlir(cls):
        raise NotImplementedError

class UnaryOp(Op):
    @classmethod
    def vmap(cls, axis_size, vals_in, dims_in):
        (x,), (x_bdim,) = vals_in, dims_in
        return [cls.do(x)], [x_bdim]

    @classmethod
    def shape_eval(cls, x: ArrayShape) -> List[ArrayShape]:
        return [ArrayShape(x.shape, x.dtype)]


class BinaryOp(Op):
    @classmethod
    def vmap(cls, axis_size, vals_in, dims_in):
        def move_batch_axis(axis_size, src, dst, x):
            if src is None:
                target_shape = list(x.shape)
                target_shape.insert(dst, axis_size)
                return Broadcast.do(x, target_shape, [dst])
            elif src == dst:
                return x
            else:
                perm = [i for i in range(x.ndim) if i != src]
                perm.insert(dst, src)
                return Transpose.do(x,perm)

        (x, y), (x_bdim, y_bdim) = vals_in, dims_in
        if x_bdim != y_bdim:
            if x_bdim is None:
                x = move_batch_axis(axis_size, x_bdim, y_bdim, x)
                x_bdim = y_bdim
            else:
                y = move_batch_axis(axis_size, y_bdim, x_bdim, y)
        return [cls.do(x, y)], [x_bdim]

    @classmethod
    def shape_eval(cls, x: ArrayShape, y: ArrayShape) -> List[ArrayShape]:
        if not isinstance(x, ArrayShape) or not isinstance(y, ArrayShape):
            raise TypeError
        if ArrayShape.like(x) != ArrayShape.like(y):
            raise TypeError
        return [ArrayShape(x.shape, x.dtype)]


class ReduceOp(Op):
    @classmethod
    def vmap(cls, axis_size, vals_in, dims_in, *, axis):
        (x,), (x_bdim,) = vals_in, dims_in
        new_axis = tuple(ax + (x_bdim <= ax) for ax in axis)
        out_bdim = x_bdim - sum(ax < x_bdim for ax in axis)
        return [cls.do(x, new_axis)], [out_bdim]

    @classmethod
    def shape_eval(cls, x: ArrayShape, *, axis: Tuple[int, ...]) -> List[ArrayShape]:
        axis_ = set(axis)
        new_shape = [d for i, d in enumerate(x.shape) if i not in axis_]
        return [ArrayShape(tuple(new_shape), x.dtype)]


class ShapeOp(Op):
    pass


# -----------------------
# UnaryOps
# -----------------------


class Identity(UnaryOp):
    @classmethod
    def eval(cls, x):
        return [x]
    
    @classmethod
    def jvp(cls, primals, tangents):
        (x,), (x_dot,) = primals, tangents
        return [cls.do(x)], [x_dot]

class Exp(UnaryOp):
    @classmethod
    def eval(cls, x):
        return [np.exp(x)]

    @classmethod
    def jvp(cls, primals, tangents):
        (x,), (x_dot,) = primals, tangents
        return [cls.do(x)], [x_dot * cls.do(x)]


class Log(UnaryOp):
    @classmethod
    def eval(cls, x):
        return [np.log(x)]

    @classmethod
    def jvp(cls, primals, tangents):
        (x,), (x_dot,) = primals, tangents
        return [cls.do(x)], [x_dot / x]


class Neg(UnaryOp):
    @classmethod
    def eval(cls, x):
        return [-x]

    @classmethod
    def jvp(cls, primals, tangents):
        (x,), (x_dot,) = primals, tangents
        return [-x], [-x_dot]
    
    @classmethod
    def T(cls, t, x):
        (z,) = t
        return [-z]


# -----------------------
# BinaryOps
# -----------------------


class Add(BinaryOp):
    @classmethod
    def eval(cls, x, y):
        return [x + y]

    @classmethod
    def jvp(cls, primals, tangents):
        (x, y), (x_dot, y_dot) = primals, tangents
        return [x + y], [x_dot + y_dot]

    @classmethod
    def T(cls, cts, x, y):
        (z_bar,) = cts
        return [z_bar, z_bar]



class Sub(BinaryOp):
    @classmethod
    def eval(cls, x, y):
        return [x - y]

    @classmethod
    def jvp(cls, primals, tangents):
        (x, y), (x_dot, y_dot) = primals, tangents
        return [x + y], [x_dot + y_dot]

    @classmethod
    def T(cls, cts, x, y):
        (z_bar,) = cts
        return [z_bar, -z_bar]

class Mul(BinaryOp):
    @classmethod
    def eval(cls, x, y):
        return [x * y]

    @classmethod
    def jvp(cls, primals, tangents):
        (x, y), (x_dot, y_dot) = primals, tangents
        return [x * y], [x_dot * y + x * y_dot]

    @classmethod
    def T(cls, cts, x, y):
        (z_bar,) = cts
        if type(x) is myad.core.UndefPrimal:
            return [(z_bar * y), None] 
        elif type(y) is myad.core.UndefPrimal:
            return [None, (x * z_bar)]


class Div(BinaryOp):
    @classmethod
    def eval(cls, x, y):
        return [x / y]

    @classmethod
    def jvp(cls, primals, tangents):
        (x, y), (x_dot, y_dot) = primals, tangents
        return [x / y], [(x_dot / y) + (-y_dot * x * (y**-2))]
    
    @classmethod
    def T(cls, cts, x, y):
        (z_bar,) = cts
        return [z_bar / y, None]


class Pow(BinaryOp):
    @classmethod
    def eval(cls, x, y):
        return [x**y]

    @classmethod
    def jvp(cls, primals, tangents):
        (x, y), (x_dot, y_dot) = primals, tangents
        return [x * y], [x_dot * y + x * y_dot]


class Max(BinaryOp):
    @classmethod
    def eval(cls, x, y):
        return [x**y]

    @classmethod
    def jvp(cls, primals, tangents):
        (x, y), (x_dot, y_dot) = primals, tangents
        return [x * y], [x_dot * y + x * y_dot]


# -----------------------
# ReduceOps
# -----------------------


class ReduceMax(ReduceOp):
    @classmethod
    def eval(cls, x, *, axis):
        return [x.sum(axis)]

    @classmethod
    def jvp(cls, primals, tangents):
        (x, y), (x_dot, y_dot) = primals, tangents
        return [x * y], [x_dot * y + x * y_dot]


class ReduceSum(ReduceOp):
    @classmethod
    def eval(cls, x, *, axis):
        return [x.sum(axis)]

    @classmethod
    def jvp(cls, primals, tangents):
        (x, y), (x_dot, y_dot) = primals, tangents
        return [x * y], [x_dot * y + x * y_dot]


# -----------------------
# ShapeOps
# -----------------------


class Broadcast(ShapeOp):
    @classmethod
    def eval(cls, x, *, shape, axes):
        for axis in sorted(axes):
            # out_ndim = len(axis) + x.ndim
            # shape_it = iter(x.shape)
            # shape = [1 if ax in axis else next(shape_it)
            #          for ax in range(out_ndim)]
            # x = x.reshape(shape)
            x = np.expand_dims(x, axis)
        return [x.broadcast(shape)]

    # @staticmethod
    # def jvp(primals, tangents):
    #     (x, y), (x_dot, y_dot) = primals, tangents
    #     return [x * y], [x_dot * y + x * y_dot]

    @classmethod

    def shape_eval(cls,
        x: ArrayShape, shape: Sequence[int], axes: Sequence[int]
    ) -> List[ArrayShape]:
        return [ArrayShape(tuple(shape), x.dtype)]


class Crop(ShapeOp):
    @classmethod
    def eval(cls, x, slice):
        return [x[slice]]


class Reshape(ShapeOp):
    @classmethod
    def eval(cls, x, *, perm):
        return [np.reshape(x, perm)]


class Transpose(ShapeOp):
    @classmethod
    def eval(cls, x, *, perm):
        return [x.transpose(perm)]


class Pad(ShapeOp):
    @classmethod
    def eval(cls, x, *, perm):
        return [x.pad(perm)]
