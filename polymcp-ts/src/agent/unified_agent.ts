/**
 * Unified PolyAgent - Supports both HTTP and Stdio MCP Servers
 * Production-ready agent that seamlessly works with both server types.
 * Provides autonomous agentic behavior with multi-step reasoning.
 */

import axios from 'axios';
import * as fs from 'fs';
import { createHash } from 'crypto';
import {
  LLMProvider,
  MCPToolMetadata,
  ToolResult,
  ToolWithServer,
  AgentAction,
  StdioServerConfig,
  ToolSelection,
  ContinuationDecision,
} from '../types';
import { MCPStdioClient, MCPStdioAdapter } from '../stdio';
import { buildSkillsShContext, loadSkillsSh, SkillsShEntry } from '../skills_sh';

export interface UnifiedPolyAgentConfig {
  llmProvider: LLMProvider;
  mcpServers?: string[];
  stdioServers?: StdioServerConfig[];
  registryPath?: string;
  verbose?: boolean;
  memoryEnabled?: boolean;
  maxRetries?: number;
  retryBackoffMs?: number;
  neverStuckMode?: boolean;
  maxNoProgressSteps?: number;
  toolCooldownSteps?: number;
  loopGuardWindow?: number;
  stepDelayMs?: number;
  skillsShEnabled?: boolean;
  skillsShDirs?: string[];
  skillsShMaxSkills?: number;
  skillsShMaxChars?: number;
}

/**
 * Enhanced PolyAgent with stdio support and autonomous behavior
 */
export class UnifiedPolyAgent {
  // System prompts
  private static TOOL_SELECTION_SYSTEM = `You are an autonomous AI agent with access to tools provided by MCP (Model Context Protocol) servers.

IMPORTANT CONCEPTS:
1. Tools are automatically available - you can use any tool listed below immediately
2. Some tools require data from other tools (e.g., to interact with elements, you need references from a snapshot first)
3. You work in steps - select ONE tool at a time that moves toward completing the user's goal
4. Available tools come from currently connected MCP servers and update dynamically

Your job: Select the NEXT BEST tool to execute based on:
- The user's original request
- What has already been done
- What information you have
- What information you still need

Available tools:
{tool_descriptions}`;

  private static CONTINUATION_DECISION_SYSTEM = `You are evaluating whether an autonomous agent should continue working or stop.

STOP when:
- The user's request is fully completed
- The task is impossible (requires login, external permissions, unavailable data)
- Multiple consecutive failures suggest the approach won't work
- No progress is being made

CONTINUE when:
- The request is partially completed and more steps are needed
- A clear next action exists that can make progress
- Previous failures were due to missing information that you can now obtain

Be decisive and realistic about what's achievable.`;

  private static FINAL_RESPONSE_SYSTEM = `You are summarizing what an autonomous agent accomplished.

RULES:
1. Use ONLY information from the actual tool results provided
2. DO NOT invent, assume, or hallucinate details
3. Be factual and concise
4. If something failed, state it clearly
5. Don't mention technical details (tool names, JSON, APIs, etc.)
6. Speak naturally as if you did the actions yourself

Focus on what was accomplished, not how it was done.`;

  private llmProvider: LLMProvider;
  private mcpServers: string[];
  private stdioConfigs: StdioServerConfig[];
  private verbose: boolean;
  private memoryEnabled: boolean;
  private httpToolsCache: Map<string, MCPToolMetadata[]>;
  private stdioClients: Map<string, MCPStdioClient>;
  private stdioAdapters: Map<string, MCPStdioAdapter>;
  private persistentHistory: AgentAction[] | null;
  private maxRetries: number;
  private retryBackoffMs: number;
  private neverStuckMode: boolean;
  private maxNoProgressSteps: number;
  private toolCooldownSteps: number;
  private loopGuardWindow: number;
  private stepDelayMs: number;
  private skillsShEnabled: boolean;
  private skillsShEntries: SkillsShEntry[];
  private skillsShMaxSkills: number;
  private skillsShMaxChars: number;
  private noProgressSteps: number;
  private toolCooldowns: Map<string, number>;
  private recentCallSignatures: string[];
  private recentResultSignatures: string[];

  constructor(config: UnifiedPolyAgentConfig) {
    this.llmProvider = config.llmProvider;
    this.mcpServers = config.mcpServers || [];
    this.stdioConfigs = config.stdioServers || [];
    this.verbose = config.verbose || false;
    this.memoryEnabled = config.memoryEnabled !== false;
    this.httpToolsCache = new Map();
    this.stdioClients = new Map();
    this.stdioAdapters = new Map();
    this.persistentHistory = this.memoryEnabled ? [] : null;
    this.maxRetries = config.maxRetries ?? 2;
    this.retryBackoffMs = config.retryBackoffMs ?? 800;
    this.neverStuckMode = config.neverStuckMode !== false;
    this.maxNoProgressSteps = config.maxNoProgressSteps ?? 4;
    this.toolCooldownSteps = config.toolCooldownSteps ?? 2;
    this.loopGuardWindow = Math.max(4, config.loopGuardWindow ?? 8);
    this.stepDelayMs = config.stepDelayMs ?? 150;
    this.skillsShEnabled = config.skillsShEnabled !== false;
    this.skillsShEntries = this.skillsShEnabled ? loadSkillsSh(config.skillsShDirs) : [];
    this.skillsShMaxSkills = config.skillsShMaxSkills ?? 4;
    this.skillsShMaxChars = config.skillsShMaxChars ?? 5000;
    this.noProgressSteps = 0;
    this.toolCooldowns = new Map();
    this.recentCallSignatures = [];
    this.recentResultSignatures = [];

    if (config.registryPath) {
      this.loadRegistry(config.registryPath);
    }
  }

  /**
   * Load servers from registry
   */
  private loadRegistry(registryPath: string): void {
    try {
      const data = fs.readFileSync(registryPath, 'utf-8');
      const registry = JSON.parse(data);

      const httpServers = registry.servers || [];
      this.mcpServers.push(...httpServers);

      const stdioServers = registry.stdio_servers || [];
      this.stdioConfigs.push(...stdioServers);

      if (this.verbose) {
        console.log(`Loaded ${httpServers.length} HTTP and ${stdioServers.length} stdio servers`);
      }
    } catch (error: any) {
      if (this.verbose) {
        console.log(`Failed to load registry: ${error.message}`);
      }
    }
  }

  /**
   * Start all stdio servers and discover tools
   */
  async start(): Promise<void> {
    for (const config of this.stdioConfigs) {
      try {
        const client = new MCPStdioClient(config);
        await client.start();

        const adapter = new MCPStdioAdapter(client);
        const serverId = `stdio://${config.command}`;
        
        this.stdioClients.set(serverId, client);
        this.stdioAdapters.set(serverId, adapter);

        if (this.verbose) {
          const tools = await adapter.getTools();
          console.log(`Started stdio server: ${serverId} (${tools.length} tools)`);
        }
      } catch (error: any) {
        if (this.verbose) {
          console.log(`Failed to start stdio server: ${error.message}`);
        }
      }
    }

    await this.discoverHttpTools();

    // Wait for stabilization
    if (this.stdioClients.size > 0 || this.mcpServers.length > 0) {
      await new Promise(resolve => setTimeout(resolve, 2000));
    }
  }

  /**
   * Discover tools from HTTP servers
   */
  private async discoverHttpTools(): Promise<void> {
    for (const serverUrl of this.mcpServers) {
      try {
        const listUrl = `${serverUrl}/list_tools`;
        const response = await axios.get(listUrl, { timeout: 5000 });

        const tools = response.data.tools || [];
        this.httpToolsCache.set(serverUrl, tools);

        if (this.verbose) {
          console.log(`Discovered ${tools.length} tools from ${serverUrl}`);
        }
      } catch (error: any) {
        if (this.verbose) {
          console.log(`Failed to discover tools from ${serverUrl}: ${error.message}`);
        }
      }
    }
  }

  /**
   * Get all tools from both HTTP and stdio servers
   */
  private async getAllTools(): Promise<ToolWithServer[]> {
    const allTools: ToolWithServer[] = [];

    // HTTP tools
    for (const [serverUrl, tools] of this.httpToolsCache.entries()) {
      for (const tool of tools) {
        allTools.push({
          ...tool,
          _server_url: serverUrl,
          _server_type: 'http',
        });
      }
    }

    // Stdio tools
    for (const [serverId, adapter] of this.stdioAdapters.entries()) {
      try {
        const tools = await adapter.getTools();
        for (const tool of tools) {
          allTools.push({
            ...tool,
            _server_url: serverId,
            _server_type: 'stdio',
          });
        }
      } catch (error: any) {
        if (this.verbose) {
          console.log(`Failed to get tools from ${serverId}: ${error.message}`);
        }
      }
    }

    return allTools;
  }

  /**
   * Execute tool (HTTP or stdio)
   */
  private async executeTool(tool: ToolWithServer): Promise<ToolResult> {
    const serverUrl = tool._server_url!;
    const serverType = tool._server_type!;
    const toolName = tool.name;
    const parameters = tool._parameters || {};

    try {
      if (serverType === 'http') {
        const invokeUrl = `${serverUrl}/invoke/${toolName}`;
        const response = await axios.post(invokeUrl, parameters, { timeout: 30000 });
        return response.data;
      } else if (serverType === 'stdio') {
        const adapter = this.stdioAdapters.get(serverUrl);
        if (!adapter) {
          return { status: 'error', error: 'Stdio adapter not found' };
        }
        return await adapter.invokeTool(toolName, parameters);
      } else {
        return { status: 'error', error: `Unknown server type: ${serverType}` };
      }
    } catch (error: any) {
      const errorMsg = `Tool execution failed: ${error.message}`;
      if (this.verbose) {
        console.log(`âŒ ${errorMsg}`);
      }
      return { status: 'error', error: errorMsg };
    }
  }

  private async executeToolWithRetry(tool: ToolWithServer): Promise<ToolResult> {
    let lastError: string | null = null;

    for (let attempt = 0; attempt <= this.maxRetries; attempt++) {
      const result = await this.executeTool(tool);
      if (result.status === 'success') {
        return result;
      }

      lastError = result.error || 'Unknown tool error';
      if (attempt < this.maxRetries) {
        const waitMs = this.retryBackoffMs * (attempt + 1);
        if (this.verbose) {
          console.log(`Retrying ${tool.name} in ${waitMs}ms (attempt ${attempt + 2}/${this.maxRetries + 1})`);
        }
        await new Promise(resolve => setTimeout(resolve, waitMs));
      }
    }

    return { status: 'error', error: lastError || 'Tool failed after retries' };
  }

  private makeCallSignature(toolName: string, params: Record<string, any>): string {
    const payload = JSON.stringify({ tool: toolName, params: params || {} });
    return createHash('md5').update(payload).digest('hex');
  }

  private makeResultSignature(result: ToolResult): string {
    const base = result.status === 'success'
      ? JSON.stringify({ status: 'success', result: result.result ?? null })
      : JSON.stringify({ status: 'error', error: result.error ?? '' });
    return createHash('md5').update(base).digest('hex');
  }

  private isToolOnCooldown(toolName: string, currentStep: number): boolean {
    const releaseAt = this.toolCooldowns.get(toolName);
    if (releaseAt === undefined) {
      return false;
    }
    if (currentStep >= releaseAt) {
      this.toolCooldowns.delete(toolName);
      return false;
    }
    return true;
  }

  private updateLoopGuard(
    toolName: string,
    parameters: Record<string, any>,
    result: ToolResult,
    currentStep: number
  ): { hardStall: boolean; cooldownApplied: boolean } {
    const callSig = this.makeCallSignature(toolName, parameters);
    const resultSig = this.makeResultSignature(result);
    const repeatedCall = this.recentCallSignatures.includes(callSig);
    const repeatedResult = this.recentResultSignatures.includes(resultSig);
    const noProgress = result.status !== 'success' || repeatedResult;

    this.recentCallSignatures.push(callSig);
    this.recentResultSignatures.push(resultSig);
    if (this.recentCallSignatures.length > this.loopGuardWindow) this.recentCallSignatures.shift();
    if (this.recentResultSignatures.length > this.loopGuardWindow) this.recentResultSignatures.shift();

    this.noProgressSteps = noProgress ? this.noProgressSteps + 1 : 0;

    let cooldownApplied = false;
    if (this.neverStuckMode && (result.status !== 'success' || (repeatedCall && repeatedResult))) {
      this.toolCooldowns.set(toolName, currentStep + Math.max(1, this.toolCooldownSteps));
      cooldownApplied = true;
    }

    return {
      hardStall: this.noProgressSteps >= Math.max(2, this.maxNoProgressSteps),
      cooldownApplied,
    };
  }

  /**
   * Extract previous results for LLM context
   */
  private extractPreviousResults(actionHistory: AgentAction[]): string {
    if (actionHistory.length === 0) {
      return 'No previous results available.';
    }

    const resultsText: string[] = [];

    // Get last 5 successful results
    const recentActions = actionHistory.slice(-5).reverse();
    
    for (const action of recentActions) {
      if (action.result.status === 'success') {
        const toolName = action.tool;
        const resultData = action.result.result || {};

        const contentParts: string[] = [];

        if (typeof resultData === 'object' && resultData !== null) {
          // Look for content field
          if ('content' in resultData) {
            const content = resultData.content;
            if (Array.isArray(content)) {
              for (const item of content.slice(0, 3)) {
                if (typeof item === 'object' && item !== null && 'text' in item) {
                  contentParts.push(String(item.text));
                } else if (typeof item === 'string') {
                  contentParts.push(item);
                }
              }
            } else if (typeof content === 'string') {
              contentParts.push(content);
            }
          }

          // Look for other common fields
          for (const field of ['output', 'data', 'result', 'text', 'value', 'message']) {
            if (field in resultData && field !== 'content') {
              const value = String(resultData[field]);
              contentParts.push(`${field}: ${value}`);
            }
          }
        } else if (typeof resultData === 'string') {
          contentParts.push(resultData);
        } else if (Array.isArray(resultData) && resultData.length > 0) {
          for (const item of resultData.slice(0, 3)) {
            contentParts.push(String(item));
          }
        }

        if (contentParts.length > 0) {
          const resultText = `\nResult from '${toolName}':\n${contentParts.join('\n')}`;
          resultsText.push(resultText);
        }
      }
    }

    if (resultsText.length > 0) {
      return `PREVIOUS TOOL RESULTS (use any values/references from here):\n${resultsText.join('\n---\n')}`;
    } else {
      return 'Previous actions completed but no detailed output available.';
    }
  }

  /**
   * Select next action using LLM
   */
  private async selectNextAction(
    userMessage: string,
    actionHistory: AgentAction[],
    allTools: ToolWithServer[]
  ): Promise<ToolWithServer | null> {
    if (allTools.length === 0) {
      return null;
    }

    // Blocking logic for repetitions
    const blockedActions = new Set<string>();
    const warnings: string[] = [];

    if (actionHistory.length > 0) {
      const lastAction = actionHistory[actionHistory.length - 1];
      const lastTool = lastAction.tool;
      const lastParams = lastAction.parameters;
      const lastStatus = lastAction.result.status;

      // Count consecutive same actions
      let consecutiveSame = 0;
      for (let i = actionHistory.length - 1; i >= 0; i--) {
        const action = actionHistory[i];
        if (action.tool === lastTool && JSON.stringify(action.parameters) === JSON.stringify(lastParams)) {
          consecutiveSame++;
        } else {
          break;
        }
      }

      // Block repeated successful actions
      if (lastStatus === 'success' && consecutiveSame >= 2) {
        const blockedKey = `${lastTool}:${JSON.stringify(lastParams)}`;
        blockedActions.add(blockedKey);
        warnings.push(`Already executed ${lastTool} successfully ${consecutiveSame} times`);
      }

      // Block repeated failures
      if (lastStatus !== 'success' && consecutiveSame >= 3) {
        const blockedKey = `${lastTool}:${JSON.stringify(lastParams)}`;
        blockedActions.add(blockedKey);
        warnings.push(`${lastTool} failed ${consecutiveSame} times`);
      }
    }

    if (this.neverStuckMode) {
      const currentStep = actionHistory.length + 1;
      for (const tool of allTools) {
        if (this.isToolOnCooldown(tool.name, currentStep)) {
          blockedActions.add(`${tool.name}:`);
        }
      }
    }

    // Build action history summary
    const historyLines: string[] = [];
    let historyContext: string;

    if (actionHistory.length === 0) {
      historyContext = 'No actions taken yet. This is your first action.';
    } else {
      const recentActions = actionHistory.slice(-5);
      for (const action of recentActions) {
        const status = action.result.status === 'success' ? 'âœ“' : 'âœ—';
        const paramsStr = Object.keys(action.parameters).length > 0 
          ? JSON.stringify(action.parameters) 
          : 'no params';
        historyLines.push(`  ${status} ${action.tool} ${paramsStr}`);
      }

      historyContext = `Recent actions:\n${historyLines.join('\n')}`;
      if (warnings.length > 0) {
        historyContext += `\n\nWarnings:\n${warnings.map(w => `  - ${w}`).join('\n')}`;
      }
    }

    // Extract previous results
    const previousResults = this.extractPreviousResults(actionHistory);

    // Build tool descriptions
    const toolsList: string[] = [];
    for (let i = 0; i < allTools.length; i++) {
      const tool = allTools[i];
      const schema = tool.input_schema || {};
      const properties = schema.properties || {};
      const required = schema.required || [];

      const paramsDesc: string[] = [];
      for (const [paramName, paramInfo] of Object.entries(properties)) {
        const info = paramInfo as any;
        const paramType = info.type || 'any';
        const reqMark = required.includes(paramName) ? '*' : '';
        const paramDesc = (info.description || '').substring(0, 80);
        paramsDesc.push(`    - ${paramName}${reqMark} (${paramType}): ${paramDesc}`);
      }

      const paramsStr = paramsDesc.length > 0 ? paramsDesc.join('\n') : '    No parameters';

      const blockedKey = `${tool.name}:`;
      const blocked = Array.from(blockedActions).some(key => key.startsWith(blockedKey)) ? ' [BLOCKED]' : '';

      toolsList.push(`[${i}] ${tool.name}${blocked} - ${tool.description}\n${paramsStr}`);
    }

    const toolDescriptions = toolsList.join('\n\n');

    // Build prompts
    const systemPrompt = UnifiedPolyAgent.TOOL_SELECTION_SYSTEM.replace(
      '{tool_descriptions}',
      toolDescriptions
    );

    const skillsCtx = this.skillsShEnabled
      ? buildSkillsShContext(
          userMessage,
          this.skillsShEntries,
          this.skillsShMaxSkills,
          this.skillsShMaxChars
        )
      : '';

    const userPrompt = `USER REQUEST: "${userMessage}"

${historyContext}

${previousResults}

${skillsCtx}

TASK: Select the NEXT tool to make progress. Use actual values from previous results when needed.

RESPONSE FORMAT (JSON only):
{
  "tool_index": <number from 0 to ${allTools.length - 1}>,
  "tool_name": "<exact tool name>",
  "parameters": {"param1": "value1", "param2": "value2"},
  "reasoning": "<why this tool and how it progresses the goal>"
}

If no suitable tool or task is complete/impossible:
{
  "tool_index": -1,
  "reasoning": "<explanation>"
}

JSON only:`;

    const fullPrompt = `${systemPrompt}\n\n${userPrompt}`;

    try {
      let llmResponse = await this.llmProvider.generate(fullPrompt);
      llmResponse = llmResponse.trim();

      // Extract JSON
      if (llmResponse.includes('```json')) {
        llmResponse = llmResponse.split('```json')[1].split('```')[0].trim();
      } else if (llmResponse.includes('```')) {
        llmResponse = llmResponse.split('```')[1].split('```')[0].trim();
      }

      const start = llmResponse.indexOf('{');
      const end = llmResponse.lastIndexOf('}') + 1;
      if (start !== -1 && end > start) {
        llmResponse = llmResponse.substring(start, end);
      }

      if (this.verbose) {
        console.log(`LLM response: ${llmResponse.substring(0, 150)}...`);
      }

      const selection: ToolSelection = JSON.parse(llmResponse);

      const toolIndex = selection.tool_index;
      if (toolIndex < 0) {
        if (this.verbose) {
          console.log(`âŠ˜ No tool selected: ${selection.reasoning}`);
        }
        return null;
      }

      if (toolIndex >= allTools.length) {
        if (this.verbose) {
          console.log(`âš  Invalid index ${toolIndex}`);
        }
        return null;
      }

      let selectedTool = { ...allTools[toolIndex] };

      // Validate tool name if provided
      const claimedName = selection.tool_name;
      if (claimedName && claimedName !== selectedTool.name) {
        // Try to find by name
        for (let i = 0; i < allTools.length; i++) {
          if (allTools[i].name === claimedName) {
            selectedTool = { ...allTools[i] };
            if (this.verbose) {
              console.log(`ðŸ”„ Corrected tool selection: ${claimedName}`);
            }
            break;
          }
        }
      }

      selectedTool._parameters = selection.parameters;
      selectedTool._reasoning = selection.reasoning;

      if (this.neverStuckMode) {
        const currentStep = actionHistory.length + 1;
        if (this.isToolOnCooldown(selectedTool.name, currentStep)) {
          const alternative = allTools.find(t => !this.isToolOnCooldown(t.name, currentStep));
          if (alternative) {
            selectedTool = { ...alternative };
            selectedTool._parameters = {};
            selectedTool._reasoning = 'Selected fallback tool due to cooldown on previous repetitive action';
          } else {
            return null;
          }
        }
      }

      if (this.verbose) {
        console.log(`âœ“ Selected: ${selectedTool.name}`);
        console.log(`  Params: ${JSON.stringify(selectedTool._parameters)}`);
        console.log(`  Why: ${selectedTool._reasoning}`);
      }

      return selectedTool;
    } catch (error: any) {
      if (this.verbose) {
        console.log(`âœ— Selection failed: ${error.message}`);
      }
      return null;
    }
  }

  /**
   * Decide if should continue execution
   */
  private async shouldContinue(
    userMessage: string,
    actionHistory: AgentAction[]
  ): Promise<{ continue: boolean; reason: string }> {
    const totalActions = actionHistory.length;
    let consecutiveFailures = 0;

    for (let i = actionHistory.length - 1; i >= 0; i--) {
      if (actionHistory[i].result.status !== 'success') {
        consecutiveFailures++;
      } else {
        break;
      }
    }

    // Auto-stop on too many failures
    if (consecutiveFailures >= 3) {
      return {
        continue: false,
        reason: `Stopped: ${consecutiveFailures} consecutive failures`,
      };
    }

    if (this.neverStuckMode && this.noProgressSteps >= this.maxNoProgressSteps + 2) {
      return {
        continue: false,
        reason: `Stopped: no progress after ${this.noProgressSteps} steps`,
      };
    }

    // Build context
    const recentActions = actionHistory.slice(-3);
    const historySummary: string[] = [];
    for (const action of recentActions) {
      const status = action.result.status === 'success' ? 'âœ“' : 'âœ—';
      historySummary.push(`  ${status} Step ${action.step}: ${action.tool}`);
    }

    const historyText = historySummary.join('\n');

    const prompt = `${UnifiedPolyAgent.CONTINUATION_DECISION_SYSTEM}

CONTEXT:
User request: "${userMessage}"
Total actions taken: ${totalActions}
Consecutive failures: ${consecutiveFailures}

Recent actions:
${historyText}

DECIDE: Should the agent continue or stop?

RESPONSE FORMAT (JSON only):
{
  "continue": true/false,
  "reason": "<brief clear explanation>"
}

JSON only:`;

    try {
      let llmResponse = await this.llmProvider.generate(prompt);
      llmResponse = llmResponse.trim();

      // Extract JSON
      if (llmResponse.includes('```json')) {
        llmResponse = llmResponse.split('```json')[1].split('```')[0].trim();
      } else if (llmResponse.includes('```')) {
        llmResponse = llmResponse.split('```')[1].split('```')[0].trim();
      }

      const start = llmResponse.indexOf('{');
      const end = llmResponse.lastIndexOf('}') + 1;
      if (start !== -1 && end > start) {
        llmResponse = llmResponse.substring(start, end);
      }

      const decision: ContinuationDecision = JSON.parse(llmResponse);
      const shouldContinue = decision.continue;
      const reason = decision.reason;

      if (this.verbose) {
        console.log(`ðŸ§  ${shouldContinue ? 'â†’ Continue' : 'âŠ¡ Stop'}: ${reason}`);
      }

      return { continue: shouldContinue, reason };
    } catch (error: any) {
      if (this.verbose) {
        console.log(`âœ— Decision failed: ${error.message}`);
      }
      return { continue: false, reason: 'Decision error, stopping to be safe' };
    }
  }

  /**
   * Generate final response
   */
  private async generateFinalResponse(
    userMessage: string,
    actionHistory: AgentAction[]
  ): Promise<string> {
    if (actionHistory.length === 0) {
      return "I couldn't find any suitable tools to complete your request.";
    }

    // Extract results
    const resultsData: string[] = [];
    for (const action of actionHistory) {
      const result = action.result;
      const status = result.status;

      if (status === 'success') {
        const resultContent = result.result || {};
        
        if (typeof resultContent === 'object' && resultContent !== null) {
          const content = (resultContent as any).content;
          if (Array.isArray(content)) {
            const textParts: string[] = [];
            for (const item of content) {
              if (typeof item === 'object' && item !== null && 'text' in item) {
                textParts.push(String(item.text));
              }
            }
            if (textParts.length > 0) {
              resultsData.push(`Step ${action.step}: ${textParts.join(' ')}`);
            } else {
              resultsData.push(`Step ${action.step}: Action completed`);
            }
          } else {
            resultsData.push(`Step ${action.step}: ${JSON.stringify(resultContent)}`);
          }
        } else {
          resultsData.push(`Step ${action.step}: ${String(resultContent)}`);
        }
      } else {
        const error = result.error || 'Unknown error';
        resultsData.push(`Step ${action.step}: Failed - ${error}`);
      }
    }

    const resultsText = resultsData.length > 0 
      ? resultsData.join('\n') 
      : 'Actions completed';

    const prompt = `${UnifiedPolyAgent.FINAL_RESPONSE_SYSTEM}

USER'S ORIGINAL REQUEST:
"${userMessage}"

WHAT HAPPENED (tool execution results):
${resultsText}

YOUR TASK: Write a natural, conversational response explaining what you accomplished.

Response:`;

    try {
      const response = await this.llmProvider.generate(prompt);
      return response.trim();
    } catch (error: any) {
      if (this.verbose) {
        console.log(`âœ— Response generation failed: ${error.message}`);
      }
      const successCount = actionHistory.filter(a => a.result.status === 'success').length;
      return `I completed ${successCount} out of ${actionHistory.length} actions.`;
    }
  }

  /**
   * Process user request with agentic loop
   */
  async runAsync(userMessage: string, maxSteps: number = 10): Promise<string> {
    if (this.verbose) {
      console.log('\n' + '='.repeat(60));
      console.log(`User: ${userMessage}`);
      console.log('='.repeat(60));
    }

    // Use persistent history if enabled
    let actionHistory: AgentAction[] = [];
    if (this.memoryEnabled && this.persistentHistory) {
      actionHistory = [...this.persistentHistory];
      if (this.verbose) {
        console.log(`ðŸ“š Loaded ${actionHistory.length} previous actions from memory`);
      }
    }

    const initialLength = actionHistory.length;
    this.noProgressSteps = 0;
    this.toolCooldowns.clear();
    this.recentCallSignatures = [];
    this.recentResultSignatures = [];

    for (let step = 0; step < maxSteps; step++) {
      const currentStep = actionHistory.length + 1;
      if (this.verbose) {
        console.log(`\nðŸ¤– Step ${currentStep} (iteration ${step + 1}/${maxSteps})`);
      }

      // Check if should continue (skip first iteration)
      if (step > 0) {
        const decision = await this.shouldContinue(userMessage, actionHistory);
        if (!decision.continue) {
          if (this.verbose) {
            console.log(`âœ“ Stopping: ${decision.reason}`);
          }
          break;
        }
      }

      // Select next action
      const allTools = await this.getAllTools();
      const selectedTool = await this.selectNextAction(userMessage, actionHistory, allTools);

      if (!selectedTool) {
        if (this.verbose) {
          console.log('âš  No tool selected');
        }
        break;
      }

      // Execute tool
      if (this.verbose) {
        console.log(`ðŸ”§ Executing: ${selectedTool.name}`);
        if (selectedTool._parameters && Object.keys(selectedTool._parameters).length > 0) {
          console.log(`   Params: ${JSON.stringify(selectedTool._parameters)}`);
        }
      }

      const toolResult = await this.executeToolWithRetry(selectedTool);

      // Log result
      if (this.verbose) {
        const status = toolResult.status;
        if (status === 'success') {
          console.log('   âœ… Success');
        } else {
          const error = toolResult.error || 'Unknown';
          console.log(`   âŒ Failed: ${error}`);
        }
      }

      // Save to history
      actionHistory.push({
        step: currentStep,
        tool: selectedTool.name,
        parameters: selectedTool._parameters || {},
        reasoning: selectedTool._reasoning || '',
        result: toolResult,
        timestamp: new Date(),
      });

      const guard = this.updateLoopGuard(
        selectedTool.name,
        selectedTool._parameters || {},
        toolResult,
        currentStep
      );
      if (this.verbose && guard.cooldownApplied) {
        console.log(`Loop guard applied cooldown to ${selectedTool.name} (no-progress steps: ${this.noProgressSteps})`);
      }
      if (guard.hardStall) {
        if (this.verbose) {
          console.log(`Stopping due to hard stall after ${this.noProgressSteps} no-progress steps`);
        }
        break;
      }

      // Pause between actions
      await new Promise(resolve => setTimeout(resolve, this.stepDelayMs));
    }

    // Update persistent history if enabled
    if (this.memoryEnabled) {
      this.persistentHistory = actionHistory;
    }

    // Generate response only for new actions
    const newActions = actionHistory.slice(initialLength);
    const response = await this.generateFinalResponse(userMessage, newActions);

    if (this.verbose) {
      console.log('\n' + '='.repeat(60));
      console.log(`Agent: ${response}`);
      console.log('='.repeat(60));
    }

    return response;
  }

  /**
   * Reset persistent memory
   */
  resetMemory(): void {
    if (this.memoryEnabled) {
      this.persistentHistory = [];
      if (this.verbose) {
        console.log('ðŸ”„ Memory reset');
      }
    }
  }

  /**
   * Stop all stdio servers
   */
  async stop(): Promise<void> {
    for (const client of this.stdioClients.values()) {
      await client.stop();
    }

    this.stdioClients.clear();
    this.stdioAdapters.clear();
  }
}
