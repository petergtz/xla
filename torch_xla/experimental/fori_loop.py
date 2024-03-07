import numpy as np
import torch
import torch_xla
import torch_xla.core.xla_builder as xb
import torch_xla.core.xla_model as xm
import torch_xla.utils.utils as xu
import torch_xla.core.xla_op_registry as xor

from torch._C import DispatchKey
from torch._ops import HigherOrderOperator
import torch._higher_order_ops.while_loop
from torch._higher_order_ops.while_loop import while_loop_op


def fori_loop(lower, upper, body_fun, init_val):

  # device = xm.xla_device()
  # upper_placeholder = torch.ones(1, dtype=torch.int32, device=device)
  # upper_placeholder[0] = upper

  # lower_placeholder = torch.ones(1, dtype=torch.int32, device=device)
  # lower_placeholder[0] = lower

  # example data:
  # init_val = torch.tensor([0], dtype=torch.int32, device=device)
  # lower = torch.tensor([0], dtype=torch.int32, device=device)
  # upper = torch.tensor([10], dtype=torch.int32, device=device)
  limit_range = upper - lower

  # iterator = lower_placeholder

  def cond_fn(init, limit_range):
    return limit_range[0] >= init[0]
  
  def body_fn(init, limit_range):
    one_value = torch.ones(1, dtype=torch.int32, device=device)
    return (body_fun(init, one_value), limit_range.clone())

  def body_fn(operands): # iterator, init_val):
    # iterator[0] = iterator[0] - 1 # one = torch.ones(1, dtype=torch.int32, device=device) torch.sub(iterator[0] - one)
    # return body_fun(iterator, init_val)
    operands[0][0] = iterator[0] - 1 # one = torch.ones(1, dtype=torch.int32, device=device) torch.sub(iterator[0] - one)
    return body_fun(operands[0], operands[1])

  return while_loop(cond_fn, body_fn, (init_val, limit_range))


@while_loop_op.py_impl(DispatchKey.XLA)
def while_loop(cond_fn, body_fn, operands):
  # cond_fn&body_fn: callable
  # operands: (Tuple of possibly nested dict/list/tuple of tensors)
  return _xla_while_loop(cond_fn, body_fn, operands)


def _xla_while_loop(cond_fn, body_fn, operands):

  # create inputs placeholder
  kwargs = {}
  shapes = xb.tensor_shape(operands)
  builder = xb.create_builder('test_while')
  params = []
  for shape in shapes:
    p = xb.mkparam(builder, len(params), shape)
    params.append(p)

  # generate cond_fn xlacomputation
  cond_result = cond_fn(operands[0], operands[1])
  cond_ctx = torch_xla._XLAC.lowering.LoweringContext()
  cond_ctx.set_name_string("condctx")
  cond_ctx.build([cond_result])
  cond_hlo = cond_ctx.hlo()
  cond_computation = xb.computation_from_module_proto("condcomputation",
                                                      cond_hlo)

  # generate body_fn xlacomputation
  body_result = body_fn(operands[0], operands[1])
  body_ctx = torch_xla._XLAC.lowering.LoweringContext()
  body_ctx.set_name_string("bodyctx")
  body_ctx.build(list(body_result))
  body_hlo = body_ctx.hlo()
  body_computation = xb.computation_from_module_proto("bodycomputation",
                                                      body_hlo)

  # generate while xlacomputation
  input_tuple = xb.Op.tuple(tuple(params))
  w = xb.mkop(
      'While', (input_tuple.op,),
      condition_computation=cond_computation,
      body_computation=body_computation)
  name = 'fori_loop_ed_torch_func'
  computation = w.build(name)

  # gain final result with generated while xlacomputation
  result = torch_xla._XLAC._xla_user_computation('xla::_op_test_while',
                                                 tuple(operands), computation)

  return result
