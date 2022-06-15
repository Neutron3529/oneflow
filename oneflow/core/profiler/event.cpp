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

#include "fmt/core.h"
#include "fmt/format.h"
#include "oneflow/core/profiler/event.h"
#include "oneflow/core/profiler/util.h"
#include "oneflow/core/common/shape.h"

using json = nlohmann::json;

namespace oneflow {

namespace profiler {
nlohmann::json IEvent::ToJson() {
  return json{{"name", name_},
              {"time", static_cast<double>(GetDuration())
                           / 1000},  // convert to us, the unit of GetDuration is ns
              {"input_shapes", "-"}};
}

std::string CustomEvent::Key() { return name_; }

nlohmann::json CustomEvent::ToJson() {
  auto j = IEvent::ToJson();
  j["type"] = EventType::kCustom;
  j["custom_type"] = type_;
  return j;
}

std::shared_ptr<CustomEvent> CustomEvent::Create(const std::string& name, CustomEventType type) {
  return std::shared_ptr<CustomEvent>(new CustomEvent(name, type));
}

void IEvent::StartedAt(time_t t) { started_at_ = t; }

void IEvent::FinishedAt(time_t t) { finished_at_ = t; }

void IEvent::Start() { StartedAt(GetTimeNow()); }

void IEvent::Finish() { FinishedAt(GetTimeNow()); }

bool IEvent::IsChildOf(const std::shared_ptr<IEvent>& e) {
  if (this == e.get()) { return false; }
  return started_at_ > e->started_at_ && finished_at_ < e->finished_at_;
}

const std::string& IEvent::GetName() const { return name_; }

time_t IEvent::GetDuration() { return finished_at_ - started_at_; }

std::string KernelEvent::Key() { return fmt::format("{}.{}", name_, GetFormatedInputShapes()); }

nlohmann::json KernelEvent::ToJson() {
  auto j = IEvent::ToJson();
  j["type"] = EventType::kOneflowKernel;
  j["input_shapes"] = GetFormatedInputShapes();
  if (!children_.empty()) { j["children"] = children_; }
  return j;
}

std::shared_ptr<KernelEvent> KernelEvent::Create(
    const std::string& name, const std::function<std::vector<Shape>(void)>& shape_getter) {
  return std::shared_ptr<KernelEvent>(new KernelEvent(name, shape_getter));
}

void KernelEvent::RecordShape(const Shape& shape) { input_shapes_.emplace_back(shape); }

std::string KernelEvent::GetFormatedInputShapes(size_t max_num_to_format) {
  if (input_shapes_.size() == 0) { return "-"; }
  std::vector<std::string> shapes_formated(std::min(input_shapes_.size(), max_num_to_format));
  for (auto i = 0; i < shapes_formated.size(); ++i) {
    const std::string current_shape = input_shapes_[i].ToString();
    shapes_formated[i] = current_shape == "()" ? "scalar" : current_shape;
  }
  if (input_shapes_.size() > max_num_to_format) { shapes_formated.emplace_back("..."); }
  return fmt::format("[{}]", fmt::join(shapes_formated, ", "));
}

}  // namespace profiler
}  // namespace oneflow