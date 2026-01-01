/**
 * PolyMCP - TypeScript Implementation
 * Model Context Protocol toolkit for building MCP servers and agents
 * 
 * @packageDocumentation
 */

// Core exports from root files
export * from './types';
export * from './constants';
export * from './errors';
export * from './version';

// Tool helpers (from toolkit)
export * from './toolkit/tool-helpers';

// Expose modules (HTTP, In-process) - from toolkit/
export { exposeToolsHttp, exposeToolsInprocess, InProcessMCPServer } from './toolkit/expose';

// NEW: Stdio Server (root level)
export { exposeToolsStdio, StdioMCPServer } from './expose_tools_stdio';

// NEW: Dual Mode (root level)
export { DualModeMCPServer, exposeDualMode, runDualMode } from './dual_mode_mcp';

// Client - from stdio/
export { createMCPClient } from './stdio/client';

// NEW: Stdio Client (root level)
export { 
  MCPStdioClient, 
  withStdioClient, 
  StdioClientPool 
} from './mcp_stdio_client';

// Agent - from agent/
export {
  PolyAgent,
  UnifiedAgent,
  CodeModeAgent,
} from './agent/agent';

export {
  UnifiedAgent as UnifiedAgentClass,
  CodeModeAgent as CodeModeAgentClass,
} from './agent/unified_agent';

export {
  CodeModeAgent as CodeMode,
} from './agent/codemode_agent';

// LLM Providers - from agent/
export {
  OpenAIProvider,
  AnthropicProvider,
  OllamaProvider,
} from './agent/llm_providers';

// Executor - from executor/
export { Executor } from './executor/executor';

// NEW: Docker Executor - from executor/
export {
  DockerSandboxExecutor,
  executeInDocker,
  type DockerExecutionResult,
  type DockerExecutorOptions,
} from './executor/docker';

// Tools API - from executor/
export { ToolsAPI } from './executor/tools_api';

// NEW: Advanced Tools - from tools/
export {
  advancedTools,
  fileTools,
  webTools,
  executionTools,
  utilityTools,
  webSearch,
  executeCode,
  readFile,
  writeFile,
  listDirectory,
  shellCommand,
  httpRequest,
  getCurrentTime,
} from './tools/advanced';

// NEW: Skills System - from skills/
export {
  MCPSkillGenerator,
  type SkillGeneratorOptions,
} from './skills/generator';

export {
  MCPSkillLoader,
  loadSkills,
  loadAllSkills,
  type LoadedSkill,
  type SkillLoaderOptions,
} from './skills/loader';

export {
  MCPSkillMatcher,
  matchSkills,
  type SkillMatch,
  type MatchOptions,
} from './skills/matcher';

// Registry - from registry/
export {
  ToolRegistry,
  MultiServerRegistry,
} from './registry';

// Validation - from validation/
export {
  validateToolDefinition,
  validateToolParameters,
} from './validation';

// Configuration - from config/
export {
  loadConfig,
  type PolyMCPConfig,
} from './config';

// CLI (programmatic access) - from cli/
export { initCommand } from './cli/commands/init';
export { testCommand } from './cli/commands/test';

// Re-export commonly used types
export type {
  MCPTool,
  MCPToolMetadata,
  ToolResult,
  LLMProvider,
  AgentOptions,
  ServerStats,
} from './types';
