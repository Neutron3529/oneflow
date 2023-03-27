"""
Copyright 2020 The OneFlow Authors. All rights reserved.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

import unittest
from collections import OrderedDict

import numpy as np

from oneflow.test_utils.test_util import GenArgList

import oneflow as flow
import oneflow.unittest


def _test_equal_normal(test_case, device):
    input1 = flow.tensor(
        np.array([1, 1, 4]).astype(np.float32),
        dtype=flow.float32,
        device=flow.device(device),
    )
    input2 = flow.tensor(
        np.array([1, 2, 3]).astype(np.float32),
        dtype=flow.float32,
        device=flow.device(device),
    )
    of_out = flow.eq(input1, input2)
    np_out = np.equal(input1.numpy(), input2.numpy())
    test_case.assertTrue(np.array_equal(of_out.numpy(), np_out))


def _test_equal_int64(test_case, device):
    input1 = flow.tensor(
        np.array([1, 1, 4]).astype(np.int64),
        dtype=flow.int64,
        device=flow.device(device),
    )
    input2 = flow.tensor(
        np.array([1, 2, 3]).astype(np.int64),
        dtype=flow.int64,
        device=flow.device(device),
    )
    of_out = flow.eq(input1, input2)
    np_out = np.equal(input1.numpy(), input2.numpy())
    test_case.assertTrue(np.array_equal(of_out.numpy(), np_out))


def _test_equal_symbol(test_case, device):
    input1 = flow.tensor(
        np.array([1, 1, 4]).astype(np.float32),
        dtype=flow.float32,
        device=flow.device(device),
    )
    input2 = flow.tensor(
        np.array([1, 2, 3]).astype(np.float32),
        dtype=flow.float32,
        device=flow.device(device),
    )
    of_out = input1 == input2
    np_out = np.equal(input1.numpy(), input2.numpy())
    test_case.assertTrue(np.array_equal(of_out.numpy(), np_out))


def _test_equal_int_scalar(test_case, device):
    np_arr = np.random.randn(2, 3, 4, 5)
    input1 = flow.tensor(np_arr, dtype=flow.float32, device=flow.device(device))
    input2 = 1
    of_out = input1 == input2
    np_out = np.equal(np_arr, input2)
    test_case.assertTrue(np.array_equal(of_out.numpy(), np_out))


def _test_equal_int_tensor_int_scalar(test_case, device):
    np_arr = np.random.randint(2, size=(2, 3, 4, 5))
    input1 = flow.tensor(np_arr, dtype=flow.int, device=flow.device(device))
    input2 = 1
    of_out = input1 == input2
    np_out = np.equal(np_arr, input2)
    test_case.assertTrue(np.array_equal(of_out.numpy(), np_out))


def _test_equal_float_scalar(test_case, device):
    np_arr = np.random.randn(3, 2, 5, 7)
    input1 = flow.tensor(np_arr, dtype=flow.float32, device=flow.device(device))
    input2 = 2.3
    of_out = input1 == input2
    np_out = np.equal(np_arr, input2)
    test_case.assertTrue(np.array_equal(of_out.numpy(), np_out))


@flow.unittest.skip_unless_1n1d()
class TestEqual(flow.unittest.TestCase):
    def test_equal(test_case):
        arg_dict = OrderedDict()
        arg_dict["test_fun"] = [
            _test_equal_normal,
            _test_equal_int64,
            _test_equal_symbol,
            _test_equal_int_scalar,
            _test_equal_int_tensor_int_scalar,
            _test_equal_float_scalar,
        ]
        arg_dict["device"] = ["mlu"]
        for arg in GenArgList(arg_dict):
            arg[0](test_case, *arg[1:])


if __name__ == "__main__":
    unittest.main()
