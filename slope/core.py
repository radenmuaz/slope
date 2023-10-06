from dataclasses import dataclass
from pathlib import Path
import os
import json
from typing import (
    Callable,
    NamedTuple,
    Dict,
    Type,
    Hashable,
    Tuple,
    List,
    Any,
    Iterable,
    Iterator,
    Type,
    List,
    Tuple,
    Optional,
    Any,
    Union,
    NamedTuple,
    Dict,
    Set,
    DefaultDict,
    Callable,
    Final,
)
import weakref
import types
from contextlib import contextmanager
import itertools
import weakref
from collections import defaultdict
from enum import Enum, auto
import operator as operator_py
import string
import numpy as np
import math
import inspect
from functools import partial, lru_cache

import slope
import importlib

# ================
#   Utils
# ================


def unzip2(pairs):
    lst1, lst2 = [], []
    for x1, x2 in pairs:
        lst1.append(x1)
        lst2.append(x2)
    return lst1, lst2


def list_map(f: Any, *xs: Any) -> Any:
    return list(map(f, *xs))


def list_zip(*args: Any) -> Any:
    fst, *rest = args = list_map(list, args)
    n = len(fst)
    for arg in rest:
        # assert len(arg) == n
        try:
            assert len(arg) == n
        except:
            breakpoint()
            raise
    return list(zip(*args))


def split_half(lst: List[Any]) -> Tuple[List[Any], List[Any]]:
    assert not len(lst) % 2
    return split_list(lst, len(lst) // 2)


def merge_lists(which: List[bool], l1: List[Any], l2: List[Any]) -> List[Any]:
    l1, l2 = iter(l1), iter(l2)
    out = [next(l2) if b else next(l1) for b in which]
    assert next(l1, None) is next(l2, None) is None
    return out


def split_list(lst: List[Any], n: int) -> Tuple[List[Any], List[Any]]:
    assert 0 <= n <= len(lst)
    return lst[:n], lst[n:]


def partition_list(bs: List[bool], l: List[Any]) -> Tuple[List[Any], List[Any]]:
    assert len(bs) == len(l)
    lst1: List[Any] = []
    lst2: List[Any] = []
    lists = lst1, lst2
    # lists = lst1: List[Any], lst2: List[Any] = list(), list()
    for b, x in list_zip(bs, l):
        lists[b].append(x)
    return lst1, lst2


class PPrint:
    lines: List[Tuple[int, str]]

    def __init__(self, lines):
        self.lines = lines

    def indent(self, indent: int) -> "PPrint":
        return PPrint([(indent + orig_indent, s) for orig_indent, s in self.lines])

    def __add__(self, rhs: "PPrint") -> "PPrint":
        return PPrint(self.lines + rhs.lines)

    def __rshift__(self, rhs: "PPrint") -> "PPrint":
        if not rhs.lines:
            return self
        if not self.lines:
            return rhs
        indent, s = self.lines[-1]
        indented_block = rhs.indent(indent + len(s))
        common_line = s + " " * rhs.lines[0][0] + rhs.lines[0][1]
        return PPrint(self.lines[:-1] + [(indent, common_line)] + indented_block.lines[1:])

    def __str__(self) -> str:
        return "\n".join(" " * indent + s for indent, s in self.lines)

    def __repr__(self):
        return str(self)

    @classmethod
    def pp(cls, s: Any):
        return cls([(0, line) for line in str(s).splitlines()])

    @classmethod
    def vcat(cls, ps: List["PPrint"]):
        return sum(ps, cls.pp(""))


class Hashed:
    val: Any

    def __init__(self, val):
        self.val = val

    def __hash__(self) -> int:
        return hash((self.val,))

    def __eq__(self, other):
        if isinstance(other, Hashed):
            return self.val == other.val
        return False


# ================
#   Tensors
# ================


class DType(NamedTuple):
    priority: int
    itemsize: int
    name: str
    np: type

    def __repr__(self):
        return f"{self.name}"


class TensorBuffer:
    def __init__(self, val):
        self.val = val


class Tensor:
    bool: Final[DType] = DType(0, 1, "bool", np.bool_)
    float16: Final[DType] = DType(0, 2, "f16", np.float16)
    float32: Final[DType] = DType(4, 4, "f32", np.float32)
    int8: Final[DType] = DType(0, 1, "i8", np.int8)
    int32: Final[DType] = DType(1, 4, "i32", np.int32)
    int64: Final[DType] = DType(2, 8, "i64", np.int64)
    uint8: Final[DType] = DType(0, 1, "u8", np.uint8)

    dtypes = {
        "bool": bool,
        "f16": float16,
        "f32": float32,
        "u8": uint8,
        "i8": int8,
        "i32": int32,
        "i64": int64,
    }
    dtypes_inv = {v: k for k, v in dtypes.items()}

    @property
    def default_dtype(self):
        return slope.M().backend.default_dtype

    def is_int(self) -> bool:
        return self.dtype in (self.int8, self.uint8, self.int32, self.int64)

    def is_float(self) -> bool:
        return self.dtype in (self.float16, self.float32)

    def is_unsigned(self) -> bool:
        return self.dtype is self.uint8

    def __getattr__(self, attr):
        if attr in self.__dict__.keys():
            return self.__dict__[attr]
        if attr in vars(slope.environment.operator_set).keys():
            op = getattr(slope.environment.operator_set, attr)
            return partial(op, self)
        elif attr in vars(slope.environment.procedure_set).keys():
            procedure = getattr(slope.environment.procedure_set, attr)
            assert not isinstance(procedure, classmethod), f"use sev.{attr} instead of self.{attr}"
            return partial(procedure, self)
        raise AttributeError(f"{self.__class__.__name__} has no attribute {attr}")

    def __getitem__(self, idx):
        return self.getitem(idx)

    def __setitem__(self, idx, item):
        raise NotImplementedError

    def str_short(self):
        return f'{str(self.dtype)}[{",".join(str(d) for d in self.shape)}]'

    __neg__ = lambda self: self.neg()
    __add__ = lambda self, other: self.add(other)
    __radd__ = lambda self, other: self.add(other)
    __sub__ = lambda self, other: self.sub(other)
    __rsub__ = lambda self, other: self.sub.func(other, self)
    __mul__ = lambda self, other: self.mul(other)
    __rmul__ = lambda self, other: self.mul(other)
    __div__ = lambda self, other: self.div(other)
    __rdiv__ = lambda self, other: self.div.func(other, self)
    __truediv__ = __div__
    __truerdiv__ = __rdiv__
    __eq__ = lambda self, other: self.equal(other)
    __ne__ = lambda self, other: self.not_equal(other)
    __ge__ = lambda self, other: self.maximum(other).equal(self)
    __le__ = lambda self, other: self.minimum(other).equal(self)
    __gt__ = lambda self, other: 1.0 - (self <= other)
    __lt__ = lambda self, other: 1.0 - (self >= other)

    def __init__(self, val: TensorBuffer):
        assert isinstance(val, TensorBuffer)
        self.buf = val

    def __hash__(self):
        return id(self.val)

    val = property(lambda self: self.buf.val)

    @property
    def dtype(self):
        return slope.M().backend.dtype_map_inv[self.buf.val.dtype]

    @property
    def device(self):
        return slope.M().backend.device_of(self)

    def numpy(self):
        return slope.M().backend.numpy_of(self)

    shape = property(lambda self: self.buf.val.shape)
    ndim = property(lambda self: self.buf.val.ndim)

    def __repr__(self):
        return f"{self.__class__.__name__}: {repr(self.val)[6:-1] if self.val.ndim > 0 else self.val}"

    __str__ = __repr__


class Typecheckor:
    def __init__(self, shape, dtype):
        self.shape = tuple(shape)
        self.dtype = dtype

    @classmethod
    def like(cls, aval):
        shape = aval.shape
        if isinstance(aval, Tensor):
            dtype = slope.M().backend.dtype_map_inv[aval.buf.val.dtype]
        else:
            dtype = aval.dtype
        return cls(shape, dtype)

    

    @property
    def ndim(self):
        return len(self.shape)

    def str_short(self):
        return f'{str(self.dtype)}[{",".join(str(d) for d in self.shape)}]'

    def __hash__(self):
        return hash((self.shape, self.dtype))

    def __eq__(self, other):
        if type(self) != type(other):
            return False
        return tuple(self.shape) == tuple(other.shape) and self.dtype == other.dtype

    def __repr__(self):
        return f"Typecheckor(shape={self.shape}, dtype={self.dtype})"


# ================
#   Operator
# ================


class OperatorType(Enum):
    Unary = auto()
    Binary = auto()
    Reduce = auto()
    Shape = auto()
    Load = auto()
    Meta = auto()


class Operator:
    def __init__(self, name, op_type=OperatorType.Meta, nary_inputs=False):
        self.name = name
        self.op_type = op_type
        self.nary_inputs = nary_inputs
        if self.nary_inputs:
            self.reorg_args = self.reorg_args_nary

    def args_fixer(self, *args, **params):
        return args, params

    def __call__(self, *args, **params):
        args, params = self.reorg_args(args, params)
        args, params = self.args_fixer(*args, **params)
        return slope.M().bind1(self, *args, **params)

    def __repr__(self) -> str:
        return f"<{self.name}>"

    def typecheck(self, *args, **params):
        raise NotImplementedError

    def jvp(self, *args, **params):
        raise NotImplementedError

    def T(self, *args, **params):
        raise NotImplementedError

    def vmap(self, *args, **params):
        raise NotImplementedError

    def reorg_args(self, args, params):
        args_, params_ = args, params
        sig = inspect.signature(self.typecheck)
        args_strs = [
            k for k, v in sig.parameters.items() if v.kind == inspect.Parameter.POSITIONAL_OR_KEYWORD and k != "self"
        ]
        params_strs = [k for k, v in sig.parameters.items() if v.kind == inspect.Parameter.KEYWORD_ONLY and k != "self"]

        if args:
            if len(args) > len(args_strs):
                args, rest = args[: len(args_strs)], args[len(args_strs) :]
                if params_strs:
                    new_params = {k: rest_arg for k, rest_arg in zip(params_strs, rest) if k not in params}
                    params = {**new_params, **params}
            else:
                args = tuple([params[k] if k in params else arg for k, arg in zip(args_strs, args)])
                assert len(args) == len(args_strs)
        return args, params

    def reorg_args_nary(self, args, params):
        return args, params

    def partial_run(self, trace, tracers, **params):
        tracers_in = [trace.instantiate_const(t) for t in tracers]
        avals_in = [t.aval for t in tracers_in]
        avals_out = self.typecheck(*avals_in, **params)
        tracers_out = [PartialEvalTracor(trace, slope.M().make_unknown_pval(aval), None) for aval in avals_out]
        instruction = InstructionDraft(self, tracers_in, params, avals_out, list_map(weakref.ref, tracers_out))
        for t in tracers_out:
            t.draft = instruction
        return tracers_out

    def partial_run_instruction(self, unks_in, instruction):
        if any(unks_in):
            instruction1 = None
            instruction2 = Instruction(
                instruction.op,
                instruction.inputs,
                instruction.params,
                instruction.out_binders,
            )
            unks_out = [True for i in instruction.out_binders]
            res = [v for unk, v in zip(unks_in, instruction.inputs) if ((not unk) and type(v) is Var)]
        else:
            instruction1 = instruction
            instruction2 = None
            unks_out = [False for i in instruction.out_binders]
            res = None

        return instruction1, instruction2, unks_out, res

    def set_method(self, method):
        setattr(self, method.__name__, types.MethodType(method, self))

    @classmethod
    def unary(cls, name, **kwargs):
        op = cls(name, OperatorType.Unary, **kwargs)

        @op.set_method
        def vmap(self, x, *, axis_size, vals_in, dims_in, **params):
            (x,), (x_bdim,) = vals_in, dims_in
            return [self(x, **params)], [x_bdim]

        @op.set_method
        def typecheck(self, x, **params):
            return [Typecheckor(x.shape, x.dtype)]

        @op.set_method
        def jvp(self, primals, tangents, **params):
            (x,), (x_dot,) = primals, tangents
            return [self(x, **params)], [self(x_dot, **params)]

        return op

    @classmethod
    def binary(cls, name, **kwargs):
        op = cls(name, OperatorType.Binary, **kwargs)

        @op.set_method
        def args_fixer(self, x, y, **params):
            if type(x) is PrimalProxy and type(y) is PrimalProxy:
                assert x.aval.shape == y.aval.shape
                return (x, y), params
            elif type(x) is PrimalProxy:
                assert x.aval.shape == y.shape
                return (x, y), params
            elif type(y) is PrimalProxy:
                assert y.aval.shape == x.shape
                return (x, y), params

            if type(x) in Tracor.PYTHON_TYPES:
                x = slope.environment.tensor(x, dtype=y.dtype)
            elif type(y) in Tracor.PYTHON_TYPES:
                y = slope.environment.tensor(y, dtype=x.dtype)

            if type(x) is Tensor and isinstance(y, Tracor):
                x = y._trace.pure(x)
            elif type(y) is Tensor and isinstance(x, Tracor):
                y = x._trace.pure(y)

            if (xshape := x.shape) == (yshape := y.shape):
                return (x, y), params
            shape_delta = len(xshape) - len(yshape)
            if shape_delta > 0:
                y = y.reshape((1,) * shape_delta + yshape)
            elif shape_delta < 0:
                x = x.reshape((1,) * -shape_delta + xshape)
            if (xshape := x.shape) == (yshape := y.shape):
                return (x, y), params

            shape_ret = tuple([max(x, y) for x, y in zip(xshape, yshape)])
            if xshape != shape_ret:
                x = x.broadcast_to(shape_ret)
            if yshape != shape_ret:
                y = y.broadcast_to(shape_ret)
            return (x, y), params

        @op.set_method
        def vmap(self, axis_size, vals_in, dims_in, **params):
            (x, y), (x_bdim, y_bdim) = vals_in, dims_in
            if x_bdim != y_bdim:
                if x_bdim is None:
                    x = BatchTrace.move_batch_axis(axis_size, x_bdim, y_bdim, x)
                    x_bdim = y_bdim
                else:
                    y = BatchTrace.move_batch_axis(axis_size, y_bdim, x_bdim, y)
            return [self(x, y, **params)], [x_bdim]

        @op.set_method
        def typecheck(self, x: Typecheckor, y: Typecheckor, **params) -> List[Typecheckor]:
            if not type(x) in (Tensor, Typecheckor) or not type(x) in (Tensor, Typecheckor):
                raise TypeError
            void_x = Typecheckor.like(x)
            void_y = Typecheckor.like(y)
            if void_x == void_y:
                return [void_x]
            shape_delta = len(void_x.shape) - len(void_y.shape)
            if shape_delta > 0:
                void_y = Typecheckor((1,) * shape_delta + void_y.shape, void_y.dtype)
            elif shape_delta < 0:
                x = x.reshape((1,) * -shape_delta + void_x.shape)
                void_x = Typecheckor((1,) * -shape_delta + void_x.shape, void_x.dtype)
            if void_x == void_y:
                return [void_x]
            else:
                shape_ret = tuple([max(x, y) for x, y in zip(void_x.shape, void_y.shape)])
                if void_x.shape != shape_ret:
                    void_x = Typecheckor(shape_ret, void_x.dtype)
                if void_y.shape != shape_ret:
                    void_y = Typecheckor(shape_ret, void_y.dtype)
                if void_x != void_y:
                    raise TypeError
                return [void_x]

        @op.set_method
        def jvp(self, primals, tangents, **params):
            (x,), (x_dot,) = primals, tangents
            return [self(x, **params)], [self(x_dot, **params)]

        return op

    @classmethod
    def reduce(cls, name, **kwargs):
        op = cls(name, OperatorType.Reduce, **kwargs)

        @op.set_method
        def args_fixer(self, x, *, axes=None, keepdims=False):
            if axes is None:
                axes = tuple(range(x.ndim))
            elif isinstance(axes, int):
                axes = (axes,)
            axes = tuple(a if a >= 0 else a + len(x.shape) for a in axes)
            return (x,), dict(axes=axes, keepdims=keepdims)

        @op.set_method
        def vmap(self, axis_size, vals_in, dims_in, **params):
            (x,), (x_bdim,) = vals_in, dims_in
            axes = list(params["axes"])
            axes = tuple(a + (x_bdim <= a) for a in axes)
            out_bdim = x_bdim - sum(a < x_bdim for a in axes)
            params["axes"] = tuple(axes)
            return [cls.do(x, **params)], [out_bdim]

        @op.set_method
        def typecheck(self, x: Typecheckor, *, axes=None, keepdims=False) -> List[Typecheckor]:
            axes = [a + len(x.shape) if a < 0 else a for a in axes]
            axes_ = set(axes)
            if keepdims:
                new_shape = [d if i not in axes_ else 1 for i, d in enumerate(x.shape)]
            else:
                new_shape = [d for i, d in enumerate(x.shape) if i not in axes_]
            return [Typecheckor(tuple(new_shape), x.dtype)]

        return op

    @classmethod
    def shape(cls, name, **kwargs):
        op = cls(name, OperatorType.Shape, **kwargs)
        return op

    @classmethod
    def load(cls, name, **kwargs):
        op = cls(name, OperatorType.Load, **kwargs)
        return op


class OperatorSet:
    def register(self, op):
        assert op.name not in vars(self)
        setattr(self, op.name, op)

    def alias(self, op, name):
        assert op.name in vars(self)
        setattr(self, name, getattr(self, op.name))


class ProcedureSet:
    def register(self, static_argnames=(), not_op=False):
        def wrap(f):
            f_procedure = self.new_procedure(f, static_argnames) if not not_op else f
            assert f.__name__ not in vars(self)
            setattr(self, f.__name__, f_procedure)
            return f_procedure

        return wrap

    def alias(self, fn, name):
        assert fn in vars(self)
        setattr(self, name, fn)

    def new_procedure(self, f, static_argnames=()):
        if type(static_argnames) is str:
            static_argnames = tuple(static_argnames.split(" "))
        assert type(static_argnames) is tuple and all(type(s) is str for s in static_argnames)
        impl_f = f
        static_argnames = static_argnames
        jvp_f = f
        T_f = f
        vmap_f = f
        typecheck_f = f

        def override_rule(f):
            if f.__name__ == "jvp":
                nonlocal jvp_f
                jvp_f = f
            elif f.__name__ == "T":
                nonlocal T_f
                T_f = f
            elif f.__name__ == "vmap_f":
                nonlocal vmap_f
                vmap_f = f
            elif f.__name__ == "typecheck":
                nonlocal typecheck_f
                typecheck_f = f

        def f_procedured(*args, **static_args):
            nonlocal impl_f, jvp_f, T_f, vmap_f, typecheck_f

            sig = inspect.signature(f)
            args_strs = [k for k, v in sig.parameters.items() if k != "self" and k not in static_argnames]
            static_args_strs = [k for k, v in sig.parameters.items() if k != "self" and k in static_argnames]

            if args:
                if len(args) > len(args_strs):
                    assert static_args_strs
                    args, rest = args[: len(args_strs)], args[len(args_strs) :]
                    new_static_args = {
                        k: rest_arg for k, rest_arg in zip(static_args_strs, rest) if k not in static_args
                    }
                    static_args = {**new_static_args, **static_args}
            else:
                args = tuple([static_args[k] if k in static_args else arg for k, arg in zip(args_strs, args)])
            assert len(args) == len(args_strs)

            for k, v in static_args.items():
                if type(v) is list:
                    static_args[k] = tuple(v)
                    for i, vov in enumerate(v):
                        if type(vov) is list:
                            static_args[k][i] = tuple(static_args[k][i])

            M = slope.M()
            # static_args = M.tree_map(lambda x: tuple(x) if type(x) is list else x, static_args)
            static_args = tuple(static_args.items())
            assert all([k in static_argnames for k, v in static_args])
            avals_in = M.tree_map(lambda x: Typecheckor.like(M.get_aval(x)), args)
            # top_trace = M.find_top_trace(args)
            program, consts, out_tree = M.make_program(impl_f, *avals_in, static_args=static_args, name=f.__name__)

            args, in_tree = M.tree_flatten(args)
            outs = M.bind(
                procedure_op,
                *consts,
                *args,
                program=program,
            )
            return M.tree_unflatten(out_tree, outs)

        f_procedured.override_rule = override_rule
        return f_procedured


procedure_op = Operator("procedure", op_type=OperatorType.Meta)


@procedure_op.set_method
def impl(self, *args, program):
    num_consts = program.num_consts
    consts, args = args[:num_consts], args[num_consts:]
    outs = slope.M().run_program(program, consts + args)
    return outs


@procedure_op.set_method
def jvp(self, primals, tangents, *, program):
    new_program, new_consts = slope.M().jvp_program(program)
    outs = slope.M().bind(self, *new_consts, *primals, *tangents, program=new_program)
    n = len(outs) // 2
    primals_out, tangents_out = outs[:n], outs[n:]
    return primals_out, tangents_out


@procedure_op.set_method
def typecheck(self, *in_types, program):
    program_type = slope.M().typecheck_program(program)
    if not all(t1 == t2 for t1, t2 in zip(program_type.in_types, in_types)):
        for i, j in zip(program_type.in_types, in_types):
            print(i, j, i == j)
        breakpoint()
        raise TypeError
    return program_type.out_types


@procedure_op.set_method
def T(self, cts, *invals, program):
    undef_primals = [type(x) is PrimalProxy for x in invals]
    transposed_program, new_consts = slope.M().transpose_program(program, tuple(undef_primals))

    residuals, _ = partition_list(undef_primals, invals)
    outs = slope.M().bind(self, *new_consts, *residuals, *cts, program=transposed_program)
    outs = iter(outs)
    return [next(outs) if undef else None for undef in undef_primals]


@procedure_op.set_method
def partial_run(self, trace, tracers, *, program):
    in_unknowns = [not t.pval.is_known for t in tracers]
    program1, program2, out_unknowns, num_res = slope.M().partial_run_program(program, in_unknowns)
    known_tracers, unknown_tracers = partition_list(in_unknowns, tracers)
    known_vals = [t.pval.const for t in known_tracers]
    outs1_res = slope.M().bind(self, *known_vals, program=program1)
    outs1, res = split_list(outs1_res, len(program1.outs) - num_res)
    res_tracers = [trace.instantiate_const(slope.M().full_raise(trace, x)) for x in res]
    outs2 = [PartialEvalTracor(trace, slope.M().make_unknown_pval(v.aval), None) for v in program2.outs]
    instruction = InstructionDraft(
        self,
        res_tracers + unknown_tracers,
        dict(program=program2),
        [v.aval for v in program2.outs],
        list_map(weakref.ref, outs2),
    )
    for t in outs2:
        t.draft = instruction

    return merge_lists(out_unknowns, outs1, outs2)


@procedure_op.set_method
def partial_run_instruction(self, unks_in, instruction) -> Tuple["Instruction", "Instruction", List[bool], List["Var"]]:
    program = instruction.params["program"]
    program1, program2, out_unknowns, num_res = slope.M().partial_run_program(program, unks_in)
    ins1, ins2 = partition_list(unks_in, instruction.inputs)
    out_binders1, out_binders2 = partition_list(out_unknowns, instruction.out_binders)
    res = [Var(v.aval) for v in program2.in_binders[:num_res]]
    instruction1 = Instruction(self, ins1, dict(program=program1), out_binders1 + res)
    instruction2 = Instruction(self, res + ins2, dict(program=program2), out_binders2)
    return instruction1, instruction2, out_unknowns, res


@procedure_op.set_method
def reorg_args(self, args, params):
    return args, params


@dataclass
class Environment:
    operator_set: OperatorSet
    procedure_set: ProcedureSet
    backends: dict

    def __getattr__(self, attr):
        try:
            # print(f"looking {attr} in operator_set")
            return getattr(self.operator_set, attr)
        except:
            pass
        try:
            # print(f"looking {attr} in procedure_set")
            return getattr(self.procedure_set, attr)
        except:
            pass
        # print(f"fallback to default getattribute")
        super().__getattribute__(attr)

    def tensor(
        self,
        val: Union[list, tuple, np.ndarray, "TensorBuffer"] = None,
        dtype: Optional[Any] = Tensor.float32,
    ):
        return (
            Tensor(val)
            if isinstance(val, TensorBuffer)
            else slope.M().backend.run_impl(self.operator_set.constant, val=val, dtype=dtype)
        )

    def save(arr: "Tensor", filename: str):
        # TODO
        arr_np = arr.numpy()

    def safe_load(self, fn: Union[Tensor, str]) -> Dict[str, Tensor]:
        t = fn if isinstance(fn, Tensor) else Tensor.empty(os.stat(fn).st_size, dtype=Tensor.uint8, device=f"disk:{fn}")
        json_len = t[0:1].cast(Tensor.int64).numpy()[0]
        metadata = json.loads(t[8 : 8 + json_len].numpy().tobytes())
        return {
            k: t[8 + json_len + v["data_offsets"][0] :]
            .cast(Tensor.safe_dtypes[v["dtype"]])[: math.prod(v["shape"])]
            .reshape(v["shape"])
            for k, v in metadata.items()
            if k != "__metadata__"
        }

    def safe_save(self, Tensors: Dict[str, Tensor], fn: str):
        metadata, offset = {}, 0
        for k, v in Tensors.items():
            metadata[k] = {
                "dtype": Tensor.safe_dtypes_inv[v.dtype],
                "shape": list(v.shape),
                "data_offsets": [offset, offset + v.nbytes()],
            }
            offset += v.nbytes()
        j = json.dumps(metadata, separators=(",", ":"))
        j += "\x20" * ((8 - len(j) % 8) % 8)
        Path(fn).unlink(missing_ok=True)
        t = Tensor.empty(8 + len(j) + offset, dtype=Tensor.uint8, device=f"disk:{fn}")
        t[0:1].cast(Tensor.int64).assign([len(j)])
        t[8 : 8 + len(j)].assign(Tensor(list(j.encode("utf-8")), dtype=Tensor.uint8, device="cpu"))
        for k, v in self.safe_load(t).items():
            v.assign(Tensors[k])


# ================
#   IR, Programs, Instructions
# ================


class Var:
    val = None
    aval: Typecheckor

    def __init__(self, aval):
        self.aval = aval


class Lit:
    val: Any
    aval: Typecheckor

    def __init__(self, val):
        self.aval = Typecheckor.like(slope.M().get_aval(val))
        self.val = val


Atom = Union[Var, Lit]


class Instruction(NamedTuple):
    op: Operator
    inputs: List[Atom]
    params: Dict[str, Any]
    out_binders: List[Atom]


class Program(NamedTuple):
    in_binders: Any
    instructions: Tuple[Instruction]
    outs: Any
    num_consts: int = 0
    static_args: Any = ()
    name: str = "my_program"

    def __hash__(self):
        return hash(repr(self))

    def __eq__(self, other):
        return self is other

    def __repr__(self):
        namegen = (
            # "z" + repr(r) for r in itertools.count()
            "".join(s)
            for r in itertools.count(1)
            for s in itertools.permutations(string.ascii_lowercase, r)
        )
        names = defaultdict(lambda: next(namegen))
        in_binders = ", ".join(self.var_str(names, x) for x in self.in_binders)
        instructions = PPrint.vcat([self.pp_instruction(names, e) for e in self.instructions])
        outs = [names[v] if isinstance(v, Var) else str(v.val) for v in self.outs]
        outs = ", ".join(outs)
        ret = str(
            PPrint.pp(f"{{ {self.name} {in_binders} .")
            + ((PPrint.pp("let ") >> instructions) + PPrint.pp(f"in ( {outs} ) }}")).indent(2)
        )
        return ret

    def pp_instruction(self, names: DefaultDict[Var, str], instruction: Instruction) -> PPrint:
        lhs = PPrint.pp(" ".join(self.var_str(names, v) for v in instruction.out_binders))
        rhs = (
            PPrint.pp(repr(instruction.op.name))
            >> self.pp_params(instruction.params)
            >> PPrint.pp(" ".join(names[x] if isinstance(x, Var) else str(x.val) for x in instruction.inputs))
        )
        return lhs >> PPrint.pp(" = ") >> rhs

    def pp_params(self, params: Dict[str, Any]) -> PPrint:
        items = sorted(params.items())
        if items:
            return PPrint.pp(" [ ") >> PPrint.vcat([PPrint.pp(f"{k}={v}") for k, v in items]) >> PPrint.pp(" ] ")
        else:
            return PPrint.pp(" ")

    def var_str(self, names: DefaultDict[Var, str], v) -> str:
        return f"{names[v]}:{v.aval.str_short()}"


class ProgramType(NamedTuple):
    in_types: Tuple[Typecheckor]
    out_types: Tuple[Typecheckor]

    def __repr__(self):
        in_types = ", ".join(aval.str_short() for aval in self.in_types)
        out_types = ", ".join(aval.str_short() for aval in self.out_types)
        return f"({in_types}) -> ({out_types})"


# ================
#   Tracer and Trace
# ================


class Empty:
    pass


empty = Empty()


class Store:
    val = empty

    def set_value(self, val):
        assert self.val is empty
        self.val = val

    def __call__(self):
        return self.val


class NodeType(NamedTuple):
    name: str
    flatten: Callable
    unflatten: Callable


class PyTreeDef(NamedTuple):
    node_type: NodeType
    node_metadata: Hashable
    child_treedefs: Tuple["PyTreeDef", ...]

    def __repr__(self):
        ret = self.to_s_expression()
        return ret
        # ret = self.pretty_print()
        # ret = f"tree {self.node_type.name}\n"
        # for i, c in enumerate(self.child_treedefs):
        #     ret += f"{i} {c}\n"

    def pretty_print(self, indent=0):
        indent_str = " " * indent
        child_str = ""
        if self.child_treedefs:
            child_str = "\n" + "\n".join(child.pretty_print(indent + 2) for child in self.child_treedefs)
        return f"{indent_str}PyTreeDef({self.node_type},\n  {child_str})"

    def to_s_expression(self, indent=0):
        if not self.child_treedefs:
            return f"({self.node_type.name})"
        indent_str = " " * indent
        child_s_expr = "\n".join(child.to_s_expression(indent + 2) for child in self.child_treedefs)
        return f"{indent_str}({self.node_type.name} {child_s_expr})"


class Leaf:
    def __repr__(self):
        return "Leaf"

    def pretty_print(self, indent=0):
        return " " * indent + repr(self)

    def to_s_expression(self, indent=0):
        return f"({repr(self)}"


leaf = Leaf()


# ================
#   jit operator
# ================


class JitFn:
    def __init__(self, code, fn, consts):
        super().__init__()
        self.code = code
        self.fn = fn
        self.consts = consts

    def __call__(self, *args, **params):
        args = slope.M().tree_map(lambda a: a.val if isinstance(a, Tensor) else a, args)
        args, in_tree = slope.M().tree_flatten(args)
        try:
            outs = self.fn(*args, **params)
        except Exception as e:
            print(self.code)
            breakpoint()
            raise
        return [slope.environment.tensor(TensorBuffer(o)) for o in outs]


jit_op = Operator("jit_op", op_type=OperatorType.Meta)


@jit_op.set_method
def impl(self, *args, program):
    hashed_program = Hashed(program)
    num_consts = program.num_consts
    consts, args = args[:num_consts], args[num_consts:]
    hashed_consts = tuple(map(Hashed, consts))
    jit_fn = slope.M().backend.gen_jit_fn(hashed_program, hashed_consts)
    ret = jit_fn(*consts, *args)
    return ret


@jit_op.set_method
def reorg_args(self, args, params):
    return args, params


@jit_op.set_method
def jvp(self, primals, tangents, *, program):
    new_program, new_consts = slope.M().jvp_program(program)
    outs = slope.M().bind(
        self,
        *new_consts,
        *primals,
        *tangents,
        program=new_program,
    )
    n = len(outs) // 2
    primals_out, tangents_out = outs[:n], outs[n:]
    return primals_out, tangents_out


@jit_op.set_method
def typecheck(self, *in_types, program):
    program_type = slope.M().typecheck_program(program)
    if not all(t1 == t2 for t1, t2 in zip(program_type.in_types, in_types)):
        for i, j in zip(program_type.in_types, in_types):
            print(i, j, i == j)
        breakpoint()
        raise TypeError
    return program_type.out_types


@jit_op.set_method
def T(self, cts, *invals, program):
    undef_primals = [type(x) is PrimalProxy for x in invals]
    transposed_program, new_consts = slope.M().transpose_program(program, tuple(undef_primals))

    residuals, _ = partition_list(undef_primals, invals)
    outs = slope.M().bind(
        self,
        *new_consts,
        *residuals,
        *cts,
        program=transposed_program,
    )
    outs = iter(outs)
    return [next(outs) if undef else None for undef in undef_primals]


@jit_op.set_method
def partial_run(self, trace, tracers, *, program):
    in_unknowns = [not t.pval.is_known for t in tracers]
    program1, program2, out_unknowns, num_res = slope.M().partial_run_program(program, in_unknowns)
    known_tracers, unknown_tracers = partition_list(in_unknowns, tracers)
    known_vals = [t.pval.const for t in known_tracers]
    outs1_res = slope.M().bind(jit_op, *known_vals, program=program1)
    outs1, res = split_list(outs1_res, len(program1.outs) - num_res)
    res_tracers = [trace.instantiate_const(slope.M().full_raise(trace, x)) for x in res]
    outs2 = [PartialEvalTracor(trace, slope.M().make_unknown_pval(v.aval), None) for v in program2.outs]
    instruction = InstructionDraft(
        self,
        res_tracers + unknown_tracers,
        dict(program=program2),
        [v.aval for v in program2.outs],
        list_map(weakref.ref, outs2),
    )
    for t in outs2:
        t.draft = instruction

    return merge_lists(out_unknowns, outs1, outs2)


@jit_op.set_method
def partial_run_instruction(self, unks_in, instruction) -> Tuple[Instruction, Instruction, List[bool], List[Var]]:
    program = instruction.params["program"]
    program1, program2, out_unknowns, num_res = slope.M().partial_run_program(program, unks_in)
    ins1, ins2 = partition_list(unks_in, instruction.inputs)
    out_binders1, out_binders2 = partition_list(out_unknowns, instruction.out_binders)
    res = [Var(v.aval) for v in program2.in_binders[:num_res]]
    instruction1 = Instruction(self, ins1, dict(program=program1), out_binders1 + res)
    instruction2 = Instruction(self, res + ins2, dict(program=program2), out_binders2)
    return instruction1, instruction2, out_unknowns, res


# ================
#   Module
# ================


class Module:
    def get_metadata(self):
        tensor_attrs = set()
        module_attrs = set()

        for k, v in self.__dict__.items():
            if isinstance(v, (Tensor, Typecheckor)):
                tensor_attrs.add(k)
            elif isinstance(v, Module):
                module_attrs.add(k)

        static_dict = {k: v for k, v in self.__dict__.items() if k not in tuple(tensor_attrs) + tuple(module_attrs)}
        return dict(
            cls=self.__class__,
            tensor_attrs=tuple(tensor_attrs),
            module_attrs=tuple(module_attrs),
            static_dict=static_dict,
        )
    
    def get_tensors(self):
        tensor_attrs = set()
        for k, v in self.__dict__.items():
            if isinstance(v, (Tensor, Typecheckor)):
                tensor_attrs.add(v)
        return tuple(tensor_attrs)
    
    def get_modules(self):
        module_attrs = set()
        for k, v in self.__dict__.items():
            if isinstance(v, Module):
                module_attrs.add(v)
        return tuple(module_attrs)

    def get_named_tensors(self):
        tensor_attrs = set()
        for k, v in self.__dict__.items():
            if isinstance(v, (Tensor, Typecheckor)):
                tensor_attrs.add((k, v))
        return tuple(tensor_attrs)
    
    def get_named_modules(self):
        module_attrs = set()
        for k, v in self.__dict__.items():
            if isinstance(v, Module):
                module_attrs.add((k, v))
        return tuple(module_attrs)

    def flatten(self):
        metadata = self.get_metadata()
        tensors = tuple(getattr(self, attr) for attr in metadata["tensor_attrs"])
        modules = tuple(getattr(self, attr) for attr in metadata["module_attrs"])
        return metadata, (tensors, modules)

    @staticmethod
    def unflatten(metadata, tensors_modules):
        mod = metadata["cls"].__new__(metadata["cls"])
        mod.__dict__.update(metadata["static_dict"])
        tensors, modules = tensors_modules
        for k, v in zip(metadata["tensor_attrs"], tensors):
            setattr(mod, k, v)
        for k, v in zip(metadata["module_attrs"], modules):
            setattr(mod, k, v)
        return mod

    def leaf_get_metadata(self):
        tensor_attrs = set()
        module_attrs = set()

        def find(obj, prefix):
            nonlocal tensor_attrs, module_attrs
            if isinstance(obj, (Tensor, Typecheckor)):
                tensor_attrs.add(prefix.strip("."))
                return
            if isinstance(obj, Module):
                if obj is not self:
                    module_attrs.add(prefix.strip("."))
                for k, v in obj.__dict__.items():
                    find(v, f"{prefix}{str(k)}.")

        find(self, "")
        static_dict = {k: v for k, v in self.__dict__.items() if k not in tuple(tensor_attrs) + tuple(module_attrs)}
        return dict(
            cls=self.__class__,
            tensor_attrs=tuple(tensor_attrs),
            module_attrs=tuple(module_attrs),
            static_dict=static_dict,
        )

    def leaf_flatten(self):
        metadata = self.get_metadata()
        tensors = tuple(operator_py.attrgetter(attr)(self) for attr in metadata["tensor_attrs"])
        rest = dict()
        for mod_attr in metadata["module_attrs"]:
            mod = operator_py.attrgetter(mod_attr)(self)
            mod_rest, _ = mod.flatten()
            rest[mod_attr] = mod_rest

        return (metadata, rest), tensors

    @staticmethod
    def leaf_unflatten(metadata_rest, tensors):
        def reassamble(metadata, rest):
            cls = metadata["cls"]
            mod = cls.__new__(cls)
            mod.__dict__.update(metadata["static_dict"])
            for mod_attr, (metadata_, rest_) in rest.items():
                setattr(mod, mod_attr, reassamble(metadata_, rest_))
            return mod

        metadata, rest = metadata_rest
        mod = reassamble(metadata, rest)

        def set_nested_attr(obj, attr, value):
            nested_attrs = attr.split(".")
            target_obj = obj
            for a in nested_attrs[:-1]:
                target_obj = getattr(target_obj, a)
            setattr(target_obj, nested_attrs[-1], value)

        for tensor, tensor_attr in list_zip(list(tensors), metadata["tensor_attrs"]):
            set_nested_attr(mod, tensor_attr, tensor)
        return mod

class Backend:
    def __init__(self, name, default_dtype=Tensor.float32, deps=("numpy as np", "math")):
        self.name = name
        self.default_dtype = default_dtype
        self.impls = dict()
        self.dtype_map = dict()
        self.dtype_map_inv = dict()
        self.deps_dict = dict()
        self.codegen_depth = 0
        self.codegen_idx = 0
        for dep in deps:
            if " as " in dep:  # e.g. "numpy as np"
                dep, _, dep_alias = dep.split(" ")
                self.deps_dict[dep] = importlib.import_module(dep)
                self.deps_dict[dep_alias] = self.deps_dict[dep]
            else:
                self.deps_dict[dep] = importlib.import_module(dep)

    def set_method(self, method):
        setattr(self, method.__name__, types.MethodType(method, self))

    @property
    def default_dtype_value(self):
        return self.dtype_map[self.default_dtype]

    def numpy_of(self, tensor):
        raise NotImplementedError

    @lru_cache
    def gen_jit_fn(
        self,
        hashed_program: Hashed,
        hashed_consts: Tuple[Hashed, ...],
    ):
        program: Program = hashed_program.val
        slope.M().typecheck_program(program)
        consts = [x.val for x in hashed_consts]
        in_avals = [v.aval for v in program.in_binders[len(consts) :]]
        codegen_out = self.codegen(program, consts + in_avals, fn_name="main")
        fn, code = self.compile(codegen_out)
        compiled = JitFn(code, fn, consts)
        return compiled

    def codegen(self, program, args, in_avals, name: str):
        "Returns IR from the Program"
        raise NotImplementedError

    def compile(self, program, args, in_avals, name: str):
        "Compiles IR to a Python callable function"
        raise NotImplementedError

    def set_dtype_map(self, dtype_map):
        self.dtype_map = dtype_map
        self.dtype_map_inv = {v: k for k, v in dtype_map.items()}

    def set_impl(self, op):
        def set_impl_(fn):
            self.impls[op] = types.MethodType(fn, self)

        return set_impl_

    def run_impl(self, op: Operator, *args, **params):
        if op.op_type is OperatorType.Meta:
            return op.impl(*args, **params)
        else:
            args_, params_ = args, params

            def extract_arg(a):
                return (
                    a.val
                    if isinstance(a, Tensor)
                    else self.dtype_map[a]
                    if isinstance(a, DType)
                    else tuple(extract_arg(aa) for aa in a)
                    if type(a) in (list, tuple)
                    else a
                )

            args = tuple([extract_arg(a) for a in args])
            params = {k: extract_arg(v) for k, v in params.items()}
            # if op.nary_inputs:
            # val = self.impls[op](args, **params)
            val = self.impls[op](*args, **params)
            return Tensor(TensorBuffer(val))


class MainTrace(NamedTuple):
    rt: "Machine"
    level: int
    trace_type: Type["Trace"]
    global_data: Optional[Any]


class Trace:
    main: MainTrace

    def __init__(self, main: MainTrace) -> None:
        self.main = main

    def pure(self, val):
        raise NotImplementedError

    def run_op(self, op, tracers, params):
        raise NotImplementedError


class EvalTrace(Trace):
    pure = lambda self, x: x

    def run_op(self, op: Operator, args, params):
        args_ = args
        args, params = op.reorg_args(args, params)
        args, params = op.args_fixer(*args, **params)
        ret = slope.M().backend.run_impl(op, *args, **params)
        if op.op_type is not OperatorType.Meta:
            ret = [ret]
        return ret


class Tracor(Tensor):
    PYTHON_TYPES = {
        bool,
        int,
        float,
    }
    _trace: "Trace"

    def __init__(self, *args, **kwargs):
        raise NotImplementedError

    aval = property(lambda self: slope.M().get_aval(self.val))
    dtype = property(lambda self: self.aval.dtype)
    shape = property(lambda self: self.aval.shape)

    @property
    def val(self):
        raise NotImplementedError

    def __str__(self):
        return repr(self)

    def full_lower(self):
        return self

    @property
    def ndim(self):
        return len(self.shape)

    def __repr__(self):
        return f"{self.__class__.__name__}({repr(self.aval)})"


BatchAxis = Union[None, int]


class BatchTracor(Tracor):
    def __init__(self, trace, val, batch_dim: BatchAxis):
        self._trace = trace
        self.val = val
        self.batch_dim = batch_dim

    @property
    def aval(self):
        aval = slope.M().get_aval(self.val)
        if self.batch_dim is None:
            return aval
        else:
            shape = list(aval.shape)
            del shape[self.batch_dim]
            return Typecheckor(tuple(shape), aval.dtype)

    def full_lower(self):
        if self.batch_dim is None:
            return slope.M().full_lower(self.val)
        else:
            return self


class BatchTrace(Trace):
    pure = lambda self, val: BatchTracor(self, val, None)

    def run_op(self, op, tracers, params):
        vals_in, bdims_in = unzip2((t.val, t.batch_dim) for t in tracers)
        val_outs, bdim_outs = op.vmap(self.axis_size, vals_in, bdims_in, **params)
        return [BatchTracor(self, x, bd) for x, bd in list_zip(val_outs, bdim_outs)]

    @property
    def axis_size(self):
        return self.main.global_data

    @staticmethod
    def move_batch_axis(axis_size, src, dst, x):
        if src is None:
            target_shape = list(x.shape)
            target_shape.insert(dst, axis_size)
            out_ndim = len(target_shape)
            if type(dst) in (tuple, list):
                out_ndim += 1
            reshape_shape = [1 if ax == dst else target_shape for ax in range(out_ndim)]
            x = x.reshape(reshape_shape)
            x = x.broadcast_in_dim(target_shape)
            return x
        elif src == dst:
            return x
        else:
            perm = [i for i in range(len(x.shape)) if i != src]
            perm.insert(dst, src)
            return x.transpose(perm)


class JVPTracor(Tracor):
    def __init__(self, trace, primal, tangent):
        self._trace = trace
        self.primal = primal
        self.tangent = tangent

    @property
    def aval(self):
        return slope.M().get_aval(self.primal)

    @property
    def val(self):
        return self.primal

    @property
    def dtype(self):
        return self.primal.dtype


class JVPTrace(Trace):
    def pure(self, val):
        if isinstance(val, PartialEvalTrace):
            val = val.pval.const
        return JVPTracor(self, val, slope.environment.zeros_like(val))

    def run_op(self, op, tracers, params):
        primals_in, tangents_in = unzip2((t.primal, t.tangent) for t in tracers)
        primals_out, tangents_out = op.jvp(primals_in, tangents_in, **params)
        # if not op.nary_inputs:
        #     primals_in, tangents_in = unzip2((t.primal, t.tangent) for t in tracers)
        #     primals_out, tangents_out = op.jvp(primals_in, tangents_in, **params)
        # else:
        #     M = slope.M()
        #     tracers_seq, treedef = M.tree_flatten(tracers)
        #     primals_in, tangents_in = unzip2((t.primal, t.tangent) for t in tracers_seq)
        #     primals_in = M.tree_unflatten(treedef, primals_in)
        #     tangents_in = M.tree_unflatten(treedef, tangents_in)
        #     primals_out, tangents_out = op.jvp(primals_in, tangents_in, **params)
        return [JVPTracor(self, x, t) for x, t in list_zip(primals_out, tangents_out)]


class ProgramTracor(Tracor):
    __slots__ = ["aval"]
    aval: Typecheckor

    def __init__(self, trace, aval):
        self._trace = trace
        self.aval = aval


class ProgramTrace(Trace):
    def new_arg(self, aval) -> ProgramTracor:
        aval = Typecheckor.like(aval)
        tracer = self.builder.new_tracer(self, aval)
        self.builder.tracer_to_var[id(tracer)] = Var(aval)

        return tracer

    def pure(self, val: Any) -> ProgramTracor:
        # get_or_make_const_tracer
        tracer = self.builder.const_tracers.get(id(val))
        if tracer is None:
            tracer = self.builder.new_tracer(self, slope.M().get_aval(val))
            self.builder.add_const(tracer, val)
        return tracer

    def run_op(self, op, tracers, params):
        avals_in = [t.aval for t in tracers]
        avals_in = slope.M().tree_map(lambda x: x.aval, tracers)
        avals_out = op.typecheck(*avals_in, **params)
        out_tracers = [self.builder.new_tracer(self, a) for a in avals_out]
        inputs = [self.builder.getvar(t) for t in tracers]
        outvars = [self.builder.add_var(t) for t in out_tracers]
        self.builder.add_instruction(Instruction(op, inputs, params, outvars))
        return out_tracers

    @property
    def builder(self):
        return self.main.global_data


class ProgramBuilder:
    instructions: List[Instruction]
    tracer_to_var: Dict[int, Var]
    const_tracers: Dict[int, Tracor]
    constvals: Dict[Var, Any]
    tracers: List[ProgramTracor]

    def __init__(self):
        self.instructions = []
        self.tracer_to_var = {}
        self.const_tracers = {}
        self.constvals = {}
        self.tracers = []

    def new_tracer(self, trace: ProgramTrace, aval: Typecheckor) -> ProgramTracor:
        tracer = ProgramTracor(trace, aval)
        self.tracers.append(tracer)
        return tracer

    def add_instruction(self, instruction: Instruction) -> None:
        self.instructions.append(instruction)

    def add_var(self, tracer: ProgramTracor) -> Var:
        assert id(tracer) not in self.tracer_to_var
        var = self.tracer_to_var[id(tracer)] = Var(tracer.aval)
        return var

    def getvar(self, tracer: ProgramTracor) -> Var:
        var = self.tracer_to_var.get(id(tracer))
        assert var is not None
        return var

    def add_const(self, tracer: ProgramTracor, val: Any) -> Var:
        var = self.add_var(tracer)
        self.const_tracers[id(val)] = tracer
        self.constvals[var] = val
        return var

    def build(self, in_tracers: Any, out_tracers: Any, static_args, name) -> Tuple[Program, List[Any]]:
        constvars, constvals = unzip2(self.constvals.items())
        t2v = lambda t: self.tracer_to_var[id(t)]
        in_binders = constvars + [t2v(t) for t in in_tracers]
        out_vars = [t2v(t) for t in out_tracers]
        program = Program(in_binders, self.instructions, out_vars, len(constvals), static_args, name)
        slope.M().typecheck_program(program)
        program, constvals = self._inline_literals(program, constvals)
        return program, constvals

    def _inline_literals(self, program: Program, consts: List[Any]) -> Tuple[Program, List[Any]]:
        const_binders, other_binders = split_list(program.in_binders, len(consts))
        scalars = [type(x) in Tracor.PYTHON_TYPES and not slope.M().get_aval(x).shape for x in consts]
        new_const_binders, lit_binders = partition_list(scalars, const_binders)
        new_consts, lit_vals = partition_list(scalars, consts)
        literals = dict(list_zip(lit_binders, list_map(Lit, lit_vals)))
        new_instructions = [
            Instruction(
                instruction.op,
                [literals.get(x, x) for x in instruction.inputs],
                instruction.params,
                instruction.out_binders,
            )
            for instruction in program.instructions
        ]
        new_outs = [literals.get(x, x) for x in program.outs]
        new_program = Program(
            new_const_binders + other_binders,
            new_instructions,
            new_outs,
            len(new_consts),
            program.static_args,
            program.name,
        )
        slope.M().typecheck_program(new_program)
        return new_program, tuple(new_consts)


class PrimalProxy(NamedTuple):
    aval: Typecheckor

    @property
    def shape(self):
        return self.aval.shape

    @property
    def dtype(self):
        return self.aval.dtype


class PartialValue(NamedTuple):
    aval: Typecheckor
    const: Optional[Any]

    is_known = property(lambda self: self.const is not None)
    is_unknown = property(lambda self: self.const is None)


class LambdaBindingDraft(NamedTuple):
    pass


class ConstDraft(NamedTuple):
    val: Any


class InstructionDraft(NamedTuple):
    prim: Operator
    tracers_in: List["PartialEvalTracor"]
    params: Dict[str, Any]
    avals_out: List[Typecheckor]
    tracer_refs_out: List[weakref.ReferenceType["PartialEvalTracor"]]


ProgramDraft = Union[LambdaBindingDraft, ConstDraft, InstructionDraft]


class PartialEvalTracor(Tracor):
    def __init__(self, trace, pval, draft):
        self._trace = trace
        self.pval = pval
        self.draft = draft

    aval = property(lambda self: self.pval.aval)
    val = property(lambda self: self.pval.const)

    def full_lower(self):
        if self.pval.is_known:
            return slope.M().full_lower(self.pval.const)
        return self


class PartialEvalTrace(Trace):
    def new_arg(self, pval: PartialValue) -> Any:
        return PartialEvalTracor(self, pval, LambdaBindingDraft())

    def pure(self, val: Any) -> PartialEvalTracor:
        return PartialEvalTracor(self, slope.M().make_known_pval(val), None)

    def instantiate_const(self, tracer: PartialEvalTracor) -> PartialEvalTracor:
        if tracer.pval.is_unknown:
            return tracer
        else:
            pval = slope.M().make_unknown_pval(Typecheckor.like(tracer.aval))
            return PartialEvalTracor(self, pval, ConstDraft(tracer.pval.const))

    def run_op(self, op, tracers, params):
        conds = tuple(t.pval.is_known for t in tracers)
        if all(conds):
            # if all(t.pval.is_known for t in tracers):
            return slope.M().bind(op, *list_map(slope.M().full_lower, tracers), **params)
        return op.partial_run(self, tracers, **params)


# ================
#   Machine
# ================


class Machine:
    def __init__(
        self,
        environment,
        default_backend="numpy",
    ):
        self.trace_stack: List[MainTrace] = []
        self.dynamic_trace: Optional[MainTrace] = None
        self.trace_stack += [MainTrace(self, 0, EvalTrace, None)]
        self.node_types = dict()
        self.register_node(tuple, lambda t: (None, t), lambda _, xs: tuple(xs), "tuple")
        self.register_node(list, lambda l: (None, l), lambda _, xs: list(xs), "list")
        self.register_node(
            dict,
            lambda d: list_map(tuple, unzip2(sorted(d.items()))),
            lambda keys, vals: dict(list_zip(keys, vals)),
            "dict",
        )
        self.register_node(PrimalProxy, lambda u: (u.aval, ()), lambda aval, _: PrimalProxy(aval), "PrimalProxy")
        self.register_node(Module, Module.flatten, Module.unflatten, "Module")

        self.environment = environment
        self.environment.operator_set.register(jit_op)
        self.environment.operator_set.register(procedure_op)
        self.backend = self.environment.backends[default_backend]

    def __repr__(self):
        ret = f"{self.__class__.__name__}\n"
        for trace in self.trace_stack:
            ret += f"{trace.level}: {trace.trace_type.__name__}\t{trace.global_data=}\n"
        return ret

    def make_known_pval(self, val: Any):
        return PartialValue(self.get_aval(val), val)

    def make_unknown_pval(self, aval: Typecheckor):
        return PartialValue(aval, None)

    def get_aval(self, x):
        if isinstance(x, Tracor):
            return x.aval
        elif type(x) in Tracor.PYTHON_TYPES:
            return self.environment.tensor(x)
        elif isinstance(x, Tensor):
            return x
        elif isinstance(x, Typecheckor):
            return x
        else:
            raise TypeError(type(x))

    def tree_flatten(self, x: Any) -> Any:
        def _tree_flatten(x_: Any) -> Tuple[Iterable, Union[PyTreeDef, Leaf]]:
            node_type = None
            for k in self.node_types.keys():
                if isinstance(x_, k):
                    node_type = self.node_types[k]

            if node_type is not None:
                node_metadata, children = node_type.flatten(x_)

                # print(f'flattened {x_}\n\n  children:\n{children}\n\n  metadata:\n{node_metadata}\n')
                children_flat, child_trees = unzip2(list_map(_tree_flatten, children))
                children_iter = itertools.chain.from_iterable(children_flat)
                treedef = PyTreeDef(node_type, node_metadata, tuple(child_trees))
                return children_iter, treedef
            else:
                # print(f'    leaf found: {x_}\n')
                return (x_,), leaf

        # print(f"flattening {x} of {type(x)}")
        children_iter, treedef = _tree_flatten(x)
        return tuple(children_iter), treedef

    def tree_unflatten(self, treedef: PyTreeDef, xs: Tuple[Any]) -> Any:
        def _tree_unflatten(treedef_: PyTreeDef, xs_: Iterator) -> Any:
            if treedef_ is leaf:
                # print(f'    tree leaf found: {xs_}\n')
                return next(xs_)
            else:
                # print(f"    now\n  {treedef_}")
                children = (_tree_unflatten(t, xs_) for t in treedef_.child_treedefs)
                # print(f"{children=}\n")
                return treedef_.node_type.unflatten(treedef_.node_metadata, children)

        # print(f'unflattening {treedef}')
        return _tree_unflatten(treedef, iter(xs))

    def flatten_fn(self, f, in_tree):
        store = Store()

        def flat_fn(*args_flat, **params):
            pytree_args = self.tree_unflatten(in_tree, args_flat)
            out = f(*pytree_args, **params)
            out_flat, out_tree = self.tree_flatten(out)
            store.set_value(out_tree)
            return out_flat

        return flat_fn, store

    def register_node(self, ty: Type, to_iter: Callable, from_iter: Callable, name=None) -> None:
        if name is None:
            name = str(ty)
        self.node_types[ty] = NodeType(name, to_iter, from_iter)

    
    def tree_map(self, f: Callable[..., Any], tree, *rest) -> Any:
        leaves, treedef = self.tree_flatten(tree)
        if len(rest)==0:
            return self.tree_unflatten(treedef, tuple(f(leaf) for leaf in leaves))
        all_leaves = [leaves]
        for t in rest:
            t_leaves, t_treedef = self.tree_flatten(t)
            assert t_treedef == treedef
            all_leaves += [t_leaves]
        # return self.tree_unflatten(treedef, f(*all_leaves))
        # return self.tree_unflatten(treedef, self.tree_flatten(f(*all_leaves))[0])
        return self.tree_unflatten(treedef, self.tree_flatten(f(*[l[0] for l in all_leaves]))[0])
    

    @contextmanager
    def new_main(self, trace_type: Type["Trace"], global_data=None):
        level = len(self.trace_stack)
        main = MainTrace(self, level, trace_type, global_data)
        self.trace_stack.append(main)

        try:
            yield main
        finally:
            self.trace_stack.pop()

    @contextmanager
    def new_dynamic(self, main: MainTrace):
        prev_dynamic_trace, self.dynamic_trace = self.dynamic_trace, main
        try:
            yield
        finally:
            self.dynamic_trace = prev_dynamic_trace

    def bind(self, op, *args, **params):
        top_trace = self.find_top_trace(args)
        # tracers = self.tree_map(partial(self.full_raise, top_trace), args)
        tracers = tuple([self.full_raise(top_trace, arg) for arg in args])
        outs = top_trace.run_op(op, tracers, params)
        # lowered = self.tree_map(self.full_lower, outs)
        lowered = tuple([self.full_lower(out) for out in outs])
        return lowered

    def bind1(self, op, *args, **params):
        return self.bind(op, *args, **params)[0]

    def find_top_trace(self, xs) -> Trace:
        arrs = []

        def get_arr_from_seq(seq):
            nonlocal arrs
            for x in seq:
                if type(x) in (tuple, list):
                    get_arr_from_seq(x)
                elif isinstance(x, Tracor):
                    arrs += [x]

        get_arr_from_seq(xs)
        arrs = tuple(arrs)
        top_main = max(
            (x._trace.main for x in arrs),
            default=self.trace_stack[0],
            key=operator_py.attrgetter("level"),
        )
        if self.dynamic_trace and self.dynamic_trace.level > top_main.level:
            top_main = self.dynamic_trace
        return top_main.trace_type(top_main)

    def full_raise(self, trace: Trace, val: Any) -> Tracor:
        if not isinstance(val, Tracor):
            return trace.pure(val)
        level = trace.main.level
        if val._trace.main is trace.main:
            return val
        elif val._trace.main.level < level:
            return trace.pure(val)
        elif val._trace.main.level > level:
            raise Exception(f"Can't lift level {val._trace.main.level} to {level}.")
        else:  # val._trace.level == level
            raise Exception(f"Different traces at same level: {val._trace}, {trace}.")

    def full_lower(self, val: Any):
        if isinstance(val, Tracor):
            return val.full_lower()
        elif type(val) in (list, tuple):
            return tuple(self.full_lower(v) for v in val)
        else:
            return val

    def typecheck_program(self, program: Program) -> ProgramType:
        environment: Set[Var] = set()

        for v in program.in_binders:
            if v in environment:
                raise TypeError
            environment.add(v)

        for instruction in program.instructions:
            in_types = [self.typecheck_atom(environment, x) for x in instruction.inputs]
            out_types = instruction.op.typecheck(*in_types, **instruction.params)
            for out_binder, out_type in list_zip(instruction.out_binders, out_types):
                if not out_type == out_binder.aval:
                    raise TypeError
            for out_binder in instruction.out_binders:
                if out_binder in environment:
                    raise TypeError
                environment.add(out_binder)

        in_types = [v.aval for v in program.in_binders]
        out_types = [self.typecheck_atom(environment, x) for x in program.outs]
        return ProgramType(tuple(in_types), tuple(out_types))

    def typecheck_atom(self, environment: Set[Var], x: Atom) -> Typecheckor:
        if isinstance(x, Var):
            if x not in environment:
                raise TypeError("unbound variable")
            return x.aval
        elif isinstance(x, Lit):
            return self.get_aval(x.val)
        else:
            assert False

    def run_program(self, program: Program, args: List[Any]) -> List[Any]:
        environment: Dict[Var, Any] = {}

        def read(x: Atom) -> Any:
            return environment[x] if type(x) is Var else x.val

        def write(v: Var, val: Any) -> None:
            assert v not in environment  # single-assignment
            environment[v] = val

        list_map(write, program.in_binders, args)
        for instruction in program.instructions:
            in_vals = list_map(read, instruction.inputs)
            outs = self.bind(instruction.op, *in_vals, **instruction.params)
            list_map(write, instruction.out_binders, outs)
        return list_map(read, program.outs)

    def program_as_fun(self, program: Program):
        return lambda *args: self.run_program(program, args)

    def vmap_flat(self, f, in_axes, *args):
        axi_set = {x.shape[ax] for x, ax in list_zip(args, in_axes) if ax is not None}
        assert len(axi_set) == 1
        (axis_size,) = axi_set
        with self.new_main(BatchTrace, axis_size) as main:
            trace = BatchTrace(main)
            tracers_in = [BatchTracor(trace, x, ax) if ax is not None else x for x, ax in list_zip(args, in_axes)]
            outs = f(*tracers_in)
            tracers_out = [self.full_raise(trace, out) for out in outs]
            vals_out, bdims_out = unzip2((t.val, t.batch_dim) for t in tracers_out)
        outs_transposed = [
            BatchTrace.move_batch_axis(axis_size, bdim, 0, val_out) for val_out, bdim in list_zip(vals_out, bdims_out)
        ]
        return outs_transposed

    def vmap(self, f, in_axes):
        def batched_f(*args):
            args_flat, in_tree = self.tree_flatten(args)
            in_axes_flat, in_tree2 = self.tree_flatten(in_axes)
            if in_tree != in_tree2:
                raise TypeError(f"{in_tree}\n!=\n{in_tree2}")
            f_flat, out_tree_store = self.flatten_fn(f, in_tree)
            outs_flat = self.vmap_flat(f_flat, in_axes_flat, *args_flat)
            return self.tree_unflatten(out_tree_store(), outs_flat)

        return batched_f

    def jvp_flat(self, f, primals, tangents, **static_args):
        with self.new_main(JVPTrace) as main:
            trace = JVPTrace(main)
            tracers_in = [JVPTracor(trace, x, t) for x, t in list_zip(primals, tangents)]
            outs = f(*tracers_in, **static_args)
            tracers_out = [self.full_raise(trace, out) for out in outs]
            primals_out, tangents_out = unzip2((t.primal, t.tangent) for t in tracers_out)
        return primals_out, tangents_out

    def jvp(self, f, primals, tangents, **static_args):
        primals_flat, in_tree = self.tree_flatten(primals)
        tangents_flat, in_tree2 = self.tree_flatten(tangents)
        if in_tree != in_tree2:
            raise TypeError
        f, out_tree_store = self.flatten_fn(f, in_tree)
        primals_out_flat, tangents_out_flat = self.jvp_flat(f, primals_flat, tangents_flat, **static_args)
        primals_out = self.tree_unflatten(out_tree_store(), primals_out_flat)
        tangents_out = self.tree_unflatten(out_tree_store(), tangents_out_flat)
        return primals_out, tangents_out

    def jacfwd(self, f, x):
        pushfwd = lambda v: self.jvp(f, (x,), (v,))[1]
        vecs_in = self.environment.eye(math.prod(x.shape)).reshape(x.shape * 2)
        return self.vmap(pushfwd, (0,))(vecs_in)

    @lru_cache
    def make_program(
        self, f: Callable, *avals_in: Typecheckor, static_args, name
    ) -> Tuple[Program, List[Any], PyTreeDef]:
        avals_in, in_tree = self.tree_flatten(avals_in)
        f, out_tree_store = self.flatten_fn(f, in_tree)

        builder = ProgramBuilder()
        with self.new_main(ProgramTrace, builder) as main:
            with self.new_dynamic(main):
                trace = ProgramTrace(main)
                tracers_in = [trace.new_arg(aval) for aval in avals_in]
                outs = f(*tracers_in, **{k: v for k, v in static_args})
                tracers_out = [self.full_raise(trace, out) for out in outs]
                program, consts = builder.build(tracers_in, tracers_out, static_args, name)

        return program, consts, out_tree_store()

    @lru_cache
    def jvp_program(self, program: Program, static_args=()) -> Tuple[Program, List[Any]]:
        def jvp_traceable(*primals_and_tangents):
            n = len(primals_and_tangents) // 2
            primals, tangents = primals_and_tangents[:n], primals_and_tangents[n:]
            return self.jvp(self.program_as_fun(program), primals, tangents)

        in_avals = self.tree_map(lambda v: v.aval, program.in_binders)
        new_program, new_consts, _ = self.make_program(
            jvp_traceable, *in_avals, *in_avals, static_args=static_args, name=f"{program.name}_jvp"
        )
        return new_program, new_consts

    def partial_run_flat(
        self, f: Callable, pvals_in: List["PartialValue"], global_data=None
    ) -> Tuple[Program, List["PartialValue"], List[Any]]:
        with self.new_main(PartialEvalTrace, global_data) as main:
            trace = PartialEvalTrace(main)
            tracers_in = [trace.new_arg(pval) for pval in pvals_in]
            outs = f(*tracers_in)
            tracers_out = [self.full_raise(trace, out) for out in outs]
            pvals_out = [t.pval for t in tracers_out]
            unk_tracers_in = [t for t in tracers_in if t.pval.is_unknown]
            unk_tracers_out = [t for t in tracers_out if t.pval.is_unknown]
            program, consts = self.tracers_to_program(unk_tracers_in, unk_tracers_out)

        return program, pvals_out, consts

    def partial_run_program(
        self, program: Program, in_unknowns: List[bool], instantiate: Optional[List[bool]] = None
    ) -> Tuple[Program, Program, List[bool], int]:
        environment: Dict[Var, bool] = {}
        residuals: Set[Var] = set()

        def read(x: Atom) -> bool:
            return type(x) is Var and environment[x]

        def write(unk: bool, v: Var) -> None:
            environment[v] = unk

        instructions1, instructions2 = [], []
        list_map(write, in_unknowns, program.in_binders)

        for instruction in program.instructions:
            unks_in = list_map(read, instruction.inputs)
            (
                instruction1,
                instruction2,
                unks_out,
                res,
            ) = instruction.op.partial_run_instruction(unks_in, instruction)
            if instruction1 is not None:
                instructions1.append(instruction1)
            if instruction2 is not None:
                instructions2.append(instruction2)
            if res is not None:
                residuals.update(res)
            list_map(write, unks_out, instruction.out_binders)

        out_unknowns = list_map(read, program.outs)
        if instantiate is not None:
            for v, uk, inst in zip(program.outs, out_unknowns, instantiate):
                if inst and not uk:
                    if type(v) is Var:
                        residuals.add(v)
            out_unknowns = list_map(operator_py.or_, out_unknowns, instantiate)

        residuals, num_res = list(residuals), len(residuals)
        assert all(type(v) is Var for v in residuals), residuals

        ins1, ins2 = partition_list(in_unknowns, program.in_binders)
        outs1, outs2 = partition_list(out_unknowns, program.outs)

        program1 = Program(ins1, instructions1, outs1 + residuals, 0, program.static_args, f"{program.name}_partial1")
        program2 = Program(residuals + ins2, instructions2, outs2, 0, program.static_args, f"{program.name}_partial2")
        self.typecheck_partial_run_program(program, in_unknowns, out_unknowns, program1, program2)

        return program1, program2, out_unknowns, num_res

    def typecheck_partial_run_program(self, program, in_unknowns, out_unknowns, program1, program2):
        programty = self.typecheck_program(program)  # (a1,  a2) -> (b1, b2 )
        program1ty = self.typecheck_program(program1)  #  a1       -> (b1, res)
        program2ty = self.typecheck_program(program2)  # (res, a2) -> b2

        a1, a2 = partition_list(in_unknowns, programty.in_types)
        b1, b2 = partition_list(out_unknowns, programty.out_types)
        b1_, res = split_list(program1ty.out_types, len(b1))
        res_, a2_ = split_list(program2ty.in_types, len(res))
        b2_ = program2ty.out_types

        a1 = tuple(a1)
        a2, a2_ = tuple(a2), tuple(a2_)
        b1, b1_ = tuple(b1), tuple(b1_)
        b2, b2_ = tuple(b2), tuple(b2_)
        res, res_ = tuple(res), tuple(res_)

        if program1ty.in_types != a1:
            raise TypeError
        if program2ty.out_types != b2:
            raise TypeError
        if b1 != b1_:
            raise TypeError
        if res != res_:
            raise TypeError
        if a2 != a2_:
            raise TypeError
        if b2 != b2_:
            raise TypeError

    def linearize_flat(self, f, *primals_in):
        pvals_in = [self.make_known_pval(x) for x in primals_in] + [
            self.make_unknown_pval(Typecheckor.like(self.get_aval(x))) for x in primals_in
        ]

        def f_jvp(*primals_tangents_in):
            primals_out, tangents_out = self.jvp(f, *split_half(primals_tangents_in))
            return [*primals_out, *tangents_out]

        program, pvals_out, consts = self.partial_run_flat(f_jvp, pvals_in)
        primal_pvals, _ = split_half(pvals_out)
        assert all(pval.is_known for pval in primal_pvals)
        primals_out = [pval.const for pval in primal_pvals]
        f_lin = lambda *tangents: self.run_program(program, [*consts, *tangents])
        return primals_out, f_lin

    def linearize(self, f, *primals_in):
        primals_in_flat, in_tree = self.tree_flatten(primals_in)
        f, out_tree_store = self.flatten_fn(f, in_tree)
        primals_out_flat, f_lin_flat = self.linearize_flat(f, *primals_in_flat)
        primals_out = self.tree_unflatten(out_tree_store(), primals_out_flat)

        def f_lin(*tangents_in):
            tangents_in_flat, in_tree2 = self.tree_flatten(tangents_in)
            if in_tree != in_tree2:
                raise TypeError
            tangents_out_flat = f_lin_flat(*tangents_in_flat)
            return self.tree_unflatten(out_tree_store(), tangents_out_flat)

        return primals_out, f_lin

    def tracers_to_program(
        self,
        tracers_in: List["PartialEvalTracor"],
        tracers_out: List["PartialEvalTracor"],
    ):
        def tracer_parents(t: PartialEvalTracor) -> List[PartialEvalTracor]:
            return t.draft.tracers_in if isinstance(t.draft, InstructionDraft) else []

        def draft_to_instruction(tracer_to_var: Dict[int, Var], draft: InstructionDraft) -> Instruction:
            inputs = [tracer_to_var[id(t)] for t in draft.tracers_in]
            out_binders = [Var(aval) for aval in draft.avals_out]
            for t_ref, var in list_zip(draft.tracer_refs_out, out_binders):
                if t_ref() is not None:
                    tracer_to_var[id(t_ref())] = var
            return Instruction(draft.prim, inputs, draft.params, out_binders)

        tracer_to_var: Dict[int, Var] = {id(t): Var(Typecheckor.like(t.aval)) for t in tracers_in}
        constvar_to_val: Dict[int, Any] = {}
        constid_to_var: Dict[int, Var] = {}
        processed_instructions: Set[int] = set()
        instructions: List[Instruction] = []
        for t in self.toposort(tracers_out, tracer_parents):
            if isinstance(t.draft, LambdaBindingDraft):
                assert id(t) in set(list_map(id, tracers_in))
            elif isinstance(t.draft, ConstDraft):
                val = t.draft.val
                var = constid_to_var.get(id(val))
                if var is None:
                    aval = Typecheckor.like(self.get_aval(val))
                    var = constid_to_var[id(val)] = Var(aval)
                    constvar_to_val[var] = val
                tracer_to_var[id(t)] = var
            elif isinstance(t.draft, InstructionDraft):
                if id(t.draft) not in processed_instructions:
                    instructions.append(draft_to_instruction(tracer_to_var, t.draft))
                    processed_instructions.add(id(t.draft))
            else:
                raise TypeError(t.draft)

        constvars, constvals = unzip2(constvar_to_val.items())
        in_binders = constvars + [tracer_to_var[id(t)] for t in tracers_in]
        out_vars = [tracer_to_var[id(t)] for t in tracers_out]
        program = Program(tuple(in_binders), tuple(instructions), tuple(out_vars))
        self.typecheck_program(program)
        return program, constvals

    def toposort(self, out_nodes: List[Any], parents: Callable[[Any], List[Any]]):
        def check_toposort(nodes: List[Any], parents: Callable[[Any], List[Any]]):
            seen = set()
            for node in nodes:
                assert all(id(parent) in seen for parent in parents(node))
                seen.add(id(node))

        def remove_duplicates(lst):
            seen = set()
            return [x for x in lst if id(x) not in seen and not seen.add(id(x))]

        if not out_nodes:
            return []
        out_nodes = remove_duplicates(out_nodes)

        child_counts = {}
        stack = list(out_nodes)
        while stack:
            node = stack.pop()
            if id(node) in child_counts:
                child_counts[id(node)] += 1
            else:
                child_counts[id(node)] = 1
                stack.extend(parents(node))
        for node in out_nodes:
            child_counts[id(node)] -= 1

        sorted_nodes = []
        childless_nodes = [node for node in out_nodes if not child_counts[id(node)]]
        while childless_nodes:
            node = childless_nodes.pop()
            sorted_nodes.append(node)
            for parent in parents(node):
                if child_counts[id(parent)] == 1:
                    childless_nodes.append(parent)
                else:
                    child_counts[id(parent)] -= 1

        sorted_nodes = sorted_nodes[::-1]
        check_toposort(sorted_nodes, parents)
        return sorted_nodes

    def vjp_flat(self, f, *primals_in, **static_args):
        pvals_in = [self.make_known_pval(x) for x in primals_in] + [
            self.make_unknown_pval(Typecheckor.like(self.get_aval(x))) for x in primals_in
        ]
        _, tangent_pvals_in = split_half(pvals_in)

        def f_jvp(*primals_tangents_in):
            primals_out, tangents_out = self.jvp(f, *split_half(primals_tangents_in), **static_args)
            return [*primals_out, *tangents_out]

        program, pvals_out, consts = self.partial_run_flat(f_jvp, pvals_in, "vjp")
        primal_pvals, _ = split_half(pvals_out)
        assert all(pval.is_known for pval in primal_pvals)
        primals_out_flat = [pval.const for pval in primal_pvals]
        transpose_inputs = consts + [PrimalProxy(p.aval) for p in tangent_pvals_in]
        f_vjp_flat = lambda *cts: self.run_program_transposed(program, transpose_inputs, cts)
        return primals_out_flat, f_vjp_flat

    def vjp(self, f, *primals_in, **static_args):
        primals_in_flat, in_tree = self.tree_flatten(primals_in)
        f, out_tree_store = self.flatten_fn(f, in_tree)
        primals_out_flat, f_vjp_flat = self.vjp_flat(f, *primals_in_flat, **static_args)
        primals_out = self.tree_unflatten(out_tree_store(), primals_out_flat)

        def f_vjp(*cotangents_out):
            cotangents_out_flat, _ = self.tree_flatten(cotangents_out)
            cotangents_in_flat = f_vjp_flat(*cotangents_out_flat)

            return self.tree_unflatten(in_tree, cotangents_in_flat)

        return primals_out, f_vjp

    def run_program_transposed(self, program: Program, args: List[Any], cotangents: List[Any], **others) -> List[Any]:
        primal_environment: Dict[Var, Any] = {}
        ct_environment: Dict[Var, Any] = {}

        def read_primal(x: Atom) -> Any:
            return primal_environment.get(x, PrimalProxy(x.aval)) if type(x) is Var else x.val

        def write_primal(v: Var, val: Any) -> None:
            if type(val) is not PrimalProxy:
                primal_environment[v] = val

        def read_cotangent(v: Var) -> Any:
            return ct_environment.pop(v, self.environment.zeros(v.aval.shape, v.aval.dtype))

        def write_cotangent(x: Atom, val: Any):
            if type(x) is Var and val is not None:
                ct_environment[x] = ct_environment[x] + val if x in ct_environment else val

        list_map(write_primal, program.in_binders, args)
        list_map(write_cotangent, program.outs, cotangents)
        # i = len(program.instructions)-1
        for instruction in program.instructions[::-1]:
            # print(i, instruction); i -= 1
            primals_in = list_map(read_primal, instruction.inputs)
            cts_in = list_map(read_cotangent, instruction.out_binders)
            inp, params = primals_in, instruction.params
            inp, params = instruction.op.reorg_args(inp, params)
            inp, params = instruction.op.args_fixer(*inp, **params)
            cts_out = instruction.op.T(cts_in, *inp, **params)
            list_map(write_cotangent, instruction.inputs, cts_out)

        ret = [read_cotangent(v) for v, x in list_zip(program.in_binders, args) if type(x) is PrimalProxy]

        return ret

    @lru_cache
    def transpose_program(self, program: Program, undef_primals: tuple[bool, ...]) -> tuple[Program, list[Any]]:
        avals_in, avals_out = self.typecheck_program(program)
        traceable = partial(self.run_program_transposed, program)
        args = [PrimalProxy(a) if u else a for a, u in zip(avals_in, undef_primals)]
        trans_program, consts, _ = self.make_program(
            traceable, tuple(args), tuple(avals_out), static_args=program.static_args, name=f"{program.name}_T"
        )
        self.typecheck_program(trans_program)

        return trans_program, consts

    def grad(self, f, *, ret_fval=False, argnums=(0,)):
        def gradfun(x, *xs, **static_args):
            y, f_vjp = self.vjp(f, x, *xs, **static_args)
            if np.shape(y) != ():
                raise TypeError
            x_bars = f_vjp(self.environment.ones(()))

            if ret_fval:
                return y, x_bars
            else:
                ret = tuple(x_bars[i] for i in argnums)
                if len(ret) == 1:
                    ret = ret[0]
                return ret

        if f.__qualname__ == "Machine.jit.<locals>.f_jitted":
            # unjit then jit back
            f = f.__closure__[0].cell_contents
            return self.jit(gradfun)
        else:
            return gradfun

    def jit(self, f, static_argnames=()):
        assert type(static_argnames) is tuple and all(type(s) is str for s in static_argnames)

        def f_jitted(*args, **static_args):
            static_args = tuple(static_args.items())
            for k, v in static_args:
                if k not in static_argnames:
                    raise TypeError("keyword args reserved for static_args")
            # sig = inspect.signature(f)
            # args_strs = [k for k, v in sig.parameters.items() if k != "self" and k not in static_argnames]
            # static_args_strs = [k for k, v in sig.parameters.items() if k != "self" and k in static_argnames]

            # if args:
            #     if len(args) > len(args_strs):
            #         assert static_args_strs
            #         args, rest = args[: len(args_strs)], args[len(args_strs) :]
            #         new_static_args = {
            #             k: rest_arg for k, rest_arg in zip(static_args_strs, rest) if k not in static_args
            #         }
            #         static_args = {**new_static_args, **static_args}
            # else:
            #     args = [static_args[k] if k in static_args else arg for k, arg in zip(args_strs, args)]
            # assert len(args) == len(args_strs)

            avals_in = self.tree_map(lambda x: Typecheckor.like(self.get_aval(x)), args)
            program, consts, out_tree = self.make_program(
                f, *avals_in, static_args=static_args, name=f"{f.__name__}_jit"
            )

            args, in_tree = self.tree_flatten(args)
            outs = self.bind(
                jit_op,
                *consts,
                *args,
                program=program,
            )
            return self.tree_unflatten(out_tree, outs)

        return f_jitted

    def jit_partial_run(self, trace, tracers, *, program):
        in_unknowns = [not t.pval.is_known for t in tracers]
        program1, program2, out_unknowns, num_res = self.partial_run_program(program, in_unknowns)
        known_tracers, unknown_tracers = partition_list(in_unknowns, tracers)
        known_vals = [t.pval.const for t in known_tracers]
        outs1_res = jit_op(*known_vals, program=program)
        outs1, res = split_list(outs1_res, len(program1.outs) - num_res)
        res_tracers = [trace.instantiate_const(self.full_raise(trace, x)) for x in res]
        outs2 = [PartialEvalTracor(trace, PartialValue.unknown(v.aval), None) for v in program2.outs]
        draft = InstructionDraft(
            jit_op,
            res_tracers + unknown_tracers,
            dict(program=program2),
            [v.aval for v in program2.outs],
            map(weakref.ref, outs2),
        )
        for t in outs2:
            t.draft = draft
        return merge_lists(out_unknowns, outs1, outs2)
