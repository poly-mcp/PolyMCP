/**
 * MCP Apps Builder
 * 
 * Simplifies creation of MCP Apps for Claude, GPT, and other LLMs.
 * Provides helpers, templates, and utilities for building UI-enabled tools.
 * 
 * MCP Apps = Tools + UI Resources
 * - Tools provide functionality
 * - UI resources provide visual interface
 * - Apps combine both for rich user experience
 */

/**
 * UI resource types
 */
export enum UIResourceType {
  /** HTML page */
  HTML = 'text/html',
  
  /** React component */
  REACT = 'text/jsx',
  
  /** JSON data */
  JSON = 'application/json',
  
  /** CSS stylesheet */
  CSS = 'text/css',
  
  /** JavaScript */
  JAVASCRIPT = 'text/javascript',
}

/**
 * UI Resource definition
 */
export interface UIResource {
  /** Resource URI (unique identifier) */
  uri: string;
  
  /** Resource name */
  name: string;
  
  /** Resource description */
  description: string;
  
  /** MIME type */
  mimeType: string;
  
  /** Resource content */
  content: string;
  
  /** Associated tool names */
  tools?: string[];
  
  /** Metadata */
  metadata?: Record<string, any>;
}

/**
 * MCP App definition
 */
export interface MCPApp {
  /** App ID */
  id: string;
  
  /** App name */
  name: string;
  
  /** App description */
  description: string;
  
  /** Tools provided by this app */
  tools: Array<{
    name: string;
    description: string;
    inputSchema: Record<string, any>;
    handler: (params: any) => Promise<any>;
  }>;
  
  /** UI resources provided by this app */
  resources: UIResource[];
  
  /** App metadata */
  metadata?: Record<string, any>;
}

/**
 * MCP Apps Builder.
 * 
 * Simplifies building MCP Apps with UI components.
 * Makes it easy to create tools with visual interfaces.
 * 
 * Features:
 * - Simple API for creating apps
 * - Built-in templates
 * - Tool + UI resource pairing
 * - Automatic URI generation
 * - Validation and testing
 * 
 * Example:
 * ```typescript
 * const builder = new MCPAppsBuilder();
 * 
 * // Create a simple calculator app
 * const calculatorApp = builder.createApp({
 *   id: 'calculator',
 *   name: 'Calculator',
 *   description: 'A simple calculator with UI'
 * });
 * 
 * // Add tool
 * calculatorApp.addTool({
 *   name: 'calculate',
 *   description: 'Perform calculation',
 *   inputSchema: {
 *     type: 'object',
 *     properties: {
 *       expression: { type: 'string' }
 *     }
 *   },
 *   handler: async (params) => {
 *     return { result: eval(params.expression) };
 *   }
 * });
 * 
 * // Add UI resource
 * calculatorApp.addHTMLResource({
 *   name: 'Calculator Interface',
 *   html: '<div>..calculator UI...</div>'
 * });
 * 
 * // Build the app
 * const app = calculatorApp.build();
 * ```
 */
export class MCPAppsBuilder {
  /**
   * Create new app builder
   */
  createApp(config: {
    id: string;
    name: string;
    description: string;
    metadata?: Record<string, any>;
  }): AppBuilder {
    return new AppBuilder(config);
  }

  /**
   * Create app from template
   */
  createFromTemplate(template: AppTemplate): AppBuilder {
    const builder = new AppBuilder({
      id: template.id,
      name: template.name,
      description: template.description,
    });

    // Add template tools
    for (const tool of template.tools) {
      builder.addTool(tool);
    }

    // Add template resources
    for (const resource of template.resources) {
      builder.addResource(resource);
    }

    return builder;
  }

  /**
   * Validate app
   */
  validate(app: MCPApp): { valid: boolean; errors: string[] } {
    const errors: string[] = [];

    if (!app.id || app.id.trim().length === 0) {
      errors.push('App must have an ID');
    }

    if (!app.name || app.name.trim().length === 0) {
      errors.push('App must have a name');
    }

    if (app.tools.length === 0 && app.resources.length === 0) {
      errors.push('App must have at least one tool or resource');
    }

    // Validate tool names are unique
    const toolNames = new Set<string>();
    for (const tool of app.tools) {
      if (toolNames.has(tool.name)) {
        errors.push(`Duplicate tool name: ${tool.name}`);
      }
      toolNames.add(tool.name);
    }

    // Validate resource URIs are unique
    const resourceUris = new Set<string>();
    for (const resource of app.resources) {
      if (resourceUris.has(resource.uri)) {
        errors.push(`Duplicate resource URI: ${resource.uri}`);
      }
      resourceUris.add(resource.uri);
    }

    return {
      valid: errors.length === 0,
      errors,
    };
  }
}

/**
 * App Builder (fluent API)
 */
export class AppBuilder {
  private config: {
    id: string;
    name: string;
    description: string;
    metadata?: Record<string, any>;
  };
  
  private tools: Array<{
    name: string;
    description: string;
    inputSchema: Record<string, any>;
    handler: (params: any) => Promise<any>;
  }> = [];
  
  private resources: UIResource[] = [];

  constructor(config: {
    id: string;
    name: string;
    description: string;
    metadata?: Record<string, any>;
  }) {
    this.config = config;
  }

  /**
   * Add a tool
   */
  addTool(tool: {
    name: string;
    description: string;
    inputSchema: Record<string, any>;
    handler: (params: any) => Promise<any>;
  }): this {
    this.tools.push(tool);
    return this;
  }

  /**
   * Add a UI resource
   */
  addResource(resource: UIResource): this {
    this.resources.push(resource);
    return this;
  }

  /**
   * Add HTML resource (helper)
   */
  addHTMLResource(config: {
    name: string;
    html: string;
    description?: string;
    tools?: string[];
  }): this {
    const uri = `app://${this.config.id}/ui/${this.sanitizeUri(config.name)}`;
    
    this.resources.push({
      uri,
      name: config.name,
      description: config.description || `UI for ${config.name}`,
      mimeType: UIResourceType.HTML,
      content: config.html,
      tools: config.tools,
    });
    
    return this;
  }

  /**
   * Add React component resource (helper)
   */
  addReactResource(config: {
    name: string;
    jsx: string;
    description?: string;
    tools?: string[];
  }): this {
    const uri = `app://${this.config.id}/ui/${this.sanitizeUri(config.name)}`;
    
    this.resources.push({
      uri,
      name: config.name,
      description: config.description || `React UI for ${config.name}`,
      mimeType: UIResourceType.REACT,
      content: config.jsx,
      tools: config.tools,
    });
    
    return this;
  }

  /**
   * Add JSON data resource (helper)
   */
  addDataResource(config: {
    name: string;
    data: any;
    description?: string;
  }): this {
    const uri = `app://${this.config.id}/data/${this.sanitizeUri(config.name)}`;
    
    this.resources.push({
      uri,
      name: config.name,
      description: config.description || `Data for ${config.name}`,
      mimeType: UIResourceType.JSON,
      content: JSON.stringify(config.data, null, 2),
    });
    
    return this;
  }

  /**
   * Build the app
   */
  build(): MCPApp {
    return {
      id: this.config.id,
      name: this.config.name,
      description: this.config.description,
      tools: this.tools,
      resources: this.resources,
      metadata: this.config.metadata,
    };
  }

  /**
   * Sanitize string for URI
   */
  private sanitizeUri(str: string): string {
    return str
      .toLowerCase()
      .replace(/\s+/g, '-')
      .replace(/[^a-z0-9-]/g, '');
  }
}

/**
 * App Template (for common patterns)
 */
export interface AppTemplate {
  id: string;
  name: string;
  description: string;
  tools: Array<{
    name: string;
    description: string;
    inputSchema: Record<string, any>;
    handler: (params: any) => Promise<any>;
  }>;
  resources: UIResource[];
}

/**
 * Built-in Templates
 */
export class MCPAppTemplates {
  /**
   * Calculator app template
   */
  static calculator(): AppTemplate {
    return {
      id: 'calculator',
      name: 'Calculator',
      description: 'Simple calculator with UI',
      tools: [
        {
          name: 'calculate',
          description: 'Perform calculation',
          inputSchema: {
            type: 'object',
            properties: {
              expression: { 
                type: 'string',
                description: 'Math expression to evaluate'
              }
            },
            required: ['expression']
          },
          handler: async (params: any) => {
            try {
              // Safe eval (in production, use a proper math parser)
              const result = Function(`'use strict'; return (${params.expression})`)();
              return { result };
            } catch (error: any) {
              return { error: error.message };
            }
          }
        }
      ],
      resources: [
        {
          uri: 'app://calculator/ui/main',
          name: 'Calculator Interface',
          description: 'Interactive calculator UI',
          mimeType: UIResourceType.HTML,
          content: `
<!DOCTYPE html>
<html>
<head>
  <title>Calculator</title>
  <style>
    body { font-family: Arial, sans-serif; padding: 20px; }
    .calculator { max-width: 300px; margin: 0 auto; }
    input { width: 100%; padding: 10px; font-size: 18px; margin-bottom: 10px; }
    .buttons { display: grid; grid-template-columns: repeat(4, 1fr); gap: 5px; }
    button { padding: 15px; font-size: 16px; cursor: pointer; }
    .result { margin-top: 10px; padding: 10px; background: #f0f0f0; }
  </style>
</head>
<body>
  <div class="calculator">
    <h2>Calculator</h2>
    <input type="text" id="display" readonly>
    <div class="buttons">
      <button onclick="append('7')">7</button>
      <button onclick="append('8')">8</button>
      <button onclick="append('9')">9</button>
      <button onclick="append('+')">+</button>
      <button onclick="append('4')">4</button>
      <button onclick="append('5')">5</button>
      <button onclick="append('6')">6</button>
      <button onclick="append('-')">-</button>
      <button onclick="append('1')">1</button>
      <button onclick="append('2')">2</button>
      <button onclick="append('3')">3</button>
      <button onclick="append('*')">*</button>
      <button onclick="append('0')">0</button>
      <button onclick="append('.')">.</button>
      <button onclick="calculate()">=</button>
      <button onclick="append('/')">/</button>
      <button onclick="clear()" style="grid-column: 1/-1;">Clear</button>
    </div>
    <div class="result" id="result"></div>
  </div>
  <script>
    function append(val) {
      document.getElementById('display').value += val;
    }
    function clear() {
      document.getElementById('display').value = '';
      document.getElementById('result').textContent = '';
    }
    async function calculate() {
      const expression = document.getElementById('display').value;
      // Call MCP tool
      const result = await window.mcpCall('calculate', { expression });
      document.getElementById('result').textContent = 'Result: ' + result.result;
    }
  </script>
</body>
</html>
          `
        }
      ]
    };
  }

  /**
   * Todo list app template
   */
  static todoList(): AppTemplate {
    const todos: any[] = [];

    return {
      id: 'todo-list',
      name: 'Todo List',
      description: 'Todo list manager with UI',
      tools: [
        {
          name: 'add_todo',
          description: 'Add a todo item',
          inputSchema: {
            type: 'object',
            properties: {
              text: { type: 'string', description: 'Todo text' }
            },
            required: ['text']
          },
          handler: async (params: any) => {
            const todo = {
              id: Date.now().toString(),
              text: params.text,
              completed: false,
              createdAt: new Date().toISOString()
            };
            todos.push(todo);
            return { todo, total: todos.length };
          }
        },
        {
          name: 'list_todos',
          description: 'List all todos',
          inputSchema: {
            type: 'object',
            properties: {}
          },
          handler: async () => {
            return { todos, total: todos.length };
          }
        },
        {
          name: 'complete_todo',
          description: 'Mark todo as complete',
          inputSchema: {
            type: 'object',
            properties: {
              id: { type: 'string', description: 'Todo ID' }
            },
            required: ['id']
          },
          handler: async (params: any) => {
            const todo = todos.find(t => t.id === params.id);
            if (todo) {
              todo.completed = true;
              return { todo };
            }
            return { error: 'Todo not found' };
          }
        }
      ],
      resources: [
        {
          uri: 'app://todo-list/ui/main',
          name: 'Todo List Interface',
          description: 'Interactive todo list',
          mimeType: UIResourceType.HTML,
          content: `
<!DOCTYPE html>
<html>
<head>
  <title>Todo List</title>
  <style>
    body { font-family: Arial, sans-serif; padding: 20px; max-width: 600px; margin: 0 auto; }
    .todo-item { padding: 10px; border-bottom: 1px solid #eee; display: flex; align-items: center; }
    .todo-item.completed { opacity: 0.5; text-decoration: line-through; }
    input[type="text"] { flex: 1; padding: 8px; margin-right: 10px; }
    button { padding: 8px 15px; cursor: pointer; }
    .add-section { margin-bottom: 20px; display: flex; }
  </style>
</head>
<body>
  <h2>📝 Todo List</h2>
  <div class="add-section">
    <input type="text" id="newTodo" placeholder="What needs to be done?">
    <button onclick="addTodo()">Add</button>
  </div>
  <div id="todoList"></div>
  <script>
    async function addTodo() {
      const input = document.getElementById('newTodo');
      const text = input.value.trim();
      if (!text) return;
      
      await window.mcpCall('add_todo', { text });
      input.value = '';
      await loadTodos();
    }
    
    async function completeTodo(id) {
      await window.mcpCall('complete_todo', { id });
      await loadTodos();
    }
    
    async function loadTodos() {
      const result = await window.mcpCall('list_todos', {});
      const list = document.getElementById('todoList');
      list.innerHTML = result.todos.map(todo => 
        '<div class="todo-item ' + (todo.completed ? 'completed' : '') + '">' +
        '<input type="checkbox" ' + (todo.completed ? 'checked' : '') + 
        ' onclick="completeTodo(\'' + todo.id + '\')">' +
        '<span>' + todo.text + '</span>' +
        '</div>'
      ).join('');
    }
    
    loadTodos();
  </script>
</body>
</html>
          `
        }
      ]
    };
  }

  /**
   * Dashboard app template
   */
  static dashboard(): AppTemplate {
    return {
      id: 'dashboard',
      name: 'Dashboard',
      description: 'Data dashboard with charts',
      tools: [
        {
          name: 'get_stats',
          description: 'Get dashboard statistics',
          inputSchema: {
            type: 'object',
            properties: {}
          },
          handler: async () => {
            return {
              stats: {
                users: 1234,
                revenue: 56789,
                orders: 890,
                growth: 12.5
              }
            };
          }
        }
      ],
      resources: [
        {
          uri: 'app://dashboard/ui/main',
          name: 'Dashboard Interface',
          description: 'Interactive dashboard',
          mimeType: UIResourceType.HTML,
          content: `
<!DOCTYPE html>
<html>
<head>
  <title>Dashboard</title>
  <style>
    body { font-family: Arial, sans-serif; padding: 20px; background: #f5f5f5; }
    .dashboard { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; }
    .card { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
    .card h3 { margin: 0 0 10px; color: #666; font-size: 14px; }
    .card .value { font-size: 32px; font-weight: bold; color: #333; }
    .card .change { color: #4caf50; font-size: 14px; margin-top: 5px; }
  </style>
</head>
<body>
  <h2>📊 Dashboard</h2>
  <div class="dashboard" id="dashboard"></div>
  <script>
    async function loadDashboard() {
      const result = await window.mcpCall('get_stats', {});
      const stats = result.stats;
      
      document.getElementById('dashboard').innerHTML = 
        '<div class="card"><h3>Total Users</h3><div class="value">' + stats.users + '</div></div>' +
        '<div class="card"><h3>Revenue</h3><div class="value">$' + stats.revenue + '</div><div class="change">↑ ' + stats.growth + '%</div></div>' +
        '<div class="card"><h3>Orders</h3><div class="value">' + stats.orders + '</div></div>';
    }
    
    loadDashboard();
    setInterval(loadDashboard, 30000); // Refresh every 30s
  </script>
</body>
</html>
          `
        }
      ]
    };
  }
}

/**
 * Utility: Quick app creation
 */
export function createSimpleApp(
  id: string,
  name: string,
  description: string,
  toolHandler: (toolName: string, params: any) => Promise<any>,
  htmlContent: string
): MCPApp {
  const builder = new MCPAppsBuilder().createApp({ id, name, description });
  
  builder.addTool({
    name: 'execute',
    description: `Execute ${name} operation`,
    inputSchema: {
      type: 'object',
      properties: {
        action: { type: 'string' },
        params: { type: 'object' }
      }
    },
    handler: async (params: any) => {
      return await toolHandler(params.action, params.params);
    }
  });
  
  builder.addHTMLResource({
    name: `${name} Interface`,
    html: htmlContent
  });
  
  return builder.build();
}
