import copy

import unittest
from unittest.mock import patch
import math
import numpy as np
import os
import sys

import torch
from torch import nn
import torch.nn.functional as F
import torch.optim as optim
import torch_xla
import torch_xla.debug.metrics as met
import torch_xla.runtime as xr
import torch_xla.core.xla_model as xm
import torch_xla.debug.metrics as met
import torch_xla.distributed.spmd as xs
from torch_xla.distributed.spmd import XLAShardedTensor
import test_xla_sharding_base

import torch_xla.core.xla_env_vars as xenv
import torch_xla.utils.utils as xu
from torch_xla._internal import tpu


class XlaAutoShardingTest(test_xla_sharding_base.XlaShardingTest):

  @classmethod
  def setUpClass(cls):
    xr.use_spmd(auto=True)
    super().setUpClass()

  @unittest.skipUnless(xr.device_type() in ["TPU", "CPU"],
                       "Auto-sharding currently supports TPU device.")
  def test_matmul(self):
    met.clear_counters()
    t1 = torch.ones(64, 128)
    t2 = torch.ones(128, 256)
    t3 = (t1 @ t2).sum()

    xt1 = t1.to(xm.xla_device())
    xt2 = t2.to(xm.xla_device())
    xt3 = (xt1 @ xt2).sum()
    xm.mark_step()
    self.assertEqual(met.counter_value("CompileWithAutoSharding"), 1)
    self.assertTrue(torch.allclose(t3, xt3.cpu()))

  @unittest.skipUnless(xr.device_type() in ["TPU", "CPU"],
                       "Auto-sharding currently supports TPU device.")
  def test_simple_linear_training(self):
    met.clear_counters()

    model = self.SimpleLinear().to(xm.xla_device())
    model.train()
    optimizer = optim.SGD(model.parameters(), lr=0.1)
    data = torch.randn(128, 128).to(xm.xla_device())
    target = torch.zeros(128).to(xm.xla_device())
    loss_fn = nn.CrossEntropyLoss()
    for i in range(5):
      optimizer.zero_grad()
      output = model(data)
      loss = loss_fn(output, target)
      loss.backward()
      optimizer.step()
      xm.mark_step()

    self.assertEqual(met.counter_value("UncachedCompile"), 3)
    self.assertEqual(met.counter_value("CachedCompile"), 2)
    self.assertEqual(met.counter_value("CompileWithAutoSharding"), 3)


if __name__ == '__main__':
  test = unittest.main()
  sys.exit(0 if test.result.wasSuccessful() else 1)