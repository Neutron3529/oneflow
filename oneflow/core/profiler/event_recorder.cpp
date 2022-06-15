#include "oneflow/core/profiler/event_recorder.h"
#include "oneflow/core/profiler/profile_manager.h"
#include "oneflow/core/common/shape.h"

namespace oneflow {
namespace profiler {

Maybe<void> EventRecorder::RegisterEventToProfileManager(const std::shared_ptr<IEvent>& event) {
  auto* pmgr = JUST(GlobalMaybe<ProfileManager>());
  pmgr->events_.push(event_);
  return Maybe<void>::Ok();
}

std::shared_ptr<EventRecorder> EventRecorder::CreateCustomEventRecorder(const std::string& name) {
  return std::make_shared<EventRecorder>(CustomEvent::Create(name));
}

Maybe<EventRecorder> EventRecorder::CreateKernelEventRecorder(
    const std::string& name,
#if defined(WITH_CUDA)
    const std::function<int64_t()>& memory_size_getter,
#endif
    const ShapeGetterFuncType& shape_getter) {
  auto pmgr = Global<ProfileManager>::Get();
  if (pmgr) {
#if defined(WITH_CUDA)
    if (pmgr->use_cpu_ || pmgr->use_cuda_) {
      auto event = KernelEvent::Create(name, pmgr->record_shapes_ ? shape_getter : nullptr);
      if (pmgr->use_cuda_) {
        if (pmgr->record_bandwidth_) { event->SetMemorySize(memory_size_getter()); }
      }
      return std::make_shared<EventRecorder>(event);
    }
#else   // WITH_CUDA
    if (pmgr->use_cpu_) {
      return std::make_shared<EventRecorder>(
          KernelEvent::Create(name, pmgr->record_shapes_ ? shape_getter : nullptr));
    }
#endif  // WITH_CUDA
  }

  std::shared_ptr<EventRecorder> null_recorder;
  return null_recorder;
}

}  // namespace profiler
}  // namespace oneflow