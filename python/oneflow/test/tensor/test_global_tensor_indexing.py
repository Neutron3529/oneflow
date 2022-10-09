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

# This test code is referenced from: https://github.com/pytorch/pytorch/blob/cd41c8f032dd06c445bf97fc76fb82008b19afcb/test/test_indexing.py

import unittest

import numpy as np

import oneflow as flow
from oneflow.test_utils.automated_test_util import *
import oneflow.unittest


def _randint(low, high):
    """
    Get a random integer in the range [low, high).
    """
    return random(low, high).to(int).value()


def _cpu_global_tensor(tensor):
    return tensor.to_global(flow.env.all_device_placement("cpu"), flow.sbp.broadcast)


def _assert_tensor_equal(test_case, tensor1, tensor2, atol=0.0, rtol=0.0):
    test_case.assertTrue(
        np.allclose(tensor1.numpy(), tensor2.numpy(), atol, rtol),
        f"{tensor1.numpy()} vs {tensor2.numpy()}",
    )


def global_broadcast_consec(size, start=1):
    """
    Generate a arithmetic progression with given size and start value.
    """
    sequence = flow.ones([int(np.array(size).prod(0)),]).cumsum(0)
    sequence.add_(start - 1)
    return _cpu_global_tensor(sequence.view(*size))


def _test_basic_slice(test_case, placement):
    broadcast_for_placement = [flow.sbp.broadcast,] * len(placement.ranks.shape)

    ref_sbp = random_sbp(placement, max_dim=3).value()
    reference = global_broadcast_consec((8, 8, 8)).to_global(placement, ref_sbp)

    # empty tensor indexing
    _assert_tensor_equal(
        test_case,
        reference[
            _cpu_global_tensor(flow.LongTensor()).to_global(
                placement, broadcast_for_placement
            )
        ],
        flow.empty(0, 8, 8),
        atol=0,
        rtol=0,
    )

    _assert_tensor_equal(
        test_case, reference[0], global_broadcast_consec((8, 8)), atol=0, rtol=0
    )
    _assert_tensor_equal(
        test_case, reference[1], global_broadcast_consec((8, 8), 65), atol=0, rtol=0
    )
    _assert_tensor_equal(
        test_case, reference[2], global_broadcast_consec((8, 8), 129), atol=0, rtol=0
    )
    _assert_tensor_equal(
        test_case, reference[0, 1], global_broadcast_consec((8,), 9), atol=0, rtol=0
    )
    _assert_tensor_equal(
        test_case, reference[0:2], global_broadcast_consec((2, 8, 8)), atol=0, rtol=0
    )
    test_case.assertEqual(reference[2, 2, 2].item(), 147)
    _assert_tensor_equal(
        test_case, reference[:], global_broadcast_consec((8, 8, 8)), atol=0, rtol=0
    )

    # indexing with Ellipsis
    _assert_tensor_equal(
        test_case,
        reference[..., 2, 2],
        flow.tensor([19, 83, 147, 211, 275, 339, 403, 467]),
        atol=0,
        rtol=0,
    )
    _assert_tensor_equal(
        test_case,
        reference[0, ..., 2],
        flow.tensor([3, 11, 19, 27, 35, 43, 51, 59]),
        atol=0,
        rtol=0,
    )
    _assert_tensor_equal(
        test_case, reference[..., 2], reference[:, :, 2], atol=0, rtol=0
    )
    _assert_tensor_equal(
        test_case, reference[0, ..., 2], reference[0, :, 2], atol=0, rtol=0
    )
    _assert_tensor_equal(
        test_case, reference[0, 2, ...], reference[0, 2], atol=0, rtol=0
    )
    test_case.assertEqual(reference[..., 2, 2, 2].item(), 147)
    test_case.assertEqual(reference[2, ..., 2, 2].item(), 147)
    test_case.assertEqual(reference[2, 2, ..., 2].item(), 147)
    test_case.assertEqual(reference[2, 2, 2, ...].item(), 147)
    _assert_tensor_equal(test_case, reference[...], reference, atol=0, rtol=0)

    reference_5d = global_broadcast_consec((8, 8, 8, 8, 8)).to_global(
        placement, sbp=random_sbp(placement, max_dim=5).value()
    )
    _assert_tensor_equal(
        test_case, reference_5d[..., 1, 0], reference_5d[:, :, :, 1, 0], atol=0, rtol=0
    )
    _assert_tensor_equal(
        test_case,
        reference_5d[2, ..., 1, 0],
        reference_5d[2, :, :, 1, 0],
        atol=0,
        rtol=0,
    )
    _assert_tensor_equal(
        test_case,
        reference_5d[2, 1, 0, ..., 1],
        reference_5d[2, 1, 0, :, 1],
        atol=0,
        rtol=0,
    )
    _assert_tensor_equal(test_case, reference_5d[...], reference_5d, atol=0, rtol=0)

    # LongTensor indexing
    sbp = random_sbp(placement, max_dim=3).value()
    reference = global_broadcast_consec((8, 8, 8)).to_global(placement, sbp)
    idx = _cpu_global_tensor(flow.LongTensor([2, 4])).to_global(
        placement, broadcast_for_placement
    )
    _assert_tensor_equal(
        test_case, reference[idx], flow.stack([reference[2], reference[4]])
    )

    # None indexing
    _assert_tensor_equal(test_case, reference[2, None], reference[2].unsqueeze(0))
    _assert_tensor_equal(
        test_case, reference[2, None, None], reference[2].unsqueeze(0).unsqueeze(0)
    )
    _assert_tensor_equal(test_case, reference[2:4, None], reference[2:4].unsqueeze(1))
    _assert_tensor_equal(
        test_case,
        reference[None, 2, None, None],
        reference.unsqueeze(0)[:, 2].unsqueeze(0).unsqueeze(0),
    )
    _assert_tensor_equal(
        test_case,
        reference[None, 2:5, None, None],
        reference.unsqueeze(0)[:, 2:5].unsqueeze(2).unsqueeze(2),
    )

    # indexing 0-length slice
    _assert_tensor_equal(test_case, flow.empty(0, 8, 8), reference[slice(0)])
    _assert_tensor_equal(test_case, flow.empty(0, 8), reference[slice(0), 2])
    _assert_tensor_equal(test_case, flow.empty(0, 8), reference[2, slice(0)])
    _assert_tensor_equal(test_case, flow.tensor([]), reference[2, 1:1, 2])

    # indexing with step
    sbp = random_sbp(placement, max_dim=3).value()
    reference = global_broadcast_consec((8, 8, 8)).to_global(placement, sbp)
    _assert_tensor_equal(
        test_case, reference[1:5:2], flow.stack([reference[1], reference[3]], 0)
    )
    _assert_tensor_equal(
        test_case,
        reference[1:6:2],
        flow.stack([reference[1], reference[3], reference[5]], 0),
    )
    _assert_tensor_equal(
        test_case, reference[1:9:4], flow.stack([reference[1], reference[5]], 0)
    )
    _assert_tensor_equal(
        test_case,
        reference[2:4, 1:5:2],
        flow.stack([reference[2:4, 1], reference[2:4, 3]], 1),
    )
    _assert_tensor_equal(
        test_case,
        reference[3, 1:6:2],
        flow.stack([reference[3, 1], reference[3, 3], reference[3, 5]], 0),
    )
    _assert_tensor_equal(
        test_case,
        reference[None, 2, 1:9:4],
        flow.stack([reference[2, 1], reference[2, 5]], 0).unsqueeze(0),
    )
    _assert_tensor_equal(
        test_case,
        reference[:, 2, 1:6:2],
        flow.stack([reference[:, 2, 1], reference[:, 2, 3], reference[:, 2, 5]], 1),
    )

    #  random check
    lst = [
        list(range(i, i + 16)) for i in range(0, 256, 16)
    ]  # arange(64).reshape(8, 8)
    tensor = _cpu_global_tensor(flow.DoubleTensor(lst))
    for _ in range(5):
        sbp = random_sbp(placement, max_dim=2).value()
        cur_tensor = tensor.to_global(placement, sbp)

        idx1_start = _randint(0, 16)
        idx1_end = idx1_start + _randint(1, 16 - idx1_start + 1)
        idx1_step = _randint(1, 14)
        idx1 = slice(idx1_start, idx1_end, idx1_step)
        if _randint(0, 2) == 0:
            idx2_start = _randint(0, 16)
            idx2_end = idx2_start + _randint(1, 16 - idx2_start + 1)
            idx2_step = _randint(1, 14)
            idx2 = slice(idx2_start, idx2_end, idx2_step)
            lst_indexed = [l[idx2] for l in lst[idx1]]
            tensor_indexed = cur_tensor[idx1, idx2]
        else:
            lst_indexed = lst[idx1]
            tensor_indexed = cur_tensor[idx1]
        _assert_tensor_equal(test_case, flow.DoubleTensor(lst_indexed), tensor_indexed)

    # error check
    sbp = random_sbp(placement, max_dim=3).value()
    reference = global_broadcast_consec((8, 8, 8)).to_global(placement, sbp)
    test_case.assertRaises(RuntimeError, lambda: reference[1:9:0])
    test_case.assertRaises(RuntimeError, lambda: reference[1:9:-1])

    test_case.assertRaises(IndexError, lambda: reference[1, 1, 1, 1])
    test_case.assertRaises(IndexError, lambda: reference[1, 1, 1, 1:1])
    test_case.assertRaises(IndexError, lambda: reference[3, 3, 3, 3, 3, 3, 3, 3])

    test_case.assertRaises(IndexError, lambda: reference[0.0])
    test_case.assertRaises(RuntimeError, lambda: reference[0.0:2.0])
    test_case.assertRaises(IndexError, lambda: reference[0.0, 0.0:2.0])
    test_case.assertRaises(IndexError, lambda: reference[0.0, :, 0.0:2.0])
    test_case.assertRaises(IndexError, lambda: reference[0.0, ..., 0.0:2.0])
    test_case.assertRaises(IndexError, lambda: reference[0.0, :, 0.0])


def _test_advanced_indexing(test_case, placement, dtype):
    broadcast_for_placement = [flow.sbp.broadcast] * len(placement.ranks.shape)

    # pick a random valid indexer type
    def ri(indices):
        choice = _randint(0, 2)
        if choice == 0:
            return _cpu_global_tensor(flow.LongTensor(indices)).to_global(
                placement, broadcast_for_placement
            )
        elif choice == 1:
            return list(indices)
        else:
            return tuple(indices)

    def validate_indexing(x):
        _assert_tensor_equal(test_case, x[[0]], global_broadcast_consec((1,)))
        _assert_tensor_equal(test_case, x[ri([0]),], global_broadcast_consec((1,)))
        _assert_tensor_equal(test_case, x[ri([3]),], global_broadcast_consec((1,), 4))
        _assert_tensor_equal(test_case, x[[2, 3, 4]], global_broadcast_consec((3,), 3))
        _assert_tensor_equal(
            test_case, x[ri([2, 3, 4]),], global_broadcast_consec((3,), 3)
        )
        _assert_tensor_equal(
            test_case, x[ri([0, 2, 4]),], flow.tensor([1, 3, 5], dtype=dtype),
        )

    def validate_setting(x):
        x[[0]] = -2
        _assert_tensor_equal(test_case, x[[0]], flow.tensor([-2], dtype=dtype))
        x[[0]] = -1
        _assert_tensor_equal(test_case, x[ri([0]),], flow.tensor([-1], dtype=dtype))
        x[[2, 3, 4]] = 4
        _assert_tensor_equal(
            test_case, x[[2, 3, 4]], flow.tensor([4, 4, 4], dtype=dtype)
        )
        x[ri([2, 3, 4]),] = 3
        _assert_tensor_equal(
            test_case, x[ri([2, 3, 4]),], flow.tensor([3, 3, 3], dtype=dtype),
        )
        x[ri([0, 2, 4]),] = _cpu_global_tensor(flow.tensor([5, 4, 3], dtype=dtype))
        _assert_tensor_equal(
            test_case, x[ri([0, 2, 4]),], flow.tensor([5, 4, 3], dtype=dtype),
        )

    # 1d tensor and integer index setitem and getitem
    sbp = random_sbp(placement, max_dim=1).value()
    reference = global_broadcast_consec((8,)).to_global(placement, sbp)
    validate_indexing(reference)
    validate_setting(reference)

    # reference is  1  2  3  4  5  6  7  8
    #               9 10 11 12 13 14 15 16
    #              17 18 19 20 21 22 23 24
    #              25 26 27 28 29 30 31 32
    #              33 34 35 36 37 38 39 40
    #              41 42 43 44 45 46 47 48
    #              49 50 51 52 53 54 55 56
    #              57 58 59 60 61 62 63 64
    sbp = random_sbp(placement, max_dim=2).value()
    reference = global_broadcast_consec((8, 8)).to_global(placement, sbp)
    _assert_tensor_equal(
        test_case,
        reference[ri([0, 1, 2]), ri([0])],
        flow.tensor([1, 9, 17], dtype=dtype),
    )
    _assert_tensor_equal(
        test_case,
        reference[ri([0, 1, 2]), ri([1])],
        flow.tensor([2, 10, 18], dtype=dtype),
    )
    _assert_tensor_equal(
        test_case, reference[ri([0]), ri([0])], global_broadcast_consec((1,))
    )
    _assert_tensor_equal(
        test_case, reference[ri([2]), ri([1])], global_broadcast_consec((1,), 18)
    )
    _assert_tensor_equal(
        test_case,
        reference[[ri([0, 0]), ri([0, 1])]],
        flow.tensor([1, 2], dtype=dtype),
    )
    _assert_tensor_equal(
        test_case,
        reference[[ri([0, 1, 1, 0, 2, 7]), ri([1])]],
        flow.tensor([2, 10, 10, 2, 18, 58], dtype=dtype),
    )
    _assert_tensor_equal(
        test_case,
        reference[[ri([0, 0, 1, 1]), ri([0, 1, 0, 0])]],
        flow.tensor([1, 2, 9, 9], dtype=dtype),
    )

    rows = ri([[0, 0], [1, 6]])
    columns = ([0],)
    _assert_tensor_equal(
        test_case,
        reference[rows, columns],
        flow.tensor([[1, 1], [9, 49]], dtype=dtype),
    )

    rows = ri([[0, 0], [1, 6]])
    columns = ri([6, 0])
    _assert_tensor_equal(
        test_case,
        reference[rows, columns],
        flow.tensor([[7, 1], [15, 49]], dtype=dtype),
    )
    rows = ri([[0, 0], [1, 2]])
    columns = ri([[0, 1], [3, 7]])
    _assert_tensor_equal(
        test_case,
        reference[rows, columns],
        flow.tensor([[1, 2], [12, 24]], dtype=dtype),
    )

    # setting values
    reference[ri([0]), ri([1])] = -1
    _assert_tensor_equal(
        test_case, reference[ri([0]), ri([1])], flow.tensor([-1], dtype=dtype),
    )
    reference[ri([0, 1, 2]), ri([0])] = _cpu_global_tensor(
        flow.tensor([-1, 2, -4], dtype=dtype)
    ).to_global(placement, broadcast_for_placement)
    _assert_tensor_equal(
        test_case,
        reference[ri([0, 1, 2]), ri([0])],
        flow.tensor([-1, 2, -4], dtype=dtype),
    )
    reference[rows, columns] = _cpu_global_tensor(
        flow.tensor([[4, 6], [2, 3]], dtype=dtype)
    ).to_global(placement, broadcast_for_placement)
    _assert_tensor_equal(
        test_case, reference[rows, columns], flow.tensor([[4, 6], [2, 3]], dtype=dtype),
    )

    # Tests using less than the number of dims, and ellipsis
    # reference is  1  2  3  4  5  6  7  8
    #               9 10 11 12 13 14 15 16
    #              17 18 19 20 21 22 23 24
    #              25 26 27 28 29 30 31 32
    #              33 34 35 36 37 38 39 40
    #              41 42 43 44 45 46 47 48
    #              49 50 51 52 53 54 55 56
    #              57 58 59 60 61 62 63 64
    sbp = random_sbp(placement, max_dim=2).value()
    reference = global_broadcast_consec((8, 8)).to_global(placement, sbp)
    _assert_tensor_equal(
        test_case,
        reference[ri([0, 2]),],
        flow.tensor(
            [[1, 2, 3, 4, 5, 6, 7, 8], [17, 18, 19, 20, 21, 22, 23, 24]], dtype=dtype
        ),
    )
    _assert_tensor_equal(
        test_case,
        reference[ri([1]), ...],
        flow.tensor([[9, 10, 11, 12, 13, 14, 15, 16]], dtype=dtype),
    )
    _assert_tensor_equal(
        test_case,
        reference[..., ri([1])],
        flow.tensor([[2], [10], [18], [26], [34], [42], [50], [58]], dtype=dtype),
    )

    # verify too many indices fails
    with test_case.assertRaises(IndexError):
        reference[ri([1]), ri([0, 2]), ri([3])]

    # test invalid index fails
    sbp = random_sbp(placement, max_dim=1).value()
    reference = _cpu_global_tensor(flow.empty(8, dtype=dtype)).to_global(placement, sbp)
    for err_idx in (10, -11):
        with test_case.assertRaisesRegex(IndexError, r"out of bounds"):
            reference[err_idx]


def _test_combined_indexing(test_case, placement, dtype):
    broadcast_for_placement = [flow.sbp.broadcast,] * len(placement.ranks.shape)

    def tensor_indices_to_np(tensor, indices):
        # convert the flow Tensor to a numpy array
        npt = tensor.numpy()

        # convert indices
        idxs = tuple(
            i.tolist() if isinstance(i, flow.LongTensor) else i for i in indices
        )

        return npt, idxs

    def get_numpy(tensor, indices):
        npt, idxs = tensor_indices_to_np(tensor, indices)

        # index and return as a oneflow local Tensor
        return flow.tensor(npt[idxs], dtype=dtype)

    def set_numpy(tensor, indices, value):
        if not isinstance(value, int):
            value = value.numpy()

        npt, idxs = tensor_indices_to_np(tensor, indices)
        npt[idxs] = value
        return npt

    def assert_get_eq(tensor, indexer):
        _assert_tensor_equal(test_case, tensor[indexer], get_numpy(tensor, indexer))

    def assert_set_eq(tensor, indexer, val):
        pyt = tensor.clone()
        np_ref = tensor.clone()
        pyt[indexer] = val
        np_ref = flow.tensor(set_numpy(np_ref, indexer, val), dtype=dtype)
        _assert_tensor_equal(test_case, pyt, np_ref)

    def assert_backward_eq(tensor, indexer):
        # compare gradient between cpu and cuda
        cpu = (
            tensor.float()
            .clone()
            .detach()
            .to_global(placement, broadcast_for_placement)
            .requires_grad_()
        )
        outcpu = cpu.clone()[indexer]
        outcpu.sum().backward()
        dev = (
            cpu.detach()
            .to_global(
                placement, random_sbp(placement, max_dim=len(tensor.shape)).value()
            )
            .requires_grad_(True)
        )
        outdev = dev[indexer]
        outdev.sum().backward()
        _assert_tensor_equal(test_case, cpu.grad, dev.grad)

    def get_set_tensor(indexed, indexer):
        set_size = indexed[indexer].size()
        set_count = indexed[indexer].numel()
        set_tensor = _cpu_global_tensor(
            flow.arange(set_count, 0, -1).view(set_size).to(dtype)
        ).to_global(placement, broadcast_for_placement)
        return set_tensor

    # Tensor is  1  2  3  4  5  6  7  8
    #            9  10 11 12 13 14 15 16
    #            17 18 19 20 21 22 23 24
    #            25 26 27 28 29 30 31 32
    #            33 34 35 36 37 38 39 40
    #            41 42 43 44 45 46 47 48
    #            49 50 51 52 53 54 55 56
    #            57 58 59 60 61 62 63 64
    sbp = random_sbp(placement, max_dim=2).value()
    reference = global_broadcast_consec((8, 8)).to_global(placement, sbp)

    indices_to_test = [
        # grab the second, fourth columns
        [slice(None), [4, 6]],
        # first, third rows,
        [[0, 6], slice(None)],
        # TODO(wyg): only support getitem but not setitem
        #  # weird shape
        #  [slice(None), [[0, 1],
        #                 [2, 3]]],
        # negatives
        [[-1], [0]],
        [[0, 7], [-1]],
        [slice(None), [-1]],
    ]

    # test getitem
    get_indices_to_test = indices_to_test + [[slice(None), [0, 1, 1, 2, 2]]]
    get_indices_to_test = indices_to_test + [
        [slice(None), [[0, 1], [2, 3]]]
    ]  # TODO: test setitem
    for indexer in get_indices_to_test:
        assert_get_eq(reference, indexer)
        if placement.type != "cpu":
            assert_backward_eq(reference, indexer)

    # test setitem
    for indexer in indices_to_test:
        assert_set_eq(reference, indexer, 44)
        assert_set_eq(reference, indexer, get_set_tensor(reference, indexer))

    #########################
    # test more dims tensor #
    #########################
    sbp = random_sbp(placement, max_dim=3).value()
    reference = global_broadcast_consec((8, 8, 8), 0).float().to_global(placement, sbp)

    indices_to_test = [
        [slice(None), slice(None), [0, 3, 4]],
        [slice(None), [2, 4, 5, 7], slice(None)],
        [[2, 3], slice(None), slice(None)],
        [slice(None), [0, 2, 3], [1, 3, 4]],
        [slice(None), [0], [1, 2, 4]],
        [slice(None), [0, 1, 3], [4]],
        [slice(None), [[0, 1], [1, 0]], [[2, 3]]],
        [slice(None), [[0, 1], [2, 3]], [[0]]],
        [slice(None), [[5, 6]], [[0, 3], [4, 4]]],
        [[0, 2, 3], [1, 3, 4], slice(None)],
        [[0], [1, 2, 4], slice(None)],
        [[0, 1, 3], [4], slice(None)],
        [[[0, 1], [1, 0]], [[2, 1], [3, 5]], slice(None)],
        [[[0, 1], [1, 0]], [[2, 3]], slice(None)],
        [[[0, 1], [2, 3]], [[0]], slice(None)],
        [[[2, 1]], [[0, 3], [4, 4]], slice(None)],
        [[[2]], [[0, 3], [4, 1]], slice(None)],
        # non-contiguous indexing subspace
        [[0, 2, 3], slice(None), [1, 3, 4]],
        # less dim, ellipsis
        [[0, 2],],
        [[0, 2], slice(None)],
        [[0, 2], Ellipsis],
        [[0, 2], slice(None), Ellipsis],
        [[0, 2], Ellipsis, slice(None)],
        [[0, 2], [1, 3]],
        [[0, 2], [1, 3], Ellipsis],
        [Ellipsis, [1, 3], [2, 3]],
        [Ellipsis, [2, 3, 4]],
        [Ellipsis, slice(None), [2, 3, 4]],
        [slice(None), Ellipsis, [2, 3, 4]],
        # ellipsis counts for nothing
        [Ellipsis, slice(None), slice(None), [0, 3, 4]],
        [slice(None), Ellipsis, slice(None), [0, 3, 4]],
        [slice(None), slice(None), Ellipsis, [0, 3, 4]],
        [slice(None), slice(None), [0, 3, 4], Ellipsis],
        [Ellipsis, [[0, 1], [1, 0]], [[2, 1], [3, 5]], slice(None)],
        [[[0, 1], [1, 0]], [[2, 1], [3, 5]], Ellipsis, slice(None)],
        [[[0, 1], [1, 0]], [[2, 1], [3, 5]], slice(None), Ellipsis],
    ]

    for indexer in indices_to_test:
        assert_get_eq(reference, indexer)
        assert_set_eq(reference, indexer, 212)
        assert_set_eq(reference, indexer, get_set_tensor(reference, indexer))
        if placement.type != "cpu":
            assert_backward_eq(reference, indexer)

    sbp = random_sbp(placement, max_dim=4).value()
    reference = (
        global_broadcast_consec((8, 8, 8, 8), 0).float().to_global(placement, sbp)
    )

    indices_to_test = [
        [slice(None), slice(None), slice(None), [0, 3, 4]],
        [slice(None), slice(None), [2, 4, 5, 7], slice(None)],
        [slice(None), [2, 3], slice(None), slice(None)],
        [[1, 2], slice(None), slice(None), slice(None)],
        [slice(None), slice(None), [0, 2, 3], [1, 3, 4]],
        [slice(None), slice(None), [0], [1, 2, 4]],
        [slice(None), slice(None), [0, 1, 3], [4]],
        [slice(None), slice(None), [[0, 1], [1, 0]], [[2, 3]]],
        [slice(None), slice(None), [[0, 1], [2, 3]], [[0]]],
        [slice(None), slice(None), [[5, 6]], [[0, 3], [4, 4]]],
        [slice(None), [0, 2, 3], [1, 3, 4], slice(None)],
        [slice(None), [0], [1, 2, 4], slice(None)],
        [slice(None), [0, 1, 3], [4], slice(None)],
        [slice(None), [[0, 1], [3, 4]], [[2, 3], [0, 1]], slice(None)],
        [slice(None), [[0, 1], [3, 4]], [[2, 3]], slice(None)],
        [slice(None), [[0, 1], [3, 2]], [[0]], slice(None)],
        [slice(None), [[2, 1]], [[0, 3], [6, 4]], slice(None)],
        [slice(None), [[2]], [[0, 3], [4, 2]], slice(None)],
        [[0, 1, 2], [1, 3, 4], slice(None), slice(None)],
        [[0], [1, 2, 4], slice(None), slice(None)],
        [[0, 1, 2], [4], slice(None), slice(None)],
        [[[0, 1], [0, 2]], [[2, 4], [1, 5]], slice(None), slice(None)],
        [[[0, 1], [1, 2]], [[2, 0]], slice(None), slice(None)],
        [[[2, 2]], [[0, 3], [4, 5]], slice(None), slice(None)],
        [[[2]], [[0, 3], [4, 5]], slice(None), slice(None)],
        [slice(None), [3, 4, 6], [0, 2, 3], [1, 3, 4]],
        [slice(None), [2, 3, 4], [1, 3, 4], [4]],
        [slice(None), [0, 1, 3], [4], [1, 3, 4]],
        [slice(None), [6], [0, 2, 3], [1, 3, 4]],
        [slice(None), [2, 3, 5], [3], [4]],
        [slice(None), [0], [4], [1, 3, 4]],
        [slice(None), [6], [0, 2, 3], [1]],
        [slice(None), [[0, 3], [3, 6]], [[0, 1], [1, 3]], [[5, 3], [1, 2]]],
        [[2, 2, 1], [0, 2, 3], [1, 3, 4], slice(None)],
        [[2, 0, 1], [1, 2, 3], [4], slice(None)],
        [[0, 1, 2], [4], [1, 3, 4], slice(None)],
        [[0], [0, 2, 3], [1, 3, 4], slice(None)],
        [[0, 2, 1], [3], [4], slice(None)],
        [[0], [4], [1, 3, 4], slice(None)],
        [[1], [0, 2, 3], [1], slice(None)],
        [[[1, 2], [1, 2]], [[0, 1], [2, 3]], [[2, 3], [3, 5]], slice(None)],
        # less dim, ellipsis
        [Ellipsis, [0, 3, 4]],
        [Ellipsis, slice(None), [0, 3, 4]],
        [Ellipsis, slice(None), slice(None), [0, 3, 4]],
        [slice(None), Ellipsis, [0, 3, 4]],
        [slice(None), slice(None), Ellipsis, [0, 3, 4]],
        [slice(None), [0, 2, 3], [1, 3, 4]],
        [slice(None), [0, 2, 3], [1, 3, 4], Ellipsis],
        [Ellipsis, [0, 2, 3], [1, 3, 4], slice(None)],
        [[0], [1, 2, 4]],
        [[0], [1, 2, 4], slice(None)],
        [[0], [1, 2, 4], Ellipsis],
        [[0], [1, 2, 4], Ellipsis, slice(None)],
        [[1],],
        [[0, 2, 1], [3], [4]],
        [[0, 2, 1], [3], [4], slice(None)],
        [[0, 2, 1], [3], [4], Ellipsis],
        [Ellipsis, [0, 2, 1], [3], [4]],
    ]

    for indexer in indices_to_test:
        assert_get_eq(reference, indexer)
        assert_set_eq(reference, indexer, 1333)
        assert_set_eq(reference, indexer, get_set_tensor(reference, indexer))
    indices_to_test += [
        [slice(None), slice(None), [[0, 1], [1, 0]], [[2, 3], [3, 0]]],
        [slice(None), slice(None), [[2]], [[0, 3], [4, 4]]],
    ]
    for indexer in indices_to_test:
        assert_get_eq(reference, indexer)
        assert_set_eq(reference, indexer, 1333)
        if placement.type != "cpu":
            assert_backward_eq(reference, indexer)


def _test_single_int(test_case, placement):
    sbp = random_sbp(placement, max_dim=1).value()
    v = _cpu_global_tensor(flow.zeros(8, 7, 3)).to_global(placement, sbp)
    test_case.assertEqual(v[2].shape, (7, 3))
    test_case.assertEqual(v[6].shape, (7, 3))


def _test_multiple_int(test_case, placement):
    sbp = random_sbp(placement, max_dim=3).value()
    v = _cpu_global_tensor(flow.zeros(8, 8, 8)).to_global(placement, sbp)
    test_case.assertEqual(v[4, :, 1].shape, (8,))


def _test_none(test_case, placement):
    sbp = random_sbp(placement, max_dim=3).value()
    v = _cpu_global_tensor(flow.zeros(8, 8, 8)).to_global(placement, sbp)
    test_case.assertEqual(v[None].shape, (1, 8, 8, 8))
    test_case.assertEqual(v[:, None].shape, (8, 1, 8, 8))
    test_case.assertEqual(v[:, None, None].shape, (8, 1, 1, 8, 8))
    test_case.assertEqual(v[..., None].shape, (8, 8, 8, 1))


def _test_step(test_case, placement):
    sbp = random_sbp(placement, max_dim=1).value()
    v = _cpu_global_tensor(flow.arange(8)).to_global(placement, sbp)
    _assert_tensor_equal(test_case, v[::1], v)
    test_case.assertEqual(v[::2].tolist(), [0, 2, 4, 6])
    test_case.assertEqual(v[::3].tolist(), [0, 3, 6])
    test_case.assertEqual(v[::11].tolist(), [0])
    test_case.assertEqual(v[1:6:2].tolist(), [1, 3, 5])


def _test_step_assignment(test_case, placement):
    broadcast_for_placement = [flow.sbp.broadcast,] * len(placement.ranks.shape)
    sbp = random_sbp(placement, max_dim=2).value()
    v = _cpu_global_tensor(flow.zeros(8, 8)).to_global(placement, sbp)
    v[0, 1::2] = _cpu_global_tensor(flow.tensor([3.0, 4.0, 5.0, 6.0])).to_global(
        placement, broadcast_for_placement
    )
    test_case.assertEqual(v[0].tolist(), [0.0, 3.0, 0.0, 4.0, 0.0, 5.0, 0.0, 6.0])
    test_case.assertEqual(v[1:].sum(), 0)


def _test_bool_indices(test_case, placement):
    broadcast_for_placement = [flow.sbp.broadcast,] * len(placement.ranks.shape)
    sbp = random_sbp(placement, max_dim=3).value()
    v = global_broadcast_consec((8, 8, 8)).to_global(placement, sbp)
    boolIndices = _cpu_global_tensor(
        flow.tensor(
            [True, False, True, True, False, False, False, True], dtype=flow.bool
        )
    ).to_global(placement, broadcast_for_placement)
    test_case.assertEqual(v[boolIndices].shape, (4, 8, 8))
    _assert_tensor_equal(
        test_case, v[boolIndices], flow.stack([v[0], v[2], v[3], v[7]])
    )


def _test_multiple_bool_indices(test_case, placement):
    broadcast_for_placement = [flow.sbp.broadcast,] * len(placement.ranks.shape)
    sbp = random_sbp(placement, max_dim=2).value()
    v = global_broadcast_consec((8, 8, 4)).to_global(placement, sbp)
    # NOTE: these broadcast together and are transposed to the first dim
    mask1 = _cpu_global_tensor(
        flow.tensor([1, 0, 1, 0, 0, 1, 0, 0], dtype=flow.bool)
    ).to_global(placement, broadcast_for_placement)
    mask2 = _cpu_global_tensor(flow.tensor([1, 1, 1, 0], dtype=flow.bool)).to_global(
        placement, broadcast_for_placement
    )
    test_case.assertEqual(v[mask1, :, mask2].shape, (3, 8))


def _test_int_indices(test_case, placement):
    sbp = random_sbp(placement, max_dim=3).value()
    v = global_broadcast_consec((8, 8, 8)).to_global(placement, sbp)
    test_case.assertEqual(v[[0, 4, 2]].shape, (3, 8, 8))
    test_case.assertEqual(v[:, [0, 4, 2]].shape, (8, 3, 8))
    test_case.assertEqual(v[:, [[0, 1], [4, 3]]].shape, (8, 2, 2, 8))


def _test_int_indices2d(test_case, placement):
    broadcast_for_placement = [flow.sbp.broadcast,] * len(placement.ranks.shape)
    sbp = random_sbp(placement, max_dim=2).value()
    x = global_broadcast_consec((8, 8)).to_global(placement, sbp)
    rows = _cpu_global_tensor(flow.tensor([[0, 0], [6, 3]])).to_global(
        placement, broadcast_for_placement
    )
    columns = _cpu_global_tensor(flow.tensor([[0, 2], [0, 7]])).to_global(
        placement, broadcast_for_placement
    )
    test_case.assertEqual(x[rows, columns].tolist(), [[1, 3], [49, 32]])


def _test_int_indices_broadcast(test_case, placement):
    broadcast_for_placement = [flow.sbp.broadcast,] * len(placement.ranks.shape)
    sbp = random_sbp(placement, max_dim=2).value()
    x = global_broadcast_consec((8, 8)).to_global(placement, sbp)
    rows = _cpu_global_tensor(flow.tensor([0, 7])).to_global(
        placement, broadcast_for_placement
    )
    columns = _cpu_global_tensor(flow.tensor([7, 2])).to_global(
        placement, broadcast_for_placement
    )
    result = x[rows[:, None], columns]
    test_case.assertEqual(result.tolist(), [[8, 3], [64, 59]])


def _test_empty_index(test_case, placement):
    broadcast_for_placement = [flow.sbp.broadcast,] * len(placement.ranks.shape)
    sbp = random_sbp(placement, max_dim=2).value()
    x = global_broadcast_consec((8, 8)).to_global(placement, sbp)
    idx = _cpu_global_tensor(flow.tensor([], dtype=flow.long)).to_global(
        placement, broadcast_for_placement
    )
    test_case.assertEqual(x[idx].numel(), 0)

    # empty assignment should have no effect but not throw an exception
    y = x.clone()
    y[idx] = -1
    _assert_tensor_equal(test_case, x, y)

    mask = _cpu_global_tensor(flow.zeros(8, 8).to(flow.bool)).to_global(
        placement, broadcast_for_placement
    )
    y[mask] = -1
    _assert_tensor_equal(test_case, x, y)


def _test_empty_ndim_index(test_case, placement):
    broadcast_for_placement = [flow.sbp.broadcast,] * len(placement.ranks.shape)
    sbp = random_sbp(placement, max_dim=1).value()
    x = global_broadcast_consec((8,)).to_global(placement, sbp)
    _assert_tensor_equal(
        test_case,
        x[
            _cpu_global_tensor(flow.empty(0, 2, dtype=flow.int64)).to_global(
                placement, broadcast_for_placement
            )
        ],
        flow.empty(0, 2),
    )

    sbp = random_sbp(placement, max_dim=1).value()
    x = _cpu_global_tensor(flow.empty(8, 0)).to_global(placement, sbp)
    test_case.assertEqual(x[[1, 2]].shape, (2, 0))
    test_case.assertEqual(x[[], []].shape, (0,))
    test_case.assertEqual(x[[[]]].shape, (0, 0))
    test_case.assertEqual(x[[[[]]]].shape, (1, 0, 0))
    test_case.assertEqual(x[[1], []].shape, (0,))
    test_case.assertEqual(x[[], [2]].shape, (0,))
    with test_case.assertRaisesRegex(IndexError, "for dimension with size 0"):
        x[:, [0, 1]]


def _test_empty_ndim_index_bool(test_case, placement):
    broadcast_for_placement = [flow.sbp.broadcast,] * len(placement.ranks.shape)
    sbp = random_sbp(placement, max_dim=1).value()
    x = global_broadcast_consec((8,)).to_global(placement, sbp)
    test_case.assertRaises(
        IndexError,
        lambda: x[
            _cpu_global_tensor(flow.empty(0, 2, dtype=flow.uint8)).to_global(
                placement, broadcast_for_placement
            )
        ],
    )


def _test_empty_slice(test_case, placement):
    sbp = random_sbp(placement, max_dim=1).value()
    x = global_broadcast_consec((8, 8, 8, 8)).to_global(placement, sbp)
    y = x[:, :, :, 1]
    z = y[:, 1:1, :]
    test_case.assertEqual((8, 0, 8), z.shape)


def _test_index_getitem_copy_bools_slices(test_case, placement):
    broadcast_for_placement = [flow.sbp.broadcast,] * len(placement.ranks.shape)
    false = _cpu_global_tensor(flow.tensor(0, dtype=flow.uint8)).to_global(
        placement, broadcast_for_placement
    )

    sbp = random_sbp(placement, max_dim=1).value()
    tensor = global_broadcast_consec((8, 8)).to_global(placement, sbp)

    _assert_tensor_equal(test_case, flow.empty(0, *tensor.shape), tensor[False])
    _assert_tensor_equal(test_case, flow.empty(0, *tensor.shape), tensor[false])


def _test_setitem_scalars(test_case, placement):
    broadcast_for_placement = [flow.sbp.broadcast,] * len(placement.ranks.shape)
    zero = _cpu_global_tensor(flow.tensor(0, dtype=flow.int64)).to_global(
        placement, broadcast_for_placement
    )

    # non-scalar indexed with scalars
    a = global_broadcast_consec((8, 8)).to_global(
        placement, random_sbp(placement, max_dim=2).value()
    )
    a_set_with_number = a.clone()
    a_set_with_scalar = a.clone()
    b = global_broadcast_consec((8,), 233).to_global(
        placement, random_sbp(placement, max_dim=1).value()
    )

    a_set_with_number[0] = b
    a_set_with_scalar[zero] = b
    _assert_tensor_equal(test_case, a_set_with_number, a_set_with_scalar)
    a[1, zero] = 7.7
    value = a[1, 0].numpy()
    test_case.assertEqual(np.array(7.7, dtype=value.dtype), value)

    np_x = np.zeros((8, 8))
    np_x[0, 6] = 1.0
    x = _cpu_global_tensor(flow.tensor(np_x)).to_global(
        placement, random_sbp(placement, max_dim=2).value()
    )
    x[0, 6] = 1.0
    test_case.assertEqual(x.numpy().all(), np_x.all())

    # scalar indexed with scalars
    r = _cpu_global_tensor(flow.tensor(1.0)).to_global(
        placement, random_sbp(placement, max_dim=0).value()
    )
    with test_case.assertRaises(IndexError):
        r[:] = 8.8
    with test_case.assertRaises(IndexError):
        r[zero] = 8.8
    r[...] = 9.9
    test_case.assertEqual(r, 9.9)

    # scalar indexed with oneflow.Size([1])
    np_x = np.zeros((8, 8))
    np_x[0, 6] = np.ones(1)
    x = _cpu_global_tensor(flow.tensor(np_x)).to_global(
        placement, random_sbp(placement, max_dim=2).value()
    )
    x[0, 0] = _cpu_global_tensor(flow.ones(1).to(flow.float64)).to_global(
        placement, broadcast_for_placement
    )
    test_case.assertEqual(x.numpy().all(), np_x.all())


def _test_basic_advanced_combined(test_case, placement):
    sbp = random_sbp(placement, max_dim=2).value()
    x = global_broadcast_consec((8, 8)).to_global(placement, sbp)
    _assert_tensor_equal(test_case, x[1:2, 3:5], x[1:2, [3, 4]])
    test_case.assertEqual(x[1:2, 1:3].tolist(), [[10, 11]])

    # Check that it is a copy
    unmodified = x.clone()
    x[1:2, [1, 2]].zero_()
    _assert_tensor_equal(test_case, x, unmodified)

    # But assignment should modify the original
    unmodified = x.clone()
    x[1:2, [1, 2]] = 0
    test_case.assertFalse(np.array_equal(x.numpy(), unmodified.numpy()))


def _test_ellipsis_tensor(test_case, placement):
    broadcast_for_placement = [flow.sbp.broadcast,] * len(placement.ranks.shape)
    sbp = random_sbp(placement, max_dim=2).value()
    x = global_broadcast_consec((8, 8)).to_global(placement, sbp)
    idx = _cpu_global_tensor(flow.tensor([0, 7])).to_global(
        placement, broadcast_for_placement
    )
    test_case.assertEqual(
        x[..., idx].tolist(),
        [[1, 8], [9, 16], [17, 24], [25, 32], [33, 40], [41, 48], [49, 56], [57, 64]],
    )
    test_case.assertEqual(
        x[idx, ...].tolist(),
        [[1, 2, 3, 4, 5, 6, 7, 8], [57, 58, 59, 60, 61, 62, 63, 64]],
    )

    # Test scalar ellipsis getitem
    x_scalar = _cpu_global_tensor(flow.tensor(9.9)).to_global(
        placement, broadcast_for_placement
    )
    test_case.assertEqual(x_scalar[...], 9.9)


class TestGlobalIndexing(flow.unittest.TestCase):
    @globaltest
    def test_global_slice(test_case):
        for placement in all_placement():
            for _ in range(5):
                _test_basic_slice(test_case, placement)
                _test_advanced_indexing(test_case, placement, dtype=flow.float32)
                _test_combined_indexing(test_case, placement, dtype=flow.float32)
                _test_single_int(test_case, placement)
                _test_multiple_int(test_case, placement)
                _test_none(test_case, placement)
                _test_step(test_case, placement)
                _test_step_assignment(test_case, placement)
                _test_bool_indices(test_case, placement)
                _test_multiple_bool_indices(test_case, placement)
                _test_int_indices(test_case, placement)
                _test_int_indices2d(test_case, placement)
                _test_int_indices_broadcast(test_case, placement)
                _test_empty_index(test_case, placement)
                _test_empty_ndim_index(test_case, placement)
                _test_empty_ndim_index_bool(test_case, placement)
                _test_empty_slice(test_case, placement)
                _test_index_getitem_copy_bools_slices(test_case, placement)
                _test_setitem_scalars(test_case, placement)
                _test_basic_advanced_combined(test_case, placement)
                _test_ellipsis_tensor(test_case, placement)


if __name__ == "__main__":
    unittest.main()
