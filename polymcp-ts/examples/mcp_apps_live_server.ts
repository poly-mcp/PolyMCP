import express from 'express';
import { MCPAppsBuilder } from '../src/mcp_apps/mcp_apps_builder';
import { MCPAppsServer } from '../src/mcp_apps/mcp_apps_server';

const PORT = Number(process.env.PORT || 3100);

function buildSalesApp() {
  const builder = new MCPAppsBuilder();
  let revenue = 125430;
  let orders = 890;
  let users = 12345;

  const app = builder
    .createApp({
      id: 'sales-dashboard',
      name: 'Sales Dashboard',
      description: 'Interactive sales dashboard with MCP tools',
    })
    .addTool({
      name: 'get_sales_stats',
      description: 'Get latest sales KPIs',
      inputSchema: {
        type: 'object',
        properties: {
          period: {
            type: 'string',
            description: 'time window, e.g. today, week, month',
          },
        },
      },
      handler: async (params: any) => {
        const period = params?.period || 'today';
        return {
          period,
          revenue,
          orders,
          users,
          conversionRate: 3.8,
          growth: 12.4,
        };
      },
    })
    .addTool({
      name: 'simulate_next_tick',
      description: 'Simulate next analytics update tick',
      inputSchema: {
        type: 'object',
        properties: {},
      },
      handler: async () => {
        revenue += Math.floor(Math.random() * 900 + 100);
        orders += Math.floor(Math.random() * 8 + 1);
        users += Math.floor(Math.random() * 20 + 1);
        return { ok: true, revenue, orders, users };
      },
    })
    .addHTMLResource({
      name: 'Sales Dashboard UI',
      html: `<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Sales Dashboard</title>
    <style>
      body { margin: 0; font-family: "Segoe UI", Arial, sans-serif; background: linear-gradient(135deg, #0b1f3a 0%, #1f4e79 100%); color: #fff; }
      .wrap { max-width: 980px; margin: 0 auto; padding: 24px; }
      .title { font-size: 32px; margin: 0 0 16px; }
      .toolbar { display: flex; gap: 10px; margin-bottom: 18px; flex-wrap: wrap; }
      .btn { border: 0; background: #00c389; color: #072016; padding: 10px 14px; border-radius: 8px; font-weight: 700; cursor: pointer; }
      .btn.secondary { background: #d4e7ff; color: #123; }
      .grid { display: grid; grid-template-columns: repeat(4, minmax(140px, 1fr)); gap: 12px; }
      .card { background: rgba(255,255,255,0.12); border: 1px solid rgba(255,255,255,0.2); border-radius: 12px; padding: 14px; backdrop-filter: blur(3px); }
      .label { font-size: 12px; opacity: .85; margin-bottom: 6px; }
      .value { font-size: 26px; font-weight: 700; }
      .log { margin-top: 18px; background: rgba(0,0,0,0.35); border-radius: 10px; padding: 12px; min-height: 90px; white-space: pre-wrap; }
      @media (max-width: 760px) { .grid { grid-template-columns: repeat(2, minmax(130px, 1fr)); } .title { font-size: 26px; } }
    </style>
  </head>
  <body>
    <div class="wrap">
      <h1 class="title">Sales Dashboard</h1>
      <div class="toolbar">
        <button class="btn secondary" onclick="refreshStats('today')">Refresh Today</button>
        <button class="btn secondary" onclick="refreshStats('week')">Refresh Week</button>
        <button class="btn" onclick="simulateTick()">Simulate Tick</button>
      </div>
      <div class="grid">
        <div class="card"><div class="label">Period</div><div class="value" id="period">-</div></div>
        <div class="card"><div class="label">Revenue</div><div class="value" id="revenue">-</div></div>
        <div class="card"><div class="label">Orders</div><div class="value" id="orders">-</div></div>
        <div class="card"><div class="label">Users</div><div class="value" id="users">-</div></div>
      </div>
      <div class="log" id="log">Loading...</div>
    </div>
    <script>
      async function mcpCall(toolName, params) {
        const r = await fetch('/tools/' + toolName, {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify(params || {})
        });
        if (!r.ok) {
          throw new Error('Tool call failed: ' + r.status);
        }
        return await r.json();
      }

      function setLog(text) {
        document.getElementById('log').textContent = text;
      }

      function render(data) {
        document.getElementById('period').textContent = data.period || 'today';
        document.getElementById('revenue').textContent = '$' + data.revenue.toLocaleString();
        document.getElementById('orders').textContent = data.orders.toLocaleString();
        document.getElementById('users').textContent = data.users.toLocaleString();
      }

      async function refreshStats(period) {
        try {
          setLog('Calling get_sales_stats...');
          const data = await mcpCall('get_sales_stats', { period });
          render(data);
          setLog('Updated at ' + new Date().toLocaleTimeString() + '\\n' + JSON.stringify(data, null, 2));
        } catch (e) {
          setLog(String(e));
        }
      }

      async function simulateTick() {
        try {
          setLog('Calling simulate_next_tick...');
          await mcpCall('simulate_next_tick', {});
          await refreshStats('today');
        } catch (e) {
          setLog(String(e));
        }
      }

      refreshStats('today');
    </script>
  </body>
</html>`,
    })
    .build();

  return app;
}

async function main() {
  const mcpApps = new MCPAppsServer({ port: PORT, enableCORS: true });
  const salesApp = buildSalesApp();
  mcpApps.registerApp(salesApp);
  await mcpApps.start();
  const defaultUiUri = salesApp.resources[0]?.uri || 'app://sales-dashboard/ui/sales-dashboard-ui';
  const encodedUiUri = encodeURIComponent(defaultUiUri);

  const app = express();
  app.use(express.json({ limit: '1mb' }));

  app.get('/', (_req, res) => {
    res.type('html').send(`
      <h2>MCP Apps Live Server</h2>
      <ul>
        <li><a href="/resources/${encodedUiUri}">Open Sales UI</a></li>
        <li><a href="/list_tools">List tools</a></li>
        <li><a href="/list_resources">List resources</a></li>
      </ul>
    `);
  });

  app.get('/list_tools', async (_req, res) => {
    const response = await mcpApps.handleRequest('GET', '/list_tools');
    res.status(response.status).set(response.headers).json(response.body);
  });

  app.get('/list_resources', async (_req, res) => {
    const response = await mcpApps.handleRequest('GET', '/list_resources');
    res.status(response.status).set(response.headers).json(response.body);
  });

  app.get('/resources/*', async (req, res) => {
    const suffix = req.originalUrl.replace('/resources/', '');
    const path = '/resources/' + suffix;
    const response = await mcpApps.handleRequest('GET', path);
    res.status(response.status).set(response.headers).send(response.body);
  });

  app.post('/tools/:toolName', async (req, res) => {
    const path = `/tools/${req.params.toolName}`;
    const response = await mcpApps.handleRequest('POST', path, req.body);
    res.status(response.status).set(response.headers).json(response.body);
  });

  app.listen(PORT, () => {
    console.log(`Live MCP Apps server listening on http://localhost:${PORT}`);
    console.log(`Open UI: http://localhost:${PORT}/resources/${encodedUiUri}`);
  });
}

main().catch((error) => {
  console.error('Server failed:', error);
  process.exit(1);
});
