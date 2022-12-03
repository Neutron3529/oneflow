/*
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
*/
#include "oneflow/core/device/cuda_util.h"
#include "oneflow/core/ep/include/primitive/copy_nd.h"
#include "oneflow/core/framework/framework.h"
#include "oneflow/core/kernel/new_kernel_util.h"
#include "oneflow/user/kernels/math_unary_elementwise_func.h"

namespace oneflow {

namespace {

template<typename Context>
std::unique_ptr<ep::primitive::CopyNd> NewCopyNdPrimitive(Context* ctx) {
  return ep::primitive::NewPrimitive<ep::primitive::CopyNdFactory>(ctx->device_type(), 2);
}

auto CopyNdPrimitiveExists() {
  return hob::make_custom("CopyNdPrimitiveExists", [](const user_op::KernelRegContext& ctx) {
    return NewCopyNdPrimitive(&ctx).operator bool();
  });
}

template<typename T>
struct PxyForwardFunctor {
  __device__ T Compute(T pxy) const {
    const T pxy_sigmoid = static_cast<T>(1.0) / (static_cast<T>(1.0) + ExpFunctor<T>::Forward(static_cast<T>(-1.0) * pxy));
    return pxy_sigmoid * static_cast<T>(2.0) - static_cast<T>(0.5);
  }
};

template<typename T>
struct PwhForwardFunctor {
  __device__ T Compute(T pwh, T anchors) const {
    const T pwh_sigmoid = static_cast<T>(1.0) / (static_cast<T>(1.0) + ExpFunctor<T>::Forward(static_cast<T>(-1.0) * pwh));
    return static_cast<T>(4.0) * pwh_sigmoid * pwh_sigmoid * anchors;
  }
};

template<typename T>
struct PxyBackwardFunctor {
  __device__ T Compute(T pxy) const {
    const T minus_pxy_exp = ExpFunctor<T>::Forward(static_cast<T>(-1.0) * pxy);
    const T minus_pxy_exp_1 = static_cast<T>(1.0) + minus_pxy_exp;
    return static_cast<T>(2.0) * minus_pxy_exp / (minus_pxy_exp_1 * minus_pxy_exp_1);
  }
};

template<typename T>
struct PwhBackwardFunctor {
  __device__ T Compute(T minus_pwh_exp, T minus_pwh_exp_1, T anchors) const {
    return static_cast<T>(8.0) * minus_pwh_exp / pow(minus_pwh_exp_1, 3);
  }
};

template<>
struct PwhBackwardFunctor<half> {
  __device__ half Compute(half minus_pwh_exp, half minus_pwh_exp_1, half anchors) const {
    return static_cast<half>(8.0) * minus_pwh_exp / (minus_pwh_exp_1 * minus_pwh_exp_1 *minus_pwh_exp_1);
  }
};

template<typename T>
struct AnchorsBackwardFunctor {
  __device__ T Compute(T minus_pwh_exp, T minus_pwh_exp_1, T anchors) const {
    return static_cast<T>(4.0) / (minus_pwh_exp_1 * minus_pwh_exp_1);
  }
};

template<typename FUNCTOR_PXY, typename FUNCTOR_PWH, typename T>
__global__ void FusedGetPboxForward(FUNCTOR_PXY pxy_functor, FUNCTOR_PWH pwh_functor, const int n, const T* pxy,
                                    const T* pwh, const T* anchors, T* tmp_buffer_pxy, T* tmp_buffer_pwh) {
  CUDA_1D_KERNEL_LOOP(i, n) {
    tmp_buffer_pxy[i] = pxy_functor.Compute(pxy[i]);
    tmp_buffer_pwh[i] = pwh_functor.Compute(pwh[i], anchors[i]);
  }
}

template<typename FUNCTOR_PXY, typename FUNCTOR_PWH, typename FUNCTOR_ANCHORS, typename T>
__global__ void FusedGetPboxBackward(FUNCTOR_PXY pxy_functor,
                                     FUNCTOR_PWH pwh_functor,
                                     FUNCTOR_ANCHORS anchors_functor, const int n, const T* pxy,
                                     const T* pwh, const T* anchors, const T* pbox_diff,
                                     T* pxy_diff, T* pwh_diff, T* anchors_diff) {
  CUDA_1D_KERNEL_LOOP(i, n) {
    const T minus_pwh_exp = ExpFunctor<T>::Forward(static_cast<T>(-1.0) * pwh[i]);
    const T minus_pwh_exp_1 = minus_pwh_exp + static_cast<T>(1.0);
    pxy_diff[i] = pxy_functor.Compute(pxy[i]) * pbox_diff[i];
    pwh_diff[i] = pwh_functor.Compute(minus_pwh_exp, minus_pwh_exp_1, anchors[i]) * pbox_diff[i];
    anchors_diff[i] = anchors_functor.Compute(minus_pwh_exp, minus_pwh_exp_1, anchors[i]) * pbox_diff[i];
  }
}

}  // namespace

template<typename T>
class FusedGetPboxKernel final : public user_op::OpKernel {
 public:
  FusedGetPboxKernel() = default;
  ~FusedGetPboxKernel() = default;

 private:
  using user_op::OpKernel::Compute;
  void Compute(user_op::KernelComputeContext* ctx) const override {
    const user_op::Tensor* pxy = ctx->Tensor4ArgNameAndIndex("pxy", 0);
    const user_op::Tensor* pwh = ctx->Tensor4ArgNameAndIndex("pwh", 0);
    const user_op::Tensor* anchors = ctx->Tensor4ArgNameAndIndex("anchors", 0);

    user_op::Tensor* pbox = ctx->Tensor4ArgNameAndIndex("pbox", 0);
    user_op::Tensor* tmp_buffer = ctx->Tensor4ArgNameAndIndex("tmp_buffer", 0);
    T* pbox_ptr = pbox->mut_dptr<T>();
    // T* tmp_buffer_ptr = tmp_buffer->mut_dptr<T>();
    T* tmp_buffer_pxy_ptr = reinterpret_cast<T*>(tmp_buffer->mut_dptr());
    T* tmp_buffer_pwh_ptr = reinterpret_cast<T*>(tmp_buffer->mut_dptr<char>() + pxy->shape_view().elem_cnt() * sizeof(T));

    const ShapeView& pxy_shape = pxy->shape_view();
    const int64_t elem_cnt = pxy_shape.elem_cnt();
    const int64_t rows = pxy_shape.At(0);
    const int64_t cols = pxy_shape.At(1);

    PxyForwardFunctor<T> pxy_functor{};
    PwhForwardFunctor<T> pwh_functor{};

    // FusedGetPboxForward
    RUN_CUDA_KERNEL((FusedGetPboxForward<decltype(pxy_functor), decltype(pwh_functor), T>),
                    ctx->stream(), elem_cnt, pxy_functor, pwh_functor, elem_cnt, 
                    pxy->dptr<T>(), pwh->dptr<T>(), anchors->dptr<T>(), tmp_buffer_pxy_ptr, tmp_buffer_pwh_ptr);

    // concat
    auto primitive = NewCopyNdPrimitive(ctx);
    CHECK(primitive);
    DimVector dst_shape = {rows, 2 * cols};
    DimVector dst_pos_vec = {0, 0};
    DimVector src_shape = {rows, cols};
    DimVector src_pos_vec = {0, 0};
    DimVector extent_vec = {rows, cols};
    primitive->Launch(ctx->stream(), tmp_buffer->data_type(), 2, pbox_ptr, dst_shape.data(),
                      dst_pos_vec.data(), tmp_buffer_pxy_ptr, src_shape.data(), src_pos_vec.data(),
                      extent_vec.data());
    DimVector dst_pos_vec2 = {0, cols};
    primitive->Launch(ctx->stream(), tmp_buffer->data_type(), 2, pbox_ptr, dst_shape.data(),
                      dst_pos_vec2.data(), tmp_buffer_pwh_ptr, src_shape.data(), src_pos_vec.data(),
                      extent_vec.data());
  }
  bool AlwaysComputeWhenAllOutputsEmpty() const override { return false; }
};

#define REGISTER_FUSED_GET_PBOX_KERNEL(dtype)                         \
  REGISTER_USER_KERNEL("fused_get_pbox")                              \
      .SetCreateFn<FusedGetPboxKernel<dtype>>()                       \
      .SetIsMatchedHob((user_op::HobDataType("pbox", 0) == GetDataType<dtype>::value) && CopyNdPrimitiveExists() == true) \
      .SetInferTmpSizeFn([](user_op::InferContext* ctx) -> size_t {   \
        const Shape& shape = ctx->InputShape("pxy", 0);               \
        size_t tmp_buffer_size = shape.elem_cnt() * sizeof(dtype);    \
        return tmp_buffer_size * 2;                                   \
      });

REGISTER_FUSED_GET_PBOX_KERNEL(float)
REGISTER_FUSED_GET_PBOX_KERNEL(double)
REGISTER_FUSED_GET_PBOX_KERNEL(half)

template<typename T>
class FusedGetPboxGradKernel final : public user_op::OpKernel {
 public:
  FusedGetPboxGradKernel() = default;
  ~FusedGetPboxGradKernel() = default;

 private:
  using user_op::OpKernel::Compute;
  void Compute(user_op::KernelComputeContext* ctx) const override {
    const user_op::Tensor* pxy = ctx->Tensor4ArgNameAndIndex("pxy", 0);
    const user_op::Tensor* pwh = ctx->Tensor4ArgNameAndIndex("pwh", 0);
    const user_op::Tensor* anchors = ctx->Tensor4ArgNameAndIndex("anchors", 0);
    const user_op::Tensor* pbox_diff = ctx->Tensor4ArgNameAndIndex("pbox_diff", 0);

    user_op::Tensor* pxy_diff = ctx->Tensor4ArgNameAndIndex("pxy_diff", 0);
    user_op::Tensor* pwh_diff = ctx->Tensor4ArgNameAndIndex("pwh_diff", 0);
    user_op::Tensor* anchors_diff = ctx->Tensor4ArgNameAndIndex("anchors_diff", 0);

    PxyBackwardFunctor<T> pxy_functor{};
    PwhBackwardFunctor<T> pwh_functor{};
    AnchorsBackwardFunctor<T> anchors_functor{};
    const int64_t elem_cnt = pxy->shape_view().elem_cnt();

    RUN_CUDA_KERNEL((FusedGetPboxBackward<decltype(pxy_functor), decltype(pwh_functor), decltype(anchors_functor), T>),
                    ctx->stream(), elem_cnt, pxy_functor, pwh_functor, anchors_functor,
                    elem_cnt, pxy->dptr<T>(), pwh->dptr<T>(), anchors->dptr<T>(), pbox_diff->dptr<T>(),
                    pxy_diff->mut_dptr<T>(), pwh_diff->mut_dptr<T>(), anchors_diff->mut_dptr<T>());

  }
  bool AlwaysComputeWhenAllOutputsEmpty() const override { return false; }
};

#define REGISTER_FUSED_GET_PBOX_GRAD_KERNEL(dtype)                         \
  REGISTER_USER_KERNEL("fused_get_pbox_grad")                              \
      .SetCreateFn<FusedGetPboxGradKernel<dtype>>()                        \
      .SetIsMatchedHob((user_op::HobDataType("pxy_diff", 0) == GetDataType<dtype>::value));

REGISTER_FUSED_GET_PBOX_GRAD_KERNEL(float)
REGISTER_FUSED_GET_PBOX_GRAD_KERNEL(double)
REGISTER_FUSED_GET_PBOX_GRAD_KERNEL(half)

}  // namespace oneflow