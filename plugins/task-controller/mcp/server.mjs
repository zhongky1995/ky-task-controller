import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import readline from "node:readline";
import { fileURLToPath } from "node:url";

const SERVER_NAME = "KY-TASK State MCP";
const HELPER = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../scripts/task_controller_state.py");
const JsonRpcError = { METHOD_NOT_FOUND: -32601, INVALID_PARAMS: -32602 };
const LANE_RUNTIMES = [
  "native_thread_lane",
  "managed_agent_worker",
  "single_thread_section",
  "thread_create_unavailable",
];
const TRUE_WORKER_RUNTIMES = ["native_thread_lane", "managed_agent_worker"];
const WORKER_LIFECYCLES = ["ephemeral", "persistent"];
const CONTEXT_POLICIES = ["packet_only", "checkpoint_delta"];
const RUNTIME_PREFERENCES = ["auto", ...TRUE_WORKER_RUNTIMES];
const RUNTIME_SELECTION_POLICIES = ["native_session_required", "lane_lifecycle"];
const PROJECT_AFFINITY_POLICIES = ["inherit_or_resolve_required", "allow_projectless"];
const PROJECT_RESOLUTION_SOURCES = [
  "controller_project",
  "workspace_path_match",
  "material_path_match",
  "user_selected",
];
const PROJECT_ENVIRONMENTS = ["local", "worktree"];
const ENFORCEMENT_MODES = ["workflow_only", "semantic_strict"];
const INTERACTION_MODES = ["discuss_only", "plan_only", "execute"];
const WRITE_BOUNDARIES = ["read-only", "draft-file", "approved-target", "review-only"];
const CALLBACK_EXPECTED = [
  "",
  "active_message_required",
  "active_message_preferred",
  "controller_poll_allowed",
  "managed_result_collected",
];
const CALLBACK_OBSERVED = [
  "",
  "active_message",
  "controller_poll_recovery",
  "managed_result_collected",
  "unavailable",
  "unspecified",
];

function send(message) {
  process.stdout.write(`${JSON.stringify(message)}\n`);
}

function sendResult(id, result) {
  send({ jsonrpc: "2.0", id, result });
}

function sendError(id, code, message) {
  send({ jsonrpc: "2.0", id, error: { code, message } });
}

function requireString(value, name) {
  if (typeof value !== "string" || value.trim().length === 0) {
    throw new Error(`${name} must be a non-empty string.`);
  }
  return value.trim();
}

function resolveStatePath(value) {
  const raw = requireString(value, "statePath");
  return path.isAbsolute(raw) ? path.resolve(raw) : path.resolve(process.cwd(), raw);
}

function pushString(argv, flag, value) {
  if (typeof value === "string" && value.length > 0) {
    argv.push(flag, value);
  }
}

function pushInteger(argv, flag, value) {
  if (Number.isInteger(value) && value > 0) {
    argv.push(flag, String(value));
  }
}

function runHelper(command, statePath, argv = []) {
  if (!fs.existsSync(HELPER)) {
    throw new Error(`KY-TASK state helper is missing: ${HELPER}`);
  }
  const target = resolveStatePath(statePath);
  const result = spawnSync("python3", [HELPER, command, "--state", target, ...argv], {
    cwd: process.cwd(),
    encoding: "utf8",
    maxBuffer: 16 * 1024 * 1024,
  });
  if (result.error) {
    throw result.error;
  }
  if (result.status !== 0) {
    const message = (result.stderr || result.stdout || `helper exited ${result.status}`).trim();
    throw new Error(message);
  }
  const output = result.stdout.trim();
  return { statePath: target, data: output ? JSON.parse(output) : {} };
}

function runReadOnlyHelper(command, argv = []) {
  if (!fs.existsSync(HELPER)) {
    throw new Error(`KY-TASK state helper is missing: ${HELPER}`);
  }
  const result = spawnSync("python3", [HELPER, command, ...argv], {
    cwd: process.cwd(),
    encoding: "utf8",
    maxBuffer: 16 * 1024 * 1024,
  });
  if (result.error) throw result.error;
  if (result.status !== 0) {
    throw new Error((result.stderr || result.stdout || `helper exited ${result.status}`).trim());
  }
  const output = result.stdout.trim();
  return output ? JSON.parse(output) : {};
}

function contentText(text, structuredContent = undefined) {
  return {
    content: [{ type: "text", text }],
    ...(structuredContent === undefined ? {} : { structuredContent }),
  };
}

function toolResult(id, action, statePath, argv = []) {
  const result = runHelper(action, statePath, argv);
  sendResult(
    id,
    contentText(JSON.stringify(result.data, null, 2), {
      statePath: result.statePath,
      result: result.data,
    }),
  );
}

function readOnlyToolResult(id, action, argv = []) {
  const result = runReadOnlyHelper(action, argv);
  sendResult(id, contentText(JSON.stringify(result, null, 2), { result }));
}

const executionPolicySchema = {
  type: "object",
  description: "Locked execution policy. Use distributed for independent workers; multi_session remains a legacy alias.",
  properties: {
    splitRequirement: { type: "string", enum: ["mandatory", "recommended", "none"], default: "none" },
    mode: { type: "string", enum: ["distributed", "multi_session", "sequential_lanes", "direct"], default: "direct" },
    eligibleRuntimes: {
      type: "array",
      items: { type: "string", enum: TRUE_WORKER_RUNTIMES },
      default: [],
    },
    downgradeReason: { type: "string", default: "" },
    requiredWorkerLanes: { type: "array", items: { type: "string" }, default: [] },
    independentReviewRequired: { type: "boolean", default: false },
    runtimeSelectionPolicy: {
      type: "string",
      enum: RUNTIME_SELECTION_POLICIES,
      default: "native_session_required",
      description: "Session-first default requires visible native Codex Session tasks for distributed lanes.",
    },
    nativeThreadUserApproved: {
      type: "boolean",
      default: false,
      description: "Explicit task-scoped user approval for distributed sidebar Session tasks.",
    },
    maxParallelWorkers: { type: "integer", minimum: 1, maximum: 8, default: 4 },
    projectAffinityPolicy: {
      type: "string",
      enum: PROJECT_AFFINITY_POLICIES,
      default: "inherit_or_resolve_required",
      description: "Require native worker Sessions to inherit or resolve one saved Codex project before dispatch.",
    },
    projectlessUserApproved: {
      type: "boolean",
      default: false,
      description: "Explicit per-task approval required before allow_projectless may create native Sessions outside projects.",
    },
    targetProjectId: {
      type: "string",
      description: "Saved Codex project id returned by list_projects and locked for every native worker Session.",
    },
    targetProjectPath: {
      type: "string",
      default: "",
      description: "Optional audited path for the resolved project.",
    },
    projectResolutionSource: {
      type: "string",
      enum: PROJECT_RESOLUTION_SOURCES,
      description: "How targetProjectId was inherited or resolved.",
    },
  },
};

const semanticItemSchema = {
  oneOf: [
    { type: "string" },
    {
      type: "object",
      properties: {
        id: { type: "string" },
        description: { type: "string" },
        lane: { type: "string" },
        lanes: { type: "array", items: { type: "string" } },
        required: { type: "boolean", default: true },
        priority: { type: "integer" },
        role: { type: "string" },
        appliesTo: { oneOf: [{ type: "string" }, { type: "array", items: { type: "string" } }] },
      },
      required: ["id"],
    },
  ],
};

const artifactManifestItemSchema = {
  type: "object",
  properties: {
    id: { type: "string", description: "Artifact identity." },
    deliverableId: { type: "string", description: "Must exactly match contractSpec.deliverable.id." },
    path: { type: "string" },
    description: { type: "string" },
    role: { type: "string", enum: ["entrypoint", "appendix", "source"] },
    unitId: { type: "string" },
    artifactFingerprint: { type: "string" },
    operationReceiptId: { type: "string", description: "Dispatcher receipt represented by this artifact entry." },
    operationArtifactFingerprint: { type: "string", pattern: "^[0-9a-f]{64}$" },
    targetVersion: { oneOf: [{ type: "string" }, { type: "integer" }, { type: "number" }] },
  },
  required: ["id", "deliverableId"],
};

const contractSpecSchema = {
  type: "object",
  description: "Complete semantic contract. The Python helper canonicalizes it and computes/verifies SHA256 identities.",
  properties: {
    specVersion: { oneOf: [{ type: "string" }, { type: "integer", minimum: 1 }] },
    interactionMode: { type: "string", enum: INTERACTION_MODES },
    deliverable: {
      type: "object",
      properties: {
        id: { type: "string" },
        kind: { type: "string" },
        target: { type: "string" },
        format: { type: "string" },
        lane: { type: "string" },
        lanes: { type: "array", items: { type: "string" } },
        audience: { oneOf: [{ type: "string" }, { type: "array", minItems: 1, items: { type: "string" } }] },
        useMode: { type: "string" },
        standalone: { type: "boolean" },
        artifactClass: { type: "string" },
        units: {
          type: "array",
          items: { type: "object", properties: { id: { type: "string" } }, required: ["id"], additionalProperties: true },
        },
        deliveryPackage: {
          type: "object",
          properties: {
            entrypoint: { type: "string" },
            selfContained: { type: "boolean" },
            maxRequiredOpens: { type: "integer", minimum: 1 },
          },
        },
      },
      required: ["id", "kind", "target", "format"],
    },
    deliverableFingerprint: { type: "string", description: "Optional supplied canonical deliverable SHA256; helper verifies or computes it." },
    canonicalSources: { type: "array", minItems: 1, items: semanticItemSchema },
    preserve: { type: "array", items: semanticItemSchema },
    allowedChanges: { type: "array", items: semanticItemSchema },
    forbidden: { type: "array", items: semanticItemSchema },
    acceptance: { type: "array", items: semanticItemSchema },
    intentAnchors: { type: "array", items: semanticItemSchema },
    decisionLedger: {
      type: "array",
      items: {
        type: "object",
        properties: {
          id: { type: "string" },
          statement: { type: "string" },
          status: { type: "string", enum: ["binding", "advisory", "superseded"] },
          lane: { type: "string" },
          lanes: { type: "array", items: { type: "string" } },
        },
        required: ["id", "statement", "status"],
      },
    },
    writePolicy: {
      type: "object",
      properties: {
        targets: {
          type: "array",
          minItems: 1,
          items: {
            type: "object",
            properties: { id: { type: "string" }, locator: { type: "string" }, environment: { type: "string" } },
            required: ["id", "locator"],
          },
        },
        allowedActions: { type: "array", minItems: 1, items: { type: "string" } },
        destructiveActionsRequireApproval: { type: "boolean" },
      },
      required: ["targets", "allowedActions", "destructiveActionsRequireApproval"],
    },
    sampleGate: {
      type: "object",
      properties: {
        required: { type: "boolean", default: false },
        lane: { type: "string" },
        blocks: { type: "array", items: { type: "string" } },
        acceptanceIds: { type: "array", items: { type: "string" } },
      },
    },
    userApprovalGate: {
      type: "object",
      properties: {
        required: { type: "boolean", default: false },
        blocks: { type: "array", items: { type: "string" } },
        artifactId: { type: "string" },
      },
    },
  },
  required: ["specVersion", "deliverable", "canonicalSources", "preserve", "allowedChanges", "forbidden", "acceptance"],
};

const taskBlueprintSchema = {
  type: "object",
  description: "TaskBlueprint v1. Python validates it and treats it as canonical when compiling schema-v2 state.",
};

const writeReceiptSchema = {
  type: "object",
  properties: {
    targetId: { type: "string" },
    targetLocator: { type: "string" },
    action: { type: "string" },
    beforeVersion: { type: "string" },
    afterVersion: { type: "string" },
    readbackEvidence: { type: "string" },
    idempotencyKey: { type: "string" },
  },
  required: ["targetId", "targetLocator", "action", "beforeVersion", "afterVersion", "readbackEvidence", "idempotencyKey"],
};

const checkResultSchema = {
  type: "object",
  properties: {
    id: { type: "string" },
    status: { type: "string", enum: ["pass", "fail", "blocked", "unknown"] },
    evidence: { type: "string" },
  },
  required: ["id", "status", "evidence"],
};

const correctionEventSchema = {
  type: "object",
  properties: {
    id: { type: "string" },
    reason: { type: "string" },
    recommendedInvalidFromLane: { type: "string" },
    keywords: { type: "array", items: { type: "string" } },
    category: { type: "string" },
    requirementIds: { type: "array", items: { type: "string" } },
  },
  required: ["reason", "recommendedInvalidFromLane"],
};

const larkOperationDescriptorSchema = {
  type: "object",
  description: "Typed Lark operation descriptor. The adapter compiles the allowlisted operation and target; callers never supply argv or executable settings.",
  properties: {
    operation: { type: "string", minLength: 1 },
    identity: { type: "string", enum: ["user", "bot"] },
    resource: { type: "object", additionalProperties: true },
    input: { type: "object", additionalProperties: true },
  },
  required: ["operation", "identity", "resource", "input"],
  additionalProperties: false,
};

const memoryTestAdapterOptionsSchema = {
  type: "object",
  description: "Test-only adapter settings. The helper rejects memory-test unless KY_TASK_TEST_MODE=1.",
  properties: {
    failExecute: { type: "boolean" },
    readbackMode: { type: "string", enum: ["match", "missing", "inconsistent"] },
  },
  additionalProperties: false,
};

const verificationResultSchema = {
  type: "object",
  properties: {
    resultVersion: { type: "string", minLength: 1 },
    resultId: { type: "string", minLength: 1 },
    caseId: { type: "string", minLength: 1 },
    caseVersion: { type: "string", minLength: 1 },
    caseFingerprint: { type: "string", pattern: "^[0-9a-f]{64}$" },
    artifactFingerprint: { type: "string", pattern: "^[0-9a-f]{64}$" },
    evaluator: {
      type: "object",
      properties: {
        capabilityId: { type: "string", minLength: 1 },
        version: { type: "string", minLength: 1 },
        runtimeHandle: { type: "string", minLength: 1 },
      },
      required: ["capabilityId", "version", "runtimeHandle"],
      additionalProperties: false,
    },
    procedureFingerprint: { type: "string", pattern: "^[0-9a-f]{64}$" },
    method: { type: "string", enum: ["structural", "hash", "readback", "semantic", "business"] },
    normalizedInputDigest: { type: "string", pattern: "^[0-9a-f]{64}$" },
    expected: {},
    actual: {},
    status: { type: "string", enum: ["pass", "fail", "error", "skipped"] },
    evidenceRefs: { type: "array" },
    evidenceDigest: { type: "string", pattern: "^[0-9a-f]{64}$" },
    confidence: { type: "number", minimum: 0, maximum: 1 },
    executedAt: { type: "string", minLength: 1 },
    attestationType: { type: "string", enum: ["self_attested", "tool_verified", "independent_reviewed", "human_approved"] },
    workerId: { type: "string", minLength: 1 },
    reviewedWorkerIds: { type: "array", items: { type: "string", minLength: 1 } },
  },
  required: [
    "resultVersion", "resultId", "caseId", "caseVersion", "caseFingerprint", "artifactFingerprint",
    "evaluator", "procedureFingerprint", "method", "normalizedInputDigest", "expected", "actual", "status",
    "evidenceRefs", "evidenceDigest", "confidence", "executedAt", "attestationType",
  ],
  additionalProperties: false,
};

const tools = [
  {
    name: "task_controller_compile_blueprint",
    title: "KY-TASK: Compile TaskBlueprint",
    description: "Read-only deterministic TaskBlueprint-to-contractSpec projection with digest and traceability.",
    inputSchema: {
      type: "object",
      properties: {
        taskBlueprint: taskBlueprintSchema,
        laneDefinitions: { type: "array", minItems: 1, items: { type: "object" } },
      },
      required: ["taskBlueprint", "laneDefinitions"],
    },
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: false },
  },
  {
    name: "task_controller_route_capabilities",
    title: "KY-TASK: Shadow Route Capabilities",
    description: "Read-only shadow capability suggestions. It does not register workers, authorize writes, or mutate controller state.",
    inputSchema: {
      type: "object",
      properties: {
        taskBlueprint: taskBlueprintSchema,
        activeCapabilityIds: { type: "array", items: { type: "string" }, default: [] },
        runtimeAvailability: { type: "object", additionalProperties: { type: "boolean" }, default: {} },
      },
      required: ["taskBlueprint"],
    },
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: false },
  },
  {
    name: "task_controller_plan_blueprint",
    title: "KY-TASK: Plan TaskBlueprint",
    description: "Read-only TaskBlueprint planning. Builds routing, SolutionGraph, lane projection, and WorkerPackets without dispatching workers.",
    inputSchema: {
      type: "object",
      properties: {
        taskBlueprint: taskBlueprintSchema,
        activeCapabilityIds: { type: "array", items: { type: "string" }, default: [] },
        runtimeAvailability: { type: "object", additionalProperties: { type: "boolean" }, default: {} },
      },
      required: ["taskBlueprint"],
    },
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: false },
  },
  {
    name: "task_controller_init",
    title: "KY-TASK: Initialize Schema-v2 State",
    description: "Create schemaVersion 2 state with contract revision 1, execution policy, lanes, and worker gates.",
    inputSchema: {
      type: "object",
      properties: {
        statePath: { type: "string" },
        goal: { type: "string" },
        contract: { type: "string", default: "" },
        enforcementMode: { type: "string", enum: ENFORCEMENT_MODES },
        semanticDowngradeReason: { type: "string", default: "" },
        contractSpec: contractSpecSchema,
        taskBlueprint: taskBlueprintSchema,
        autoPlan: { type: "boolean", default: false },
        runtimeAvailability: { type: "object", additionalProperties: { type: "boolean" }, default: {} },
        activeCapabilityIds: { type: "array", items: { type: "string" }, default: [] },
        executionPolicy: executionPolicySchema,
        lanes: {
          type: "array",
          items: { type: "string" },
          description: "Backward-compatible lane names.",
        },
        laneDefinitions: {
          type: "array",
          description: "Explicit lane definitions. Takes precedence over lanes.",
          items: {
            type: "object",
            properties: {
              name: { type: "string" },
              kind: { type: "string" },
              workerRequired: { type: "boolean", default: false },
              writeBoundary: { type: "string", enum: WRITE_BOUNDARIES },
              workerLifecycle: { type: "string", enum: WORKER_LIFECYCLES, default: "ephemeral" },
              contextPolicy: { type: "string", enum: CONTEXT_POLICIES },
              runtimePreference: { type: "string", enum: RUNTIME_PREFERENCES, default: "auto" },
              dependsOn: {
                type: "array",
                items: { type: "string" },
                description: "Explicit DAG dependencies. An empty array makes the lane immediately parallel-ready.",
              },
            },
            required: ["name"],
          },
        },
        force: { type: "boolean", default: false },
      },
      required: ["statePath", "goal"],
    },
    annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: false, openWorldHint: false },
  },
  {
    name: "task_controller_status",
    title: "KY-TASK: Read State",
    description: "Read schema v1 or v2 state. V1 is read-only and requires migration before continuing operations.",
    inputSchema: {
      type: "object",
      properties: { statePath: { type: "string" } },
      required: ["statePath"],
    },
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: false },
  },
  {
    name: "task_controller_next_lane",
    title: "KY-TASK: Get Next Lane",
    description: "Return the first incomplete schema-v2 lane.",
    inputSchema: {
      type: "object",
      properties: { statePath: { type: "string" } },
      required: ["statePath"],
    },
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: false },
  },
  {
    name: "task_controller_ready_lanes",
    title: "KY-TASK: Get Parallel-Ready Lanes",
    description: "Return the dependency-ready dispatch frontier, bounded by maxParallelWorkers.",
    inputSchema: {
      type: "object",
      properties: { statePath: { type: "string" } },
      required: ["statePath"],
    },
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: false },
  },
  {
    name: "task_controller_complete_lane",
    title: "KY-TASK: Complete Lane",
    description: "Complete a lane. Pass uses the same upstream/current-worker guard as gate-check and requires an artifact.",
    inputSchema: {
      type: "object",
      properties: {
        statePath: { type: "string" },
        lane: { type: "string" },
        artifact: { type: "string", default: "" },
        decision: { type: "string", enum: ["pass", "needs-work", "blocked"], default: "pass" },
        notes: { type: "string", default: "" },
      },
      required: ["statePath", "lane"],
    },
    annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: false, openWorldHint: false },
  },
  {
    name: "task_controller_insert_lane",
    title: "KY-TASK: Insert Lane",
    description: "Insert a schema-v2 lane with kind, worker requirement, write boundary, and current revision validity.",
    inputSchema: {
      type: "object",
      properties: {
        statePath: { type: "string" },
        lane: { type: "string" },
        beforeLane: { type: "string", default: "" },
        afterLane: { type: "string", default: "" },
        kind: { type: "string", default: "" },
        workerRequired: { type: "boolean", default: false },
        writeBoundary: { type: "string", enum: WRITE_BOUNDARIES },
        workerLifecycle: { type: "string", enum: WORKER_LIFECYCLES, default: "ephemeral" },
        contextPolicy: { type: "string", enum: CONTEXT_POLICIES },
        runtimePreference: { type: "string", enum: RUNTIME_PREFERENCES, default: "auto" },
        dependsOn: {
          type: "array",
          items: { type: "string" },
          description: "Explicit dependencies; [] marks the inserted lane independent of earlier lanes.",
        },
        status: { type: "string", enum: ["pending", "running", "done", "needs-work", "blocked", "stale"], default: "pending" },
        artifact: { type: "string", default: "" },
        decision: { type: "string", enum: ["", "pass", "needs-work", "blocked"], default: "" },
        notes: { type: "string", default: "" },
      },
      required: ["statePath", "lane"],
    },
    annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: false, openWorldHint: false },
  },
  {
    name: "task_controller_register_worker",
    title: "KY-TASK: Register Worker",
    description: "Register a revision-bound worker with a unique request and runtime identity.",
    inputSchema: {
      type: "object",
      properties: {
        statePath: { type: "string" },
        workerId: { type: "string" },
        threadId: {
          type: "string",
          minLength: 1,
          description: "Required for native_thread_lane and must equal runtimeHandle.",
        },
        runtimeHandle: {
          type: "string",
          minLength: 1,
          description: "Managed agent id, or the exact threadId for native_thread_lane.",
        },
        requestId: { type: "string", default: "" },
        contractRevision: { type: "integer", minimum: 1 },
        contractDigest: { type: "string", default: "" },
        deliverableFingerprint: { type: "string", default: "" },
        controllerThreadId: { type: "string", default: "" },
        replyToThreadId: { type: "string", default: "" },
        projectTargetType: {
          type: "string",
          enum: ["project", "projectless"],
          description: "Explicit create_thread target type. The strict Session-first policy requires project.",
        },
        projectId: {
          type: "string",
          default: "",
          description: "Actual projectId used in create_thread target; strict native workers must match executionPolicy.targetProjectId.",
        },
        projectEnvironment: {
          type: "string",
          enum: PROJECT_ENVIRONMENTS,
          description: "Project thread environment passed to create_thread: local or worktree.",
        },
        lane: { type: "string" },
        laneRuntime: { type: "string", enum: LANE_RUNTIMES, default: "single_thread_section" },
        task: { type: "string", default: "" },
        prompt: { type: "string", default: "" },
        packetId: { type: "string", default: "" },
        packetDigest: { type: "string", default: "" },
        toolProfile: { type: "string", default: "" },
        credentialPolicy: { type: "string", default: "" },
        threadToolCheck: { type: "string", default: "" },
        writeBoundary: { type: "string", enum: WRITE_BOUNDARIES },
        reviewsWorkerIds: { type: "array", items: { type: "string" }, default: [] },
        callbackExpected: { type: "boolean", default: true },
        callbackModeExpected: { type: "string", enum: CALLBACK_EXPECTED, default: "" },
      },
      required: ["statePath", "workerId", "lane"],
      allOf: [
        {
          if: {
            properties: { laneRuntime: { const: "native_thread_lane" } },
            required: ["laneRuntime"],
          },
          then: { required: ["threadId", "runtimeHandle"] },
        },
        {
          if: {
            properties: { laneRuntime: { const: "native_thread_lane" } },
            required: ["laneRuntime"],
          },
          then: { required: ["projectTargetType"] },
        },
        {
          if: {
            properties: { projectTargetType: { const: "project" } },
            required: ["projectTargetType"],
          },
          then: { required: ["projectId", "projectEnvironment"] },
        },
      ],
    },
    annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: false, openWorldHint: false },
  },
  {
    name: "task_controller_update_worker",
    title: "KY-TASK: Update Worker",
    description: "Update non-pass worker state. Use record_callback for done/pass so callback guards cannot be bypassed.",
    inputSchema: {
      type: "object",
      properties: {
        statePath: { type: "string" },
        workerId: { type: "string" },
        status: {
          type: "string",
          enum: ["pending", "running", "needs-work", "blocked", "superseded", "stale", "resolved"],
          default: "running",
        },
        artifact: { type: "string", default: "" },
        decision: { type: "string", enum: ["", "needs-work", "blocked"], default: "" },
        notes: { type: "string", default: "" },
      },
      required: ["statePath", "workerId"],
    },
    annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: false, openWorldHint: false },
  },
  {
    name: "task_controller_list_workers",
    title: "KY-TASK: List Workers",
    description: "List workers from schema v1 or v2 state without changing it.",
    inputSchema: {
      type: "object",
      properties: { statePath: { type: "string" } },
      required: ["statePath"],
    },
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: false },
  },
  {
    name: "task_controller_record_correction",
    title: "KY-TASK: Record Controller Correction",
    description: "Record an independent controller-observed correction event without requiring a worker callback.",
    inputSchema: {
      type: "object",
      properties: {
        statePath: { type: "string" },
        eventId: { type: "string" },
        summary: { type: "string" },
        category: { type: "string" },
        requirementIds: { type: "array", minItems: 1, items: { type: "string" } },
        recommendedInvalidFromLane: { type: "string" },
      },
      required: [
        "statePath",
        "eventId",
        "summary",
        "category",
        "requirementIds",
        "recommendedInvalidFromLane",
      ],
    },
    annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: false, openWorldHint: false },
  },
  {
    name: "task_controller_record_approval",
    title: "KY-TASK: Record User Approval",
    description: "Record user approval bound to the current contract revision and exact artifact fingerprint.",
    inputSchema: {
      type: "object",
      properties: {
        statePath: { type: "string" },
        approvalId: { type: "string", default: "" },
        artifactId: { type: "string" },
        artifactFingerprint: { type: "string" },
        approver: { type: "string" },
        timestamp: { type: "string", default: "" },
      },
      required: ["statePath", "artifactId", "artifactFingerprint", "approver"],
    },
    annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: false, openWorldHint: false },
  },
  {
    name: "task_controller_record_callback",
    title: "KY-TASK: Record Callback",
    description: "Record a current-revision callback. In structured-v1 graph work, approved-target callbacks must cite dispatched operation receipt IDs and ledger-backed verification results; free-text evidence and writeReceipt are legacy-only.",
    inputSchema: {
      type: "object",
      properties: {
        statePath: { type: "string" },
        workerId: { type: "string", minLength: 1 },
        requestId: { type: "string", minLength: 1 },
        contractRevision: { type: "integer", minimum: 1 },
        contractDigest: { type: "string", default: "" },
        deliverableFingerprint: { type: "string", default: "" },
        packetId: { type: "string", default: "" },
        packetDigest: { type: "string", default: "" },
        messageType: { type: "string", enum: ["completion", "blocker", "review_request", "fix_request", "approved"], default: "completion" },
        fromLane: { type: "string" },
        artifact: { type: "string", default: "" },
        keyFindings: { type: "string", default: "" },
        evidence: { type: "string", default: "" },
        risks: { type: "string", default: "" },
        gateDecision: { type: "string", enum: ["pass", "needs-work", "blocked"], default: "pass" },
        nextRecommendation: { type: "string", default: "" },
        callbackModeObserved: { type: "string", enum: CALLBACK_OBSERVED, default: "" },
        artifactManifest: { type: "array", minItems: 1, items: artifactManifestItemSchema, default: [] },
        checkResults: { type: "array", items: checkResultSchema, default: [] },
        writeReceipt: writeReceiptSchema,
        operationReceiptId: { type: "string", default: "" },
        operationReceiptIds: { type: "array", minItems: 1, items: { type: "string", minLength: 1 }, default: [] },
        verificationResults: { type: "array", items: verificationResultSchema, default: [] },
        correctionEvents: { type: "array", items: correctionEventSchema, default: [] },
      },
      required: ["statePath", "fromLane"],
      anyOf: [{ required: ["workerId"] }, { required: ["requestId"] }],
      additionalProperties: false,
    },
    annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: false, openWorldHint: false },
  },
  {
    name: "task_controller_issue_operation_permit",
    title: "KY-TASK: Issue Operation Permit",
    description: "After registering an active approved-target worker, issue a revision-bound permit for the packet-allowlisted target, action, capability, payload, and readback plan. Issuing never executes the operation.",
    inputSchema: {
      type: "object",
      properties: {
        statePath: { type: "string", minLength: 1 },
        permitId: { type: "string", minLength: 1 },
        workerId: { type: "string", minLength: 1 },
        capabilityId: { type: "string", minLength: 1 },
        operationId: { type: "string", minLength: 1 },
        targetId: { type: "string", minLength: 1 },
        targetLocator: { type: "string", minLength: 1 },
        action: { type: "string", minLength: 1 },
        payload: { type: "object" },
        restrictedFields: { type: "array", items: { type: "string", minLength: 1 }, default: [] },
        approvalRefs: { type: "array", items: { type: "string", minLength: 1 }, default: [] },
        idempotencyKey: { type: "string", minLength: 1 },
        adapterId: { type: "string", enum: ["lark-cli", "memory-test"] },
        adapterOptions: { type: "object", default: {} },
        readbackSpec: { type: "object" },
        expiresAt: { type: "string", minLength: 1 },
      },
      required: [
        "statePath", "permitId", "workerId", "capabilityId", "operationId", "targetId", "targetLocator",
        "action", "payload", "idempotencyKey", "adapterId", "readbackSpec", "expiresAt",
      ],
      additionalProperties: false,
      allOf: [
        {
          if: { properties: { adapterId: { const: "lark-cli" } }, required: ["adapterId"] },
          then: {
            properties: { payload: larkOperationDescriptorSchema, readbackSpec: larkOperationDescriptorSchema, adapterOptions: { type: "object", maxProperties: 0 } },
          },
        },
        {
          if: { properties: { adapterId: { const: "memory-test" } }, required: ["adapterId"] },
          then: { properties: { adapterOptions: memoryTestAdapterOptionsSchema } },
        },
      ],
    },
    annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: false, openWorldHint: false },
  },
  {
    name: "task_controller_dispatch_operation",
    title: "KY-TASK: Dispatch Permitted Operation",
    description: "Consume an issued permit through the restricted dispatcher and record its readback receipt. Dispatch accepts only a permit ID and optional claim ID; it cannot supply a command, environment, working directory, or replacement payload.",
    inputSchema: {
      type: "object",
      properties: {
        statePath: { type: "string", minLength: 1 },
        permitId: { type: "string", minLength: 1 },
        claimId: { type: "string", default: "" },
      },
      required: ["statePath", "permitId"],
      additionalProperties: false,
    },
    annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: false, openWorldHint: false },
  },
  {
    name: "task_controller_reconcile_operation",
    title: "KY-TASK: Reconcile Interrupted Operation",
    description: "Resolve a previously claimed operation through readback only. It never repeats the external write.",
    inputSchema: {
      type: "object",
      properties: {
        statePath: { type: "string", minLength: 1 },
        permitId: { type: "string", minLength: 1 },
      },
      required: ["statePath", "permitId"],
      additionalProperties: false,
    },
    annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: true, openWorldHint: false },
  },
  {
    name: "task_controller_revoke_operation_permit",
    title: "KY-TASK: Revoke Operation Permit",
    description: "Revoke an unconsumed structured-v1 permit before dispatch. Revocation creates no callback evidence and cannot make an approved-target lane pass.",
    inputSchema: {
      type: "object",
      properties: {
        statePath: { type: "string", minLength: 1 },
        permitId: { type: "string", minLength: 1 },
        reason: { type: "string", default: "" },
      },
      required: ["statePath", "permitId"],
      additionalProperties: false,
    },
    annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: false, openWorldHint: false },
  },
  {
    name: "task_controller_record_verification_result",
    title: "KY-TASK: Record Verification Result",
    description: "Record a structured-v1 verification result bound to the active worker packet and artifact manifest. Semantic and business cases must name their declared external verifier; high-risk work requires independent review before finalization.",
    inputSchema: {
      type: "object",
      properties: {
        statePath: { type: "string", minLength: 1 },
        workerId: { type: "string", minLength: 1 },
        packetId: { type: "string", minLength: 1 },
        packetDigest: { type: "string", pattern: "^[0-9a-f]{64}$" },
        caseId: { type: "string", minLength: 1 },
        artifactManifest: { type: "array", minItems: 1, items: artifactManifestItemSchema },
        verificationResult: verificationResultSchema,
      },
      required: ["statePath", "workerId", "packetId", "packetDigest", "caseId", "artifactManifest", "verificationResult"],
      additionalProperties: false,
    },
    annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: false, openWorldHint: false },
  },
  {
    name: "task_controller_gate_check",
    title: "KY-TASK: Gate Check",
    description: "Check lane, current-revision worker, callback, artifact, runtime, and independent-review gates.",
    inputSchema: {
      type: "object",
      properties: {
        statePath: { type: "string" },
        targetLane: { type: "string", default: "" },
      },
      required: ["statePath"],
    },
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: false },
  },
  {
    name: "task_controller_revise_contract",
    title: "KY-TASK: Revise Contract",
    description: "Increment contractRevision, invalidate lanes from invalidFromLane, and supersede old workers/callbacks.",
    inputSchema: {
      type: "object",
      properties: {
        statePath: { type: "string" },
        invalidFromLane: { type: "string" },
        contract: { type: "string", default: "" },
        contractSpec: contractSpecSchema,
        taskBlueprint: taskBlueprintSchema,
        consumeCorrectionEventIds: { type: "array", items: { type: "string" }, default: [] },
        reason: { type: "string", default: "" },
      },
      required: ["statePath", "invalidFromLane"],
    },
    annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: false, openWorldHint: false },
  },
  {
    name: "task_controller_finalize",
    title: "KY-TASK: Finalize",
    description: "Run the final gate and persist finalized state. Completed lanes alone are only finalizable.",
    inputSchema: {
      type: "object",
      properties: { statePath: { type: "string" } },
      required: ["statePath"],
    },
    annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: false, openWorldHint: false },
  },
];

async function handleToolCall(id, params) {
  const name = params?.name;
  const args = params?.arguments ?? {};
  const argv = [];

  if (name === "task_controller_compile_blueprint") {
    if (!args.taskBlueprint || typeof args.taskBlueprint !== "object" || Array.isArray(args.taskBlueprint)) {
      throw new Error("taskBlueprint must be an object.");
    }
    if (!Array.isArray(args.laneDefinitions) || args.laneDefinitions.length === 0) {
      throw new Error("laneDefinitions must be a non-empty array.");
    }
    readOnlyToolResult(id, "compile-blueprint", [
      "--task-blueprint", JSON.stringify(args.taskBlueprint),
      "--lane-definitions", JSON.stringify(args.laneDefinitions),
    ]);
    return;
  }
  if (name === "task_controller_route_capabilities") {
    if (!args.taskBlueprint || typeof args.taskBlueprint !== "object" || Array.isArray(args.taskBlueprint)) {
      throw new Error("taskBlueprint must be an object.");
    }
    if (args.activeCapabilityIds !== undefined && !Array.isArray(args.activeCapabilityIds)) {
      throw new Error("activeCapabilityIds must be an array.");
    }
    if (args.runtimeAvailability !== undefined) {
      if (args.runtimeAvailability === null || typeof args.runtimeAvailability !== "object" || Array.isArray(args.runtimeAvailability)) {
        throw new Error("runtimeAvailability must be an object.");
      }
      if (Object.values(args.runtimeAvailability).some((value) => typeof value !== "boolean")) {
        throw new Error("runtimeAvailability values must be booleans.");
      }
    }
    const routeArgs = ["--task-blueprint", JSON.stringify(args.taskBlueprint)];
    if (args.activeCapabilityIds?.length) {
      routeArgs.push(
        "--active-capability-ids",
        args.activeCapabilityIds.map((item) => requireString(item, "activeCapabilityIds item")).join(","),
      );
    }
    if (args.runtimeAvailability !== undefined) {
      routeArgs.push("--runtime-availability", JSON.stringify(args.runtimeAvailability));
    }
    readOnlyToolResult(id, "route-capabilities", routeArgs);
    return;
  }
  if (name === "task_controller_plan_blueprint") {
    if (!args.taskBlueprint || typeof args.taskBlueprint !== "object" || Array.isArray(args.taskBlueprint)) {
      throw new Error("taskBlueprint must be an object.");
    }
    if (args.activeCapabilityIds !== undefined && !Array.isArray(args.activeCapabilityIds)) {
      throw new Error("activeCapabilityIds must be an array.");
    }
    if (args.runtimeAvailability !== undefined) {
      if (args.runtimeAvailability === null || typeof args.runtimeAvailability !== "object" || Array.isArray(args.runtimeAvailability)) {
        throw new Error("runtimeAvailability must be an object.");
      }
      if (Object.values(args.runtimeAvailability).some((value) => typeof value !== "boolean")) {
        throw new Error("runtimeAvailability values must be booleans.");
      }
    }
    const planArgs = ["--task-blueprint", JSON.stringify(args.taskBlueprint)];
    if (args.activeCapabilityIds?.length) {
      planArgs.push("--active-capability-ids", args.activeCapabilityIds.map((item) => requireString(item, "activeCapabilityIds item")).join(","));
    }
    if (args.runtimeAvailability !== undefined) planArgs.push("--runtime-availability", JSON.stringify(args.runtimeAvailability));
    readOnlyToolResult(id, "plan-blueprint", planArgs);
    return;
  }
  if (name === "task_controller_init") {
    argv.push("--goal", requireString(args.goal, "goal"));
    pushString(argv, "--contract", args.contract);
    pushString(argv, "--enforcement-mode", args.enforcementMode);
    pushString(argv, "--semantic-downgrade-reason", args.semanticDowngradeReason);
    if (args.contractSpec && typeof args.contractSpec === "object") {
      argv.push("--contract-spec", JSON.stringify(args.contractSpec));
    }
    if (args.taskBlueprint && typeof args.taskBlueprint === "object") {
      argv.push("--task-blueprint", JSON.stringify(args.taskBlueprint));
    }
    if (args.autoPlan === true) argv.push("--auto-plan");
    if (args.runtimeAvailability !== undefined) {
      if (args.runtimeAvailability === null || typeof args.runtimeAvailability !== "object" || Array.isArray(args.runtimeAvailability)) {
        throw new Error("runtimeAvailability must be an object.");
      }
      argv.push("--runtime-availability", JSON.stringify(args.runtimeAvailability));
    }
    if (args.activeCapabilityIds !== undefined) {
      if (!Array.isArray(args.activeCapabilityIds)) throw new Error("activeCapabilityIds must be an array.");
      if (args.activeCapabilityIds.length) {
        argv.push("--active-capability-ids", args.activeCapabilityIds.map((item) => requireString(item, "activeCapabilityIds item")).join(","));
      }
    }
    if (Array.isArray(args.lanes) && args.lanes.length > 0) {
      argv.push("--lanes", args.lanes.map((lane) => requireString(lane, "lane")).join(","));
    }
    if (Array.isArray(args.laneDefinitions) && args.laneDefinitions.length > 0) {
      argv.push("--lane-definitions", JSON.stringify(args.laneDefinitions));
    }
    if (args.executionPolicy && typeof args.executionPolicy === "object") {
      argv.push("--execution-policy", JSON.stringify(args.executionPolicy));
    }
    if (args.force === true) argv.push("--force");
    toolResult(id, "init", args.statePath, argv);
    return;
  }
  if (name === "task_controller_status") {
    toolResult(id, "status", args.statePath);
    return;
  }
  if (name === "task_controller_next_lane") {
    toolResult(id, "next-lane", args.statePath);
    return;
  }
  if (name === "task_controller_ready_lanes") {
    toolResult(id, "ready-lanes", args.statePath);
    return;
  }
  if (name === "task_controller_complete_lane") {
    argv.push("--lane", requireString(args.lane, "lane"));
    pushString(argv, "--artifact", args.artifact);
    pushString(argv, "--decision", args.decision);
    pushString(argv, "--notes", args.notes);
    toolResult(id, "complete-lane", args.statePath, argv);
    return;
  }
  if (name === "task_controller_insert_lane") {
    argv.push("--lane", requireString(args.lane, "lane"));
    pushString(argv, "--before", args.beforeLane);
    pushString(argv, "--after", args.afterLane);
    pushString(argv, "--kind", args.kind);
    if (args.workerRequired === true) argv.push("--worker-required");
    pushString(argv, "--write-boundary", args.writeBoundary);
    pushString(argv, "--worker-lifecycle", args.workerLifecycle);
    pushString(argv, "--context-policy", args.contextPolicy);
    pushString(argv, "--runtime-preference", args.runtimePreference);
    if (Array.isArray(args.dependsOn)) {
      if (args.dependsOn.length === 0) argv.push("--independent");
      else argv.push("--depends-on", args.dependsOn.map((lane) => requireString(lane, "dependsOn lane")).join(","));
    }
    pushString(argv, "--status", args.status);
    pushString(argv, "--artifact", args.artifact);
    pushString(argv, "--decision", args.decision);
    pushString(argv, "--notes", args.notes);
    toolResult(id, "insert-lane", args.statePath, argv);
    return;
  }
  if (name === "task_controller_register_worker") {
    argv.push("--worker-id", requireString(args.workerId, "workerId"));
    argv.push("--lane", requireString(args.lane, "lane"));
    pushString(argv, "--task", args.task);
    pushString(argv, "--thread-id", args.threadId);
    pushString(argv, "--runtime-handle", args.runtimeHandle);
    pushString(argv, "--request-id", args.requestId);
    pushInteger(argv, "--contract-revision", args.contractRevision);
    pushString(argv, "--contract-digest", args.contractDigest);
    pushString(argv, "--deliverable-fingerprint", args.deliverableFingerprint);
    pushString(argv, "--controller-thread-id", args.controllerThreadId);
    pushString(argv, "--reply-to-thread-id", args.replyToThreadId);
    pushString(argv, "--project-target-type", args.projectTargetType);
    pushString(argv, "--project-id", args.projectId);
    pushString(argv, "--project-environment", args.projectEnvironment);
    pushString(argv, "--lane-runtime", args.laneRuntime);
    pushString(argv, "--prompt", args.prompt);
    pushString(argv, "--packet-id", args.packetId);
    pushString(argv, "--packet-digest", args.packetDigest);
    pushString(argv, "--tool-profile", args.toolProfile);
    pushString(argv, "--credential-policy", args.credentialPolicy);
    pushString(argv, "--thread-tool-check", args.threadToolCheck);
    pushString(argv, "--write-boundary", args.writeBoundary);
    if (Array.isArray(args.reviewsWorkerIds) && args.reviewsWorkerIds.length > 0) {
      argv.push("--reviews-worker-ids", args.reviewsWorkerIds.map((item) => requireString(item, "reviewsWorkerIds item")).join(","));
    }
    if (args.callbackExpected === false) argv.push("--no-callback-expected");
    pushString(argv, "--callback-mode-expected", args.callbackModeExpected);
    toolResult(id, "register-worker", args.statePath, argv);
    return;
  }
  if (name === "task_controller_update_worker") {
    argv.push("--worker-id", requireString(args.workerId, "workerId"));
    pushString(argv, "--status", args.status);
    pushString(argv, "--artifact", args.artifact);
    pushString(argv, "--decision", args.decision);
    pushString(argv, "--notes", args.notes);
    toolResult(id, "update-worker", args.statePath, argv);
    return;
  }
  if (name === "task_controller_list_workers") {
    toolResult(id, "list-workers", args.statePath);
    return;
  }
  if (name === "task_controller_record_correction") {
    argv.push("--event-id", requireString(args.eventId, "eventId"));
    argv.push("--summary", requireString(args.summary, "summary"));
    argv.push("--category", requireString(args.category, "category"));
    if (!Array.isArray(args.requirementIds) || args.requirementIds.length === 0) {
      throw new Error("requirementIds must be a non-empty array.");
    }
    argv.push(
      "--requirement-ids",
      args.requirementIds.map((item) => requireString(item, "requirementIds item")).join(","),
    );
    argv.push(
      "--recommended-invalid-from-lane",
      requireString(args.recommendedInvalidFromLane, "recommendedInvalidFromLane"),
    );
    toolResult(id, "record-correction", args.statePath, argv);
    return;
  }
  if (name === "task_controller_record_approval") {
    pushString(argv, "--approval-id", args.approvalId);
    argv.push("--artifact-id", requireString(args.artifactId, "artifactId"));
    argv.push("--artifact-fingerprint", requireString(args.artifactFingerprint, "artifactFingerprint"));
    argv.push("--approver", requireString(args.approver, "approver"));
    pushString(argv, "--timestamp", args.timestamp);
    toolResult(id, "record-approval", args.statePath, argv);
    return;
  }
  if (name === "task_controller_record_callback") {
    pushString(argv, "--worker-id", args.workerId);
    pushString(argv, "--request-id", args.requestId);
    pushInteger(argv, "--contract-revision", args.contractRevision);
    pushString(argv, "--contract-digest", args.contractDigest);
    pushString(argv, "--deliverable-fingerprint", args.deliverableFingerprint);
    pushString(argv, "--packet-id", args.packetId);
    pushString(argv, "--packet-digest", args.packetDigest);
    pushString(argv, "--message-type", args.messageType);
    argv.push("--from-lane", requireString(args.fromLane, "fromLane"));
    pushString(argv, "--artifact", args.artifact);
    pushString(argv, "--key-findings", args.keyFindings);
    pushString(argv, "--evidence", args.evidence);
    pushString(argv, "--risks", args.risks);
    pushString(argv, "--gate-decision", args.gateDecision);
    pushString(argv, "--next-recommendation", args.nextRecommendation);
    pushString(argv, "--callback-mode-observed", args.callbackModeObserved);
    if (Array.isArray(args.artifactManifest)) argv.push("--artifact-manifest", JSON.stringify(args.artifactManifest));
    if (Array.isArray(args.checkResults)) argv.push("--check-results", JSON.stringify(args.checkResults));
    if (args.writeReceipt && typeof args.writeReceipt === "object") argv.push("--write-receipt", JSON.stringify(args.writeReceipt));
    pushString(argv, "--operation-receipt-id", args.operationReceiptId);
    if (Array.isArray(args.operationReceiptIds) && args.operationReceiptIds.length > 0) {
      argv.push("--operation-receipt-ids", JSON.stringify(args.operationReceiptIds.map((item) => requireString(item, "operationReceiptIds item"))));
    }
    if (Array.isArray(args.verificationResults)) argv.push("--verification-results", JSON.stringify(args.verificationResults));
    if (Array.isArray(args.correctionEvents)) argv.push("--correction-events", JSON.stringify(args.correctionEvents));
    toolResult(id, "record-callback", args.statePath, argv);
    return;
  }
  if (name === "task_controller_issue_operation_permit") {
    argv.push("--permit-id", requireString(args.permitId, "permitId"));
    argv.push("--worker-id", requireString(args.workerId, "workerId"));
    argv.push("--capability-id", requireString(args.capabilityId, "capabilityId"));
    argv.push("--operation-id", requireString(args.operationId, "operationId"));
    argv.push("--target-id", requireString(args.targetId, "targetId"));
    argv.push("--target-locator", requireString(args.targetLocator, "targetLocator"));
    argv.push("--action", requireString(args.action, "action"));
    if (!args.payload || typeof args.payload !== "object" || Array.isArray(args.payload)) throw new Error("payload must be an object.");
    argv.push("--payload", JSON.stringify(args.payload));
    if (args.restrictedFields !== undefined) {
      if (!Array.isArray(args.restrictedFields)) throw new Error("restrictedFields must be an array.");
      if (args.restrictedFields.length) argv.push("--restricted-fields", args.restrictedFields.map((item) => requireString(item, "restrictedFields item")).join(","));
    }
    if (args.approvalRefs !== undefined) {
      if (!Array.isArray(args.approvalRefs)) throw new Error("approvalRefs must be an array.");
      if (args.approvalRefs.length) argv.push("--approval-refs", args.approvalRefs.map((item) => requireString(item, "approvalRefs item")).join(","));
    }
    argv.push("--idempotency-key", requireString(args.idempotencyKey, "idempotencyKey"));
    argv.push("--adapter-id", requireString(args.adapterId, "adapterId"));
    if (args.adapterOptions !== undefined) {
      if (args.adapterOptions === null || typeof args.adapterOptions !== "object" || Array.isArray(args.adapterOptions)) throw new Error("adapterOptions must be an object.");
      argv.push("--adapter-options", JSON.stringify(args.adapterOptions));
    }
    if (!args.readbackSpec || typeof args.readbackSpec !== "object" || Array.isArray(args.readbackSpec)) throw new Error("readbackSpec must be an object.");
    argv.push("--readback-spec", JSON.stringify(args.readbackSpec));
    argv.push("--expires-at", requireString(args.expiresAt, "expiresAt"));
    toolResult(id, "issue-operation-permit", args.statePath, argv);
    return;
  }
  if (name === "task_controller_dispatch_operation") {
    argv.push("--permit-id", requireString(args.permitId, "permitId"));
    pushString(argv, "--claim-id", args.claimId);
    toolResult(id, "dispatch-operation", args.statePath, argv);
    return;
  }
  if (name === "task_controller_reconcile_operation") {
    argv.push("--permit-id", requireString(args.permitId, "permitId"));
    toolResult(id, "reconcile-operation", args.statePath, argv);
    return;
  }
  if (name === "task_controller_revoke_operation_permit") {
    argv.push("--permit-id", requireString(args.permitId, "permitId"));
    pushString(argv, "--reason", args.reason);
    toolResult(id, "revoke-operation-permit", args.statePath, argv);
    return;
  }
  if (name === "task_controller_record_verification_result") {
    argv.push("--worker-id", requireString(args.workerId, "workerId"));
    argv.push("--packet-id", requireString(args.packetId, "packetId"));
    argv.push("--packet-digest", requireString(args.packetDigest, "packetDigest"));
    argv.push("--case-id", requireString(args.caseId, "caseId"));
    if (!Array.isArray(args.artifactManifest) || args.artifactManifest.length === 0) throw new Error("artifactManifest must be a non-empty array.");
    argv.push("--artifact-manifest", JSON.stringify(args.artifactManifest));
    if (!args.verificationResult || typeof args.verificationResult !== "object" || Array.isArray(args.verificationResult)) throw new Error("verificationResult must be an object.");
    argv.push("--verification-result", JSON.stringify(args.verificationResult));
    toolResult(id, "record-verification-result", args.statePath, argv);
    return;
  }
  if (name === "task_controller_gate_check") {
    pushString(argv, "--target-lane", args.targetLane);
    toolResult(id, "gate-check", args.statePath, argv);
    return;
  }
  if (name === "task_controller_revise_contract") {
    argv.push("--invalid-from-lane", requireString(args.invalidFromLane, "invalidFromLane"));
    pushString(argv, "--contract", args.contract);
    if (args.contractSpec && typeof args.contractSpec === "object") {
      argv.push("--contract-spec", JSON.stringify(args.contractSpec));
    }
    if (args.taskBlueprint && typeof args.taskBlueprint === "object") {
      argv.push("--task-blueprint", JSON.stringify(args.taskBlueprint));
    }
    if (Array.isArray(args.consumeCorrectionEventIds) && args.consumeCorrectionEventIds.length > 0) {
      argv.push("--consume-correction-event-ids", args.consumeCorrectionEventIds.map((item) => requireString(item, "consumeCorrectionEventIds item")).join(","));
    }
    pushString(argv, "--reason", args.reason);
    toolResult(id, "revise-contract", args.statePath, argv);
    return;
  }
  if (name === "task_controller_finalize") {
    toolResult(id, "finalize", args.statePath);
    return;
  }
  throw new Error(`Unknown tool: ${name ?? ""}`);
}

async function handleRequest(message) {
  const { id, method, params } = message;
  if (method === "initialize") {
    sendResult(id, {
      protocolVersion: params?.protocolVersion ?? "2025-11-25",
      capabilities: { tools: {} },
      serverInfo: { name: SERVER_NAME, version: "0.1.0" },
      instructions:
        "KY-TASK schema-v2 state enforces execution policy, revision-bound workers, callback identity, and independent review. State tools do not create workers or write final artifacts.",
    });
    return;
  }
  if (method === "ping") {
    sendResult(id, {});
    return;
  }
  if (method === "tools/list") {
    sendResult(id, { tools });
    return;
  }
  if (method === "tools/call") {
    try {
      await handleToolCall(id, params);
    } catch (error) {
      sendError(id, JsonRpcError.INVALID_PARAMS, error instanceof Error ? error.message : String(error));
    }
    return;
  }
  if (id !== undefined) {
    sendError(id, JsonRpcError.METHOD_NOT_FOUND, `Method not found: ${method}`);
  }
}

const lines = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });
lines.on("line", (line) => {
  if (!line.trim()) return;
  try {
    void handleRequest(JSON.parse(line));
  } catch {
    // Ignore malformed non-RPC input.
  }
});
