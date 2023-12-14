import slope
from slope.core import (
    Compiler,
    Backend,
    Operator,
    OperatorSet,
    ProcedureSet,
    Tensor,
    TensorBuffer,
    Typecheckor,
    PrimalProxy,
    list_zip,
    list_map,
)

import math
import numpy as np
from typing import Tuple, List, Dict, Any, Optional, Sequence, Union, Iterator, NamedTuple
from collections import defaultdict
import iree.compiler
import iree.runtime
import os

sum_py = sum
max_py = max
abs_py = abs
slice_py = slice

# --------------
# Operator
# --------------

operator_set = OperatorSet()

# -----------------------
# Unary
# -----------------------

stop_gradient = Operator.unary("stop_gradient")
operator_set.register(stop_gradient)


@stop_gradient.set_method
def jvp(self, primals, tangents, **params):
    (x,), (x_dot,) = primals, tangents
    return [x], [slope.zeros_like(x_dot)]


@stop_gradient.set_method
def T(self, cotangents, x):
    return [None]


cast = Operator.unary("cast")
astype = cast
operator_set.register(cast)
operator_set.alias(cast, "astype")


@cast.set_method
def typecheck(self, x: Typecheckor, *, dtype) -> List[Typecheckor]:
    return [Typecheckor(x.shape, dtype)]


@cast.set_method
def jvp(self, primals, tangents, *, dtype):
    (x,), (x_dot,) = primals, tangents
    return [x.cast(dtype)], [x_dot.cast(dtype)]


@cast.set_method
def T(self, cotangents, x):
    (grad_L_y,) = cotangents
    return [grad_L_y.cast(x.dtype)]


sqrt = Operator.unary("sqrt")
operator_set.register(sqrt)


@sqrt.set_method
def jvp(self, primals, tangents, **params):
    (x,), (x_dot,) = primals, tangents
    y = x.sqrt()
    return [y], [x_dot / (y * 2)]


@sqrt.set_method
def T(self, cotangents, x):
    (grad_L_y,) = cotangents
    return [grad_L_y / (x.sqrt() * 2)]


sin = Operator.unary("sin")
operator_set.register(sin)


@sin.set_method
def jvp(self, primals, tangents, **params):
    (x,), (x_dot,) = primals, tangents
    return [x.sin()], [(x_dot * ((math.pi / 2) - x).sin())]


@sin.set_method
def T(self, cotangents, x):
    (grad_L_y,) = cotangents
    return [(grad_L_y * ((math.pi / 2) - x).sin())]


exp = Operator.unary("exp")
operator_set.register(exp)


@exp.set_method
def jvp(self, primals, tangents, **params):
    (x,), (x_dot,) = primals, tangents
    y = x.exp()
    return [y], [x_dot * y]


@exp.set_method
def T(self, cotangents, x):
    (grad_L_y,) = cotangents
    return [1 / grad_L_y]


log = Operator.unary("log")
operator_set.register(log)


@log.set_method
def jvp(self, primals, tangents, **params):
    (x,), (x_dot,) = primals, tangents
    return [x.log()], [x_dot / x]


@log.set_method
def T(self, cotangents, x):
    (grad_L_y,) = cotangents
    return [1 / grad_L_y]


neg = Operator.unary("neg")
operator_set.register(neg)


@neg.set_method
def jvp(self, primals, tangents, **params):
    (x,), (x_dot,) = primals, tangents
    return [-x], [-x_dot]


@neg.set_method
def T(self, cotangents, x):
    (grad_L_y,) = cotangents
    return [-grad_L_y]


invert = Operator.unary("invert")
operator_set.register(invert)


@invert.set_method
def jvp(self, primals, tangents, **params):
    (x,), (x_dot,) = primals, tangents
    return [~x], [~x_dot]


@invert.set_method
def T(self, cotangents, x):
    (grad_L_y,) = cotangents
    return [~grad_L_y]


@invert.set_method
def typecheck(self, x, **params):
    return [Typecheckor(x.shape, slope.bool)]


# -----------------------
# Binary
# -----------------------


add = Operator.binary("add")
operator_set.register(add)


@add.set_method
def jvp(self, primals, tangents):
    (x, w), (x_dot, w_dot) = primals, tangents
    return [x + w], [x_dot + w_dot]


@add.set_method
def T(self, cotangents, x, w):
    (grad_L_y,) = cotangents
    return [grad_L_y, grad_L_y]


sub = Operator.binary("sub")
operator_set.register(sub)


@sub.set_method
def jvp(self, primals, tangents):
    (x, w), (x_dot, w_dot) = primals, tangents
    return [x - w], [x_dot - w_dot]


@sub.set_method
def T(self, cotangents, x, w):
    (grad_L_y,) = cotangents
    return [grad_L_y, -grad_L_y]


mul = Operator.binary("mul")
operator_set.register(mul)


@mul.set_method
def jvp(self, primals, tangents):
    (x, w), (x_dot, w_dot) = primals, tangents
    return [x * w], [(x_dot * w) + (w_dot * x)]


@mul.set_method
def T(self, cotangents, x, w):
    (grad_L_y,) = cotangents
    assert (type(x) is PrimalProxy) ^ (type(w) is PrimalProxy)
    if type(x) is PrimalProxy:
        return [grad_L_y * w, None]
    elif type(w) is PrimalProxy:
        return [None, x * grad_L_y]


div = Operator.binary("div")
operator_set.register(div)


@div.set_method
def jvp(self, primals, tangents):
    (x, w), (x_dot, w_dot) = primals, tangents
    return [x / w], [(x_dot / w) + (-w_dot * x * 1 / (w * w))]


@div.set_method
def T(self, cotangents, x, w):
    (grad_L_y,) = cotangents
    return [grad_L_y / w, None]


pow = Operator.binary("pow")
operator_set.register(pow)


@pow.set_method
def jvp(self, primals, tangents):
    (x, w), (x_dot, w_dot) = primals, tangents
    y = x**w
    y_dot1 = x_dot * (w * (x ** (w - slope.ones_like(w))))
    y_dot2 = w_dot * (y * (x if x != 0.0 else slope.zeros_like(x)).log())
    return [y], [y_dot1 + y_dot2]


@pow.set_method
def T(self, cotangents, x, w):
    (grad_L_y,) = cotangents
    assert (type(x) is PrimalProxy) ^ (type(w) is PrimalProxy)
    if type(x) is PrimalProxy:
        return [(grad_L_y * (w * (x ** (w - slope.ones_like(w))))), None]
    elif type(w) is PrimalProxy:
        return [None, grad_L_y * ((x**w) * (x.log() if x != 0.0 else slope.zeros_like(x)))]


maximum = Operator.binary("maximum")
operator_set.register(maximum)


@maximum.set_method
def jvp(self, primals, tangents):
    def _balanced_eq(x, z, y):
        xz = (x == z).where(slope.ones_like(z), slope.zeros_like(z))
        yz = (y == z).where(slope.full_like(z, 2), slope.ones_like(z))
        return xz / yz

    (x, w), (x_dot, w_dot) = primals, tangents
    y = x.maximum(w)
    y_dot = x_dot * _balanced_eq(x, y, w) + w_dot * _balanced_eq(w, y, x)
    return [y], [y_dot]


@maximum.set_method
def T(self, cotangents, x, w):
    (grad_L_y,) = cotangents
    return [grad_L_y, None]


equal = Operator.binary("equal")
operator_set.register(equal)


@equal.set_method
def jvp(self, primals, tangents):
    (x, w), _ = primals, tangents
    out_primal = x.equal(w)
    return [out_primal], [slope.full(out_primal.shape, True, Tensor.bool)]


@equal.set_method
def T(self, cotangents, x, w):
    (grad_L_y,) = cotangents
    grad_L_y = grad_L_y.cast(x.dtype)
    return [grad_L_y, None]


@equal.set_method
def typecheck(self, x: Typecheckor, y: Typecheckor, **params) -> List[Typecheckor]:
    # difference with default binary typecheck: force dtype bool
    if not type(x) in (Tensor, Typecheckor) or not type(x) in (
        Tensor,
        Typecheckor,
    ):
        raise TypeError
    if x.dtype != y.dtype:
        raise TypeError
    void_x = Typecheckor.like(x)
    void_y = Typecheckor.like(y)
    if void_x == void_y:
        return [Typecheckor(void_x.shape, Tensor.bool)]
    shape_delta = len(void_x.shape) - len(void_y.shape)
    if shape_delta > 0:
        void_y = Typecheckor((1,) * shape_delta + void_y.shape, Tensor.bool)
    elif shape_delta < 0:
        x = x.reshape((1,) * -shape_delta + void_x.shape)
        void_x = Typecheckor((1,) * -shape_delta + void_x.shape, Tensor.bool)
    if void_x == void_y:
        return [void_x]
    else:
        shape_ret = tuple([max(x, w) for x, w in zip(void_x.shape, void_y.shape)])
        if void_x.shape != shape_ret:
            void_x = Typecheckor(shape_ret, Tensor.bool)
        if void_y.shape != shape_ret:
            void_y = Typecheckor(shape_ret, Tensor.bool)
        if void_x != void_y:
            raise TypeError
        return [void_x]


max = Operator.reduce("max")
operator_set.register(max)


@max.set_method
def jvp(self, primals, tangents, *, dim, keepdim):
    (x,), (x_dot,) = primals, tangents
    y = x.max(dim, keepdim)
    y_ = y
    if not keepdim:
        dim = tuple([a if a >= 0 else len(y.shape) + a + 1 for a in dim])
        for a in reversed(sorted(dim)):
            y_ = y_.reshape(y.shape[:a] + (1,) + y.shape[a:])
    locs = x.equal(y_.expand(x.shape))
    locs = locs.cast(x_dot.dtype)
    counts = locs.sum(dim, keepdim)
    y_dot = (x_dot * locs).sum(dim, keepdim)
    y_dot = y_dot / counts.expand(y_dot.shape)

    return [y], [y_dot]


@max.set_method
def T(self, cotangents, x, *, dim, keepdim):
    # TODO: this is sum gradient, define max gradient
    (grad_L_y,) = cotangents
    grad_L_x = grad_L_y
    if not keepdim:
        dim = [a if a >= 0 else len(grad_L_x.shape) + a + 1 for a in dim]
        for a in reversed(sorted(dim)):
            grad_L_x = grad_L_x.reshape(grad_L_x.shape[:a] + (1,) + grad_L_x.shape[a:])
    grad_L_x = grad_L_x.expand(x.aval.shape)


sum = Operator.reduce("sum")
operator_set.register(sum)


@sum.set_method
def jvp(self, primals, tangents, *, dim, keepdim):
    (x,), (x_dot,) = primals, tangents
    y = x.sum(dim, keepdim)
    y_dot = x_dot.sum(dim, keepdim)
    return [y], [y_dot]


@sum.set_method
def T(self, cotangents, x, *, dim, keepdim):
    (grad_L_y,) = cotangents
    grad_L_x = grad_L_y
    if not keepdim:
        dim = [a if a >= 0 else len(grad_L_x.shape) + a + 1 for a in dim]
        for a in reversed(sorted(dim)):
            grad_L_x = grad_L_x.reshape(grad_L_x.shape[:a] + (1,) + grad_L_x.shape[a:])
    grad_L_x = grad_L_x.expand(x.aval.shape)

    return [grad_L_x]


# -----------------------
# Shape
# -----------------------


expand = Operator.other("expand")
operator_set.register(expand)


@expand.set_method
def args_fixer(self, x, *, shape):
    return (x,), dict(shape=shape)


@expand.set_method
def vmap(self, dim_size, vals_in, dims_in, *, shape):
    (x,), (x_bdim,) = vals_in, dims_in
    shape = list(shape)

    shape = shape[:x_bdim] + [dim_size] + shape[x_bdim:]

    return [self(x, shape)], [x_bdim]


@expand.set_method
def jvp(self, primals, tangents, *, shape, dim=None):
    (x,), (x_dot,) = primals, tangents
    return (
        [self(x, shape=shape)],
        [self(x_dot, shape=shape)],
    )


@expand.set_method
def typecheck(self, x: Typecheckor, *, shape: Sequence[int]) -> List[Typecheckor]:
    e_shape = list(x.shape)
    assert len(e_shape) == len(shape)
    assert all(a <= b for a, b in zip(e_shape, shape))
    return [Typecheckor(tuple(shape), x.dtype)]


@expand.set_method
def T(self, cotangents, x, *, shape):
    (grad_L_y,) = cotangents
    grad_L_x = grad_L_y
    if x.aval.shape == grad_L_x.shape:
        return [grad_L_x]
    else:
        b_dim = []
        assert len(x.aval.shape) == len(grad_L_x.shape)
        for i, (xd, od) in enumerate(zip(x.aval.shape, grad_L_x.shape)):
            if xd != od:
                b_dim += [i]
        grad_L_x = grad_L_x.sum(dim=tuple(b_dim), keepdim=True)
    if grad_L_x.shape != x.aval.shape:
        raise ValueError(f"not same {grad_L_x.shape=}, {x.aval.shape=}")
    return [grad_L_x]


reshape = Operator.other("reshape", nary_inputs=True)
operator_set.register(reshape)
operator_set.alias(reshape, "view")


@reshape.set_method
def args_fixer(self, x, *args, **kwargs):
    if "shape" in kwargs.keys():
        shape = kwargs["shape"]
    elif isinstance(args[0], (tuple, list)):
        shape = args[0]
    else:
        shape = args
    shape = tuple(shape)
    if -1 in shape:
        others = math.prod([d for d in shape if d != -1])
        numel = math.prod(x.shape)
        shape = tuple(d if d != -1 else (numel // others) for d in shape)
    return (x,), dict(shape=shape)


@reshape.set_method
def jvp(self, primals, tangents, *, shape):
    (x,), (x_dot,) = primals, tangents
    return [x.reshape(shape)], [x_dot.reshape(shape)]


@reshape.set_method
def typecheck(self, x: Typecheckor, *, shape: Sequence[int]) -> List[Typecheckor]:
    return [Typecheckor(tuple(shape), x.dtype)]


@reshape.set_method
def T(self, cotangents, x, *, shape):
    (z,) = cotangents
    return [z.reshape(x.aval.shape)]


permute = Operator.other("permute")
operator_set.register(permute)


@permute.set_method
def vmap(self, dim_size, vals_in, dims_in, *, perm):
    (x,), (x_bdim,) = vals_in, dims_in
    perm_ = list(perm)
    x_bdim_ = int(x_bdim)
    assert x_bdim >= 0
    perm = perm[:x_bdim] + [x_bdim] + perm[x_bdim:]
    perm = tuple(d + int(d >= x_bdim) if i != x_bdim else d for i, d in enumerate(perm))
    assert len(set(perm)) == len(perm)
    return [x.tranpose(perm)], [x_bdim]


@permute.set_method
def jvp(self, primals, tangents, *, perm):
    (x,), (x_dot,) = primals, tangents
    return [x.permute(perm)], [x_dot.permute(perm)]


@permute.set_method
def typecheck(self, x: Typecheckor, *, perm: Sequence[int]) -> List[Typecheckor]:
    shape = [x.shape[i] for i in perm]
    return [Typecheckor(shape, x.dtype)]


@permute.set_method
def T(self, cotangents, x, *, perm):
    (z,) = cotangents
    inv_perm = tuple(i[0] for i in sorted(enumerate(perm), key=lambda x: x[1]))
    return [z.permute(inv_perm)]


pad = Operator.other("pad")
operator_set.register(pad)


@pad.set_method
def args_fixer(self, x, *, padding, mode="constant", value=0.0):
    if isinstance(padding, int):
        padding = (padding, padding) * x.ndim
    elif all(isinstance(pw, int) for pw in padding):
        assert (len(x.shape) * 2) % len(padding) == 0
        padding = (0, 0) * (len(x.shape) - len(padding) // 2) + tuple(padding)
    return (x,), dict(padding=padding, mode=mode, value=value)


@pad.set_method
def vmap(self, dim_size, vals_in, dims_in, *, padding, mode, value):
    raise NotImplementedError
    Operand, padding_value = batched_args
    Operand_bdim, padding_value_bdim = batch_dims
    if Operand_bdim is None:
        Operand_bdim = 0
        Operand = broadcast_in_dim(operand, (padding_value.shape[padding_value_bdim],))

    padding_config = list(padding_config)
    padding_config.insert(operand_bdim, (0, 0, 0))
    if padding_value_bdim is None:
        return pad(operand, padding_value, padding_config), Operand_bdim

    assert padding_value_bdim == 0, padding_value_bdim

    x = pad(operand, _zero(operand), padding_config)
    mask = pad(full_like(operand, True, np.bool_), False, padding_config)
    broadcast_in_dimed_padding = broadcast_in_dim_in_dim(padding_value, x.shape, (operand_bdim,))
    return select(mask, x, broadcast_in_dimed_padding), Operand_bdim


@pad.set_method
def jvp(self, primals, tangents, *, padding, mode, value):
    (x,), (x_dot,) = primals, tangents
    return [x.pad(padding, mode, value)], [x_dot.pad(padding, mode, value)]


@pad.set_method
def typecheck(self, x: Typecheckor, *, padding, mode, value) -> List[Typecheckor]:
    lo, hi = padding[0::2], padding[1::2]
    interior = [0] * (len(padding) // 2)

    def _dilate_dim(d, dilation):
        return 0 if d == 0 else 1 + dilation * (d - 1)

    shape = tuple(sum_py([l, h, _dilate_dim(d, r + 1)]) for l, h, r, d in list_zip(lo, hi, interior, x.shape))
    if not all(d >= 0 for d in shape):
        raise ValueError(
            f"Dimension size after padding is not at least 0, "
            f"got result shape {res}, for {lo=} {hi=} {interior=} {value=}"
            f"{shape=}"
        )
    res = Typecheckor(shape, x.dtype)
    return [res]


@pad.set_method
def T(self, cotangents, x, *, padding, mode, value):
    (z,) = cotangents
    lo, hi = padding[0::2], padding[1::2]
    interior = [0] * (len(padding) // 2)

    def t_op():
        unpadded = z.slice(
            lo,
            tuple(s - h for s, h in list_zip(z.shape, hi)),
            tuple([1] * len(interior)),
        )
        return unpadded.slice(tuple([0] * len(lo)), unpadded.shape, tuple(r + 1 for r in interior))

    res = t_op() if isinstance(x, PrimalProxy) else None
    return [res]


slice = Operator.other("slice")
operator_set.register(slice)


@slice.set_method
def args_fixer(self, x, *, starts, limits, strides=None):
    if strides is None:
        strides = (1,) * len(starts)
    return (x,), dict(starts=starts, limits=limits, strides=strides)


@slice.set_method
def vmap(self, dim_size, vals_in, dims_in, *, starts, limits, strides=None):
    raise NotImplementedError
    (x,) = vals_in
    (x_bdim,) = dims_in

    new_start_indices = list(starts)
    new_start_indices.insert(x_bdim, 0)

    new_limit_indices = list(limits)
    new_limit_indices.insert(x_bdim, x.shape[x_bdim])

    if strides is None:
        new_strides = None
    else:
        new_strides = list(strides)
        new_strides.insert(x_bdim, 1)

    out = x.slice(new_start_indices, new_limit_indices, new_strides)
    return out, x_bdim


@slice.set_method
def jvp(self, primals, tangents, *, starts, limits, strides=None):
    (x,), (x_dot,) = primals, tangents
    return [x.slice(starts, limits, strides)], [x_dot.slice(starts, limits, strides)]


@slice.set_method
def typecheck(self, x: Typecheckor, *, starts, limits, strides=None) -> List[Typecheckor]:
    if strides is None or tuple(strides) == (1,) * len(x.shape):
        shape = tuple(
            [limit if type(start) is int and start == 0 else limit - start for start, limit in list_zip(starts, limits)]
        )
        return [Typecheckor(shape, x.dtype)]
    else:
        # TODO: compute strided shape without numpy
        x = np.zeros_like(x.shape)
        x = x[tuple(slice(s, l, r) for s, l, r in list_zip(starts, limits, strides))]
        return [Typecheckor(x.shape, x.dtype)]


@slice.set_method
def T(self, cotangents, x, *, starts, limits, strides=None):
    # TODO: compute tuple arithmetic without numpy
    (z,) = cotangents
    x_shape = x.aval.shape
    assert isinstance(x, PrimalProxy)
    if strides is None or np.all(np.equal(strides, 1)):
        lo, hi, interior = (
            starts,
            tuple(np.subtract(x.aval.shape, limits)),
            (0,) * len(starts),
        )
    else:
        real_limits = np.add(
            starts,
            tuple(
                np.where(
                    np.array(x.shape) == 0,
                    0,
                    np.add(1, np.multiply(np.subtract(t.shape, 1), strides)),
                )
            ),
        )
        lo, hi, interior = list_zip(starts, np.subtract(x_shape, real_limits), np.subtract(strides, 1))
    padding = []
    for l, h in zip(lo, hi):
        padding += [l, h]
    padding = tuple(padding)
    res = z.pad(padding)
    assert res.shape == x_shape, f"{res.shape=} {x_shape=}"
    return [res]


flip = Operator.other("flip")
operator_set.register(flip)


@flip.set_method
def args_fixer(self, x, *, dim=None):
    if dim is None:
        dim = tuple(range((x.ndim)))
    elif type(dim) is int:
        dim = (dim,)
    elif type(dim) is list:
        dim = tuple(dim)
    return (x,), dict(dim=dim)


@flip.set_method
def vmap(self, dim_size, vals_in, dims_in, *, dim):
    raise NotImplementedError


@flip.set_method
def jvp(self, primals, tangents, *, dim):
    (x,), (x_dot,) = primals, tangents
    return [x.flip(dim)], [x_dot.flip(dim)]


@flip.set_method
def typecheck(self, x: Typecheckor, *, dim):
    return [Typecheckor(tuple(x.shape), x.dtype)]


@flip.set_method
def T(self, cotangents, x, *, dim):
    (z,) = cotangents
    return [z.flip(dim)]


cat = Operator.other("cat", nary_inputs=True)
operator_set.register(cat)
operator_set.alias(cat, "cat")


@cat.set_method
def args_fixer(self, *xs, dim=0):
    if type(xs) in (tuple, list) and type(xs[0]) in (tuple, list):
        xs = xs[0]
    xs = tuple(xs)
    return xs, dict(dim=dim)


@cat.set_method
def vmap(self, dim_size, vals_in, dims_in, *, dim=0):
    raise NotImplementedError


@cat.set_method
def jvp(self, primals, tangents, *, dim=0):
    return [cat(*primals, dim=dim)], [cat(*tangents, dim=dim)]


@cat.set_method
def typecheck(self, *xs: Typecheckor, dim=0) -> List[Typecheckor]:
    if len(set(x.ndim for x in xs)) != 1:
        msg = "Cannot cat tensors with different numbers of dimensions: got {}."
        raise TypeError(msg.format(", ".join(str(o.shape) for o in xs)))
    if not 0 <= dim < xs[0].ndim:
        msg = "cat dimension out of bounds: dimension {} for shapes {}."
        raise TypeError(msg.format(dim, ", ".join([str(o.shape) for o in xs])))
    shapes = [x.shape[:dim] + x.shape[dim + 1 :] for x in xs]
    if not shapes[:-1] == shapes[1:]:
        msg = (
            "Cannot cat tensors with shapes that differ in dimensions "
            "other than the one being catd: concatenating along "
            "dimension {} for shapes {}."
        )
        shapes = [x.shape for x in xs]
        raise TypeError(msg.format(dim, ", ".join(map(str, shapes))))

    concat_size = sum_py(x.shape[dim] for x in xs)
    ex_shape = xs[0].shape
    return [Typecheckor(ex_shape[:dim] + (concat_size,) + ex_shape[dim + 1 :], xs[0].dtype)]


@cat.set_method
def T(self, cotangents, *xs, dim=0):
    (z,) = cotangents
    x_shapes = [o.aval.shape if type(o) is PrimalProxy else o.shape for o in xs]
    if type(z) is None:
        return [None if type(o) is PrimalProxy else None for o in xs]
    else:  # TODO: replace numpy with pure Python
        limit_points = np.cumsum([shape[dim] for shape in x_shapes]).tolist()
        starts = np.zeros((len(xs), z.ndim), dtype=int).tolist()
        limits = np.tile(z.shape, (len(xs), 1)).tolist()

    for i, s in enumerate(starts[1:]):
        s[dim] = limit_points[:-1][i]
    for i, l in enumerate(limits):
        l[dim] = limit_points[i]

    return [
        z.slice(tuple(start), tuple(limit)) if type(o) is PrimalProxy else None
        for o, start, limit in zip(xs, starts, limits)
    ]


# -----------------------
# InitOps
# -----------------------

full = Operator.init("full")
operator_set.register(full)


@full.set_method
def args_fixer(self, *, shape, fill_value, dtype=Tensor.float32):
    if isinstance(shape, int):
        shape = (shape,)
    elif shape is None:
        shape = ()
    if "float" in dtype.name:
        fill_value = float(fill_value)
    elif "int" in dtype.name:
        fill_value = int(fill_value)
    return (), dict(shape=shape, fill_value=fill_value, dtype=dtype)


@full.set_method
def jvp(self, primals, tangents, *, shape, fill_value, dtype):
    out = self(shape=shape, fill_value=fill_value, dtype=dtype)
    out_jvp = slope.ones_like(out)
    return [out], [out_jvp]


@full.set_method
def T(self, cotangents, *, shape, fill_value, dtype):
    return [None]


@full.set_method
def typecheck(self, *, shape, fill_value, dtype) -> List[Typecheckor]:
    return [Typecheckor(tuple(shape), dtype)]


random_uniform = Operator.init("random_uniform")
rand = random_uniform
operator_set.register(random_uniform)
operator_set.alias(random_uniform, "rand")


@random_uniform.set_method
def args_fixer(self, *, shape=None, dtype=Tensor.float32):
    if isinstance(shape, int):
        shape = (shape,)
    elif shape is None:
        shape = ()
    return (), dict(shape=shape, dtype=dtype)


@random_uniform.set_method
def jvp(self, primals, tangents, *, shape, dtype):
    out = self(shape=shape, dtype=dtype)
    out_jvp = slope.ones_like(out)
    return [out], [out_jvp]


@random_uniform.set_method
def T(self, cotangents, *, shape, dtype):
    return [None]


@random_uniform.set_method
def typecheck(self, *, shape, dtype) -> List[Typecheckor]:
    return [Typecheckor(tuple(shape), dtype)]


random_normal = Operator.init("random_normal")
randn = random_normal
operator_set.register(random_normal)
operator_set.alias(random_normal, "randn")


@random_normal.set_method
def args_fixer(self, *, shape=None, dtype=Tensor.float32):
    if isinstance(shape, int):
        shape = (shape,)
    elif shape is None:
        shape = ()
    return (), dict(shape=shape, dtype=dtype)


@random_normal.set_method
def jvp(self, primals, tangents, *, shape, dtype=Tensor.float32):
    out = self(random_normal, shape, dtype)
    out_jvp = slope.ones_like(out)
    return [out], [out_jvp]


@random_normal.set_method
def T(self, cotangents, *, shape, dtype=Tensor.float32):
    return [None]


@random_normal.set_method
def typecheck(self, *, shape, dtype=Tensor.float32) -> List[Typecheckor]:
    return [Typecheckor(tuple(shape), dtype)]


arange = Operator.init("arange")
operator_set.register(arange)


@arange.set_method
def args_fixer(self, *, start, stop=None, stride=None, dtype=Tensor.int64):
    if stop is None:
        stop = start
        start = 0
    if stride is None:
        stride = 1
    return (), dict(start=start, stop=stop, stride=stride, dtype=dtype)


@arange.set_method
def jvp(self, primals, tangents, *, start, stop, stride, dtype):
    out = self(arange, start, stop, stride, dtype)
    out_jvp = slope.ones_like(out)
    return [out], [out_jvp]


@arange.set_method
def T(self, cotangents, *, start, stop, stride, dtype):
    return [None]


@arange.set_method
def typecheck(self, *, start, stop, stride, dtype) -> List[Typecheckor]:
    return [Typecheckor((((stop - start) * stride),), dtype)]


# -------------------
# Other
# -------------------


matmul = Operator.other("matmul")
operator_set.register(matmul)


@matmul.set_method
def typecheck(self, x, w):
    assert x.dtype == w.dtype
    if x.ndim == w.ndim == 2:
        # Both arguments are 2-D, multiply like conventional matrices
        assert x.shape[-1] == w.shape[-2]
        shape = x.shape[:-1] + (w.shape[-1],)
    elif x.ndim > 2 and w.ndim > 2:
        # Treat as a stack of matrices and broadcast accordingly
        assert x.shape[-1] == w.shape[-2]
        shape = x.shape[:-2] + (x.shape[-2], y.shape[-1])
    elif x.ndim == 1 and w.ndim > 1:
        # Promote the 1-D argument to a matrix by prepending a 1
        assert x.shape[0] == w.shape[-2]
        shape = (1,) + (w.shape[-2], w.shape[-1])
    elif x.ndim > 1 and w.ndim == 1:
        # Promote the 1-D argument to a matrix by appending a 1
        assert x.shape[-1] == w.shape[0]
        shape = x.shape[:-1] + (w.shape[0],)
    else:
        raise ValueError("Invalid dimensions for matmul")

    return [Typecheckor(shape, x.dtype)]


@matmul.set_method
def jvp(self, primals, tangents):
    (x, w), (x_dot, w_dot) = primals, tangents
    return [x @ w], [(x_dot @ w) + (x @ w_dot)]


@matmul.set_method
def T(self, cotangents, x, w):
    (grad_L_y,) = cotangents
    assert (type(x) is PrimalProxy) ^ (type(w) is PrimalProxy)
    if type(x) is PrimalProxy:
        return [grad_L_y @ w.transpose(-1, -2), None]
    elif type(w) is PrimalProxy:
        return [None, x.transpose(-1, -2) @ grad_L_y]


conv = Operator.other("conv")
operator_set.register(conv)


@conv.set_method
def args_fixer(self, x, w, *, groups=1, stride=1, dilation=1, padding=0):
    def make_pair(x: Union[int, Tuple[int, ...]], cnt=2) -> Tuple[int, ...]:
        return (x,) * cnt if isinstance(x, int) else x

    (bs, cin_), (cout, cin), HW = x.shape[:2], w.shape[:2], w.shape[2:]
    assert groups * cin == cin_ and len(x.shape) == len(
        w.shape
    ), f"Input dim shape {x.shape} does not match the shape of the ws {w.shape}. ({groups*cin} vs. {cin_})"
    if isinstance(padding, (tuple, list)):
        assert len(padding) == 2 * len(HW) or len(padding) == len(
            HW
        ), f"Expected padding of length {2*len(HW)} or {len(HW)}, but got {len(padding)} for tensor of shape {x.shape}"
    padding = (
        [padding] * 2 * len(HW)
        if isinstance(padding, int)
        else (padding if len(padding) == 2 * len(HW) else [p for p in padding for _ in range(2)][::-1])
    )
    padding = tuple(padding)
    if isinstance(stride, int):
        stride = make_pair(stride, len(HW))
    if isinstance(dilation, int):
        dilation = make_pair(dilation, len(HW))
    assert len(HW) == len(stride) and len(HW) == len(
        dilation
    ), f"stride/dilation mismatch kernel:{HW} stride:{stride} dilation:{dilation}"
    return (x, w), dict(groups=groups, stride=stride, dilation=dilation, padding=padding)


@conv.set_method
def typecheck(self, x, w, *, groups, stride, dilation, padding):
    assert x.dtype == w.dtype
    x_shape = x.shape
    w_shape = w.shape
    # Calculate output spatial dimensions
    if isinstance(padding, tuple):
        # TODO
        padding_h = padding_w = padding[0]
    else:
        padding_h = padding_w = padding

    if isinstance(stride, tuple):
        # TODO
        stride_h = stride_w = stride[0]
    else:
        stride_h = stride_w = stride

    if isinstance(dilation, tuple):
        # TODO
        dilation_h = dilation_w = dilation[0]
    else:
        dilation_h = dilation_w = dilation
    out_h = ((x_shape[2] + 2 * padding_h - dilation_h * (w_shape[2] - 1) - 1) // stride_h) + 1
    out_w = ((x_shape[3] + 2 * padding_w - dilation_w * (w_shape[3] - 1) - 1) // stride_w) + 1

    # Calculate output shape
    out_channels = w_shape[0]
    out_shape = (x_shape[0], out_channels, out_h, out_w)

    return [Typecheckor(out_shape, x.dtype)]


@conv.set_method
def jvp(self, primals, tangents, *, groups, stride, dilation, padding):
    (x, w), (x_dot, w_dot) = primals, tangents
    y = x.conv(w, groups=groups, stride=stride, dilation=dilation, padding=padding)
    y_dot1 = x_dot.conv(w, groups=groups, stride=stride, dilation=dilation, padding=padding)
    y_dot2 = x.conv(w_dot, groups=groups, stride=stride, dilation=dilation, padding=padding)

    return [y], [y_dot1 + y_dot2]


# https://deeplearning.cs.cmu.edu/F21/document/recitation/Recitation5/CNN_Backprop_Recitation_5_F21.pdf
# x_grad = F.conv_transpose2d(y.grad, w, stride=stride, padding=padding, dilation=dilation, output_padding=stride-padding)
# assert torch.allclose(x_grad, x.grad)
# w_grad = F.conv2d(x.transpose(0,1), y.grad.transpose(0,1), stride=dilation, padding=padding, dilation=stride, groups=groups).transpose(0,1)
# w_grad = w_grad[:,:,:w.size(2),:w.size(3)]
# assert torch.allclose(w_grad, w.grad)


@conv.set_method
def T(self, cotangents, x, w, *, groups, stride, dilation, padding):
    (grad_L_y,) = cotangents
    if type(x) is PrimalProxy:
        grad_L_x = grad_L_y.conv_transpose(
            w, groups=groups, stride=stride, dilation=dilation, padding=padding, output_padding=stride[0] - dilation[0]
        )
        assert grad_L_x.shape == x.shape
        return [grad_L_x, None]
    elif type(w) is PrimalProxy:
        grad_L_w = (
            x.transpose(0, 1)
            .conv(grad_L_y.transpose(0, 1), groups=groups, stride=dilation, dilation=stride, padding=padding)
            .transpose(0, 1)
        )
        if grad_L_w.shape != w.shape:
            starts = (0,) * len(grad_L_w.shape)
            ends = (grad_L_w.shape[0], grad_L_w.shape[1]) + w.shape[2:]
            grad_L_w = grad_L_w.slice(starts, ends)
        assert grad_L_w.shape == w.shape
        return [None, grad_L_w]


conv_transpose = Operator.other("conv_transpose")
operator_set.register(conv_transpose)


@conv_transpose.set_method
def args_fixer(self, x, w, *, groups=1, stride=1, dilation=1, padding=0, output_padding=0):
    def make_pair(x: Union[int, Tuple[int, ...]], cnt=2) -> Tuple[int, ...]:
        return (x,) * cnt if isinstance(x, int) else x

    (bs, cin_), (cin, cout), HW = x.shape[:2], w.shape[:2], w.shape[2:]
    assert groups * cin == cin_ and len(x.shape) == len(
        w.shape
    ), f"Input dim shape {x.shape} does not match the shape of the ws {w.shape}. ({groups*cin} vs. {cin_})"
    if isinstance(padding, (tuple, list)):
        assert len(padding) == 2 * len(HW) or len(padding) == len(
            HW
        ), f"Expected padding of length {2*len(HW)} or {len(HW)}, but got {len(padding)} for tensor of shape {x.shape}"

    if isinstance(output_padding, (tuple, list)):
        assert len(output_padding) == 2 * len(HW) or len(output_padding) == len(
            HW
        ), f"Expected padding of length {2*len(HW)} or {len(HW)}, but got {len(output_padding)} for tensor of shape {x.shape}"
    padding = tuple(
        [padding] * 2 * len(HW)
        if isinstance(padding, int)
        else (padding if len(padding) == 2 * len(HW) else [p for p in padding for _ in range(2)][::-1])
    )
    output_padding = tuple(
        [output_padding] * 2 * len(HW)
        if isinstance(output_padding, int)
        else (
            output_padding
            if len(output_padding) == 2 * len(HW)
            else [p for p in output_padding for _ in range(2)][::-1]
        )
    )
    if isinstance(stride, int):
        stride = make_pair(stride, len(HW))
    if isinstance(dilation, int):
        dilation = make_pair(dilation, len(HW))
    assert len(HW) == len(stride) and len(HW) == len(
        dilation
    ), f"stride/dilation mismatch kernel:{HW} stride:{stride} dilation:{dilation}"
    return (x, w), dict(groups=groups, stride=stride, dilation=dilation, padding=padding, output_padding=output_padding)


@conv_transpose.set_method
def typecheck(self, x, w, *, groups, stride, dilation, padding, output_padding):
    assert x.dtype == w.dtype
    x_shape = x.shape
    w_shape = w.shape
    (bs, cin_), (cin, cout), HW = x_shape[:2], w_shape[:2], w_shape[2:]
    assert (
        groups * cin == cin_
    ), f"Input dim shape {x_shape} does not match the shape of the ws {w_shape}. ({groups*cin} vs. {cin_})"

    if isinstance(padding, (tuple, list)):
        assert len(padding) == 2 * len(HW) or len(padding) == len(
            HW
        ), f"Expected padding of length {2*len(HW)} or {len(HW)}, but got {len(padding)} for tensor of shape {x_shape}"

    if isinstance(output_padding, (tuple, list)):
        assert len(output_padding) == 2 * len(HW) or len(output_padding) == len(
            HW
        ), f"Expected padding of length {2*len(HW)} or {len(HW)}, but got {len(output_padding)} for tensor of shape {x_shape}"

    if isinstance(stride, int):
        stride = [stride] * len(HW)

    if isinstance(dilation, int):
        dilation = [dilation] * len(HW)

    assert len(HW) == len(stride) and len(HW) == len(
        dilation
    ), f"stride/dilation mismatch kernel:{HW} stride:{stride} dilation:{dilation}"

    # Calculate output shape
    result_shape = tuple(
        [bs, cout]
        + [
            (s - 1) * stride[i]
            - (padding[i * 2] + padding[i * 2 + 1])
            + dilation[i] * (HW[i] - 1)
            + (output_padding[i * 2] + output_padding[i * 2 + 1]) // 2
            + 1
            for i, s in enumerate(x_shape[2:])
        ]
    )
    return [Typecheckor(result_shape, x.dtype)]


@conv_transpose.set_method
def jvp(self, primals, tangents, *, groups, stride, dilation, padding, output_padding):
    (x, w), (x_dot, w_dot) = primals, tangents
    y = x.conv_transpose(w)
    y_dot1 = x_dot.conv_transpose(
        w, groups=groups, stride=stride, dilation=dilation, padding=padding, output_padding=output_padding
    )
    y_dot2 = x.conv_transpose(
        w_dot, groups=groups, stride=stride, dilation=dilation, padding=padding, output_padding=output_padding
    )
    print(y.shape)

    return [y], [y_dot1 + y_dot2]


@conv_transpose.set_method
def T(self, cotangents, x, w, *, groups, stride, dilation, padding, output_padding):
    (grad_L_y,) = cotangents
    if type(x) is PrimalProxy:
        grad_L_x = grad_L_y.conv(w, groups=groups, stride=stride, dilation=dilation, padding=padding)
        return [grad_L_x, None]
    elif type(w) is PrimalProxy:
        x_T = x.transpose(0, 1)
        grad_L_y_T = grad_L_y.transpose(0, 1)
        grad_L_w = grad_L_y_T.conv(x_T, groups=groups, stride=stride, dilation=dilation, padding=padding)
        return [None, grad_L_w]


# --------------
# Compiler
# --------------

#

compile_py = compile
compiler = Compiler(name="iree", default_dtype=Tensor.float32, default_device=slope.SLOPE_DEVICE)
compiler.set_dtype_map(
    {
        Tensor.float32: np.dtypes.Float32DType(),
        Tensor.uint8: np.dtypes.UInt8DType(),
        Tensor.int8: np.dtypes.Int8DType(),
        Tensor.bool: np.dtypes.BoolDType(),
        Tensor.int32: np.dtypes.Int32DType(),
        Tensor.int64: np.dtypes.Float64DType(),
        Tensor.float16: np.dtypes.Float16DType(),
    }
)

@compiler.set_method
def from_numpy(self, val, dtype=compiler.default_dtype_value, device=compiler.default_device):
    # device_type, device_id = device.split(":") if ":" in device else (device, 0)
    np_val = np.array(val, dtype=dtype.numpy)
    iree_device = iree.runtime.get_device("local-task")
    val = iree.runtime.asdevicearray(iree_device, np_val)
    return Tensor(TensorBuffer(val))


@compiler.set_method
def numpy_of(self, tensor):
    return tensor.buf.val.to_host()


@compiler.set_method
def device_of(self, tensor):
    return tensor.buf.val.device_name()


@compiler.set_method
def shape_of(self, tensor):
    return tuple(tensor.buf.val.shape)


@compiler.set_method
def dtype_of(self, tensor):
    return self.dtype_map_inv[tensor.buf.val.dtype]


@compiler.set_method
def export(self, jit_object: slope.core.JitObject, output_path, *args, **kwargs):
    code = jit_object.code
    model = onnx.parser.parse_model(code)
    os.makedirs(output_path, exist_ok=True)
    in_binders = jit_object.codegen_out["in_binders"]
    outs = jit_object.codegen_out["outs"]
    num_consts = jit_object.program.num_consts
    for i in range(num_consts):
        const_array = in_binders[i]["type"].numpy()
        const_name = in_binders[i]["name"]
        const = onnx.numpy_helper.from_array(const_array, name=const_name)
        model.graph.initializer.append(const)
        # TODO: try if need these
        # const_tensor = next(t for t in model.graph.input if t.name == const_name)
        # const_tensor.type.tensor_type.shape.dim[0].dim_param = const_name
        # const_tensor.type.tensor_type.elem_type = onnx.TensorProto.FLOAT

    onnx.save(model.SerializeToString(), os.path.join(output_path, "model.onnx"))
    input_arg_names = [ib["name"] for ib in in_binders[num_consts:]]
    input_arg_names_str = ", ".join(input_arg_names)
    outs_names = [out["name"] for out in outs]

    test_input_code = ""
    for i in range(num_consts, len(in_binders)):
        input_name = in_binders[i]["name"]
        input_shape = in_binders[i]["type"].shape
        dtype = in_binders[i]["type"].dtype
        input_dtype = ("np." + dtype.numpy.__name__) if dtype is not Tensor.bool else "bool"
        test_input_code += f"""    {input_name} = np.ones({input_shape}, dtype={input_dtype})\n"""

    module_path = os.path.join(output_path, "__init__.py")
    module_code = f"""import onnxruntime
import os
import numpy as np

root_path = os.path.dirname(__file__)
model_path = os.path.join(root_path, "model.onnx")
session = onnxruntime.InferenceSession(model_path, providers=["CPUExecutionProvider"])
input_arg_names = {input_arg_names}
out_names = {outs_names}

def run(*args, **kwargs):
    if len(args) > 0:
        for a_name, a in zip(input_arg_names, args):
            assert a_name not in kwargs.keys()
            kwargs[a_name] = a
    outputs = session.run(out_names, kwargs)
    return outputs
if __name__ == "__main__":
{test_input_code}
    print("inputs:")
    for inp_name, inp in zip(input_arg_names, ({input_arg_names_str})):
        print(f"{{inp_name}} = ")
        print(inp)
        print(f"dtype: {{inp.dtype}}")
        print(f"shape: {{inp.shape}}")
        print()

    outs = run({input_arg_names_str})

    print("outputs:")
    for out_name, out in zip(out_names, outs):
        print(f"{{out_name}} = ")
        print(out)
        print(f"dtype: {{out.dtype}}")
        print(f"shape: {{out.shape}}")
        print()
"""
    with open(module_path, "w") as f:
        f.write(module_code)
        slope.dblog(module_code, enable=slope.LOG_JIT)


@compiler.set_method
def compile(self, codegen_out):
    code_lines = codegen_out["code_lines"]
    code = "\n".join(code_lines)
    instance = iree.runtime.VmInstance()
    iree_device = iree.runtime.get_device("local-task")
    hal_module = iree.runtime.create_hal_module(instance, iree_device)
    # iree.compiler.core.DEFAULT_TESTING_BACKENDS
    binary = iree.compiler.compile_str(code, target_backends='llvm-cpu',
    )
    m = iree.runtime.VmModule.from_flatbuffer(instance, binary)
    context = iree.runtime.VmContext(instance, modules=[hal_module, m])
    f = m.lookup_function("main")
    finv = iree.runtime.FunctionInvoker(context, iree_device, f, tracer=None)
    return finv, code


@compiler.set_method
def codegen(self, program, args, *, fn_name: str = "main", fn_defs=dict()) -> List[Any]:
    def typecheckor_mlir_format(typecheckor):
        xshape = f"{'x'.join((repr(i) for i in typecheckor.shape))}"
        xdtype = typecheckor.dtype.short_name
        return f"tensor<{xshape}x{xdtype}>"
    if fn_name == "main":
        assert not hasattr(self, "fn_count")
        self.fn_count = 0

    def indent(code, amount):
        spaces = " " * (len(code) - len(code.lstrip()))
        spaces += " " * amount
        return "\n".join([spaces + line for line in code.strip().split("\n")])

    # codegen is recursive if jit-of-jit happens
    backend: Dict[slope.Var, Any] = {}
    il1 = 4  # indent length
    body_code_lines = []

    for inb in program.in_binders:
        prefix = "x" if type(inb.aval) is Typecheckor else "c"
        idx = sum_py([1 if v["name"][0] == prefix else 0 for v in backend.values()])
        backend[inb] = dict(name=f"{prefix}{idx}", type=inb.aval)

    for instruction in program.instructions:
        if len(instruction.out_binders) == 0:  # skip codegen for function returns nothing
            continue
        in_vals = list_map(lambda x: backend[x]["name"], instruction.inputs)
        for outb in instruction.out_binders:
            prefix = "y" if outb in program.outs else "z"
            idx = sum_py([1 if v["name"][0] == prefix else 0 for v in backend.values()])
            backend[outb] = dict(name=f"{prefix}{idx}", type=outb.aval)

        out_vals = list_map(lambda z: backend[z]["name"], instruction.out_binders)
        if instruction.op.op_type is slope.core.OperatorType.Meta:
            lhs = ", ".join(out_vals)
            rhs, fn_defs = self.impls[instruction.op](program, args, instruction, in_vals, fn_defs)
            impl_code = f"{lhs} = {rhs}"
        else:
            impl_code = self.impls[instruction.op](*in_vals, **instruction.params)
            if len(out_vals) == 1:
                impl_code = impl_code.replace("ret", out_vals[0])
            else:
                raise NotImplementedError
        for impl_code_line in impl_code.split("\n"):  # handle multi-line code
            body_code_lines += [indent(impl_code_line, il1)]

    # inb_consts = [v for v in backend.values() if "c" in v["name"]]
    # const_type_strs = [f"{self.dtype_map[c['type'].dtype]}[{repr(c['type'].shape)[1:-1]}] {c['name']}" for c in inb_consts]

    in_binders = list_map(lambda x: backend[x], program.in_binders)
    arg_type_strs = [
        f"{self.dtype_map[i['type'].dtype]}[{repr(list(i['type'].shape))[1:-1]}] {i['name']}" for i in in_binders
    ]
    fn_args_str = ", ".join(arg_type_strs)

    outs = list_map(lambda x: backend[x], program.outs)  # TODO: input that is output should has identity op
    out_type_strs = [
        f"{self.dtype_map[o['type'].dtype]}[{repr(list(o['type'].shape))[1:-1]}] {o['name']}" for o in outs
    ]
    out_type_str = ", ".join(out_type_strs)

    head_code_lines = []
    head_code_lines += [f"func.func @{fn_name} ({fn_args_str}) -> ({out_type_str})"]
    model_code_lines = head_code_lines + ["{"] + body_code_lines + ["}"]

    functions_head_def = '<domain: "slope",  opset_import: ["" : 18, "slope":1]>'
    functions_code_lines = []
    for op, fn_def_code_lines in fn_defs.items():
        functions_code_lines += [functions_head_def] + fn_def_code_lines
    code_lines = model_code_lines + functions_code_lines
    slope.dblog(
        f"\n---- {program.name} codegen:\n\n" + "\n".join(code_lines) + "\n\n===============\n", enable=slope.LOG_JIT
    )
    breakpoint()

    if fn_name == "main":
        del self.fn_count
    assert len(outs) == len(program.outs)
    return dict(code_lines=code_lines, fn_defs=fn_defs, in_binders=in_binders, outs=outs)
'''
func.func @main(
  %image: tensor<28x28xf32>,
  %weights: tensor<784x10xf32>,
  %bias: tensor<1x10xf32>
) -> tensor<1x10xf32> {
  %0 = "stablehlo.reshape"(%image) : (tensor<28x28xf32>) -> tensor<1x784xf32>
  %1 = "stablehlo.dot"(%0, %weights) : (tensor<1x784xf32>, tensor<784x10xf32>) -> tensor<1x10xf32>
  %2 = "stablehlo.add"(%1, %bias) : (tensor<1x10xf32>, tensor<1x10xf32>) -> tensor<1x10xf32>
  %3 = "stablehlo.constant"() { value = dense<0.0> : tensor<1x10xf32> } : () -> tensor<1x10xf32>
  %4 = "stablehlo.maximum"(%2, %3) : (tensor<1x10xf32>, tensor<1x10xf32>) -> tensor<1x10xf32>
  "func.return"(%4): (tensor<1x10xf32>) -> ()
}
'''


### Operator Impls


compiler.set_impl(operator_set.cast)(lambda self, x, *, dtype: f"ret = Cast<to={onnx_dtype_enum_map[dtype]}>({x})")
compiler.set_impl(operator_set.stop_gradient)(lambda self, x: f"ret = Identity({x})")
compiler.set_impl(operator_set.neg)(lambda self, x: f"ret =  Neg({x})")
compiler.set_impl(operator_set.sqrt)(lambda self, x: f"ret = Sqrt({x})")
compiler.set_impl(operator_set.exp)(lambda self, x: f"ret = Exp({x})")
compiler.set_impl(operator_set.log)(lambda self, x: f"ret = Log({x})")
compiler.set_impl(operator_set.sin)(lambda self, x: f"ret = Sin({x})")
compiler.set_impl(operator_set.add)(lambda self, x, w: f"ret = Add({x}, {w})")
compiler.set_impl(operator_set.sub)(lambda self, x, w: f"ret = Sub({x}, {w})")
compiler.set_impl(operator_set.mul)(lambda self, x, w: f"ret = Mul({x}, {w})")
compiler.set_impl(operator_set.div)(lambda self, x, w: f"ret = Div({x}, {w})")
compiler.set_impl(operator_set.pow)(lambda self, x, w: f"ret = Pow({x}, {w})")
compiler.set_impl(operator_set.invert)(lambda self, x: f"ret = Not({x})")
compiler.set_impl(operator_set.equal)(lambda self, x, w: f"ret = Equal({x}, {w})")
compiler.set_impl(operator_set.maximum)(lambda self, x, w: f"ret = Max({x}, {w})")
compiler.set_impl(operator_set.matmul)(lambda self, x, w: f"ret = MatMul({x}, {w})")


@compiler.set_impl(operator_set.sum)
def sum_impl(self, x, *, dim, keepdim):
    return f"""
ret_dim = Constant <value = int64[{len(dim)}]  {{ {repr(dim)[1:(-1 if len(dim) > 1 else -2)]} }} >()
ret = ReduceSum<keepdims={int(keepdim)}> ({x}, ret_dim)
"""


@compiler.set_impl(operator_set.max)
def max_impl(self, x, *, dim, keepdim):
    return f"""
ret_dim = Constant <value = int64[{len(dim)}]  {{ {repr(dim)[1:(-1 if len(dim) > 1 else -2)]} }} >()
ret = ReduceMax<keepdims={int(keepdim)}> ({x}, ret_dim)
"""


@compiler.set_impl(operator_set.arange)
def arange_impl(self, *, start, stop, stride, dtype):
    return f"""
ret_start = Constant <value_int = {start}> ()
ret_limit = Constant <value_int = {stop}> ()
ret_delta = Constant <value_int = {stride}> ()
{f'''
ret_range = Range(ret_start, ret_limit, ret_delta)
ret = Cast<to={onnx_dtype_enum_map[dtype]}>(ret_range)
''' if dtype is not Tensor.int64 else
f'''
ret = Range(ret_start, ret_limit, ret_delta)
'''
}
"""


# ret_range = Range(ret_start, ret_limit, ret_delta)
# {f'ret = Cast<to={onnx_dtype_enum_map[dtype]}>(ret_range)'}
@compiler.set_impl(operator_set.full)
def full_impl(self, *, shape, fill_value, dtype):
    if dtype is not Tensor.bool:
        if "float" in dtype.name:
            fill_value = float(fill_value)
        elif "int" in dtype.name:
            fill_value = int(fill_value)

        if len(shape) > 0:
            return f"""
ret_fill_value = Constant < value = {self.dtype_map[dtype]}[1] {{ {fill_value} }}>()
ret_shape = Constant <value = int64[{len(shape)}] {{ {repr(list(shape))[1:-1]} }} >()
ret = Expand (ret_fill_value, ret_shape)
"""
        else:  # scalar case
            return f"""
ret_fill_value = Constant < value = {self.dtype_map[dtype]}[1] {{ {fill_value} }}>()
ret_squeeze_dim = Constant <value = int64[1] {{0}}> ()
ret = Squeeze (ret_fill_value, ret_squeeze_dim)
"""
    else:
        if len(shape) > 0:
            return f"""
ret_fill_value = Constant < value = int64[1] {{ {int(fill_value)} }}>()
ret_shape = Constant <value = int64[{len(shape)}] {{ {repr(list(shape))[1:-1]} }} >()
ret_expand = Expand (ret_fill_value, ret_shape)
ret = Cast<to={onnx_dtype_enum_map[dtype]}>(ret_expand)
"""
        else:  # scalar case
            return f"""
ret_fill_value = Constant < value = int64[1] {{ {int(fill_value)} }}>()
ret_squeeze_dim = Constant <value = int64[1] {{0}}> ()
ret_squeeze = Squeeze (ret_fill_value, ret_squeeze_dim)
ret = Cast<to={onnx_dtype_enum_map[dtype]}>(ret_squeeze)
"""


@compiler.set_impl(operator_set.random_uniform)
def random_uniform_impl(self, *, shape, dtype):
    if len(shape) > 0:
        return f"""
ret = RandomUniform<dtype={onnx_dtype_enum_map[dtype]},shape={repr(list(shape))}>()
"""
    else:  # scalar case
        return f"""
ret_rand = RandomUniform<dtype={onnx_dtype_enum_map[dtype]}, shape=[1]>()
ret_squeeze_dim = Constant <value = int64[1] {{0}}> ()
ret = Squeeze (ret_rand, ret_squeeze_dim)
"""


@compiler.set_impl(operator_set.random_normal)
def random_normal_impl(self, *, shape, dtype):
    if len(shape) > 0:
        return f"""
ret = RandomNormal<dtype={onnx_dtype_enum_map[dtype]}, shape={repr(list(shape))}>()
"""
    else:  # scalar case
        return f"""
ret_randn = RandomNormal<dtype={onnx_dtype_enum_map[dtype]}, shape=[1]>()
ret_squeeze_dim = Constant <value = int64[1] {{0}}> ()
ret = Squeeze (ret_randn, ret_squeeze_dim)
"""


@compiler.set_impl(operator_set.expand)
def expand_impl(self, x, *, shape):
    return f"""
ret_shape = Constant <value = int64[{len(shape)}] {{ {repr(list(shape))[1:-1]} }} >()
ret = Expand ({x}, ret_shape)
"""


@compiler.set_impl(operator_set.reshape)
def reshape_impl(self, x, *, shape):
    if len(shape) > 0:
        return f"""
ret_shape = Constant <value = int64[{len(shape)}] {{ {repr(list(shape))[1:-1]} }} >()
ret = Reshape({x}, ret_shape)
"""
    else:  # scalar case
        f"""
        ret_shape = Constant <value = int64[1] {1} >()
        ret_reshape = Reshape({x}, ret_shape)
        ret_squeeze_dim = Constant <value = int64[1] {{0}}> ()
        ret = Squeeze (ret_reshape, ret_squeeze_dim)"""


@compiler.set_impl(operator_set.pad)
def pad_impl(self, x, *, padding, mode, value):
    padding = padding[0::2] + padding[1::2]
    return f"""
ret_padding = Constant <value = int64[{len(padding)}]  {{ {repr(list(padding))[1:-1]} }}>()
ret = Pad({x}, ret_padding)
"""


#     return f"""
# ret_padding = Constant <value = int64[{len(padding)}]  {{ {repr(list(padding))[1:-1]} }}>()
# ret_constant_value =  Constant <value = {value} >()
# ret = Pad({x}, ret_padding, ret_constant_value)
# """


@compiler.set_impl(operator_set.slice)
def slice_impl(self, x, *, starts, limits, strides):
    return f"""
ret_starts = Constant <value = int64[{len(starts)}]  {{ {repr(list(starts))[1:-1]} }}>()
ret_ends = Constant <value = int64[{len(limits)}]  {{ {repr(list(limits))[1:-1]} }}>()
ret_dim = Constant <value = int64[{len(strides)}]  {{ {repr(list(range(len(starts))))[1:-1]} }}>()
ret_steps = Constant <value = int64[{len(strides)}]  {{ {repr(list(strides))[1:-1]} }}>()
ret = Slice({x}, ret_starts, ret_ends, ret_dim, ret_steps)
"""


@compiler.set_impl(operator_set.cat)
def cat_impl(self, *xs, dim):
    return f"ret = Concat< axis={dim}>({','.join(xs)})"


@compiler.set_impl(operator_set.permute)
def permute_impl(self, x, *, perm):
    return f"ret = Transpose<perm={repr(list(perm))}>({x})"


@compiler.set_impl(operator_set.flip)
def flip_impl(self, x, *, dim):
    return f"""
ret_starts = Constant <value = int64[{len(dim)}] {{ {", ".join(["0"] * len(dim))} }}>()
ret_ends = Constant <value = int64[{len(dim)}]  {{ {", ".join(["-1"] * len(dim))} }}>()
ret_dim = Constant <value = int64[{len(dim)}]  {{ {repr(list(dim))[1:-1]} }}>()
ret_steps = Constant <value = int64[{len(dim)}] {{ {", ".join(["-1"] * len(dim))} }}>()
ret = Slice({x}, ret_starts, ret_ends, ret_dim, ret_steps)
"""


@compiler.set_impl(operator_set.conv)
def conv_impl(self, x, w, *, groups, stride, dilation, padding):
    dilations_attr = f"dilations=[{repr(list(dilation))[1:-1]}]"
    pads_attr = f"pads=[{repr(list(padding))[1:-1]}]"
    strides_attr = f"strides=[{repr(list(stride))[1:-1]}]"
    group_attr = f"group={groups}"
    return f"""ret = Conv<{dilations_attr}, {pads_attr}, {strides_attr}, {group_attr}>({x}, {w})"""


@compiler.set_impl(operator_set.conv_transpose)
def conv_transpose_impl(self, x, w, *, groups, stride, dilation, padding, output_padding):
    dilations_attr = f"dilations=[{repr(list(dilation))[1:-1]}]"
    pads_attr = f"pads=[{repr(list(padding))[1:-1]}]"
    output_padding_attr = f"output_padding=[{repr(list(output_padding))[1:-1]}]"
    strides_attr = f"strides=[{repr(list(stride))[1:-1]}]"
    group_attr = f"group={groups}"
    return f"""ret = ConvTranspose<{dilations_attr}, {group_attr}, {output_padding_attr}, {pads_attr}, {strides_attr}>({x}, {w})"""


@compiler.set_impl(slope.core.jit_op)
def jit_op_impl(self, program, args, instruction, in_vals, fn_defs):
    jit_program = instruction.params["program"]
    jit_name = f"{program.name}"
    jit_codegen_out = self.codegen(
        jit_program,
        args,
        fn_name=jit_name,
        fn_defs=fn_defs,
    )
    assert jit_name not in fn_defs.keys()
    fn_defs[jit_name] = jit_codegen_out["code_lines"]
    fn_defs = {**fn_defs, **jit_codegen_out["fn_defs"]}
    args_str = ", ".join(in_vals)
    rhs = f"slope.{jit_name}({args_str})"
    return rhs, fn_defs


@compiler.set_impl(slope.core.procedure_op)
def procedure_op_impl(self, program, args, instruction, in_vals, fn_defs):
    proc_program = instruction.params["program"]
    proc_name = f"{proc_program.name}_{self.fn_count}"
    self.fn_count += 1
    proc_codegen_out = self.codegen(
        proc_program,
        args,
        fn_name=proc_name,
        fn_defs=fn_defs,
    )
    fn_defs[proc_name] = proc_codegen_out["code_lines"]
    fn_defs = {**fn_defs, **proc_codegen_out["fn_defs"]}
    args_str = ", ".join(in_vals)
    rhs = f"slope.{proc_name}({args_str})"
    return rhs, fn_defs


procedure_set = ProcedureSet()


@procedure_set.register(inline=True)
def zeros(*args, **kwargs):
    dtype = kwargs.get("dtype", slope.SLOPE_DTYPE)
    if kwargs.get("shape", None) is None:
        shape = args[0] if isinstance(args[0], (tuple, list)) else args
        assert all(i >= 0 for i in shape)
    return slope.full(shape, 0.0, dtype)


@procedure_set.register(inline=True)
def ones(*args, **kwargs):
    dtype = kwargs.get("dtype", slope.SLOPE_DTYPE)
    if kwargs.get("shape", None) is None:
        shape = args[0] if isinstance(args[0], (tuple, list)) else args
        assert all(i >= 0 for i in shape)
    return slope.full(shape=shape, fill_value=1.0, dtype=dtype)


@procedure_set.register(static_argnames="fill_value")
def full_like(y, fill_value):
    return slope.full(shape=y.shape, fill_value=fill_value, dtype=y.dtype)


@procedure_set.register()
def zeros_like(y):
    return full_like(y, 0.0)


@procedure_set.register()
def ones_like(y):
    return full_like(y, 1.0)


@procedure_set.register()
def where(x, trueval, falseval):
    cond = x != 0.0
    if not isinstance(trueval, Tensor):
        trueval = slope.full((), trueval)
    if not isinstance(falseval, Tensor):
        falseval = slope.full((), falseval)
    cond = cond.cast(trueval.dtype)
    return cond * trueval + (1.0 - cond) * falseval


@procedure_set.register(static_argnames="dim keepdim")
def mean(x, dim=None, keepdim=False):
    out = x.sum(dim=dim, keepdim=keepdim)
    return out * (math.prod(out.shape) / math.prod(x.shape))


@procedure_set.register()
def rsqrt(x):
    return (slope.ones_like(x) / x).sqrt()


@procedure_set.register()
def cos(x):
    return ((math.pi / 2) - x).sin()


@procedure_set.register()
def tan(x):
    return x.sin() / x.cos()


@procedure_set.register()
def not_equal(x, w):
    return ~(x.equal(w))


@procedure_set.register()
def greater_equal(x, w):
    return x.maximum(w).equal(w)


@procedure_set.register()
def less_equal(x, w):
    return x.minimum(w).equal(w)


@procedure_set.register()
def greater(x, w):
    return 1.0 - (x <= w)


@procedure_set.register()
def less(x, w):
    return 1.0 - (x >= w)


@procedure_set.register()
def minimum(x, w):
    return -x.maximum(-x, -w)


@procedure_set.register(static_argnames="dim keepdim")
def min(x, dim=None, keepdim=False):
    return -((-x).max(x, dim, keepdim))


@procedure_set.register(static_argnames="dim keepdim")
def argmax(x, dim=None, keepdim=False):
    if dim is None:
        idx = (x == x.max(dim)) * slope.arange(
            math.prod(x.shape) - 1,
            -1,
            -1,
            dtype=slope.int32,
        ).reshape(x.shape)
        return math.prod(x.shape) - idx.max() - 1
    dim = dim + len(x.shape) if dim < 0 else dim
    m = (x == x.max(dim=dim, keepdim=True)).cast(slope.int32)
    idx = m * slope.arange(x.shape[dim] - 1, -1, -1, dtype=slope.int32).reshape(
        (x.shape[dim], *[1] * (x.ndim - dim - 1))
    )
    ret = x.shape[dim] - idx.max(dim=dim, keepdim=keepdim) - 1
    return ret


@procedure_set.register(static_argnames="dim keepdim")
def argmin(x, dim=None, keepdim=False):
    return (-x).argmax(dim=dim, keepdim=keepdim)


@procedure_set.register()
def log2(x):
    return x.log() / math.log(2)


@procedure_set.register()
@staticmethod
def _tri(r: int, c: int, k: int = 0, **kwargs) -> Tensor:
    return slope.arange(r, **kwargs).unsqueeze(1).expand(r, c) <= Tensor.arange(-k, c - k, **kwargs).unsqueeze(
        0
    ).expand(r, c)


@procedure_set.register()
def triu(self, k: int = 0) -> Tensor:
    return slope._tri(self.shape[-2], self.shape[-1], k=k, dtype=self.dtype, device=self.device).where(
        self, slope.zeros_like(self)
    )


@procedure_set.register()
def tril(self, k: int = 0) -> Tensor:
    return slope._tri(self.shape[-2], self.shape[-1], k=k + 1, dtype=self.dtype, device=self.device).where(
        slope.zeros_like(self), self
    )


@procedure_set.register()
def trunc(self: Tensor) -> Tensor:
    return self.cast(slope.int32).cast(self.dtype)


@procedure_set.register()
def ceil(self: Tensor) -> Tensor:
    return (self > (b := self.trunc())).where(b + 1, b)


@procedure_set.register()
def floor(self: Tensor) -> Tensor:
    return (self < (b := self.trunc())).where(b - 1, b)


@procedure_set.register()
def square(self):
    return self * self


@procedure_set.register()
def clip(self, min_, max_):
    return self.maximum(min_).minimum(max_)


@procedure_set.register()
def abs(self):
    return self.relu() + (-self).relu()


@procedure_set.register()
def sign(self):
    return self / (self.abs() + 1e-10)


@procedure_set.register()
def reciprocal(self):
    return 1.0 / self


@procedure_set.register()
def matmul(x, w):
    x = x.reshape((*x.shape[0:-1], 1, x.shape[-1]))
    w = w.reshape((*w.shape[0:-2], 1, w.shape[-2], w.shape[-1])).T()
    return (x * w).sum(-1).reshape((*x.shape[0:-2], -1))


@procedure_set.register()
def T(x):
    perm = list(range(x.ndim))
    perm[-2], perm[-1] = perm[-1], perm[-2]
    return x.permute(tuple(perm))


@procedure_set.register(inline=True)
def getitem(self, val):
    # Union[int, slice, Tensor, None, Ellipsis, Tuple[Union[int, slice, Tensor, None, Ellipsis], ...]]
    def normalize_int(e, i, dim_sz):
        if -dim_sz <= e < dim_sz:
            return e if e != -1 else dim_sz - 1
        raise IndexError(f"index {e} is out of bounds for dimension {i} with size {self.shape[i]}")

    orig_slices = list(val) if isinstance(val, tuple) else [val]
    count = defaultdict(list)
    for i, v in enumerate(orig_slices):
        count[type(v) if not isinstance(v, slope.core.Tensor) else "tensor"] += [i]

    if (num_slices := len(count[int]) + len(count[slice_py]) + len(count["tensor"])) > len(self.shape):
        raise IndexError(f"too many indices for tensor of dimension {len(self.shape)}")
    if len(ellipsis_found := count[type(Ellipsis)]) > 1:
        raise IndexError("an index can only have a single ellipsis ('...')")

    ellipsis_idx = ellipsis_found[0] if ellipsis_found else len(orig_slices)
    orig_slices[ellipsis_idx : ellipsis_idx + 1] = [slice_py(None)] * (len(self.shape) - num_slices)

    valid_slices = [v for v in orig_slices if v is not None]
    valid_slices = [
        v
        if isinstance(v, slice_py)
        else slice_py(y_ := normalize_int(v, i, dim_sz), y_ + 1)
        if isinstance(v, int)
        else slice_py(None)
        for i, (v, dim_sz) in enumerate(zip(valid_slices, self.shape))
    ]

    start, stop, strides = (
        zip(*y) if (y := [s.indices(dim_sz) for s, dim_sz in zip(valid_slices, self.shape)]) else ((), (), ())
    )
    new_slice = tuple((s, e) if st > 0 else (e + 1, s + 1) for s, e, st in zip(start, stop, strides))
    sliced_tensor = self.padslice(new_slice).flip(dim=tuple([i for i, s in enumerate(strides) if s < 0]))
    new_shape = sliced_tensor.shape
    if any(abs_py(s) != 1 for s in strides):
        strides = tuple(abs_py(s) for s in strides)
        # Pad: add pad at the end: [dim_sz] -> [dim_sz_padded]
        padded_tensor = sliced_tensor.pad(
            tuple((0, s - (dim_sz % s) if dim_sz % s != 0 else 0) for s, dim_sz in zip(strides, sliced_tensor.shape))
        )
        # Reshape: [dim_sz_padded] -> [dim_sz_padded // s, s]
        reshaped_tensor = padded_tensor.reshape(flatten([sh // s, s] for sh, s in zip(padded_tensor.shape, strides)))
        new_shape = reshaped_tensor.shape[::2]
        # Shrink: do [:, 0]
        sliced_tensor = reshaped_tensor.padslice(tuple(flatten(((0, sh), (0, 1)) for sh in new_shape)))

    final_shape, it_shape, dim, tensors, dim_collapsed = [], iter(new_shape), [], [], 0
    for i, s in enumerate(orig_slices):
        if s is None:
            final_shape.append(1)
        else:  # s is int or slice or Tensor
            dim_shape = next(it_shape)
            if isinstance(s, int):
                dim_collapsed += 1
            else:
                final_shape.append(dim_shape)
                if isinstance(s, slope.core.Tensor):
                    tensors.append(s)
                    dim.append(i - dim_collapsed)
    ret = sliced_tensor.reshape(tuple(final_shape))

    if tensors:  # Fancy/tensor indexing
        # normalize idx
        idx = [t.sign().neg().relu() * ret.shape[d] + t for d, t in zip(dim, tensors)]
        max_dim = max(i.ndim for i in idx)
        # compute sum_dim, arange, and idx
        sum_dim = [d if n == 0 else d + max_dim - n for n, d in enumerate(dim)]
        slice_arange = [
            slope.arange(ret.shape[d], dtype=slope.int32, requires_grad=False, device=self.device).reshape(
                *[1] * sd, ret.shape[d], *[1] * (ret.ndim + max_dim - n - sd - 1)
            )
            for n, (sd, d) in enumerate(zip(sum_dim, dim))
        ]
        first_idx = [
            idx[0].reshape(
                *[1] * dim[0],
                *[1] * (1 + max_dim - idx[0].ndim),
                *idx[0].shape,
                *[1] * (ret.ndim - dim[0] - 1),
            )
        ]
        rest_idx = [
            i.reshape(
                *[1] * dim[0],
                *[1] * (max_dim - i.ndim),
                *i.shape,
                *[1] * (ret.ndim - dim[0] - n),
            )
            for n, i in enumerate(idx[1:], 1)
        ]
        idx = first_idx + rest_idx
        ret = ret.reshape(*ret.shape[: sum_dim[0] + 1], *[1] * max_dim, *ret.shape[sum_dim[0] + 1 :])
        # iteratively fancy index
        for a, i, sd in zip(slice_arange, idx, sum_dim):
            ret = (a == i).mul(ret).sum(sd)
        # special permute case
        if dim[0] != 0 and len(dim) != 1 and dim != list(range(dim[0], dim[-1] + 1)):
            ret_dims = list(range(ret.ndim))
            ret = ret.permute(ret_dims[dim[0] : dim[0] + max_dim] + ret_dims[: dim[0]] + ret_dims[dim[0] + max_dim :])
    return ret


@procedure_set.register(static_argnames=("arg", "value"))
def padslice(x, arg: Sequence[Optional[Tuple[int, int]]], value: float = 0):
    def flatten_seq(l: Iterator):
        return [item for sublist in l for item in sublist]

    # some dim are pad, some are sliced
    arg_ = tuple([a if a is not None else (0, s) for s, a in zip(x.shape, arg)])
    padding = tuple([(max_py(0, -p[0]), max_py(0, p[1] - x.shape[i])) for i, p in enumerate(arg_)])
    x = x.pad(flatten_seq(padding), value=value)  # flatten
    starts, limits, strides = tuple(zip(*[(p[0] + padding[i][0], p[1] + padding[i][0], 1) for i, p in enumerate(arg_)]))
    x = x.slice(starts, limits, strides)
    return x


@procedure_set.register(static_argnames="padding value")
def pad2d(x, padding: Union[List[int], Tuple[int, ...]], value: float = 0):
    # (padding_left, padding_right, padding_top, padding_bottom)
    slc = [(-p0, s + p1) for p0, p1, s in zip(padding[::2], padding[1::2], x.shape[::-1])][::-1]
    return x.padslice([(0, s) for s in x.shape[: -(len(padding) // 2)]] + slc, value=value)


@procedure_set.register(static_argnames="dim")
def gather(x, idx, dim: int):
    assert idx.ndim == x.ndim, "x.ndim must equal idx.ndim"
    assert all(s >= i for s, i in zip(x.shape, idx.shape)), "all dim of idx.shape must be smaller than x.shape"
    if dim < 0:
        dim += x.ndim
    idx = idx.transpose(ax=dim, aw=0).expand_dims(-1)
    permarg = list(range(x.ndim))
    permarg = (
        permarg[1:dim] + [permarg[0]] + permarg[dim + 1 :] + [permarg[dim]] if dim != 0 else permarg[1:] + [permarg[0]]
    )
    return (
        (
            (
                idx
                == slope.arange(
                    x.shape[dim],
                    dtype=slope.int32,
                    requires_grad=False,
                    device=x.device,
                )
            )
            * x.permute(*permarg)
            .padslice(tuple([*[(0, sh) for sh in idx.shape[1:-1]], (0, x.shape[dim])]))
            .expand_dims(0)
        )
        .sum(-1)
        .transpose(ax=0, aw=dim)
    )


@procedure_set.register(static_argnames="dim")
@staticmethod
def stack(tensors, dim=0):
    first = tensors[0].expand_dims(dim)
    expand_dimsd_tensors = [tensor.expand_dims(dim) for tensor in tensors[1:]]
    return first.cat(*expand_dimsd_tensors, dim=dim)


@procedure_set.register(static_argnames="repeats")
def repeat(x, repeats):
    base_shape = (1,) * (len(repeats) - x.ndim) + x.shape
    new_shape = [x for b in base_shape for x in [1, b]]
    expand_shape = [x for rs in zip(repeats, base_shape) for x in rs]
    final_shape = [r * s for r, s in zip(repeats, base_shape)]
    return x.reshape(new_shape).broadcast(expand_shape).reshape(final_shape)


@procedure_set.register(static_argnames="dim")
def split(x, num: int, dim: int):
    dim, step = dim + x.ndim if dim < 0 else dim, math.ceil(x.shape[dim] / num)
    slice_params = [[slice(None)] * dim + [slice(k, k + step)] for k in range(0, x.shape[dim], step)]
    return tuple(x[tuple(sl)] for sl in slice_params)


@procedure_set.register(static_argnames="dim")
def squeeze(x, dim=None):
    if dim is None:
        return x if 1 not in x.shape else x.reshape(*[size for size in x.shape if size != 1])
    if dim <= 0 and x.ndim == 0:
        return x  # This is to match PyTorch behavior
    if not -x.ndim <= dim < x.ndim:
        raise IndexError(
            f"Dimension out of range (expected to be in range of [{-x.ndim if x.ndim > 0 else x.ndim-1}, {x.ndim-1 if x.ndim > 0 else x.ndim}], but got {dim})"
        )
    if dim < 0:
        dim += x.ndim
    return x if x.shape[dim] != 1 else x.reshape(*[size for idx, size in enumerate(x.shape) if idx != dim])


@procedure_set.register(static_argnames="dim")
def expand_dims(x, dim):
    if dim < 0:
        dim = len(x.shape) + dim + 1
    return x.reshape(x.shape[:dim] + (1,) + x.shape[dim:])


@procedure_set.register(static_argnames="ax aw")
def transpose(x, ax=1, aw=0):
    order = list(range(len(x.shape)))
    order[ax], order[aw] = order[aw], order[ax]
    return x.permute(tuple(order))


@procedure_set.register(static_argnames="start_dim")
def flatten(x, start_dim=0):
    return x.reshape(shape=x.shape[:start_dim] + (-1,))


@procedure_set.register(static_argnames="dim")
def cumsum(x, dim: int = 0):
    return x.transpose(dim, -1).pad((x.shape[dim] - 1, 0)).pool((x.shape[dim],)).sum(-1).transpose(dim, -1)


@staticmethod
@procedure_set.register(static_argnames="start stop step")
def arange_with_cumsum(start, stop=None, step=1):
    if stop is None:
        stop, start = start, 0
    return slope.full((math.ceil((stop - start) / step),), step).cumsum() + (start - step)


@procedure_set.register(static_argnames="dtype")
def one_hot(x, k, dtype=Tensor.int32):
    return (x[:, None].cast(dtype) == slope.arange(k, dtype=dtype)).cast(dtype)


iree_backend = Backend(operator_set, procedure_set, compiler)
