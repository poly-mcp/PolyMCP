import { UnifiedPolyAgent } from '../src/agent/unified_agent';
import { OllamaProvider } from '../src/agent/llm_providers';

async function main() {
  console.log('Playwright Client - Stdio Mode\n');

  const agent = new UnifiedPolyAgent({
    llmProvider: new OllamaProvider({
      model: 'gpt-oss:120b-cloud',
      baseUrl: 'http://localhost:11434',
    }),

    // Existing config
    stdioServers: [
      {
        command: 'npx',
        args: ['@playwright/mcp@latest'],
      },
    ],
    memoryEnabled: true,
    verbose: true,

    // -----------------------------
    // New “production/enterprise” options (v2.0 style)
    // -----------------------------

    // Budget limits
    maxWallTime: 300,            // seconds
    maxTokens: 100000,           // token budget for the run
    maxToolCalls: 20,            // hard cap on tool executions
    maxPayloadBytes: 10 * 1024 * 1024, // 10MB payload safety

    // Security
    redactLogs: true,
    toolAllowlist: new Set([
      // keep empty if you don’t want allowlisting,
      // or list known-safe tools you expect to use
      // 'browser.goto',
      // 'browser.screenshot',
      // 'browser.read'
    ]),
    toolDenylist: new Set([
      // example:
      // 'filesystem.write'
    ]),

    // Observability
    enableStructuredLogs: true,
    logFile: 'agent.log', // write JSON structured logs to file

    // Resilience
    maxRetries: 3,
    retryBackoff: 1.0,
    enableHealthChecks: true,
    circuitBreakerThreshold: 5,

    // Rate limiting
    enableRateLimiting: true,
    defaultRateLimit: 10, // calls per 60s (server-level default)

    // Architecture
    usePlanner: true,
    useValidator: true,
    goalAchievementThreshold: 0.7,

    // Performance tuning
    toolsCacheTtl: 60,       // seconds
    maxMemorySize: 50,       // bounded history
    maxRelevantTools: 15,    // keep tool shortlist small
  });

  console.log('Starting Playwright via stdio...');
  await agent.start();
  console.log('Playwright ready!\n');

  const response = await agent.runAsync(
    `
Go to github.com/llm-use/polymcp,
take a screenshot,
analyze the README,
and summarize the key features
`,
    15
  );

  console.log('\nResult:', response);

  // Optional: read metrics/logs (if you expose these methods in TS like Python)
  // const metrics = agent.getMetrics?.();
  // const logs = agent.exportLogs?.('json');
  // console.log('\nMetrics:', metrics);
}

main().catch(console.error);
