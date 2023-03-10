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
#include "oneflow/core/job/global_for.h"
#include "oneflow/core/job/resource_desc.h"
#include "oneflow/core/hardware/node_device_descriptor_manager.h"
#include "oneflow/cambricon/ep/mlu_stream.h"
#include "oneflow/cambricon/ep/mlu_event.h"
#include "oneflow/cambricon/ep/mlu_device.h"

#ifdef WITH_MLU

namespace oneflow {

namespace ep {

namespace {

constexpr size_t kDefaultWorkspaceSizeMb = 4;  // 4M
}  // namespace

MluStream::MluStream(MluDevice* device)
    : device_index_(device->device_index()), device_(device) {
  MluCurrentDeviceGuard guard(device_index_);
  OF_MLU_CHECK(cnrtQueueCreate(&mlu_stream_));
}

MluStream::~MluStream() {
  MluCurrentDeviceGuard guard(device_index_);
  OF_MLU_CHECK(cnrtQueueSync(mlu_stream_));
  OF_MLU_CHECK(cnrtQueueDestroy(mlu_stream_));
}

Maybe<void> MluStream::OnExecutionContextSetup() {
  OF_MLU_CHECK(cnrtSetDevice(device_index_));
  return Maybe<void>::Ok();
}

Maybe<void> MluStream::OnExecutionContextTeardown() { return Maybe<void>::Ok(); }

DeviceType MluStream::device_type() const { return DeviceType::kMLU; }

MluDevice* MluStream::device() const { return device_; }

Maybe<void> MluStream::Sync() {
  cnrtRet_t err = cnrtQueueSync(mlu_stream_);
  if (err == cnrtSuccess) {
    return Maybe<void>::Ok();
  } else {
    return Error::RuntimeError() << "MluStream::Sync error";
  }
}

void MluStream::RecordEvent(Event* event) {
  auto* mlu_event = static_cast<MluEvent*>(event);  // NOLINT
  OF_MLU_CHECK(topsEventRecord(mlu_event->mlu_event(), mlu_stream_));
}

Maybe<void> MluStream::GetAsyncError() {
  return Maybe<void>::Ok();
}

topsStream_t MluStream::mlu_stream() const { return mlu_stream_; }

}  // namespace ep

}  // namespace oneflow

#endif  // WITH_MLU
