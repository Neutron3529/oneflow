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
import math
from typing import Optional, Tuple, Union

import oneflow as flow


def interpolate(
    input,
    size=None,
    scale_factor=None,
    mode="nearest",
    align_corners=None,
    recompute_scale_factor=None,
):
    r"""The interface is consistent with PyTorch.    
    
    The documentation is referenced from: https://pytorch.org/docs/1.10/_modules/torch/nn/functional.html#interpolate.
    

    Down/up samples the input to either the given :attr:`size` or the given
    :attr:`scale_factor`

    The algorithm used for interpolation is determined by :attr:`mode`.

    Currently temporal, spatial and volumetric sampling are supported, i.e.
    expected inputs are 3-D, 4-D or 5-D in shape.

    The input dimensions are interpreted in the form:
    `mini-batch x channels x [optional depth] x [optional height] x width`.

    The modes available for resizing are: `nearest`, `linear` (3D-only),
    `bilinear`, `bicubic` (4D-only), `trilinear` (5D-only), `area`

    Args:
        input (Tensor): the input tensor
        size (int or Tuple[int] or Tuple[int, int] or Tuple[int, int, int]):
            output spatial size.
        scale_factor (float or Tuple[float]): multiplier for spatial size. Has to match input size if it is a tuple.
        mode (str): algorithm used for upsampling:
            ``'nearest'`` | ``'linear'`` | ``'bilinear'`` | ``'bicubic'`` |
            ``'trilinear'`` | ``'area'``. Default: ``'nearest'``
        align_corners (bool, optional): Geometrically, we consider the pixels of the
            input and output as squares rather than points.
            If set to ``True``, the input and output tensors are aligned by the
            center points of their corner pixels, preserving the values at the corner pixels.
            If set to ``False``, the input and output tensors are aligned by the corner
            points of their corner pixels, and the interpolation uses edge value padding
            for out-of-boundary values, making this operation *independent* of input size
            when :attr:`scale_factor` is kept the same. This only has an effect when :attr:`mode`
            is ``'linear'``, ``'bilinear'``, ``'bicubic'`` or ``'trilinear'``.
            Default: ``False``
        recompute_scale_factor (bool, optional): recompute the scale_factor for use in the
            interpolation calculation.  When `scale_factor` is passed as a parameter, it is used
            to compute the `output_size`.  If `recompute_scale_factor` is ``False`` or not specified,
            the passed-in `scale_factor` will be used in the interpolation computation.
            Otherwise, a new `scale_factor` will be computed based on the output and input sizes for
            use in the interpolation computation (i.e. the computation will be identical to if the computed
            `output_size` were passed-in explicitly).  Note that when `scale_factor` is floating-point,
            the recomputed scale_factor may differ from the one passed in due to rounding and precision
            issues.

    .. note::
        With ``mode='bicubic'``, it's possible to cause overshoot, in other words it can produce
        negative values or values greater than 255 for images.
        Explicitly call ``result.clamp(min=0, max=255)`` if you want to reduce the overshoot
        when displaying the image.

    .. warning::
        With ``align_corners = True``, the linearly interpolating modes
        (`linear`, `bilinear`, and `trilinear`) don't proportionally align the
        output and input pixels, and thus the output values can depend on the
        input size. This was the default behavior for these modes up to version
        0.3.1. Since then, the default behavior is ``align_corners = False``.
        See :class:`~torch.nn.Upsample` for concrete examples on how this
        affects the outputs.

    .. warning::
        When scale_factor is specified, if recompute_scale_factor=True,
        scale_factor is used to compute the output_size which will then
        be used to infer new scales for the interpolation.

    For example:

    .. code-block:: python

        >>> import oneflow as flow
        >>> import numpy as np
        
        >>> input = flow.tensor(np.arange(1, 5).reshape((1, 1, 4)), dtype=flow.float32)
        >>> output = flow.nn.functional.interpolate(input, scale_factor=2.0, mode="linear")
        >>> output
        tensor([[[1.0000, 1.2500, 1.7500, 2.2500, 2.7500, 3.2500, 3.7500, 4.0000]]],
               dtype=oneflow.float32)

    """
    if isinstance(scale_factor, tuple):
        scale_factor = tuple((float(factor) for factor in scale_factor))
    else:
        scale_factor = float(scale_factor) if scale_factor else None
    if mode in ("nearest", "area") and align_corners is not None:
        raise ValueError(
            "align_corners option can only be set with the interpolating modes: linear | bilinear | bicubic | trilinear"
        )
    if align_corners == None:
        align_corners = False
    align_corners = align_corners
    height_scale = None
    width_scale = None
    if isinstance(scale_factor, float):
        height_scale = scale_factor
        width_scale = scale_factor
    elif isinstance(scale_factor, tuple):
        height_scale = scale_factor[0]
        width_scale = scale_factor[1]
    else:
        pass
    if mode not in ("nearest", "bilinear", "linear", "area", "bicubic", "trilinear",):
        raise ValueError(
            'interpolation must be "nearest" or "bilinear" or "linear" or "area" or "bicubic" or "trilinear".'
        )
    if mode == "nearest" and align_corners:
        raise ValueError('interpolation "nearest" does not support align_corners.')

    if len(input.shape) == 3 and mode == "bilinear":
        raise NotImplementedError("Got 3D input, but bilinear mode needs 4D input")
    if len(input.shape) == 3 and mode == "trilinear":
        raise NotImplementedError("Got 3D input, but trilinear mode needs 5D input")
    if len(input.shape) == 4 and mode == "linear":
        raise NotImplementedError("Got 4D input, but linear mode needs 3D input")
    if len(input.shape) == 4 and mode == "trilinear":
        raise NotImplementedError("Got 4D input, but trilinear mode needs 5D input")
    if len(input.shape) == 5 and mode == "linear":
        raise NotImplementedError("Got 5D input, but linear mode needs 3D input")
    if len(input.shape) == 5 and mode == "bilinear":
        raise NotImplementedError("Got 5D input, but bilinear mode needs 4D input")

    dim = len(input.shape) - 2
    if size is not None and scale_factor is not None:
        raise ValueError("only one of size or scale_factor should be defined")
    elif size is not None:
        assert scale_factor is None
        scale_factors = []
        if isinstance(size, (list, tuple)):
            if len(size) != dim:
                raise ValueError(
                    "size shape must match input shape. Input is {}D, size is {}".format(
                        dim, len(size)
                    )
                )
            output_size = size
        else:
            output_size = [size for _ in range(dim)]
        for i in range(dim):
            scale_factors.append(output_size[i] / input.shape[i + 2])
    elif scale_factor is not None:
        assert size is None
        output_size = None
        if isinstance(scale_factor, (list, tuple)):
            if len(scale_factor) != dim:
                raise ValueError(
                    "scale_factor shape must match input shape. Input is {}D, scale_factor is {}".format(
                        dim, len(scale_factor)
                    )
                )
            scale_factors = scale_factor
        else:
            scale_factors = [scale_factor for _ in range(dim)]
    else:
        raise ValueError("either size or scale_factor should be defined")
    if recompute_scale_factor and size is not None:
        raise ValueError(
            "recompute_scale_factor is not meaningful with an explicit size."
        )
    if mode == "area" and output_size is None:
        recompute_scale_factor = True
    if recompute_scale_factor is True:
        assert scale_factors is not None
        output_size = [
            int(math.floor(float(input.size(i + 2)) * scale_factors[i]))
            for i in range(dim)
        ]
        scale_factors = []
        for i in range(dim):
            scale_factors.append(output_size[i] / input.shape[2 + i])
    if len(input.shape) == 3 and mode == "nearest":
        return flow._C.upsample_nearest_1d(
            input,
            scale_factor=scale_factors[0],
            output_size=output_size,
            data_format="channels_first",
        )
    if len(input.shape) == 4 and mode == "nearest":
        return flow._C.upsample_nearest_2d(
            input,
            height_scale=scale_factors[0],
            width_scale=scale_factors[1],
            output_size=output_size,
            data_format="channels_first",
        )
    if len(input.shape) == 5 and mode == "nearest":
        return flow._C.upsample_nearest_3d(
            input,
            depth_scale=scale_factors[0],
            height_scale=scale_factors[1],
            width_scale=scale_factors[2],
            output_size=output_size,
            data_format="channels_first",
        )
    if len(input.shape) == 3 and mode == "area":
        assert output_size is not None
        return flow._C.adaptive_avg_pool1d(input, output_size)
    if len(input.shape) == 4 and mode == "area":
        assert output_size is not None
        return flow._C.adaptive_avg_pool2d(input, output_size)
    if len(input.shape) == 5 and mode == "area":
        assert output_size is not None
        return flow._C.adaptive_avg_pool3d(input, output_size)
    if len(input.shape) == 3 and mode == "linear":
        assert align_corners is not None
        return flow._C.upsample_linear_1d(
            input,
            scale_factor=scale_factors[0],
            align_corners=align_corners,
            output_size=output_size,
            data_format="channels_first",
        )
    if len(input.shape) == 4 and mode == "bilinear":
        assert align_corners is not None
        return flow._C.upsample_bilinear_2d(
            input,
            height_scale=scale_factors[0],
            width_scale=scale_factors[1],
            align_corners=align_corners,
            output_size=output_size,
            data_format="channels_first",
        )
    if len(input.shape) == 4 and mode == "bicubic":
        assert align_corners is not None
        return flow._C.upsample_bicubic_2d(
            input,
            height_scale=scale_factors[0],
            width_scale=scale_factors[1],
            align_corners=align_corners,
            output_size=output_size,
            data_format="channels_first",
        )
    if len(input.shape) == 5 and mode == "trilinear":
        assert align_corners is not None
        return flow._C.upsample_trilinear_3d(
            input,
            depth_scale=scale_factors[0],
            height_scale=scale_factors[1],
            width_scale=scale_factors[2],
            align_corners=align_corners,
            output_size=output_size,
            data_format="channels_first",
        )

    raise NotImplementedError(
        "Input Error: Only 3D, 4D and 5D input Tensors supported"
        " (got {}D) for the modes: nearest | linear | bilinear | bicubic | trilinear | area"
        " (got {})".format(len(input.shape), mode)
    )


def upsample(
    input,
    size: Optional[Union[int, Tuple[int, ...]]] = None,
    scale_factor: Optional[Union[float, Tuple[float, ...]]] = None,
    mode: str = "nearest",
    align_corners: Optional[bool] = None,
):
    r"""    
    Upsamples a given multi-channel 1D (temporal), 2D (spatial) or 3D (volumetric) data.

    See :class:`~oneflow.nn.Upsample`, :class:`~oneflow.nn.UpsamplingNearest2d`,
    :class:`~oneflow.nn.UpsamplingBilinear2d` for details.
    """
    return flow.nn.functional.interpolate(
        input,
        size=size,
        scale_factor=scale_factor,
        mode=mode,
        align_corners=align_corners,
    )
