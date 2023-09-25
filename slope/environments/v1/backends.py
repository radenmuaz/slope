import slope
from slope.environments.v1.operators import operator_set
from slope.core import Backend, BaseArray, VoidArray, list_zip, list_map
import numpy as np
from typing import (
    List,
    Dict,
    Any,
)
import pickle
import math
import inspect
import re
from functools import partial
compile_py = compile
numpy_backend = Backend(
    name="numpy", default_dtype=BaseArray.float32, deps=("numpy as np", "math")
)
numpy_dtype_map = {
    BaseArray.float32: np.dtype("float32"),
    BaseArray.int64: np.dtype("int64"),
    BaseArray.int8: np.dtype("int8"),
    BaseArray.bool: np.dtype("bool"),
}
numpy_backend.set_dtype_map(numpy_dtype_map)

default_dtype_backend = numpy_backend.default_dtype_value


@numpy_backend.set_method
def set_numpy_of(self, array):
    return array.buf.val


@numpy_backend.set_method
def set_device_of(self, array):
    return "cpu"


@numpy_backend.set_method
def compile(self, codegen_out):
    code_lines = codegen_out["code_lines"]
    exec_locals = {}
    code = "\n".join(code_lines)
    exec(compile_py(code, "<string>", "exec"), self.deps_dict, exec_locals)
    fn = exec_locals["main"]
    return fn, code


@numpy_backend.set_method
def codegen(self, program, args, *, fn_name: str="main", depth=0, fn_defs = dict()) -> List[Any]:
    def indent(code_line, amount):
        spaces = " " * (len(code_line) - len(code_line.lstrip()))
        spaces += " " * amount
        return "\n".join([spaces + line for line in code_line.strip().split("\n")])
    # codegen is recursive if jit-of-jit happens
    environment: Dict[slope.Var, Any] = {}
    il0 = depth*4 # il = indent level
    il1 = (depth+1)*4
    ncs = 0
    nxs = 0
    nzs = 0
    inb_args = []
    inb_consts = []

    for inb in program.in_binders:
        if type(inb.aval) is not VoidArray:
            environment[inb] = f"c{ncs}"
            inb_consts += [environment[inb]]
            ncs += 1
        else:
            environment[inb] = f"x{nxs}"
            inb_args += [environment[inb]]
            nxs += 1

    code_lines = []    
    fn_args_strs = f""
    if inb_consts:
        fn_args_strs += f"{', '.join(inb_consts)}, "
    fn_args_strs += f"{', '.join(inb_args)}"
    code_lines += [indent(f"def {fn_name}({fn_args_strs}):", il0)]
    for instruction in program.instructions:
        in_vals = list_map(lambda x: environment[x], instruction.inputs)
        in_avals = [x.aval for x in instruction.inputs]
        for outb in instruction.out_binders:
            environment[outb] = f"z{nzs}"
            nzs += 1
        out_vals = list_map(lambda z: environment[z], instruction.out_binders)

        if instruction.op.op_type is slope.core.OperatorType.Meta:
            if instruction.op is slope.core.procedure_op:
                params = instruction.params
                proc_name, proc_program = params['name'], params['program']
                breakpoint()
                if proc_name not in fn_defs.keys():
                    proc_codegen_out = self.codegen(proc_program, args, 
                                        fn_name=proc_name,
                                        depth=depth + 1,
                                        fn_defs=fn_defs)
                    proc_code_lines = proc_codegen_out["code_lines"]
                    fn_defs = proc_codegen_out["fn_defs"]
                    fn_defs[proc_name] = proc_code_lines
                breakpoint()
                    
                args_str = ", ".join(in_vals)
                lhs = (
                    f"{out_vals[0] if len(out_vals) == 1 else ', '.join([o for o in out_vals])}"
                    )
                if len(params['static_args']) > 0:
                    for k, v in params.static_args:
                        args_str += f", {k}={v}"
                rhs = f"{proc_name}({args_str})"
                if len(proc_program.outs) == 1:
                    rhs += "[0]"
            else:
                raise
        else:
            impl = slope.M().backend.impls[instruction.op]
            args_str = ", ".join(in_vals)
            lhs = (
                f"{out_vals[0] if len(out_vals) == 1 else ', '.join([o for o in out_vals])}"
            )
            
            impl_lines = inspect.getsourcelines(impl)[0]
            if impl_lines[0][0] == "@":  # delete decorator line
                impl_lines = impl_lines[1:]

            if len(impl_lines) > 2:
                params = {
                    k: v if not isinstance(v, slope.core.DType) else self.dtype_map[v]
                    for k, v in instruction.params.items()
                }
                kwargs_str = ", ".join([f"{k}={v}" for k, v in params.items()])
                rhs = f"{instruction.op.name}({args_str}, {kwargs_str})"

                if instruction.op.name not in fn_defs.keys():
                    def_str = impl_lines[0]
                    impl_lines[0] = f"def {instruction.op.name}{def_str[def_str.find('('):]}"
                    impl_lines[0] = impl_lines[0].replace("self, ", "")
                    fn_defs[instruction.op.name] = [impl_lines]
            else:
                sig = inspect.signature(impl)
                args_strs = [
                    k
                    for k, v in sig.parameters.items()
                    if v.kind == inspect.Parameter.POSITIONAL_OR_KEYWORD and k != "self"
                ]
                rhs = impl_lines[1].replace("return", "").strip()

                for argname, arg in list_zip(args_strs, in_vals):
                    mark = (
                        ","
                        if argname != args_strs[-1] or len(instruction.params) > 0
                        else ")"
                    )
                    rhs = rhs.replace(f"{argname}{mark}", f"{arg}{mark}")
                for kwargname, kwarg in instruction.params.items():
                    if isinstance(kwarg, slope.core.DType):
                        kwarg = self.dtype_map[kwarg]
                    rhs = rhs.replace(f"={kwargname}", f"={kwarg}")
        code_line = f"{lhs} = {rhs}"
        code_lines += [indent(code_line, il1)]
    outs = list_map(lambda x: environment[x], program.outs)
    ret_str = f"{', '.join(outs)}{',' if len(outs)==1 else ''}"
    code_lines += [indent(f"return {ret_str}", il1)]
    
    if len(fn_defs) > 0:
        code_lines = (
            code_lines[0:1]
            + [
                indent(line, il0)
                for impl_lines in fn_defs.values()
                for line in impl_lines
            ]
            + code_lines[1:]
        )

    if depth == 0:
        code_lines = [indent(f"float32 = np.float32", il0)] + code_lines # TODO: cleanup dtype translation
    return dict(
        code_lines=code_lines, fn_defs=fn_defs
    )


### Operator Impls


@numpy_backend.set_impl(operator_set.convert)
def f(self, x, *, dtype):
    ret = x
    return ret.astype(dtype=dtype)


@numpy_backend.set_impl(operator_set.stop_gradient)
def f(self, x, *, dtype):
    return x


@numpy_backend.set_impl(operator_set.neg)
def f(self, x):
    return np.negative(x)


@numpy_backend.set_impl(operator_set.sqrt)
def f(self, x):
    return np.sqrt(x)


# @numpy_backend.set_impl(operator_set.relu)
# def f(self, x):
#     return np.maximum(x, 0)


@numpy_backend.set_impl(operator_set.exp)
def f(self, x):
    return np.exp(x)


@numpy_backend.set_impl(operator_set.log)
def f(self, x):
    return np.log(x)


@numpy_backend.set_impl(operator_set.sin)
def f(self, x):
    return np.sin(x)


@numpy_backend.set_impl(operator_set.add)
def f(self, x, y):
    return np.add(x, y)


@numpy_backend.set_impl(operator_set.sub)
def f(self, x, y):
    return np.subtract(x, y)


@numpy_backend.set_impl(operator_set.mul)
def f(self, x, y):
    return np.multiply(x, y)


@numpy_backend.set_impl(operator_set.div)
def f(self, x, y):
    return np.divide(x, y)


@numpy_backend.set_impl(operator_set.equal)
def f(self, x, y):
    return np.equal(x, y)


@numpy_backend.set_impl(operator_set.not_equal)
def f(self, x, y):
    return np.not_equal(x, y)


@numpy_backend.set_impl(operator_set.maximum)
def f(self, x, y):
    return np.maximum(x, y)


@numpy_backend.set_impl(operator_set.sum)
def f(self, x, *, axes=None, keepdims=False):
    return np.sum(x, axis=axes, keepdims=keepdims)


@numpy_backend.set_impl(operator_set.max)
def f(self, x, *, axes=None, keepdims=False):
    return np.max(x, axis=axes, keepdims=keepdims)


@numpy_backend.set_impl(operator_set.constant)
def f(self, val, *, dtype=default_dtype_backend):
    return np.array(val, dtype=dtype)


@numpy_backend.set_impl(operator_set.arange)
def f(self, *, start, stop, stride, dtype=default_dtype_backend):
    return np.arange(start=start, stop=stop, stride=stride, dtype=dtype)


@numpy_backend.set_impl(operator_set.full)
def f(self, *, shape, fill_value, dtype=default_dtype_backend):
    return np.full(shape=shape, fill_value=fill_value, dtype=dtype)


@numpy_backend.set_impl(operator_set.random_uniform)
def f(self, *, shape, dtype=default_dtype_backend):
    return np.random.uniform(size=shape).astype(dtype=dtype)


@numpy_backend.set_impl(operator_set.random_normal)
def f(self, *, shape, dtype=default_dtype_backend):
    return np.random.normal(loc=np.zeros(shape=shape)).astype(dtype=dtype)


@numpy_backend.set_impl(operator_set.broadcast_in_dim)
def f(self, x, *, shape, axes=None):
    ret = x
    if not axes is None:
        for a in sorted(axes):
            ret = np.expand_dims(ret, a)
    ret = np.broadcast_to(ret, shape)
    return ret


@numpy_backend.set_impl(operator_set.reshape)
def f(self, x, *, shape):
    return np.reshape(x, newshape=shape)

@numpy_backend.set_impl(operator_set.pad_hlo)
def f(self, x, *, lo, hi, interior, value):
    # TODO: implement interior pad
    return np.pad(x, list(zip(lo, hi)), constant_values=value)


@numpy_backend.set_impl(operator_set.slice_hlo)
def f(self, x, *, starts, limits, strides):
    slices = tuple(slice(s, l, st) for s, l, st in zip(starts, limits, strides))
    return x[slices]


@numpy_backend.set_impl(operator_set.concatenate)
def f(self, xs, *, axes):
    return np.concatenate(xs, axes)


@numpy_backend.set_impl(operator_set.transpose)
def f(self, x, *, perm):  # NOTE: np.transpose is like torch.permute
    return np.transpose(x, axes=perm)


@numpy_backend.set_impl(operator_set.flip)
def f(self, x, *, axes):
    return np.flip(x, axes)

# def inline():
    # if instruction.op.op_dtype is slope.core.OperatorType.Meta:
        #     # TODO: generalize interface to other than jit_op
        #     raise NotImplementedError
        #     breakpoint()
        #     op_out = impl(in_vals, in_avals, params=instruction.params)
        #     co = op_out["codegen_out"]
        #     outs = co["outs"]
        #     rhs = f"{outs[0] if len(outs) == 1 else ', '.join([o for o in outs])}"
        #     op_code_lines = co["code_lines"]
        #     input_lhs = ", ".join((co["inb_args"] + co["inb_consts"]))
        #     input_code_line = f"{input_lhs} = {args_str}"
        #     output_code_line = f"{lhs} = {rhs}"
        #     code_lines += [input_code_line] + op_code_lines + [output_code_line]
        #     continue