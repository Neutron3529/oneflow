#ifndef ONEFLOW_CORE_ACTOR_BOXING_ACTOR_H_
#define ONEFLOW_CORE_ACTOR_BOXING_ACTOR_H_

#include "oneflow/core/actor/actor.h"

namespace oneflow {

class BoxingActor final : public Actor {
 public:
  OF_DISALLOW_COPY_AND_MOVE(BoxingActor);
  BoxingActor() = default;
  ~BoxingActor() = default;

  void VirtualActorInit(const TaskProto&, const ThreadCtx&) override;

 private:
  int HandlerNormal(const ActorMsg&) override;
  int HandlerUntilNoReadableRegst(const ActorMsg&) override;

  bool IsReadReady() override { return !mut_num_of_read_empty(); }
  void Act() override;

  // <regst_desc_id, queue<regst>>
  HashMap<int64_t, std::queue<Regst*>> read_regst_;
};

}  // namespace oneflow

#endif  // ONEFLOW_CORE_ACTOR_BOXING_ACTOR_H_
