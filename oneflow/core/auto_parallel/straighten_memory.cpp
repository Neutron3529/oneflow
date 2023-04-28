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

#include "oneflow/core/auto_parallel/straighten_memory.h"
#include "oneflow/core/auto_parallel/auto_memory.h"
#include "oneflow/core/rpc/include/global_process_ctx.h"

namespace oneflow {
namespace auto_parallel {

namespace {

class TopoStruct {
 public:
  const OpNode* op_node = nullptr;
  // Memory increment = (memory of out registers) - (memory of in registers)
  int64_t memory_increment = -1;
  bool is_reusable = false;
  int32_t blob_id = -1;

  std::vector<TopoStruct*> in_topo_structs;
  std::vector<TopoStruct*> out_topo_structs;

  explicit TopoStruct(const OpNode* op_node_);
  explicit TopoStruct(int32_t blob_id_) : blob_id(blob_id_){};

  void ComputeIsReusable();
};

TopoStruct::TopoStruct(const OpNode* op_node_) : op_node(op_node_) { ComputeIsReusable(); }

void TopoStruct::ComputeIsReusable() { is_reusable = IsProducedRegisterReusable(op_node->op()); }

void InitInOutTopoStructs(std::vector<TopoStruct*>* topo_structs) {
  // Generate the map from operator names to topological structure
  HashMap<std::string, TopoStruct*> op_name2topo_structs;
  for (auto& topo_struct : *topo_structs) {
    op_name2topo_structs[topo_struct->op_node->op().op_name()] = topo_struct;
  }

  // Traverse the topological structures
  for (auto& this_topo_struct : *topo_structs) {
    auto& node = this_topo_struct->op_node;
    // Initialize input nodes for edges with data
    node->ForEachNodeOnInEdge([&](OpNode* in) {
      // Since we might be looking at a sub-graph of the operator graph.
      // We need to check if the op_node exists in the sub-graph.
      auto it = op_name2topo_structs.find(in->op().op_name());
      if (it != op_name2topo_structs.end()) {
        this_topo_struct->in_topo_structs.push_back(it->second);
        it->second->out_topo_structs.push_back(this_topo_struct);
      }
    });
    // Initialize input nodes for control edges
    for (const auto& ctrl_in_op_name : node->op().op_conf().ctrl_in_op_name()) {
      auto it = op_name2topo_structs.find(ctrl_in_op_name);
      if (it != op_name2topo_structs.end()) {
        auto& ctrl_in_topo_struct = it->second;
        this_topo_struct->in_topo_structs.push_back(ctrl_in_topo_struct);
        // Initialize output nodes for this control edge simultaneously
        ctrl_in_topo_struct->out_topo_structs.push_back(this_topo_struct);
      }
    }
  }
}

// Compute the memory increment for all the topological structures
void ComputeAllMemoryIncrement(std::vector<TopoStruct*>& topo_structs,
                               std::vector<TopoStruct>& release_topo_structs,
                               HashMap<LogicalBlobId, int32_t>& lbi2id,
                               std::vector<TopoStruct*>& id2producer_topo_struct,
                               std::vector<std::vector<TopoStruct*>>& id2consumer_topo_structs,
                               std::vector<int64_t>& id2blob_size) {
  // Compute the memory increment for produced blobs
  for (auto& topo_struct : topo_structs) { topo_struct->memory_increment = 0; }

  for (int32_t id = 0; id < id2producer_topo_struct.size(); id++) {
    const auto& topo_struct = id2producer_topo_struct[id];
    if (topo_struct->is_reusable) { topo_struct->memory_increment += id2blob_size[id]; }
  }
  // Subtract the consumed memory
  for (int32_t id = 0; id < id2consumer_topo_structs.size(); id++) {
    if (id2producer_topo_struct[id]->is_reusable) {
      // Check whether two blobs have the same consumer_topo_structs
      auto& consumer_topo_structs = id2consumer_topo_structs[id];
      auto& first_consumer_outs = consumer_topo_structs[0]->out_topo_structs;
      bool not_merged = true;
      for (int32_t out_id = first_consumer_outs.size() - 1; out_id >= 0; out_id--) {
        int32_t curr_release_blob_id = first_consumer_outs[out_id]->blob_id;
        if (curr_release_blob_id == -1) { break; }
        // Compare whether the consumer_topo_structs are the same
        const auto& curr_topo_structs = id2consumer_topo_structs[curr_release_blob_id];
        bool is_same = curr_topo_structs.size() == consumer_topo_structs.size();
        for (int32_t consumer_id = 0; consumer_id < consumer_topo_structs.size(); consumer_id++) {
          if (consumer_topo_structs[consumer_id] != curr_topo_structs[consumer_id]) {
            is_same = false;
            break;
          }
        }
        // If they have the same consumer_topo_structs, merge them
        if (is_same) {
          first_consumer_outs[out_id]->memory_increment -= id2blob_size[id];
          not_merged = false;
          break;
        }
      }
      // If they have different consumer_topo_structs, add a new release_topo_struct
      if (not_merged) {
        release_topo_structs.emplace_back(id);
        auto& release_topo_struct = release_topo_structs.back();
        topo_structs.push_back(&release_topo_struct);
        release_topo_struct.memory_increment = -id2blob_size[id];
        // We need to execute all the consumers before releasing the blob
        release_topo_struct.in_topo_structs.insert(release_topo_struct.in_topo_structs.end(),
                                                   consumer_topo_structs.begin(),
                                                   consumer_topo_structs.end());
        for (auto& consumer_topo_struct : consumer_topo_structs) {
          consumer_topo_struct->out_topo_structs.push_back(&release_topo_struct);
        }
      }
    }
  }
}

void InitAllParameters(std::vector<TopoStruct*>* topo_structs,
                       std::vector<TopoStruct>* release_topo_structs,
                       HashMap<LogicalBlobId, int32_t>* lbi2id,
                       std::vector<std::vector<TopoStruct*>>* id2consumer_topo_structs,
                       std::vector<int64_t>* id2blob_size) {
  // Construct the map from a lbi to its id, consumers, blob size
  std::vector<TopoStruct*> id2producer_topo_struct;

  for (auto& topo_struct : *topo_structs) {
    const auto& producer = topo_struct->op_node->op();

    // Find all the blobs produced by this operator
    for (const auto& obn : producer.output_bns()) {
      const LogicalBlobId& lbi = producer.BnInOp2Lbi(obn);
      auto it = lbi2id->find(lbi);
      // We check existence in case of inplace operators, whose producer and consumer produce the
      // same blob
      if (it == lbi2id->end()) {
        (*lbi2id)[lbi] = id2blob_size->size();
        const BlobDesc& logical_blob_desc = topo_struct->op_node->LogicalBlobDesc4Lbi(lbi);
        id2blob_size->push_back(TotalByteSize4BlobDesc(logical_blob_desc));
        id2producer_topo_struct.push_back(topo_struct);
      }
    }
  }

  // Reserve the space for release topological structures
  // We do not define a copy method for TopoStruct. During each size expansion, the data might be
  // screwed up if we do not reserve the space.
  release_topo_structs->reserve(id2blob_size->size());
  // initialize the id2consumer_topo_structs
  id2consumer_topo_structs->resize(id2blob_size->size());
  // Find all the blobs consumed by this operator
  for (auto& topo_struct : *topo_structs) {
    const auto& consumer = topo_struct->op_node->op();
    for (const auto& ibn : consumer.input_bns()) {
      const LogicalBlobId& lbi = consumer.BnInOp2Lbi(ibn);
      id2consumer_topo_structs->at(lbi2id->find(lbi)->second).push_back(topo_struct);
    }
  }

  for (int32_t id = 0; id < id2consumer_topo_structs->size(); id++) {
    if (id2consumer_topo_structs->at(id).empty()) {
      // If a blob does not have a consumer, then the blob is consumed by its producer itself
      id2consumer_topo_structs->at(id).push_back(id2producer_topo_struct[id]);
    } else {
      // Sort the consumer topological structure for later matching
      std::sort(id2consumer_topo_structs->at(id).begin(), id2consumer_topo_structs->at(id).end(),
                [](const TopoStruct* a, const TopoStruct* b) { return a < b; });
    }
  }

  // Construct all the data edges and control edges
  InitInOutTopoStructs(topo_structs);

  // Compute the memory increment for all the topological structures
  ComputeAllMemoryIncrement(*topo_structs, *release_topo_structs, *lbi2id, id2producer_topo_struct,
                            *id2consumer_topo_structs, *id2blob_size);
}

void StraightenMemoryOpNodes(HashMap<const OpNode*, TopoStruct>& op_node2topo_struct,
                             std::vector<TopoStruct*>* topo_structs,
                             HashMap<LogicalBlobId, int32_t>* lbi2id,
                             std::vector<std::vector<TopoStruct*>>* id2consumer_topo_structs,
                             std::vector<int64_t>* id2blob_size,
                             std::vector<TopoStruct*>* ordered_topo_structs) {
  // Extra release topological structures
  std::vector<TopoStruct> release_topo_structs;
  InitAllParameters(topo_structs, &release_topo_structs, lbi2id, id2consumer_topo_structs,
                    id2blob_size);

  if (GlobalProcessCtx::Rank() == 0) {
    std::cout << "Print all the topological structures:" << std::endl;
    int64_t total_memory = 0;
    int32_t total_in_size = 0, total_out_size = 0;
    for (const auto& topo_struct : *topo_structs) {
      std::cout << "In size: " << topo_struct->in_topo_structs.size()
                << ", out size: " << topo_struct->out_topo_structs.size() << ", ";
      total_in_size += topo_struct->in_topo_structs.size();
      total_out_size += topo_struct->out_topo_structs.size();
      if (topo_struct->blob_id != -1) {
        std::cout << "Blob id: " << topo_struct->blob_id
                  << " Memory increment: " << topo_struct->memory_increment << std::endl;
      } else {
        std::cout << "Op node: " << topo_struct->op_node->op().op_name()
                  << " Memory increment: " << topo_struct->memory_increment << std::endl;
      }
      total_memory += topo_struct->memory_increment;
    }
    std::cout << "Total memory: " << total_memory << ", total in size: " << total_in_size
              << ", total out size: " << total_out_size << std::endl;
  }
}
}  // namespace

// Straighten a subset of the op graph
void StraightenMemorySubGraph(const std::vector<const OpNode*>& sub_graph,
                              std::vector<const OpNode*>* ordered_op_nodes) {
  // Generate topological data structure for each op node
  HashMap<const OpNode*, TopoStruct> op_node2topo_struct;
  std::vector<TopoStruct*> topo_structs;
  std::vector<TopoStruct*> ordered_topo_structs;

  // Traverse all the nodes in the sub graph
  for (const auto& node : sub_graph) {
    op_node2topo_struct.insert({node, TopoStruct(node)});
    topo_structs.push_back(&op_node2topo_struct.at(node));
  }

  // Construct the map from a lbi to its id, consumers, blob size
  HashMap<LogicalBlobId, int32_t> lbi2id;
  std::vector<std::vector<TopoStruct*>> id2consumer_topo_structs;
  std::vector<int64_t> id2blob_size;

  StraightenMemoryOpNodes(op_node2topo_struct, &topo_structs, &lbi2id, &id2consumer_topo_structs,
                          &id2blob_size, &ordered_topo_structs);

  for (auto& ordered_topo_struct : ordered_topo_structs) {
    ordered_op_nodes->push_back(ordered_topo_struct->op_node);
  }
}

// Straighten the whole op graph
void StraightenMemoryOpGraph(const OpGraph& op_graph,
                             std::vector<const OpNode*>* ordered_op_nodes) {
  std::vector<const OpNode*> sub_graph;

  // Traverse and store all the nodes in the op graph
  op_graph.ForEachNode([&](OpNode* node) { sub_graph.push_back(node); });

  StraightenMemorySubGraph(sub_graph, ordered_op_nodes);
}

}  // namespace auto_parallel
}  // namespace oneflow