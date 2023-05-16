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
#include "Transform/TransformDialectExtension.h"
#include "Transform/TransformStateExtension.h"
#include "mlir/Dialect/PDL/IR/PDL.h"
#include "mlir/Dialect/Func/IR/FuncOps.h"
#include "mlir/Dialect/Transform/IR/TransformDialect.h"
#include "mlir/Dialect/Transform/IR/TransformInterfaces.h"
#include "mlir/IR/OpImplementation.h"
#include "llvm/ADT/STLExtras.h"
#include "llvm/ADT/TypeSwitch.h"
#include "llvm/Support/Compiler.h"
#include "llvm/Support/raw_ostream.h"
#include "mlir/Transforms/GreedyPatternRewriteDriver.h"
#include "mlir/Transforms/GreedyPatternRewriteDriver.h"
#include "mlir/Dialect/Bufferization/TransformOps/BufferizationTransformOps.h"
#include "mlir/Dialect/Bufferization/IR/Bufferization.h"
#include "mlir/Dialect/Bufferization/Transforms/OneShotAnalysis.h"
#include "mlir/Dialect/Bufferization/Transforms/OneShotModuleBufferize.h"
#include "mlir/Dialect/Bufferization/Transforms/Transforms.h"
#include "mlir/Dialect/MemRef/IR/MemRef.h"
#include "mlir/Dialect/PDL/IR/PDL.h"
#include "mlir/Dialect/PDL/IR/PDLTypes.h"
#include "mlir/Dialect/Tensor/IR/Tensor.h"
#include "mlir/Dialect/Transform/IR/TransformDialect.h"
#include "mlir/IR/FunctionInterfaces.h"
#include "mlir/Dialect/GPU/IR/GPUDialect.h"
#include "mlir/Dialect/GPU/Transforms/ParallelLoopMapper.h"

using namespace mlir;
using namespace mlir::oneflow;
using namespace mlir::bufferization;
using namespace mlir::transform;

//===----------------------------------------------------------------------===//
// OneShotBufferizeOp
//===----------------------------------------------------------------------===//

namespace {
FailureOr<Value> gpuComprehensiveBufferizeAllocationFn(OpBuilder& builder, Location loc,
                                                       MemRefType memRefType,
                                                       ValueRange dynamicSizes,
                                                       unsigned alignment) {
  auto addressSpaceAttr =
      gpu::AddressSpaceAttr::get(builder.getContext(), gpu::GPUDialect::getWorkgroupAddressSpace());
  MemRefType allocType = MemRefType::get(memRefType.getShape(), memRefType.getElementType(),
                                         AffineMap(), addressSpaceAttr);
  Operation* parentOp = builder.getInsertionBlock()->getParentOp();
  do {
    // Note: alloc in device
    if (parentOp->hasAttr(gpu::getMappingAttrName())) {
      return builder
          .create<memref::AllocOp>(loc, allocType, dynamicSizes,
                                   builder.getI64IntegerAttr(alignment))
          .getResult();
    }

    // Note: alloc in host
    if (llvm::dyn_cast<func::FuncOp>(parentOp)) {
      auto alloc = builder.create<memref::AllocOp>(loc, memRefType, dynamicSizes,
                                                   builder.getI64IntegerAttr(alignment));
      auto casted = builder.create<memref::MemorySpaceCastOp>(loc, allocType, alloc);
      auto rankedType = casted.getType();
      Type unrankedType =
          UnrankedMemRefType::get(rankedType.getElementType(), rankedType.getMemorySpace());
      auto unrankCasted = builder.create<memref::CastOp>(loc, unrankedType, casted);
      builder.create<gpu::HostRegisterOp>(loc, unrankCasted);
      return casted.getResult();
    }
  } while ((parentOp = parentOp->getParentOp()));
  return failure();
}

LogicalResult gpuComprehensiveBufferizeDeallocationFn(OpBuilder& builder, Location loc,
                                                      Value allocation) {
  builder.create<memref::DeallocOp>(loc, allocation);
  return success();
}

}  // namespace

DiagnosedSilenceableFailure transform_dialect::OneShotBufferizeOp::apply(
    TransformResults& transformResults, TransformState& state) {
  OneShotBufferizationOptions options;
  options.allowReturnAllocs = getAllowReturnAllocs();
  options.allowUnknownOps = getAllowUnknownOps();
  options.bufferizeFunctionBoundaries = getBufferizeFunctionBoundaries();
  options.createDeallocs = getCreateDeallocs();
  options.testAnalysisOnly = getTestAnalysisOnly();
  options.printConflicts = getPrintConflicts();

  if (getSupportGpu()) {
    options.allocationFn = gpuComprehensiveBufferizeAllocationFn;
    options.deallocationFn = gpuComprehensiveBufferizeDeallocationFn;
  }
  if (getFunctionBoundaryTypeConversion().has_value())
    options.setFunctionBoundaryTypeConversion(*getFunctionBoundaryTypeConversion());

  ArrayRef<Operation*> payloadOps = state.getPayloadOps(getTarget());
  for (Operation* target : payloadOps) {
    if (!isa<ModuleOp, FunctionOpInterface>(target))
      return emitSilenceableError() << "expected module or function target";
    auto moduleOp = dyn_cast<ModuleOp>(target);
    if (options.bufferizeFunctionBoundaries) {
      if (!moduleOp) return emitSilenceableError() << "expected module target";
      if (failed(bufferization::runOneShotModuleBufferize(moduleOp, options)))
        return emitSilenceableError() << "bufferization failed";
    } else {
      if (failed(bufferization::runOneShotBufferize(target, options)))
        return emitSilenceableError() << "bufferization failed";
    }
  }

  // This transform op is currently restricted to ModuleOps and function ops.
  // Such ops are modified in-place.
  transformResults.set(getTransformed().cast<OpResult>(), payloadOps);
  return DiagnosedSilenceableFailure::success();
}

//===---------------------------------------------------------------------===//
// ApplyPatternsOp
//===---------------------------------------------------------------------===//
void transform_dialect::ApplyPatternsOp::build(
    OpBuilder& builder, OperationState& result, Value target,
    const transform_dialect::ApplyPatternsOpPatterns& patterns) {
  result.addOperands(target);

  auto unitAttr = builder.getUnitAttr();

#define ADD_PATTERN(NAME, ATTR) \
  if (patterns.NAME) result.addAttribute(ApplyPatternsOp::ATTR(result.name), unitAttr);

  ADD_PATTERN(canonicalization, getCanonicalizationAttrName)
  ADD_PATTERN(cse, getCseAttrName)
  ADD_PATTERN(memrefCanonicalization, getMemrefCanonicalizationAttrName)
#undef ADD_PATTERN
}

namespace {

void addAllRegisteredCanonicalizationPatterns(RewritePatternSet& patterns) {
  MLIRContext* ctx = patterns.getContext();
  for (Dialect* dialect : ctx->getLoadedDialects()) dialect->getCanonicalizationPatterns(patterns);
  for (RegisteredOperationName op : ctx->getRegisteredOperations())
    op.getCanonicalizationPatterns(patterns, ctx);
}

struct MemrefCopyOpFoldPatterns final : public OpRewritePattern<memref::CopyOp> {
 public:
  using OpRewritePattern<memref::CopyOp>::OpRewritePattern;
  LogicalResult matchAndRewrite(memref::CopyOp op, PatternRewriter& rewriter) const override {
    if (op.getSource() == op.getTarget()) rewriter.eraseOp(op);
    return success();
  }
};

void addMemrefCanonicalizationPatterns(RewritePatternSet& patterns) {
  patterns.add<MemrefCopyOpFoldPatterns>(patterns.getContext());
}

}  // namespace

DiagnosedSilenceableFailure transform_dialect::ApplyPatternsOp::applyToOne(
    Operation* target, transform::ApplyToEachResultList& results,
    transform::TransformState& state) {
  if (!target->hasTrait<OpTrait::IsIsolatedFromAbove>()) {
    return mlir::emitDefiniteFailure(
        target, "applies only to isolated-from-above targets because it needs to apply "
                "patterns greedily");
  }
  MLIRContext* ctx = target->getContext();
  RewritePatternSet patterns(ctx);
  if (getCanonicalization()) addAllRegisteredCanonicalizationPatterns(patterns);
  if (getMemrefCanonicalization()) addMemrefCanonicalizationPatterns(patterns);
  SmallVector<Operation*> ops;
  GreedyRewriteConfig config;
  target->walk([&](Operation* nestedOp) {
    if (target != nestedOp) ops.push_back(nestedOp);
  });
  LogicalResult result = applyOpPatternsAndFold(ops, std::move(patterns), config);
  if (failed(result)) { return DiagnosedSilenceableFailure::definiteFailure(); }
  if (getCse()) {
    func::FuncOp lastFuncVisited;
    auto walkResult = target->walk([&](func::FuncOp funcOp) -> WalkResult {
      lastFuncVisited = funcOp;
      eliminateCommonSubexpressions(funcOp);
      if (failed(result)) return WalkResult::interrupt();
      return WalkResult::advance();
    });
    if (walkResult.wasInterrupted()) {
      if (failed(result)) {
        return mlir::emitDefiniteFailure(lastFuncVisited, "greedy patterns failed");
      }
    }
  }
  return DiagnosedSilenceableFailure::success();
}

void transform_dialect::ApplyPatternsOp::getEffects(
    SmallVectorImpl<MemoryEffects::EffectInstance>& effects) {
  transform::onlyReadsHandle(getTarget(), effects);
  transform::modifiesPayload(effects);
}

namespace {
class OneFlowTransformDialectExtension
    : public transform::TransformDialectExtension<OneFlowTransformDialectExtension> {
 public:
  using Base::Base;

  void init() {
    declareDependentDialect<pdl::PDLDialect>();
    registerTransformOps<
#define GET_OP_LIST
#include "Transform/TransformDialectExtension.cpp.inc"
        >();
    registerTypes<
#define GET_TYPEDEF_LIST
#include "Transform/TransformDialectExtensionTypes.cpp.inc"
        >();
  }
};
}  // namespace

// These are automatically generated by ODS but are not used as the Transform
// dialect uses a different dispatch mechanism to support dialect extensions.
LLVM_ATTRIBUTE_UNUSED static OptionalParseResult generatedTypeParser(AsmParser& parser,
                                                                     StringRef* mnemonic,
                                                                     Type& value);
LLVM_ATTRIBUTE_UNUSED static LogicalResult generatedTypePrinter(Type def, AsmPrinter& printer);

#define GET_TYPEDEF_CLASSES
#include "Transform/TransformDialectExtensionTypes.cpp.inc"

#define GET_OP_CLASSES
#include "Transform/TransformDialectExtension.cpp.inc"

void mlir::oneflow::transform_dialect::registerTransformDialectExtension(
    DialectRegistry& registry) {
  registry.addExtensions<OneFlowTransformDialectExtension>();
}
