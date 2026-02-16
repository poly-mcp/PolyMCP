/**
 * PolyClaw Agent
 *
 * Autonomous shell-first agent inspired by OpenClaw, specialized for PolyMCP workflows.
 */

import { createHash, randomUUID } from 'crypto';
import { spawn } from 'child_process';
import readline from 'readline';
import { LLMProvider } from '../types';

const FINAL_BLOCK_RE = /```(?:FINAL|final)\s*\r?\n([\s\S]*?)```/;

const COMMON_SHELL_COMMANDS = new Set([
  'ls',
  'dir',
  'find',
  'rg',
  'grep',
  'cat',
  'head',
  'tail',
  'wc',
  'echo',
  'pwd',
  'cd',
  'python',
  'python3',
  'pip',
  'pip3',
  'git',
  'docker',
  'npm',
  'pnpm',
  'yarn',
  'curl',
  'wget',
  'sed',
  'awk',
  'xargs',
  'sort',
  'uniq',
  'stat',
  'tree',
  'node',
  'npx',
  'tsx',
]);

const MCP_INTENT_HINTS = [
  'mcp',
  'polymcp',
  'server',
  'registry',
  'list_tools',
  'invoke',
  'stdio',
  '/mcp',
  'tool',
];

const RESEARCH_INTENT_HINTS = [
  'best',
  'miglior',
  'ristorante',
  'restaurant',
  'news',
  'notizie',
  'search',
  'ricerca',
  'trova',
  'meteo',
  'weather',
  'prezzo',
  'price',
  'who is',
  'chi e',
  'quale',
  'dimmi',
];

const FINAL_PLACEHOLDER_PATTERNS = new Set([
  'clear final answer for the user',
  'final user-facing answer with concrete results',
  'your final answer here',
]);

const REMOVAL_CLAIM_PATTERNS = [
  /\brimoss[oaie]\b/i,
  /\beliminat[oaie]\b/i,
  /\brimozion[ea]\b/i,
  /\bdeleted?\b/i,
  /\bremoved?\b/i,
];

const DANGEROUS_COMMAND_PATTERNS: Array<{ pattern: RegExp; reason: string }> = [
  { pattern: /\bgit\s+reset\s+--hard\b/i, reason: 'blocked dangerous git reset --hard' },
  { pattern: /\bgit\s+clean\s+-[a-z]*f[a-z]*\b/i, reason: 'blocked dangerous git clean' },
  { pattern: /\brm\s+-rf\s+\/(?:\s|$)/i, reason: 'blocked dangerous rm -rf /' },
  { pattern: /\brm\s+-rf\s+~(?:\s|$)/i, reason: 'blocked dangerous rm -rf ~' },
  { pattern: /\bmkfs(\.[a-z0-9]+)?\b/i, reason: 'blocked dangerous filesystem formatting' },
  { pattern: /\bdd\s+if=.*\bof=\/dev\//i, reason: 'blocked dangerous direct disk write' },
  { pattern: /\bshutdown\b|\breboot\b|\bpoweroff\b/i, reason: 'blocked shutdown/reboot command' },
  { pattern: /:\(\)\s*\{:\|\:&\};:/, reason: 'blocked fork bomb pattern' },
];

const BOOTSTRAP_COMMAND_PATTERNS: Array<{ pattern: RegExp; reason: string }> = [
  { pattern: /\bpip3?\s+install\b/i, reason: 'blocked bootstrap install command' },
  { pattern: /\bpython3?\s+-m\s+pip\s+install\b/i, reason: 'blocked bootstrap install command' },
  { pattern: /\buv\s+pip\s+install\b/i, reason: 'blocked bootstrap install command' },
  { pattern: /\bapt(?:-get)?\s+install\b/i, reason: 'blocked bootstrap install command' },
  { pattern: /\byum\s+install\b/i, reason: 'blocked bootstrap install command' },
  { pattern: /\bdnf\s+install\b/i, reason: 'blocked bootstrap install command' },
  { pattern: /\bapk\s+add\b/i, reason: 'blocked bootstrap install command' },
  { pattern: /\bbrew\s+install\b/i, reason: 'blocked bootstrap install command' },
  { pattern: /\bnpm\s+install\b/i, reason: 'blocked bootstrap install command' },
  { pattern: /\bpnpm\s+add\b/i, reason: 'blocked bootstrap install command' },
  { pattern: /\byarn\s+add\b/i, reason: 'blocked bootstrap install command' },
];

const DELETE_COMMAND_PATTERNS = [
  /(^|[;&|]\s*)rm\s+/im,
  /(^|[;&|]\s*)rmdir\s+/im,
  /(^|[;&|]\s*)unlink\s+/im,
  /\bfind\b[^\n;]*\s-delete\b/im,
  /(^|[;&|]\s*)del\s+/im,
  /(^|[;&|]\s*)erase\s+/im,
];

const ALLOWED_RESOLVED_INTENTS = new Set(['research', 'execution', 'mcp_orchestration']);

export type PolyClawIntentMode = 'auto' | 'research' | 'execution' | 'mcp_orchestration' | 'mcp';
type PolyClawResolvedIntent = 'research' | 'execution' | 'mcp_orchestration';
type DeleteConfirmationMode = 'ask' | 'always_allow' | 'always_deny';

export type PolyClawDeleteConfirmationResult = 'yes' | 'no' | 'always_yes' | 'always_no' | boolean;

export type PolyClawDeleteConfirmationHandler = (context: {
  commandBlock: string;
  step: number;
  index: number;
  preview: string;
}) => Promise<PolyClawDeleteConfirmationResult> | PolyClawDeleteConfirmationResult;

export interface PolyClawAgentConfig {
  llmProvider: LLMProvider;
  mcpServers?: string[];
  maxIterations?: number;
  commandTimeoutMs?: number;
  maxOutputChars?: number;
  maxHistoryChars?: number;
  verbose?: boolean;
  allowDangerousCommands?: boolean;
  useDocker?: boolean;
  dockerImage?: string;
  dockerWorkspace?: string;
  dockerEnableNetwork?: boolean;
  dockerStartTimeoutMs?: number;
  dockerStopTimeoutMs?: number;
  dockerRunArgs?: string[];
  intent?: PolyClawIntentMode;
  allowBootstrap?: boolean;
  strictNoSetup?: boolean;
  confirmDeleteCommands?: boolean;
  deleteConfirmationHandler?: PolyClawDeleteConfirmationHandler;
  researchWebAttempts?: number;
  researchResultLimit?: number;
  noCommandPatience?: number;
  commandRecoveryAttempts?: number;
  maxStagnantSteps?: number;
  liveMode?: boolean;
  liveMaxOutputLines?: number;
}

type ParsedModelResponse = {
  text: string;
  commands: string[];
  finalText: string;
};

type ProcessRunResult = {
  stdout: string;
  stderr: string;
  exitCode: number;
  timedOut: boolean;
};

type SearchResult = {
  title: string;
  url: string;
  snippet: string;
};

type NormalizedConfig = {
  maxIterations: number;
  commandTimeoutMs: number;
  maxOutputChars: number;
  maxHistoryChars: number;
  verbose: boolean;
  allowDangerousCommands: boolean;
  useDocker: boolean;
  dockerImage: string;
  dockerWorkspace: string;
  dockerEnableNetwork: boolean;
  dockerStartTimeoutMs: number;
  dockerStopTimeoutMs: number;
  dockerRunArgs: string[];
  intent: PolyClawIntentMode;
  allowBootstrap: boolean;
  strictNoSetup: boolean;
  confirmDeleteCommands: boolean;
  deleteConfirmationHandler?: PolyClawDeleteConfirmationHandler;
  researchWebAttempts: number;
  researchResultLimit: number;
  noCommandPatience: number;
  commandRecoveryAttempts: number;
  maxStagnantSteps: number;
  liveMode: boolean;
  liveMaxOutputLines: number;
};

/**
 * PolyClaw autonomous shell-first agent.
 */
export class PolyClawAgent {
  private readonly llmProvider: LLMProvider;
  private readonly mcpServers: string[];
  private readonly config: NormalizedConfig;

  private history: string[] = [];
  private dockerContainerName: string | null = null;
  private intent: PolyClawResolvedIntent = 'execution';
  private deleteConfirmationMode: DeleteConfirmationMode = 'ask';

  private static readonly SYSTEM_PROMPT = `You are PolyClaw, an autonomous execution agent for PolyMCP.

Mission:
- Receive a user goal.
- Execute the work end-to-end.
- Prefer concrete actions over asking questions.
- You are autonomous and resourceful: try, inspect output, adapt strategy, and continue.
- Use shell commands, PolyMCP CLI, network requests, and file operations whenever useful.
- If needed, you may create or configure MCP components to solve the user task.
- Keep a human tone in visible messages (THINK/SAY) and explain decisions briefly.
- As soon as the goal is achieved, stop executing commands and emit FINAL immediately.
- Never invent command outputs or external facts.

PolyMCP CLI quick reference:
- polymcp init <name> --type http-server|stdio-server|agent --with-examples
- polymcp server add <url> --name <name>
- polymcp server list
- polymcp test server <url>
- polymcp test tool <url> <tool_name> --params '{"k":"v"}'
- polymcp agent run --type unified|codemode|basic|polyclaw

Runtime notes:
- Your shell commands run inside a Docker container.
- Workspace is mounted at /workspace.
- Changes in /workspace persist on host filesystem.

Response format rules:
1) If commands are needed, output one or more shell blocks:
\`\`\`bash
command here
\`\`\`
2) If the task is complete, output:
\`\`\`FINAL
final user-facing answer with concrete results
\`\`\`
3) Before shell blocks, include short operational lines in plain text:
THINK: what you are about to do (1 sentence)
SAY: what you are doing for the user (1 sentence)
4) Never output fake command results.
5) Keep commands idempotent when possible.
6) Never output placeholder text like "clear final answer for the user".
7) Do not repeat the same command with the same expected outcome multiple times.
8) For execution tasks, THINK/SAY alone is invalid: always include at least one bash block.`;

  constructor(config: PolyClawAgentConfig) {
    this.llmProvider = config.llmProvider;
    this.mcpServers = [...(config.mcpServers || [])];
    this.config = {
      maxIterations: Math.max(1, config.maxIterations ?? 24),
      commandTimeoutMs: Math.max(1000, config.commandTimeoutMs ?? 300_000),
      maxOutputChars: Math.max(1000, config.maxOutputChars ?? 12_000),
      maxHistoryChars: Math.max(2000, config.maxHistoryChars ?? 70_000),
      verbose: config.verbose ?? false,
      allowDangerousCommands: config.allowDangerousCommands ?? false,
      useDocker: config.useDocker ?? true,
      dockerImage: config.dockerImage || 'python:3.11-slim',
      dockerWorkspace: config.dockerWorkspace || '/workspace',
      dockerEnableNetwork: config.dockerEnableNetwork ?? true,
      dockerStartTimeoutMs: Math.max(2000, config.dockerStartTimeoutMs ?? 300_000),
      dockerStopTimeoutMs: Math.max(1000, config.dockerStopTimeoutMs ?? 30_000),
      dockerRunArgs: [...(config.dockerRunArgs || [])],
      intent: config.intent || 'auto',
      allowBootstrap: config.allowBootstrap ?? true,
      strictNoSetup: config.strictNoSetup ?? false,
      confirmDeleteCommands: config.confirmDeleteCommands ?? true,
      deleteConfirmationHandler: config.deleteConfirmationHandler,
      researchWebAttempts: Math.max(1, config.researchWebAttempts ?? 3),
      researchResultLimit: Math.max(1, config.researchResultLimit ?? 6),
      noCommandPatience: Math.max(1, config.noCommandPatience ?? 4),
      commandRecoveryAttempts: Math.max(1, config.commandRecoveryAttempts ?? 2),
      maxStagnantSteps: Math.max(1, config.maxStagnantSteps ?? 2),
      liveMode: config.liveMode ?? (config.verbose ?? false),
      liveMaxOutputLines: Math.max(1, config.liveMaxOutputLines ?? 20),
    };
  }

  /**
   * Run PolyClaw for one user request.
   */
  async run(userMessage: string): Promise<string> {
    this.history = [];
    this.deleteConfirmationMode = 'ask';
    this.intent = await this.resolveIntent(userMessage);

    let noCommandTurns = 0;
    let blockedOnlySteps = 0;
    let lastStepFingerprint: string | null = null;
    let stagnantSteps = 0;
    let deleteCommandsExecuted = 0;
    let deleteCommandsBlocked = 0;

    try {
      if (this.config.liveMode) {
        this.liveStatus(`intent selected: ${this.intent}`);
      }
      this.addHistory(`[SYSTEM] Intent selected: ${this.intent}`);

      if (this.shouldAnswerResearchDirect()) {
        if (this.config.liveMode) {
          this.liveStatus(
            'research mode without tool access, trying built-in web retrieval without shell'
          );
        }
        return this.runResearchWithoutServers(userMessage);
      }

      if (this.config.useDocker) {
        await this.startDockerContainer();
      }

      for (let step = 1; step <= this.config.maxIterations; step += 1) {
        if (this.config.liveMode) {
          this.liveStatus(`step ${step}/${this.config.maxIterations} started (${this.runtimeLabel()})`);
        }

        const prompt = this.buildPrompt(userMessage, step);
        let llmResponse = '';
        try {
          llmResponse = (await this.llmProvider.generate(prompt, { temperature: 0.1 })).trim();
        } catch (error: any) {
          return `PolyClaw failed to contact the LLM: ${error?.message || String(error)}`;
        }

        let { text, commands, finalText } = this.parseResponse(llmResponse);

        if (this.config.verbose) {
          console.log(`[polyclaw] step=${step} commands=${commands.length}`);
          if (text) {
            console.log(`[polyclaw] note: ${text.slice(0, 240)}`);
          }
        }
        if (this.config.liveMode && text) {
          this.liveModelText(text);
        }

        this.addHistory(`[STEP ${step}] model\n${llmResponse}`);

        if (commands.length === 0 && !finalText) {
          const recoverThreshold = Math.max(1, this.config.commandRecoveryAttempts);
          if (noCommandTurns < recoverThreshold) {
            const recovered = await this.recoverCommands(userMessage, step);
            if (recovered.raw) {
              this.addHistory(`[STEP ${step}] recovery_model\n${recovered.raw}`);
            }
            if (recovered.finalText && !finalText) {
              finalText = recovered.finalText;
            }
            if (recovered.commands.length > 0) {
              commands = recovered.commands;
              if (this.config.liveMode) {
                this.liveStatus('recovered missing shell commands');
              }
            }
          }
        }

        if (commands.length === 0) {
          noCommandTurns += 1;

          if (finalText) {
            if (this.isPlaceholderFinal(finalText)) {
              if (this.config.liveMode) {
                this.liveStatus('placeholder FINAL detected, forcing continuation');
              }
              this.addHistory(
                '[SYSTEM] Invalid FINAL placeholder detected. Continue with real commands/results.'
              );
              continue;
            }
            if (this.config.liveMode) {
              this.liveStatus('task completed by FINAL block');
            }
            return this.finalWithSafetyNote(finalText.trim(), deleteCommandsExecuted, deleteCommandsBlocked);
          }

          if (noCommandTurns >= this.config.noCommandPatience) {
            if (this.config.liveMode) {
              this.liveStatus('no actions produced repeatedly, generating summary');
            }
            return this.finalWithSafetyNote(
              await this.summarizeRun(
                userMessage,
                'Model returned no executable commands for multiple consecutive steps.'
              ),
              deleteCommandsExecuted,
              deleteCommandsBlocked
            );
          }

          this.addHistory('[SYSTEM] No shell commands emitted. Continue with concrete commands or FINAL block.');
          if (this.config.liveMode) {
            this.liveStatus('no command emitted, asking model to continue');
          }
          continue;
        }

        noCommandTurns = 0;
        const commandResults: string[] = [];
        let blockedThisStep = 0;

        for (let index = 0; index < commands.length; index += 1) {
          const commandBlock = commands[index].trim();
          if (!commandBlock) {
            continue;
          }

          const commandNumber = index + 1;
          const policyReason = this.findPolicyViolationReason(commandBlock);
          if (policyReason) {
            blockedThisStep += 1;
            const blockedOutput = `[POLICY BLOCKED] ${policyReason}\n${commandBlock}`;
            if (this.config.liveMode) {
              this.liveStatus(`policy blocked command ${commandNumber}: ${policyReason}`);
            }
            commandResults.push(`$ [blocked command ${commandNumber}]\n${blockedOutput}\n[exit code: 125]`);
            if (this.requiresDeleteConfirmation(commandBlock)) {
              deleteCommandsBlocked += 1;
            }
            continue;
          }

          const dangerReason = this.findDangerousCommandReason(commandBlock);
          if (dangerReason && !this.config.allowDangerousCommands) {
            blockedThisStep += 1;
            const blockedOutput = `[BLOCKED] ${dangerReason}\n${commandBlock}`;
            if (this.config.liveMode) {
              this.liveStatus(`blocked command ${commandNumber}: ${dangerReason}`);
            }
            commandResults.push(`$ [blocked command ${commandNumber}]\n${blockedOutput}\n[exit code: 126]`);
            if (this.requiresDeleteConfirmation(commandBlock)) {
              deleteCommandsBlocked += 1;
            }
            continue;
          }

          if (this.config.confirmDeleteCommands && this.requiresDeleteConfirmation(commandBlock)) {
            const isConfirmed = await this.resolveDeleteConfirmation(commandBlock, step, commandNumber);
            if (!isConfirmed) {
              blockedThisStep += 1;
              const blockedOutput = `[BLOCKED] destructive delete command not confirmed by user\n${commandBlock}`;
              commandResults.push(`$ [blocked command ${commandNumber}]\n${blockedOutput}\n[exit code: 125]`);
              deleteCommandsBlocked += 1;
              if (this.config.liveMode) {
                this.liveStatus(`delete command ${commandNumber} denied by user`);
              }
              continue;
            }
          }

          if (this.config.liveMode) {
            this.liveCommand(step, commandNumber, commandBlock);
          }

          const runResult = await this.runShell(commandBlock);
          if (this.requiresDeleteConfirmation(commandBlock)) {
            deleteCommandsExecuted += 1;
          }
          commandResults.push(
            `$ [command ${commandNumber}]\n${commandBlock}\n${runResult.output}\n[exit code: ${runResult.exitCode}]`
          );

          if (this.config.liveMode) {
            this.liveOutput(runResult.exitCode, runResult.elapsedMs / 1000, runResult.output);
          }

          if (this.config.verbose) {
            console.log(
              `[polyclaw] command=${commandNumber} exit=${runResult.exitCode} elapsed=${(runResult.elapsedMs / 1000).toFixed(1)}s`
            );
          }
        }

        if (commands.length > 0 && blockedThisStep === commands.length) {
          blockedOnlySteps += 1;
          this.addHistory(
            '[SYSTEM] All proposed commands were blocked by policy. Propose policy-compliant commands or return FINAL.'
          );
          if (this.config.liveMode) {
            this.liveStatus(`policy-only step detected (${blockedOnlySteps}/2), requesting compliant replan`);
          }
          if (blockedOnlySteps >= 2) {
            return this.finalWithSafetyNote(
              await this.summarizeRun(
                userMessage,
                'Model repeatedly proposed commands blocked by policy. Need policy-compliant plan or direct FINAL.'
              ),
              deleteCommandsExecuted,
              deleteCommandsBlocked
            );
          }
        } else {
          blockedOnlySteps = 0;
        }

        if (commandResults.length > 0) {
          this.addHistory(`[STEP RESULT]\n${commandResults.join('\n\n')}`);
          const stepFingerprint = this.computeStepFingerprint(commands, commandResults);

          if (stepFingerprint === lastStepFingerprint) {
            stagnantSteps += 1;
            this.addHistory(
              '[SYSTEM] Repeated identical commands/output detected. Finalize with a concrete FINAL answer.'
            );
            if (this.config.liveMode) {
              this.liveStatus(`stagnation detected (${stagnantSteps}/${this.config.maxStagnantSteps})`);
            }
            if (stagnantSteps >= this.config.maxStagnantSteps) {
              if (this.config.liveMode) {
                this.liveStatus('stagnation threshold reached, generating summary');
              }
              return this.finalWithSafetyNote(
                await this.summarizeRun(userMessage, 'Repeated commands with unchanged outputs.'),
                deleteCommandsExecuted,
                deleteCommandsBlocked
              );
            }
          } else {
            stagnantSteps = 0;
          }

          lastStepFingerprint = stepFingerprint;
        }

        if (finalText) {
          if (this.isPlaceholderFinal(finalText)) {
            if (this.config.liveMode) {
              this.liveStatus('placeholder FINAL detected, forcing continuation');
            }
            this.addHistory(
              '[SYSTEM] Invalid FINAL placeholder detected. Continue with real commands/results.'
            );
            continue;
          }
          if (this.config.liveMode) {
            this.liveStatus('task completed by FINAL block');
          }
          return this.finalWithSafetyNote(finalText.trim(), deleteCommandsExecuted, deleteCommandsBlocked);
        }
      }

      if (this.config.liveMode) {
        this.liveStatus('iteration budget exhausted, generating final summary');
      }
      return this.finalWithSafetyNote(
        await this.summarizeRun(userMessage, 'Iteration budget exhausted before receiving FINAL block.'),
        deleteCommandsExecuted,
        deleteCommandsBlocked
      );
    } catch (error: any) {
      return `PolyClaw runtime error: ${error?.message || String(error)}`;
    } finally {
      await this.stopDockerContainer();
    }
  }

  private buildPrompt(userMessage: string, step: number): string {
    const servers = this.mcpServers.length > 0 ? this.mcpServers.join(', ') : '(none configured)';
    let historyText = this.history.join('\n\n');
    if (historyText.length > this.config.maxHistoryChars) {
      historyText = historyText.slice(-this.config.maxHistoryChars);
    }

    const runtime = this.config.useDocker ? 'Docker container' : 'host shell';
    const intentGuidance = this.intentGuidance();

    return (
      `${PolyClawAgent.SYSTEM_PROMPT}\n\n` +
      `Execution intent: ${this.intent}\n` +
      `Intent guidance:\n${intentGuidance}\n\n` +
      `Runtime: ${runtime}\n` +
      `Working directory: ${process.cwd()}\n` +
      `Configured MCP servers: ${servers}\n` +
      `Current step: ${step}/${this.config.maxIterations}\n\n` +
      `User goal:\n${userMessage}\n\n` +
      `Execution history:\n${historyText || '(no history yet)'}\n\n` +
      'Produce the next action now.'
    );
  }

  private parseResponse(response: string): ParsedModelResponse {
    const shellBlockRe = /```(?:SHELL|shell|bash|sh)\s*\r?\n([\s\S]*?)```/g;
    const finalMatch = response.match(FINAL_BLOCK_RE);
    let finalText = finalMatch ? finalMatch[1].trim() : '';

    if (!finalText) {
      const partialFinalMatch = response.match(/```(?:FINAL|final)\s*\r?\n([\s\S]*)$/i);
      if (partialFinalMatch) {
        finalText = partialFinalMatch[1].trim();
      }
    }

    const commands: string[] = [];
    for (const match of response.matchAll(shellBlockRe)) {
      const block = (match[1] || '').trim();
      if (block) {
        commands.push(block);
      }
    }

    let text = response
      .replace(shellBlockRe, '')
      .replace(/```(?:FINAL|final)\s*\r?\n[\s\S]*?```/gi, '');

    if (!finalMatch && finalText) {
      text = text.replace(/```(?:FINAL|final)\s*\r?\n[\s\S]*$/i, '');
    }

    return { text: text.trim(), commands, finalText };
  }

  private async recoverCommands(
    userMessage: string,
    step: number
  ): Promise<{ commands: string[]; finalText: string; raw: string }> {
    const prompt =
      'You failed to emit executable shell blocks.\n' +
      'Produce ONLY one of:\n' +
      '1) one or more fenced bash blocks with concrete commands, OR\n' +
      '2) one fenced FINAL block if no command is needed.\n' +
      'No THINK, no SAY, no explanations.\n\n' +
      `User goal:\n${userMessage}\n` +
      `Current step: ${step}\n` +
      `Working directory: ${process.cwd()}\n`;

    try {
      const raw = (await this.llmProvider.generate(prompt, { temperature: 0 })).trim();
      const parsed = this.parseResponse(raw);
      let commands = parsed.commands;
      if (commands.length === 0) {
        commands = this.extractInlineCommands(raw);
      }
      return { commands, finalText: parsed.finalText, raw };
    } catch {
      return { commands: [], finalText: '', raw: '' };
    }
  }

  private extractInlineCommands(text: string): string[] {
    const lines: string[] = [];
    for (const rawLine of text.split('\n')) {
      let line = rawLine.trim();
      if (!line) {
        continue;
      }
      const lower = line.toLowerCase();
      if (lower.startsWith('think:') || lower.startsWith('say:') || lower.startsWith('final')) {
        continue;
      }
      if (line.startsWith('$ ')) {
        line = line.slice(2).trim();
      }
      if (this.looksLikeShellCommand(line)) {
        lines.push(line);
      }
    }
    return lines.length > 0 ? [lines.join('\n')] : [];
  }

  private looksLikeShellCommand(line: string): boolean {
    const token = line.trim().split(' ', 1)[0]?.trim();
    if (!token) {
      return false;
    }
    if (COMMON_SHELL_COMMANDS.has(token)) {
      return true;
    }
    if (token.startsWith('./') || token.startsWith('../') || token.startsWith('/')) {
      return true;
    }
    if ((line.includes('|') || line.includes('>') || line.includes('<') || line.includes('&&') || line.includes('||') || line.includes(';'))
      && /^[a-zA-Z0-9._/-]+$/.test(token)) {
      return true;
    }
    return false;
  }

  private runtimeLabel(): 'docker' | 'host' {
    return this.config.useDocker ? 'docker' : 'host';
  }

  private liveStatus(message: string): void {
    console.log(`[POLYCLAW][STATUS] ${message}`);
  }

  private liveModelText(text: string): void {
    const thoughts: string[] = [];
    const says: string[] = [];
    const neutral: string[] = [];

    for (const rawLine of text.split('\n')) {
      const line = rawLine.trim();
      if (!line) {
        continue;
      }
      const lower = line.toLowerCase();
      if (lower.startsWith('think:')) {
        thoughts.push(line.split(':', 2)[1]?.trim() || '');
      } else if (lower.startsWith('say:')) {
        says.push(line.split(':', 2)[1]?.trim() || '');
      } else {
        neutral.push(line);
      }
    }

    for (const item of thoughts) {
      console.log(`[POLYCLAW][THINK] ${item}`);
    }
    for (const item of says) {
      console.log(`[POLYCLAW][SAY] ${item}`);
    }
    for (const item of neutral) {
      console.log(`[POLYCLAW][NOTE] ${item}`);
    }
  }

  private liveCommand(step: number, index: number, command: string): void {
    console.log(`[POLYCLAW][ACTION][step=${step} cmd=${index}]`);
    for (const line of command.split('\n')) {
      console.log(`$ ${line}`);
    }
  }

  private liveOutput(exitCode: number, elapsedSeconds: number, output: string): void {
    console.log(`[POLYCLAW][OUTPUT] exit=${exitCode} elapsed=${elapsedSeconds.toFixed(1)}s`);
    const lines = output.split('\n');
    const limit = this.config.liveMaxOutputLines;
    const preview = lines.slice(0, limit);
    for (const line of preview) {
      console.log(`  ${line}`);
    }
    if (lines.length > limit) {
      console.log(`  ... (${lines.length - limit} more lines)`);
    }
  }

  private isPlaceholderFinal(finalText: string): boolean {
    const normalized = finalText.trim().toLowerCase().replace(/\s+/g, ' ');
    return FINAL_PLACEHOLDER_PATTERNS.has(normalized);
  }

  private findDangerousCommandReason(commandBlock: string): string | null {
    for (const rule of DANGEROUS_COMMAND_PATTERNS) {
      if (rule.pattern.test(commandBlock)) {
        return rule.reason;
      }
    }
    return null;
  }

  private requiresDeleteConfirmation(commandBlock: string): boolean {
    return DELETE_COMMAND_PATTERNS.some((pattern) => pattern.test(commandBlock));
  }

  private async resolveDeleteConfirmation(commandBlock: string, step: number, index: number): Promise<boolean> {
    if (this.deleteConfirmationMode === 'always_deny') {
      return false;
    }
    if (this.deleteConfirmationMode === 'always_allow') {
      return true;
    }

    const preview = this.previewCommand(commandBlock);
    const handler = this.config.deleteConfirmationHandler;
    if (handler) {
      try {
        const result = await handler({ commandBlock, step, index, preview });
        return this.applyConfirmationResult(result);
      } catch {
        this.deleteConfirmationMode = 'always_deny';
        return false;
      }
    }

    return this.requestDeleteConfirmation(commandBlock, step, index);
  }

  private applyConfirmationResult(result: PolyClawDeleteConfirmationResult): boolean {
    if (typeof result === 'boolean') {
      return result;
    }
    const normalized = String(result).trim().toLowerCase();
    if (normalized === 'always_yes' || normalized === 'a') {
      this.deleteConfirmationMode = 'always_allow';
      return true;
    }
    if (normalized === 'always_no' || normalized === 'x') {
      this.deleteConfirmationMode = 'always_deny';
      return false;
    }
    if (normalized === 'yes' || normalized === 'y' || normalized === 'si' || normalized === 's') {
      return true;
    }
    this.deleteConfirmationMode = 'always_deny';
    return false;
  }

  private async requestDeleteConfirmation(commandBlock: string, step: number, index: number): Promise<boolean> {
    const preview = this.previewCommand(commandBlock);

    if (this.config.liveMode) {
      this.liveStatus(`delete confirmation required for step=${step} cmd=${index}`);
    }

    if (!process.stdin.isTTY) {
      this.addHistory('[SYSTEM] Delete confirmation required but no interactive TTY is available.');
      this.deleteConfirmationMode = 'always_deny';
      return false;
    }

    const question =
      '[POLYCLAW][CONFIRM] Eseguire comando distruttivo? [y/N/a/x]\n' +
      '  y=yes, n=no (blocca i prossimi delete), a=sempre si, x=sempre no\n' +
      `  step=${step} cmd=${index}: ${preview}\n> `;

    const answer = await this.prompt(question);
    const normalized = answer.trim().toLowerCase();

    if (normalized === 'a' || normalized === 'all' || normalized === 'always' || normalized === 'sempre') {
      this.deleteConfirmationMode = 'always_allow';
      return true;
    }
    if (normalized === 'x' || normalized === 'never' || normalized === 'mai' || normalized === 'noall') {
      this.deleteConfirmationMode = 'always_deny';
      return false;
    }
    if (normalized === 'y' || normalized === 'yes' || normalized === 's' || normalized === 'si') {
      return true;
    }

    this.deleteConfirmationMode = 'always_deny';
    return false;
  }

  private previewCommand(commandBlock: string): string {
    let preview = commandBlock.trim().replace(/\n/g, ' ; ');
    if (preview.length > 220) {
      preview = `${preview.slice(0, 220)}...`;
    }
    return preview;
  }

  private prompt(question: string): Promise<string> {
    return new Promise((resolve) => {
      const rl = readline.createInterface({
        input: process.stdin,
        output: process.stdout,
      });
      rl.question(question, (answer) => {
        rl.close();
        resolve(answer);
      });
    });
  }

  private findPolicyViolationReason(commandBlock: string): string | null {
    if (this.config.strictNoSetup && this.intent !== 'mcp_orchestration' && /\bpolymcp\b/i.test(commandBlock)) {
      return 'polymcp CLI blocked for non-MCP intent';
    }

    if (!this.config.allowBootstrap) {
      for (const rule of BOOTSTRAP_COMMAND_PATTERNS) {
        if (rule.pattern.test(commandBlock)) {
          return `${rule.reason} (set allowBootstrap=true to enable)`;
        }
      }
    }

    if (this.config.strictNoSetup && this.intent === 'research' && /\b(polymcp\s+init|git\s+clone)\b/i.test(commandBlock)) {
      return 'project scaffolding blocked for research intent';
    }

    return null;
  }

  private async resolveIntent(userMessage: string): Promise<PolyClawResolvedIntent> {
    const configured = (this.config.intent || 'auto').trim().toLowerCase() as PolyClawIntentMode;

    if (configured === 'mcp') {
      return 'mcp_orchestration';
    }
    if (ALLOWED_RESOLVED_INTENTS.has(configured)) {
      return configured as PolyClawResolvedIntent;
    }
    if (configured !== 'auto') {
      return 'execution';
    }

    const llmIntent = await this.inferIntentWithLLM(userMessage);
    if (llmIntent) {
      return llmIntent;
    }
    return this.inferIntentWithRules(userMessage);
  }

  private inferIntentWithRules(userMessage: string): PolyClawResolvedIntent {
    const text = userMessage.trim().toLowerCase();
    if (MCP_INTENT_HINTS.some((hint) => text.includes(hint))) {
      return 'mcp_orchestration';
    }
    if (RESEARCH_INTENT_HINTS.some((hint) => text.includes(hint))) {
      return 'research';
    }
    if (/\bhttps?:\/\//i.test(text)) {
      return 'execution';
    }
    return 'execution';
  }

  private async inferIntentWithLLM(userMessage: string): Promise<PolyClawResolvedIntent | null> {
    const prompt =
      'Classify the user request intent for an autonomous shell agent.\n' +
      'Return ONLY one label from: research | execution | mcp_orchestration.\n\n' +
      'Label meaning:\n' +
      '- research: information/recommendation/search questions.\n' +
      '- execution: file/system/task execution not specifically about MCP setup.\n' +
      '- mcp_orchestration: requests explicitly about MCP servers, tools, registry, or PolyMCP setup.\n\n' +
      `User request:\n${userMessage}\n`;

    try {
      const raw = (await this.llmProvider.generate(prompt, { temperature: 0 })).trim().toLowerCase();
      const normalized = raw.replace(/`/g, '').trim();
      if (normalized === 'mcp') {
        return 'mcp_orchestration';
      }
      if (normalized.includes('mcp') && !normalized.includes('orchestration')) {
        return 'mcp_orchestration';
      }
      if (normalized.includes('mcp_orchestration')) {
        return 'mcp_orchestration';
      }
      if (normalized.includes('research')) {
        return 'research';
      }
      if (normalized.includes('execution')) {
        return 'execution';
      }
      return null;
    } catch {
      return null;
    }
  }

  private intentGuidance(): string {
    if (this.intent === 'research') {
      return [
        '- Prefer information retrieval and synthesis.',
        '- Use practical retrieval strategies (HTTP, APIs, scraping, tools) and adapt if one fails.',
        '- If strict mode is enabled and no tool/server access exists, use built-in web retrieval.',
        '- Use PolyMCP setup only if it clearly helps solve the request.',
        '- Use installs only when they are necessary for progress.',
        '- If reliable evidence is insufficient, report limits clearly in FINAL.',
      ].join('\n');
    }
    if (this.intent === 'mcp_orchestration') {
      return [
        '- Focus on MCP orchestration/build/runbook execution.',
        '- Use PolyMCP CLI as needed.',
        '- Keep actions minimal and stop once requested outcome is met.',
      ].join('\n');
    }
    return [
      '- Focus on direct task execution with minimal commands.',
      '- Avoid unrelated setup or scaffolding.',
      '- Stop and emit FINAL immediately after success criteria are met.',
    ].join('\n');
  }

  private computeStepFingerprint(commands: string[], commandResults: string[]): string {
    const normalizedCommands = commands.map((c) => c.trim().replace(/\s+/g, ' ')).filter(Boolean);
    const payload = `${normalizedCommands.join('\n---\n')}\n====\n${commandResults.join('\n---\n')}`;
    return createHash('sha256').update(payload, 'utf8').digest('hex');
  }

  private async runShell(command: string): Promise<{ output: string; exitCode: number; elapsedMs: number }> {
    if (this.config.useDocker) {
      return this.runShellInDocker(command);
    }
    return this.runShellOnHost(command);
  }

  private async runShellOnHost(command: string): Promise<{ output: string; exitCode: number; elapsedMs: number }> {
    const started = Date.now();

    if (process.platform === 'win32') {
      const result = await this.runProcess('cmd.exe', ['/d', '/s', '/c', command], this.config.commandTimeoutMs);
      const output = this.formatProcessOutput(result);
      return { output, exitCode: result.timedOut ? 124 : result.exitCode, elapsedMs: Date.now() - started };
    }

    const wrapped = `set -o pipefail\n${command}`;
    const result = await this.runProcess('/bin/bash', ['-lc', wrapped], this.config.commandTimeoutMs);
    const output = this.formatProcessOutput(result);
    return { output, exitCode: result.timedOut ? 124 : result.exitCode, elapsedMs: Date.now() - started };
  }

  private async startDockerContainer(): Promise<void> {
    if (this.dockerContainerName) {
      return;
    }

    const containerName = `polyclaw-${randomUUID().replace(/-/g, '').slice(0, 12)}`;
    const workspaceHost = process.cwd();
    const workspaceMount = `${workspaceHost}:${this.config.dockerWorkspace}`;

    const args = [
      'run',
      '-d',
      '--rm',
      '--name',
      containerName,
      '-v',
      workspaceMount,
      '-w',
      this.config.dockerWorkspace,
      '-e',
      'PYTHONUNBUFFERED=1',
    ];

    if (!this.config.dockerEnableNetwork) {
      args.push('--network', 'none');
    }
    if (this.config.dockerRunArgs.length > 0) {
      args.push(...this.config.dockerRunArgs);
    }
    args.push(this.config.dockerImage, 'sleep', 'infinity');

    const result = await this.runProcess('docker', args, this.config.dockerStartTimeoutMs);
    if (result.exitCode !== 0) {
      const err = (result.stderr || result.stdout || 'unknown Docker error').trim();
      throw new Error(`Failed to start Docker container: ${err}`);
    }

    this.dockerContainerName = containerName;
    if (this.config.liveMode) {
      this.liveStatus(`docker container started: ${containerName}`);
    } else if (this.config.verbose) {
      console.log(`[polyclaw] docker container started: ${containerName}`);
    }
  }

  private async stopDockerContainer(): Promise<void> {
    if (!this.dockerContainerName) {
      return;
    }

    const containerName = this.dockerContainerName;
    this.dockerContainerName = null;

    const result = await this.runProcess(
      'docker',
      ['stop', containerName],
      this.config.dockerStopTimeoutMs
    );

    if (this.config.liveMode) {
      this.liveStatus(`docker container stopped: ${containerName}`);
    } else if (this.config.verbose && result.exitCode === 0) {
      console.log(`[polyclaw] docker container stopped: ${containerName}`);
    }
  }

  private async runShellInDocker(command: string): Promise<{ output: string; exitCode: number; elapsedMs: number }> {
    if (!this.dockerContainerName) {
      throw new Error('Docker container is not running');
    }

    const started = Date.now();
    const wrapped = `set -o pipefail\n${command}`;
    const result = await this.runProcess(
      'docker',
      ['exec', '-i', this.dockerContainerName, '/bin/bash', '-lc', wrapped],
      this.config.commandTimeoutMs
    );
    const output = this.formatProcessOutput(result);
    return { output, exitCode: result.timedOut ? 124 : result.exitCode, elapsedMs: Date.now() - started };
  }

  private async runProcess(command: string, args: string[], timeoutMs: number): Promise<ProcessRunResult> {
    return new Promise((resolve) => {
      const child = spawn(command, args, { stdio: ['ignore', 'pipe', 'pipe'] });
      let stdout = '';
      let stderr = '';
      let timedOut = false;
      let settled = false;

      const timeoutHandle = setTimeout(() => {
        timedOut = true;
        try {
          child.kill('SIGKILL');
        } catch {
          // no-op
        }
      }, timeoutMs);

      child.stdout.on('data', (chunk: Buffer | string) => {
        stdout += chunk.toString();
      });
      child.stderr.on('data', (chunk: Buffer | string) => {
        stderr += chunk.toString();
      });

      child.on('error', (error) => {
        if (settled) {
          return;
        }
        settled = true;
        clearTimeout(timeoutHandle);
        resolve({
          stdout,
          stderr: `${stderr}${stderr ? '\n' : ''}${error.message}`,
          exitCode: 1,
          timedOut,
        });
      });

      child.on('close', (code) => {
        if (settled) {
          return;
        }
        settled = true;
        clearTimeout(timeoutHandle);
        resolve({
          stdout,
          stderr,
          exitCode: typeof code === 'number' ? code : (timedOut ? 124 : 1),
          timedOut,
        });
      });
    });
  }

  private formatProcessOutput(result: ProcessRunResult): string {
    if (result.timedOut) {
      return `[TIMEOUT ${Math.floor(this.config.commandTimeoutMs / 1000)}s]`;
    }
    let output = '';
    if (result.stdout) {
      output += result.stdout;
    }
    if (result.stderr) {
      if (output && !output.endsWith('\n')) {
        output += '\n';
      }
      output += result.stderr;
    }
    output = output.trim() || '(no output)';
    return this.truncateOutput(output);
  }

  private truncateOutput(output: string): string {
    if (output.length <= this.config.maxOutputChars) {
      return output;
    }
    const half = Math.floor(this.config.maxOutputChars / 2);
    const head = output.slice(0, half);
    const tail = output.slice(-half);
    return `${head}\n[...TRUNCATED...]\n${tail}`;
  }

  private shouldAnswerResearchDirect(): boolean {
    return this.intent === 'research' && this.config.strictNoSetup && this.mcpServers.length === 0;
  }

  private async runResearchWithoutServers(userMessage: string): Promise<string> {
    const results = await this.searchWebResults(userMessage);
    if (results.length > 0) {
      if (this.config.liveMode) {
        this.liveStatus(`built-in web retrieval succeeded with ${results.length} sources`);
      }
      const evidenceLines = results.map((r, idx) => {
        const snippet = r.snippet ? ` | ${r.snippet}` : '';
        return `${idx + 1}. ${r.title} | ${r.url}${snippet}`;
      });
      this.addHistory(`[RESEARCH EVIDENCE]\n${evidenceLines.join('\n')}`);
      return this.generateResearchGroundedFinal(userMessage, results);
    }

    if (this.config.liveMode) {
      this.liveStatus('built-in web retrieval failed, returning limitation-aware answer');
    }
    return this.generateResearchFinal(userMessage);
  }

  private async searchWebResults(userMessage: string): Promise<SearchResult[]> {
    const attempts = Math.max(1, this.config.researchWebAttempts);
    const limit = Math.max(1, this.config.researchResultLimit);

    const base = userMessage.trim();
    const queries = [base, `${base} recensioni`, `${base} tripadvisor`, `${base} michelin`];
    const collected: SearchResult[] = [];
    const seen = new Set<string>();

    for (const query of queries.slice(0, attempts)) {
      const rows = await this.fetchDuckDuckGoResults(query, limit);
      for (const row of rows) {
        const key = row.url.trim().toLowerCase();
        if (!key || seen.has(key)) {
          continue;
        }
        seen.add(key);
        collected.push(row);
        if (collected.length >= limit) {
          return collected;
        }
      }
    }

    return collected;
  }

  private async fetchDuckDuckGoResults(query: string, limit: number): Promise<SearchResult[]> {
    const endpoints = [
      `https://duckduckgo.com/html/?q=${encodeURIComponent(query)}`,
      `https://html.duckduckgo.com/html/?q=${encodeURIComponent(query)}`,
    ];

    const headers: Record<string, string> = {
      'User-Agent':
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0 Safari/537.36',
    };

    const linkRe = /<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>([\s\S]*?)<\/a>/gi;
    const snippetRe = /<(?:a|div)[^>]*class="result__snippet"[^>]*>([\s\S]*?)<\/(?:a|div)>/gi;

    for (const endpoint of endpoints) {
      try {
        const response = await fetch(endpoint, { headers });
        if (!response.ok) {
          continue;
        }
        const html = await response.text();

        const anchors: Array<{ href: string; title: string }> = [];
        for (const match of html.matchAll(linkRe)) {
          anchors.push({ href: match[1], title: match[2] });
        }

        const snippets: string[] = [];
        for (const match of html.matchAll(snippetRe)) {
          snippets.push(match[1]);
        }

        const rows: SearchResult[] = [];
        for (let idx = 0; idx < anchors.length; idx += 1) {
          const anchor = anchors[idx];
          const url = this.normalizeSearchUrl(anchor.href);
          if (!url) {
            continue;
          }
          const title = this.stripHtml(anchor.title);
          const snippet = idx < snippets.length ? this.stripHtml(snippets[idx]) : '';
          if (title) {
            rows.push({ title, url, snippet });
          }
          if (rows.length >= limit) {
            return rows;
          }
        }

        if (rows.length > 0) {
          return rows;
        }
      } catch {
        // keep trying next endpoint
      }
    }

    return [];
  }

  private normalizeSearchUrl(rawHref: string): string {
    let href = this.decodeHtml(rawHref || '').trim();
    if (!href) {
      return '';
    }

    if (href.startsWith('//')) {
      href = `https:${href}`;
    } else if (href.startsWith('/l/?')) {
      href = `https://duckduckgo.com${href}`;
    }

    if (href.includes('duckduckgo.com/l/?')) {
      try {
        const parsed = new URL(href);
        const uddg = parsed.searchParams.get('uddg');
        if (uddg) {
          href = decodeURIComponent(uddg);
        }
      } catch {
        return '';
      }
    }

    if (!href.startsWith('http://') && !href.startsWith('https://')) {
      return '';
    }

    return href;
  }

  private decodeHtml(value: string): string {
    return value
      .replace(/&amp;/g, '&')
      .replace(/&lt;/g, '<')
      .replace(/&gt;/g, '>')
      .replace(/&quot;/g, '"')
      .replace(/&#39;/g, "'");
  }

  private stripHtml(value: string): string {
    return this.decodeHtml(value || '').replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
  }

  private async generateResearchGroundedFinal(userMessage: string, results: SearchResult[]): Promise<string> {
    const today = new Date().toISOString().slice(0, 10);
    const evidenceLines = results.map((r, idx) => {
      const snippet = r.snippet ? ` | snippet: ${r.snippet}` : '';
      return `${idx + 1}. ${r.title} | ${r.url}${snippet}`;
    });

    const prompt =
      'Rispondi in italiano con un risultato concreto e verificabile.\n' +
      'Usa SOLO le evidenze fornite qui sotto; non inventare nomi, rating o fonti.\n' +
      "Se 'migliore' non e oggettivo, proponi una prima scelta motivata e due alternative.\n" +
      "Chiudi con una sezione 'Fonti:' contenente 2-5 URL presi dalle evidenze.\n" +
      'Nessun blocco di codice.\n\n' +
      `Oggi: ${today}\n` +
      `Richiesta utente:\n${userMessage}\n\n` +
      `Evidenze web raccolte:\n${evidenceLines.join('\n')}\n`;

    try {
      return (await this.llmProvider.generate(prompt, { temperature: 0.2 })).trim();
    } catch {
      const top = results[0];
      return (
        'Non posso determinare con certezza assoluta un singolo migliore, ma dalla ricerca web ' +
        `la prima fonte utile e: ${top.title} (${top.url}).`
      );
    }
  }

  private generateResearchFinal(userMessage: string): string {
    const today = new Date().toISOString().slice(0, 10);
    return (
      'Ho provato a recuperare risultati web verificabili ma non sono riuscito a ottenere fonti affidabili ' +
      `(data: ${today}). Per evitare risposte inventate non posso indicare un risultato vero in questo momento.\n` +
      'Se vuoi un risultato verificato, collega un MCP server/tool di ricerca web e rilancio subito la richiesta:\n' +
      `- richiesta: ${userMessage}`
    );
  }

  private async summarizeRun(userMessage: string, reason?: string): Promise<string> {
    const historyText = this.history.slice(-20).join('\n\n');
    const reasonText = reason || 'General completion summary.';
    const prompt =
      'Create a concise final user-facing report in Italian.\n' +
      'Describe what was completed, what failed, and next concrete action.\n' +
      'Do not invent results.\n\n' +
      `Why summary is needed:\n${reasonText}\n\n` +
      `User goal:\n${userMessage}\n\n` +
      `Execution log:\n${historyText || '(no execution log)'}`;

    try {
      return (await this.llmProvider.generate(prompt, { temperature: 0.1 })).trim();
    } catch {
      return 'PolyClaw could not produce a final summary from the execution log. Run again with a more specific goal.';
    }
  }

  private finalWithSafetyNote(
    finalText: string,
    deleteCommandsExecuted: number,
    deleteCommandsBlocked: number
  ): string {
    const text = (finalText || '').trim();
    if (!text) {
      return text;
    }
    if (deleteCommandsExecuted > 0) {
      return text;
    }
    if (deleteCommandsBlocked <= 0) {
      return text;
    }

    const claimsRemoval = REMOVAL_CLAIM_PATTERNS.some((pattern) => pattern.test(text));
    const safetyNote = 'Nota sicurezza: nessuna rimozione e stata eseguita (comandi delete negati o bloccati).';

    if (!claimsRemoval) {
      if (text.toLowerCase().includes(safetyNote.toLowerCase())) {
        return text;
      }
      return `${safetyNote}\n\n${text}`;
    }

    const filteredLines = text
      .split('\n')
      .filter((line) => !REMOVAL_CLAIM_PATTERNS.some((pattern) => pattern.test(line)));
    const filteredText = filteredLines.join('\n').trim();
    if (filteredText) {
      return `${safetyNote}\n\n${filteredText}`;
    }
    return safetyNote;
  }

  private addHistory(item: string): void {
    this.history.push(item.trim());
  }
}
