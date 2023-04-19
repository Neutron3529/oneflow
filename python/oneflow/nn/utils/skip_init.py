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
import oneflow as flow
from oneflow.nn.modules.module import Module


def skip_init(module_cls, *args, **kwargs):
    if not issubclass(module_cls, Module):
        raise RuntimeError("Expected a Module; got {}".format(module_cls))

    default_device = flow.get_global_default_device()
    final_device = kwargs["device"] if "device" in kwargs else default_device
    flow.set_global_default_device(flow.device("meta"))
    module_obj = module_cls(*args, **kwargs)
    flow.set_global_default_device(default_device)
    return module_obj.to_empty(device=final_device)
