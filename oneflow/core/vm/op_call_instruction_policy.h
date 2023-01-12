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
#ifndef ONEFLOW_CORE_VM_OP_CALL_INSTRUCTION_POLICY_H_
#define ONEFLOW_CORE_VM_OP_CALL_INSTRUCTION_POLICY_H_

#include <memory>
#include "oneflow/core/eager/call_context.h"
#include "oneflow/core/eager/dev_vm_dep_object_consume_mode.h"
#include "oneflow/core/framework/user_op_kernel_registry.h"
#include "oneflow/core/vm/instruction_policy.h"
#include "oneflow/core/vm/stream.h"
#include "oneflow/user/kernels/stateful_opkernel.h"

namespace oneflow {

namespace user_op {

class OpKernel;

}  // namespace user_op

namespace vm {

inline int64_t unique_id() {
  static size_t id = 0;
  return id++;
}

class DtrOpCallInstructionPolicy;

class OpCallInstructionPolicy final : public InstructionPolicy {
 public:
  size_t id;
  OpCallInstructionPolicy(const OpCallInstructionPolicy& other)
      : id(unique_id()),
        vm_stream_(other.vm_stream_),
        call_ctx_(other.call_ctx_),
        opkernel_(other.opkernel_),
        user_opkernel_(other.user_opkernel_),
        infer_tmp_size_fn_(other.infer_tmp_size_fn_),
        need_temp_storage_(other.need_temp_storage_),
        dev_vm_dep_object_consume_mode_(other.dev_vm_dep_object_consume_mode_),
        input_dependences_(other.input_dependences_),
        output_dependences_(other.output_dependences_) {
  }
  OpCallInstructionPolicy(OpCallInstructionPolicy&& other) noexcept
      : id(unique_id()),
        vm_stream_(other.vm_stream_),
        call_ctx_(other.call_ctx_),
        opkernel_(other.opkernel_),
        user_opkernel_(other.user_opkernel_),
        infer_tmp_size_fn_(other.infer_tmp_size_fn_),
        need_temp_storage_(other.need_temp_storage_),
        dev_vm_dep_object_consume_mode_(other.dev_vm_dep_object_consume_mode_),
        input_dependences_(other.input_dependences_),
        output_dependences_(other.output_dependences_) {
    other.vm_stream_ = nullptr;
    other.opkernel_ = nullptr;
    other.user_opkernel_ = nullptr;
    other.infer_tmp_size_fn_ = nullptr;

  }
  OpCallInstructionPolicy& operator=(const OpCallInstructionPolicy& other) = delete;
  OpCallInstructionPolicy& operator=(OpCallInstructionPolicy&& other) = delete;
  ~OpCallInstructionPolicy() override { }

  template<typename... Args>
  static Maybe<OpCallInstructionPolicy> New(Args&&... args) {
    auto* ptr = new OpCallInstructionPolicy(std::forward<Args>(args)...);
    JUST(ptr->Init());
    return std::shared_ptr<OpCallInstructionPolicy>(ptr);
  }

  const one::StatefulOpKernel& opkernel() const { return *opkernel_; }
  const EagerBlobObjectList& inputs() const { return call_ctx_.inputs(); }
  const EagerBlobObjectList& outputs() const { return call_ctx_.outputs(); }
  EagerBlobObjectList& mut_inputs() { return call_ctx_.mut_inputs(); }
  EagerBlobObjectList& mut_outputs() { return call_ctx_.mut_outputs(); }
  const ComposedAttrMap& composed_attrs() const { return call_ctx_.composed_attrs(); }
  const one::OpExprInterpContext& op_interp_ctx() const { return call_ctx_.op_interp_ctx(); }
  const one::DevVmDepObjectConsumeMode& dev_vm_dep_object_consume_mode() const {
    return dev_vm_dep_object_consume_mode_;
  }

  one::StatefulOpKernel* mut_opkernel() { return opkernel_.get(); }

  template<typename DoEachT>
  Maybe<void> ForEachOutputTensor(const DoEachT& DoEach) {
    for (const auto& output : outputs()) { JUST(DoEach(output.get())); }
    return Maybe<void>::Ok();
  }

  const DependenceVector& input_dependences() const override { return input_dependences_; }
  const DependenceVector& output_dependences() const override { return output_dependences_; }

  template<typename DoEachT>
  void ForEachConstDependence(const DoEachT& DoEach) const;

  template<typename DoEachT>
  void ForEachMutDependence(const DoEachT& DoEach) const;

  template<typename DoEachT>
  void ForEachMut2Dependence(const DoEachT& DoEach) const;

  bool need_temp_storage() const { return need_temp_storage_; }
  const user_op::OpKernel* user_opkernel() const { return user_opkernel_; }
  const user_op::InferTmpSizeFn& infer_tmp_size_fn() const { return *infer_tmp_size_fn_; }

  const std::shared_ptr<const one::GlobalTensorInferResult>& global_tensor_infer_result() const {
    return call_ctx_.global_tensor_infer_result();
  }

  const eager::CallContext& call_ctx() const { return call_ctx_; }
  eager::CallContext* mut_call_ctx() { return &call_ctx_; }

  Stream* vm_stream() const { return vm_stream_; }

  InstructionFuseType fuse_type() const override { return kEnableInstructionFuseAtAnyPosition; }

  std::string DebugName(const vm::Instruction& instruction) const override;

  explicit OpCallInstructionPolicy(const DtrOpCallInstructionPolicy& policy);
 private:
  OpCallInstructionPolicy(
      Stream* vm_stream, const std::shared_ptr<one::StatefulOpKernel>& opkernel,
      EagerBlobObjectList&& inputs, EagerBlobObjectList&& outputs,
      const std::shared_ptr<const one::GlobalTensorInferResult>& global_tensor_infer_result,
      const one::OpExprInterpContext& op_interp_ctx,
      const one::DevVmDepObjectConsumeMode dev_vm_dep_object_consume_mode);
  Maybe<void> Init();
  void InitStreamSequentialDependence();
  Maybe<void> Prepare(Instruction* instruction) override;
  void Compute(Instruction* instruction) override;

  Stream* vm_stream_;
  eager::CallContext call_ctx_;
  std::shared_ptr<one::StatefulOpKernel> opkernel_;
  const user_op::OpKernel* user_opkernel_;
  const user_op::InferTmpSizeFn* infer_tmp_size_fn_;
  bool need_temp_storage_;
  const one::DevVmDepObjectConsumeMode dev_vm_dep_object_consume_mode_;
  DependenceVector input_dependences_;
  DependenceVector output_dependences_;
  friend class DtrOpCallInstructionPolicy;
};

class DtrOpCallInstructionPolicy {
  Stream* vm_stream_;
  eager::DtrCallContext dtr_call_ctx_;
  std::shared_ptr<one::StatefulOpKernel> opkernel_;
  const user_op::OpKernel* user_opkernel_;
  const user_op::InferTmpSizeFn* infer_tmp_size_fn_;
  bool need_temp_storage_;
  const one::DevVmDepObjectConsumeMode dev_vm_dep_object_consume_mode_;
  DependenceVector input_dependences_;
  DependenceVector output_dependences_;
  public:
  explicit DtrOpCallInstructionPolicy(const OpCallInstructionPolicy& op)
      : vm_stream_(op.vm_stream()),
        dtr_call_ctx_(op.call_ctx()),
        opkernel_(op.opkernel_),
        user_opkernel_(op.user_opkernel_),
        infer_tmp_size_fn_(op.infer_tmp_size_fn_),
        need_temp_storage_(op.need_temp_storage()),
        dev_vm_dep_object_consume_mode_(op.dev_vm_dep_object_consume_mode()),
        input_dependences_(op.input_dependences()),
        output_dependences_(op.output_dependences()) {}
  friend class OpCallInstructionPolicy;
  EagerBlobObjectList& mut_inputs() { return dtr_call_ctx_.mut_inputs(); }
  WeakEagerBlobObjectList& mut_outputs() { return dtr_call_ctx_.mut_outputs(); }
  const one::StatefulOpKernel& opkernel() const { return *opkernel_; }
};

Maybe<void> Recompute(OpCallInstructionPolicy* op_call_instruction_policy, vm::Stream* vm_stream);

}  // namespace vm
}  // namespace oneflow

#endif  // ONEFLOW_CORE_VM_OP_CALL_INSTRUCTION_POLICY_H_
