# A set of code samples showing different usage of the ONNX Runtime Python API
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

import numpy as np
import onnxruntime
import onnx
# from onnx import parser, printer

MODEL_FILE = '.model.onnx'
DEVICE_NAME = 'cpu'
DEVICE_INDEX = 0
DEVICE=f'{DEVICE_NAME}:{DEVICE_INDEX}'
SIZE = (1, 3, 32, 32)


model_text = """
<
   ir_version: 9,
   opset_import: ["" : 15]
>
agraph (int64[] x) => (int64[] y) {
   c = Constant <value = true> ()
   y= And(c)
}

"""

model = onnx.parser.parse_model(model_text)
# onnx.checker.check_model(model)
model_text = onnx.printer.to_text(model)
print(model_text)

path = "/tmp/model.onnx"
onnx.save_model(model, path)
sess= onnxruntime.InferenceSession(path,  providers=['CPUExecutionProvider'])
input = dict(x=np.array([True]))
output_names = ['y']
out = sess.run(output_names, input)
for o in out:
    print(f"{o.shape=}\n{o=}")


model_text = """
<
   ir_version: 9,
   opset_import: ["" : 15]
>
agraph (int64[] l) => (int64[] y) {
   s=Constant <value_int = 0> ()
   d=Constant <value_int = 1> ()
   y= Range(s, l, d)
}

"""

model = onnx.parser.parse_model(model_text)
# onnx.checker.check_model(model)
model_text = onnx.printer.to_text(model)
print(model_text)

path = "/tmp/model.onnx"
onnx.save_model(model, path)
sess= onnxruntime.InferenceSession(path,  providers=['CPUExecutionProvider'])
input = dict(l=np.array([5]))
output_names = ['y']
out = sess.run(output_names, input)
for o in out:
    print(f"{o.shape=}\n{o=}")

# model_text = """
# <
#    ir_version: 9,
#    opset_import: ["" : 15, "slope" : 1]
# >
# agraph (int64[] shape) => (float[] y, float[] z,) {
#    one = Constant <value = float[1] {1}> ()
#    y, z = slope.full (one, shape)
# }
# <
#   domain: "slope",
#   opset_import: ["" : 1]
# >
# full (x, shape) => (y, z)
# {
#    y = Expand (x, shape)
#    z = x
# }
# """

# model = onnx.parser.parse_model(model_text)
# # onnx.checker.check_model(model)
# model_text = onnx.printer.to_text(model)
# print(model_text)

# path = "/tmp/model.onnx"
# onnx.save_model(model, path)
# sess= onnxruntime.InferenceSession(path,  providers=['CPUExecutionProvider'])
# input = dict()
# output_names = ['y']
# out = sess.run(output_names, input)
# for o in out:
#     print(f"{o.shape=}\n{o=}")
    

# model_text = """
# <ir_version: 9, opset_import: ["" : 17, "slope" : 1]>
# model () => (float[] y) {
#    y = Constant <value = float[1] {1.0} > ()
# }
# """

# model = onnx.parser.parse_model(model_text)
# # onnx.checker.check_model(model)
# model_text = onnx.printer.to_text(model)
# print(model_text)

# path = "/tmp/model.onnx"
# onnx.save_model(model, path)
# sess= onnxruntime.InferenceSession(path,  providers=['CPUExecutionProvider'])
# input = dict()
# output_names = ['y']
# out = sess.run(output_names, input)
# for o in out:
#     print(f"{o.shape=}\n{o=}")
    
# model_text = """
# <ir_version: 9, opset_import: ["" : 17, "slope" : 1]>
# model () => (float[] y) {
#    y = Constant <value = float[1] {1}> ()
# }
# """

# model = onnx.parser.parse_model(model_text)
# model_text = onnx.printer.to_text(model)
# print(model_text)

# path = "/tmp/model.onnx"
# onnx.save_model(model, path)
# sess= onnxruntime.InferenceSession(path,  providers=['CPUExecutionProvider'])
# input = dict()
# output_names = ['y']
# out = sess.run(output_names, input)
# for o in out:
#     print(f"{o.shape=}\n{o=}")

# model_text = """
# <ir_version: 9, opset_import: ["" : 17, "slope" : 1]>
# model (int64[] shape) => (float[] y) {
#    y = slope.ones (shape)
# }

# <domain: "slope", opset_import: ["" : 17]>
# full (x, shape) => (y)
# {
#    y = Expand (x, shape)
# }

# <domain: "slope", opset_import: ["" : 17, "slope" : 1]>
# ones (shape) => (y)
# {
#    one = Constant <value = float[1] {1}> ()
# y = slope.full(one, shape)
# }
# """
# model = onnx.parser.parse_model(model_text)
# model_text = onnx.printer.to_text(model)
# print(model_text)

# path = "/tmp/model.onnx"
# onnx.save_model(model, path)
# sess= onnxruntime.InferenceSession(path,  providers=['CPUExecutionProvider'])
# input = dict( shape=np.array([2]) )
# output_names = ['y']
# out = sess.run(output_names, input)
# for o in out:
#     print(f"{o.shape=}\n{o=}")

# onnx.checker.checkm _model(model)
