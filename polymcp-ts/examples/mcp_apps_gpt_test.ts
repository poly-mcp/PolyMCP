import OpenAI from 'openai';

const BASE_URL = process.env.MCP_APPS_BASE_URL || 'http://localhost:3100';
const MODEL = process.env.OPENAI_MODEL || 'gpt-4o-mini';

type MCPTool = {
  name: string;
  description: string;
  input_schema: Record<string, any>;
};

async function fetchMCPTools(): Promise<MCPTool[]> {
  const response = await fetch(`${BASE_URL}/list_tools`);
  if (!response.ok) {
    throw new Error(`Failed to load MCP tools (${response.status})`);
  }
  const data = (await response.json()) as { tools?: MCPTool[] };
  return data.tools || [];
}

async function callMCPTool(name: string, args: Record<string, any>): Promise<any> {
  const response = await fetch(`${BASE_URL}/tools/${name}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(args || {}),
  });
  if (!response.ok) {
    throw new Error(`MCP tool ${name} failed (${response.status})`);
  }
  return await response.json();
}

async function runConversation(userPrompt: string) {
  if (!process.env.OPENAI_API_KEY) {
    throw new Error('OPENAI_API_KEY is required');
  }

  const mcpTools = await fetchMCPTools();
  if (mcpTools.length === 0) {
    throw new Error('No tools available from MCP Apps server');
  }

  const tools = mcpTools.map((tool) => ({
    type: 'function' as const,
    function: {
      name: tool.name,
      description: tool.description,
      parameters: tool.input_schema || { type: 'object', properties: {} },
    },
  }));

  const openai = new OpenAI({ apiKey: process.env.OPENAI_API_KEY });

  const messages: OpenAI.Chat.Completions.ChatCompletionMessageParam[] = [
    {
      role: 'system',
      content:
        'You are a precise assistant. Use available tools when they provide the required data.',
    },
    { role: 'user', content: userPrompt },
  ];

  for (let i = 0; i < 6; i++) {
    const completion = await openai.chat.completions.create({
      model: MODEL,
      messages,
      tools,
      tool_choice: 'auto',
      temperature: 0,
    });

    const message = completion.choices[0]?.message;
    if (!message) {
      throw new Error('Model returned no message');
    }

    messages.push(message);

    const toolCalls = message.tool_calls || [];
    if (toolCalls.length === 0) {
      console.log('\nFinal answer:\n');
      console.log(message.content || '(empty)');
      return;
    }

    for (const call of toolCalls) {
      const name = call.function.name;
      let args: Record<string, any> = {};
      try {
        args = call.function.arguments ? JSON.parse(call.function.arguments) : {};
      } catch {
        args = {};
      }

      const result = await callMCPTool(name, args);

      messages.push({
        role: 'tool',
        tool_call_id: call.id,
        content: JSON.stringify(result),
      });
    }
  }

  throw new Error('Conversation reached max tool iterations');
}

async function main() {
  const prompt =
    process.argv.slice(2).join(' ') ||
    'Get current sales stats for this week and summarize the KPI trend in 3 bullet points.';

  console.log(`Using MCP server: ${BASE_URL}`);
  console.log(`Using model: ${MODEL}`);
  console.log(`Prompt: ${prompt}`);

  await runConversation(prompt);
}

main().catch((error) => {
  console.error('GPT bridge failed:', error.message);
  process.exit(1);
});
