import slope
from slope.core import Tensor, Typecheckor
from typing import Tuple

import operator as operator_py

from typing import Sequence, Callable, Union, Callable, NamedTuple
import math
import numpy as np

# ====================
# Module
# ====================


class Module:
    def __hash__(self):
        self_flat, tree = slope.tree_flatten(self)
        # TODO: also use tree to compute hash
        return hash(self_flat)

    def __eq__(self, other):
        if type(self) != type(other):
            return False
        return hash(self) == hash(other)

    def get_metadata(self):
        tensor_attrs = set()
        module_attrs = set()

        for k, v in self.__dict__.items():
            if isinstance(v, (Tensor, Typecheckor)):
                tensor_attrs.add(k)
            elif isinstance(v, (list, tuple)):
                v_flat, v_treedef = slope.tree_flatten(v)
                if all(isinstance(vi, (Tensor, Typecheckor)) for vi in v_flat):
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

    def get_attrs(self, attr_types, with_name=False):
        attrs = dict()
        for k, v in self.__dict__.items():
            if isinstance(v, attr_types):
                attrs[k] = v
            # elif isinstance(v, (list, tuple)):
            #     v_flat, v_treedef = slope.tree_flatten(v)
            #     if all(isinstance(vi, attr_types) for vi in v_flat):
            #         attrs[k] = v
        return attrs if with_name else tuple(attrs.values())

    def get_tensors(self, with_name=False):
        return self.get_attrs((Tensor, Typecheckor), with_name)

    def get_modules(self, with_name=False):
        return self.get_attrs(Module, with_name)

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

        for tensor, tensor_attr in tuple(zip(tuple(tensors), metadata["tensor_attrs"])):
            set_nested_attr(mod, tensor_attr, tensor)
        return mod


slope.M().register_node(Module, Module.flatten, Module.unflatten, "Module")
# slope.M().register_node(Module, Module.leaf_flatten, Module.leaf_unflatten, "Module")


# ====================
# Init
# ====================


def compute_fans(shape: Sequence, in_axis=-2, out_axis=-1, batch_axis=()):
    if isinstance(in_axis, int):
        in_size = shape[in_axis]
    else:
        in_size = int(np.prod([shape[i] for i in in_axis]))
    if isinstance(out_axis, int):
        out_size = shape[out_axis]
    else:
        out_size = int(np.prod([shape[i] for i in out_axis]))
    if isinstance(batch_axis, int):
        batch_size = shape[batch_axis]
    else:
        batch_size = int(np.prod([shape[i] for i in batch_axis]))
    receptive_field_size = math.prod(shape) / in_size / out_size / batch_size
    fan_in = in_size * receptive_field_size
    fan_out = out_size * receptive_field_size
    return fan_in, fan_out


def normal(dtype=slope.float32) -> Callable:
    def init(shape, dtype=dtype):
        return slope.randn(shape)

    return init


def variance_scaling(
    scale,
    mode: str,
    distribution: str,
    in_axis: Union[int, Sequence[int]] = -2,
    out_axis: Union[int, Sequence[int]] = -1,
    batch_axis: Sequence[int] = (),
    dtype=slope.float32,
) -> Callable:
    def init(shape, dtype=dtype):
        fan_in, fan_out = compute_fans(shape, in_axis, out_axis, batch_axis)
        if mode == "fan_in":
            denominator = fan_in
        elif mode == "fan_out":
            denominator = fan_out
        elif mode == "fan_avg":
            denominator = (fan_in + fan_out) / 2
        else:
            raise ValueError(f"invalid mode for variance scaling initializer: {mode}")
        variance = slope.tensor(scale / denominator, dtype=dtype)
        if distribution == "normal":
            return slope.randn(shape) * variance.sqrt()
        elif distribution == "uniform":
            return slope.rand(size=shape.astype(dtype)) * (3 * variance).sqrt()

        else:
            raise ValueError(f"invalid distribution for variance scaling initializer: {distribution}")

    return init


def glorot_normal(
    in_axis: Union[int, Sequence[int]] = -2,
    out_axis: Union[int, Sequence[int]] = -1,
    batch_axis: Sequence[int] = (),
    dtype=slope.float32,
) -> Callable:
    return variance_scaling(
        1.0,
        "fan_avg",
        "normal",
        in_axis=in_axis,
        out_axis=out_axis,
        batch_axis=batch_axis,
        dtype=dtype,
    )


def glorot_uniform(
    in_axis: Union[int, Sequence[int]] = -2,
    out_axis: Union[int, Sequence[int]] = -1,
    batch_axis: Sequence[int] = (),
    dtype=slope.float32,
) -> Callable:
    return variance_scaling(
        1.0,
        "fan_avg",
        "uniform",
        in_axis=in_axis,
        out_axis=out_axis,
        batch_axis=batch_axis,
        dtype=dtype,
    )


# ====================
# Layers
# ====================


class Linear(Module):
    # def __init__(self, in_dim, out_dim, bias=True, W_init=glorot_normal(), b_init=normal()):
    def __init__(self, in_dim, out_dim, bias=False, W_init=glorot_normal(), b_init=normal()):
        self.weight = W_init((out_dim, in_dim))
        self.bias = b_init((out_dim,)) if bias else None

    def __call__(self, x):
        x = x @ self.weight.transpose(-2,-1)
        return x + self.bias[None, ...] if self.bias is not None else x


class MLP(Module):
    def __init__(self, in_dim, hid_dim, out_dim):
        self.linear1 = Linear(in_dim, hid_dim)
        self.linear2 = Linear(hid_dim, out_dim)

    def __call__(self, x):
        x = self.linear1(x)
        x = x.relu()
        x = self.linear2(x)
        return x


class Fn(Module):
    def __init__(self, fn):
        self.fn = fn

    def __call__(self, x):
        return self.fn(x)


class Serial(Module):
    def __init__(self, modules):
        self.num_modules = len(modules)
        for i in range(len(modules)):
            setattr(self, f"m{i}", modules[i])

    def __call__(self, x):
        for i in range(self.num_modules):
            x = getattr(self, f"m{i}")(x)
        return x


#
# Optimizers
#


class Optimizer(Module):
    def __init__(self, params, lr: float):
        self.params = params
        self.params_flat, self.params_treedef = slope.tree_flatten(params)
        self.state = Module()
        self.hp = Module()
        self.hp.lr = slope.full((), lr)
        self.iters = slope.zeros(())

    def step(self, p, g, *state_attrs):
        return p, state_attrs

    def __call__(self, params, g_params):
        state_names, state_attrs = zip(*self.state.get_modules(with_name=True).items())
        step_out, (leaf0, leaf0_treedef) = slope.tree_map(self.step, params, *(g_params, *state_attrs), out_leaf=True)
        step_out_T = slope.tree_transpose(self.params_treedef, leaf0_treedef, step_out)
        params_out, state_attrs_out = step_out_T
        state = Module()
        for k, v in zip(state_names, state_attrs_out):
            setattr(state, k, v)
        self.state = state
        self.iters = self.iters + 1
        return (params_out, self)


class GD(Optimizer):
    def __init__(self, params, lr=0.001):
        super().__init__(params, lr)

    def step(self, p, g, *state_attrs):
        lr = self.hp.lr
        p = p - lr * g
        return p, state_attrs


class SGD(Optimizer):
    def __init__(self, params, lr=0.001, momentum: float = 0.9, weight_decay=0.0, nesterov=False):
        super().__init__(params, lr)
        self.hp.momentum = momentum
        self.hp.weight_decay = weight_decay
        self.hp.nesterov = nesterov
        self.state.b = slope.tree_map(lambda x: x.zeros_like(), self.params)

    def step(self, p, g, b):
        lr, m, wd = self.hp.lr, self.hp.momentum, self.hp.weight_decay
        g = g + wd * p
        b = m * b + g
        g = (g + m * b) if self.hp.nesterov else b
        p = p - lr * g
        return (p, (b,))


def AdamW(params: Tuple[Tensor], lr=0.001, b1=0.9, b2=0.999, eps=1e-8, wd=0.01):
    return LAMB(params, lr, b1, b2, eps, wd, adam=True)


def Adam(params: Tuple[Tensor], lr=0.001, b1=0.9, b2=0.999, eps=1e-8):
    return LAMB(params, lr, b1, b2, eps, 0.0, adam=True)


class LAMB(Optimizer):
    def __init__(self, params, lr=0.001, b1=0.9, b2=0.999, eps=1e-6, weight_decay=0.0, adam=False):
        super().__init__(params, lr)
        self.hp.b1 = b1
        self.hp.b2 = b2
        self.hp.eps = eps
        self.hp.wd = weight_decay
        self.hp.adam = adam
        self.state.m = slope.tree_map(lambda x: x.zeros_like(), self.params)
        self.state.v = slope.tree_map(lambda x: x.zeros_like(), self.params)

    def step(self, p, g, m, v):
        lr, wd, adam = self.hp.lr, self.hp.wd, self.hp.adam
        b1, b2, eps = self.hp.b1, self.hp.b2, self.hp.eps
        m = b1 * m + (1.0 - b1) * g
        v = b2 * v + (1.0 - b2) * (g * g)
        m_hat = m / (1.0 - b1**self.iters)
        v_hat = v / (1.0 - b2**self.iters)
        up = (m_hat / (v_hat.sqrt() + eps)) + wd * p
        if not adam:
            r1 = p.square().sum().sqrt()
            r2 = up.square().sum().sqrt()
            r = slope.where(r1 > 0, slope.where(r2 > 0, r1 / r2, 1.0), 1.0)
        else:
            r = 1.0
        p = p * lr * r * up
        state = Module()
        state.m = m
        state.v = v
        return p, state
