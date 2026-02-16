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
export { PolyAgent, type PolyAgentConfig } from './agent/agent';
export { UnifiedPolyAgent, type UnifiedPolyAgentConfig } from './agent/unified_agent';
export { CodeModeAgent, type CodeModeAgentConfig } from './agent/codemode_agent';
export { PolyClawAgent, type PolyClawAgentConfig } from './agent/polyclaw_agent';
export {
  UnifiedPolyAgent as UnifiedAgent,
  UnifiedPolyAgent as UnifiedAgentClass,
} from './agent/unified_agent';
export {
  CodeModeAgent as CodeMode,
  CodeModeAgent as CodeModeAgentClass,
} from './agent/codemode_agent';
export {
  PolyClawAgent as PolyClaw,
  PolyClawAgent as PolyClawAgentClass,
} from './agent/polyclaw_agent';

// LLM Providers - from agent/
export {
  OpenAIProvider,
  AnthropicProvider,
  OllamaProvider,
} from './agent/llm_providers';

// Executor - from executor/
export { SandboxExecutor as Executor, SandboxExecutor } from './executor/executor';

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

// Skills CLI (skills.sh)
export { runSkillsCli, type SkillsCliOptions } from './skills_cli';

// MCP Apps
export {
  MCPAppsBuilder,
  MCPAppTemplates,
  createSimpleApp,
  type MCPApp,
  type UIResource,
  type AppTemplate,
  UIResourceType,
} from './mcp_apps/mcp_apps_builder';
export {
  MCPAppsServer,
  MCPAppsServerFactory,
} from './mcp_apps/mcp_apps_server';
export {
  MCPAppBuilder,
  MCPAppRegistry,
  UIComponentType,
  type UIComponent,
} from './mcp_apps/mcp_apps';

// Registry - from registry/
export {
  ServerRegistry,
  ToolRegistry,
  MultiServerRegistry,
  getGlobalRegistry,
  resetGlobalRegistry,
} from './registry';

// Validation - from validation/
export {
  validate,
  validateOrThrow,
  validateToolDefinition,
  validateToolParameters,
  schemas,
} from './validation';

// Configuration - from config/
export {
  ConfigManager,
  loadConfig,
  getRequiredEnv,
  getGlobalConfig,
  initConfig,
  resetGlobalConfig,
  loadFromEnv,
  getDefaultPort,
  isProduction,
  isDevelopment,
  getLogLevel,
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
  AgentConfig,
  ServerStats,
  PolyMCPConfig,
} from './types';
