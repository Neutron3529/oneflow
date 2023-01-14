#include "oneflow/core/vm/dtr_env.h"
#include "oneflow/core/eager/tensor_storage.h"

namespace oneflow {
namespace dtr {

vm::OpCallInstructionPolicy Env::update_tensor_with_storage(
    vm::TensorStorage* storage, vm::OpCallInstructionPolicy* current_compute_op) {
  // FIXME: set disjnode properly
  auto new_storage = std::make_shared<vm::InsideVmTensorStorage>();
  std::unordered_map<vm::EagerBlobObject*, std::shared_ptr<vm::EagerBlobObject>> old2new;
  auto update = [&new_storage, &old2new](std::shared_ptr<vm::EagerBlobObject>& old) {
    auto it = old2new.find(old.get());
    if (it != old2new.end()) {
      old = it->second;
    } else {
      auto local_tensor_meta = old->tensor_meta();
      const auto& eager_blob_object = std::make_shared<vm::EagerBlobObject>(
          std::make_shared<MemoryCase>(old->mem_case()), local_tensor_meta, old->mut_tensor_meta(),
          local_tensor_meta->dtype(), new_storage);
      eager_blob_object->set_storage_offset(old->storage_offset());
      old2new.emplace(old.get(), eager_blob_object);
      old = eager_blob_object;
    }
  };
  auto update_output = [&old2new, &new_storage](std::weak_ptr<vm::EagerBlobObject>& old) {
    auto it = old2new.find(CHECK_NOTNULL(old.lock()).get());
    if (it != old2new.end()) {
      old = it->second;
    } else {
      auto old_locked = old.lock();
      auto local_tensor_meta = old_locked->tensor_meta();
      const auto& eager_blob_object = std::make_shared<vm::EagerBlobObject>(
          std::make_shared<MemoryCase>(old_locked->mem_case()), local_tensor_meta,
          old_locked->mut_tensor_meta(), local_tensor_meta->dtype(), new_storage);
      eager_blob_object->set_storage_offset(old_locked->storage_offset());
      old2new.emplace(old_locked.get(), eager_blob_object);
      old = eager_blob_object;
    }
  };
  for (int i = ops.size() - 1; i >= 0; i--) {
    auto& op = ops[i];
    for (int j = 0; j < op->mut_inputs().size(); j++) {
      auto& x = op->mut_inputs()[j];
      if (x == nullptr) {
        LOG(INFO) << "No." << j << " input of " << op->opkernel().op_type_name() << " is nullptr"
                  << std::endl;
        continue;
      }
      if (x->tensor_storage().get() == storage) {
        vm::EagerBlobObject* old_ptr = x.get();
        update(x);
        VLOG(1) << "update input of " << op->opkernel().op_type_name() << " from " << old_ptr
                << " (storage " << storage << ") to " << x.get() << " (storage "
                << new_storage.get() << "), op addr " << op << std::endl;
      }
    }
    for (int j = 0; j < op->mut_outputs().size(); j++) {
      auto& y = op->mut_outputs()[j];
      if (y.lock() == nullptr) {
        LOG(INFO) << "No." << j << " output of " << op->opkernel().op_type_name() << " is nullptr"
                  << std::endl;
        continue;
      }
      if (CHECK_NOTNULL(y.lock())->tensor_storage().get() == storage) {
        vm::EagerBlobObject* old_ptr = y.lock().get();
        update_output(y);
        VLOG(1) << "update output of " << op->opkernel().op_type_name() << " from " << old_ptr
                << " (storage " << storage << ") to " << y.lock().get() << " (storage "
                << new_storage.get() << "), op addr " << op << std::endl;
      }
    }
  }
  vm::OpCallInstructionPolicy new_compute_op = *current_compute_op;
  // only update inputs
  for (auto& x : new_compute_op.mut_inputs()) {
    if (x->tensor_storage().get() == storage) {
      vm::EagerBlobObject* old_ptr = x.get();
      update(x);
      VLOG(1) << "update input of " << new_compute_op.opkernel().op_type_name() << " from "
              << old_ptr << " to " << x.get() << std::endl;
    }
  }
  // set compute_op_ and compute_time_
  new_storage->set_compute_op(storage->compute_op());
  // set blob_bytes_
  new_storage->set_blob_dptr(nullptr, storage->blob_bytes());
  // set is_initialized_
  new_storage->set_initialized();
  // set last_access_time_
  new_storage->Access();
  storage->clear_compute_op();
  return new_compute_op;
}

void Env::add_eviction_num(bool eager_eviction) {
  if (eager_eviction) {
    eager_eviction_num_++;
  } else {
    forced_eviction_num_++;
  }
}

Env::~Env() {
  LOG(INFO) << "forced eviction num: " << forced_eviction_num_;
  LOG(INFO) << "eager eviction num: " << eager_eviction_num_;
  LOG(INFO) << "recomputation num: " << recomputation_num_;
  LOG(INFO) << "duration: " << time_now_;
}

}  // namespace dtr
}  // namespace oneflow