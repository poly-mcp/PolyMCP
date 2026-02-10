/**
 * MCP Apps Builder
 * 
 * Simplifies creating MCP Apps for Claude, GPT, and other LLMs.
 * 
 * PolyMCP makes it EASY to build interactive apps that work with ANY LLM:
 * - Define app metadata
 * - Describe UI components
 * - Add interactivity
 * - Deploy to any MCP server
 * 
 * The LLM (Claude, GPT, etc.) will automatically:
 * - Understand your app's capabilities
 * - Render the UI appropriately
 * - Handle user interactions
 */

/**
 * UI component types supported by MCP Apps
 */
export enum UIComponentType {
  /** Simple text display */
  TEXT = 'text',
  
  /** Heading/title */
  HEADING = 'heading',
  
  /** Button for actions */
  BUTTON = 'button',
  
  /** Text input field */
  INPUT = 'input',
  
  /** Dropdown/select */
  SELECT = 'select',
  
  /** Checkbox */
  CHECKBOX = 'checkbox',
  
  /** Image display */
  IMAGE = 'image',
  
  /** Chart/graph */
  CHART = 'chart',
  
  /** Table */
  TABLE = 'table',
  
  /** Card container */
  CARD = 'card',
  
  /** List */
  LIST = 'list',
  
  /** Progress bar */
  PROGRESS = 'progress',
  
  /** Custom HTML */
  HTML = 'html',
}

/**
 * UI component definition
 */
export interface UIComponent {
  /** Component type */
  type: UIComponentType;
  
  /** Component ID (for interactions) */
  id?: string;
  
  /** Component content/data */
  content?: any;
  
  /** Component properties */
  props?: Record<string, any>;
  
  /** Child components */
  children?: UIComponent[];
  
  /** Event handlers */
  events?: {
    onClick?: string;
    onChange?: string;
    onSubmit?: string;
  };
}

/**
 * MCP App definition
 */
export interface MCPApp {
  /** App unique identifier */
  id: string;
  
  /** App display name */
  name: string;
  
  /** App description */
  description: string;
  
  /** App version */
  version: string;
  
  /** App icon (URL or emoji) */
  icon?: string;
  
  /** App UI components */
  ui: UIComponent[];
  
  /** App tools/actions */
  tools?: Array<{
    name: string;
    description: string;
    handler: (params: any) => Promise<any>;
  }>;
  
  /** App metadata */
  metadata?: {
    author?: string;
    category?: string;
    tags?: string[];
    llmCompatibility?: string[]; // ['claude', 'gpt', 'gemini', etc.]
  };
}

/**
 * MCP App Builder.
 * 
 * Makes it DEAD SIMPLE to create MCP Apps for any LLM.
 * 
 * Features:
 * - Fluent API for building UIs
 * - Automatic tool registration
 * - Works with Claude, GPT, Gemini, etc.
 * - Zero configuration needed
 * - Type-safe
 * 
 * Example - Simple Counter App:
 * ```typescript
 * const app = new MCPAppBuilder('counter', 'Counter App')
 *   .description('A simple counter application')
 *   .icon('🔢')
 *   
 *   // Add UI
 *   .addHeading('Counter')
 *   .addText('Current count: 0', { id: 'count-display' })
 *   .addButton('Increment', { id: 'increment-btn', onClick: 'increment' })
 *   .addButton('Reset', { id: 'reset-btn', onClick: 'reset' })
 *   
 *   // Add tools
 *   .addTool('increment', 'Increment the counter', async () => {
 *     // Your logic here
 *     return { count: currentCount + 1 };
 *   })
 *   .addTool('reset', 'Reset counter to 0', async () => {
 *     return { count: 0 };
 *   })
 *   
 *   .build();
 * ```
 * 
 * Example - Task Manager:
 * ```typescript
 * const app = new MCPAppBuilder('tasks', 'Task Manager')
 *   .description('Manage your tasks')
 *   .icon('✅')
 *   .llmCompatibility(['claude', 'gpt', 'gemini'])
 *   
 *   .addHeading('My Tasks')
 *   .addInput('New task', { id: 'task-input', placeholder: 'Enter task...' })
 *   .addButton('Add Task', { id: 'add-btn', onClick: 'addTask' })
 *   .addList([], { id: 'task-list' })
 *   
 *   .addTool('addTask', 'Add a new task', async (params) => {
 *     tasks.push(params.task);
 *     return { tasks, success: true };
 *   })
 *   .addTool('completeTask', 'Mark task as complete', async (params) => {
 *     tasks[params.index].completed = true;
 *     return { tasks, success: true };
 *   })
 *   
 *   .build();
 * ```
 */
export class MCPAppBuilder {
  private app: MCPApp;

  constructor(id: string, name: string) {
    this.app = {
      id,
      name,
      description: '',
      version: '1.0.0',
      ui: [],
      tools: [],
      metadata: {
        llmCompatibility: ['claude', 'gpt', 'gemini'], // Works with all by default
      },
    };
  }

  /**
   * Set app description
   */
  description(text: string): this {
    this.app.description = text;
    return this;
  }

  /**
   * Set app version
   */
  version(version: string): this {
    this.app.version = version;
    return this;
  }

  /**
   * Set app icon
   */
  icon(icon: string): this {
    this.app.icon = icon;
    return this;
  }

  /**
   * Set author
   */
  author(author: string): this {
    if (!this.app.metadata) this.app.metadata = {};
    this.app.metadata.author = author;
    return this;
  }

  /**
   * Set category
   */
  category(category: string): this {
    if (!this.app.metadata) this.app.metadata = {};
    this.app.metadata.category = category;
    return this;
  }

  /**
   * Set tags
   */
  tags(tags: string[]): this {
    if (!this.app.metadata) this.app.metadata = {};
    this.app.metadata.tags = tags;
    return this;
  }

  /**
   * Set LLM compatibility
   */
  llmCompatibility(llms: string[]): this {
    if (!this.app.metadata) this.app.metadata = {};
    this.app.metadata.llmCompatibility = llms;
    return this;
  }

  // ========================================
  // UI COMPONENTS - Fluent API
  // ========================================

  /**
   * Add text component
   */
  addText(text: string, props?: Record<string, any>): this {
    this.app.ui.push({
      type: UIComponentType.TEXT,
      content: text,
      props,
    });
    return this;
  }

  /**
   * Add heading component
   */
  addHeading(text: string, props?: Record<string, any>): this {
    this.app.ui.push({
      type: UIComponentType.HEADING,
      content: text,
      props,
    });
    return this;
  }

  /**
   * Add button component
   */
  addButton(label: string, props?: Record<string, any>): this {
    this.app.ui.push({
      type: UIComponentType.BUTTON,
      content: label,
      props,
      events: props?.onClick ? { onClick: props.onClick } : undefined,
    });
    return this;
  }

  /**
   * Add input component
   */
  addInput(label: string, props?: Record<string, any>): this {
    this.app.ui.push({
      type: UIComponentType.INPUT,
      content: label,
      props,
    });
    return this;
  }

  /**
   * Add select/dropdown component
   */
  addSelect(label: string, options: string[], props?: Record<string, any>): this {
    this.app.ui.push({
      type: UIComponentType.SELECT,
      content: { label, options },
      props,
    });
    return this;
  }

  /**
   * Add checkbox component
   */
  addCheckbox(label: string, props?: Record<string, any>): this {
    this.app.ui.push({
      type: UIComponentType.CHECKBOX,
      content: label,
      props,
    });
    return this;
  }

  /**
   * Add image component
   */
  addImage(url: string, props?: Record<string, any>): this {
    this.app.ui.push({
      type: UIComponentType.IMAGE,
      content: url,
      props,
    });
    return this;
  }

  /**
   * Add chart component
   */
  addChart(data: any, props?: Record<string, any>): this {
    this.app.ui.push({
      type: UIComponentType.CHART,
      content: data,
      props,
    });
    return this;
  }

  /**
   * Add table component
   */
  addTable(data: any[][], headers?: string[], props?: Record<string, any>): this {
    this.app.ui.push({
      type: UIComponentType.TABLE,
      content: { data, headers },
      props,
    });
    return this;
  }

  /**
   * Add card container
   */
  addCard(children: UIComponent[], props?: Record<string, any>): this {
    this.app.ui.push({
      type: UIComponentType.CARD,
      children,
      props,
    });
    return this;
  }

  /**
   * Add list component
   */
  addList(items: string[], props?: Record<string, any>): this {
    this.app.ui.push({
      type: UIComponentType.LIST,
      content: items,
      props,
    });
    return this;
  }

  /**
   * Add progress bar
   */
  addProgress(value: number, max: number = 100, props?: Record<string, any>): this {
    this.app.ui.push({
      type: UIComponentType.PROGRESS,
      content: { value, max },
      props,
    });
    return this;
  }

  /**
   * Add custom HTML
   */
  addHTML(html: string, props?: Record<string, any>): this {
    this.app.ui.push({
      type: UIComponentType.HTML,
      content: html,
      props,
    });
    return this;
  }

  /**
   * Add custom component
   */
  addComponent(component: UIComponent): this {
    this.app.ui.push(component);
    return this;
  }

  // ========================================
  // TOOLS/ACTIONS
  // ========================================

  /**
   * Add tool/action
   */
  addTool(
    name: string,
    description: string,
    handler: (params: any) => Promise<any>
  ): this {
    if (!this.app.tools) this.app.tools = [];
    this.app.tools.push({ name, description, handler });
    return this;
  }

  // ========================================
  // BUILD & EXPORT
  // ========================================

  /**
   * Build the app
   */
  build(): MCPApp {
    return this.app;
  }

  /**
   * Export as MCP tool metadata
   */
  exportAsToolMetadata(): any {
    return {
      name: this.app.id,
      description: this.app.description,
      input_schema: {
        type: 'object',
        properties: {
          action: {
            type: 'string',
            description: 'Action to perform',
            enum: this.app.tools?.map(t => t.name) || [],
          },
          params: {
            type: 'object',
            description: 'Action parameters',
          },
        },
        required: ['action'],
      },
      _app: true,
      _app_metadata: {
        id: this.app.id,
        name: this.app.name,
        version: this.app.version,
        icon: this.app.icon,
        ui: this.app.ui,
        metadata: this.app.metadata,
      },
    };
  }

  /**
   * Export as JSON
   */
  toJSON(): string {
    return JSON.stringify(this.app, null, 2);
  }

  /**
   * Import from JSON
   */
  static fromJSON(json: string): MCPAppBuilder {
    const app = JSON.parse(json) as MCPApp;
    const builder = new MCPAppBuilder(app.id, app.name);
    builder.app = app;
    return builder;
  }
}

/**
 * Quick app templates
 */
export class MCPAppTemplates {
  /**
   * Create a simple counter app
   */
  static counter(): MCPAppBuilder {
    return new MCPAppBuilder('counter', 'Counter')
      .description('Simple counter application')
      .icon('🔢')
      .addHeading('Counter')
      .addText('Count: 0', { id: 'count' })
      .addButton('Increment', { id: 'inc', onClick: 'increment' })
      .addButton('Decrement', { id: 'dec', onClick: 'decrement' })
      .addButton('Reset', { id: 'reset', onClick: 'reset' });
  }

  /**
   * Create a todo list app
   */
  static todoList(): MCPAppBuilder {
    return new MCPAppBuilder('todo', 'Todo List')
      .description('Task management application')
      .icon('✅')
      .addHeading('My Tasks')
      .addInput('New task', { id: 'task-input', placeholder: 'Enter task...' })
      .addButton('Add Task', { id: 'add', onClick: 'addTask' })
      .addList([], { id: 'tasks' });
  }

  /**
   * Create a data dashboard
   */
  static dashboard(title: string): MCPAppBuilder {
    return new MCPAppBuilder('dashboard', title)
      .description('Data visualization dashboard')
      .icon('📊')
      .addHeading(title)
      .addCard([
        { type: UIComponentType.TEXT, content: 'Loading data...' },
      ], { id: 'stats' });
  }

  /**
   * Create a form app
   */
  static form(title: string, fields: Array<{ label: string; type: string }>): MCPAppBuilder {
    const builder = new MCPAppBuilder('form', title)
      .description('Form application')
      .icon('📝')
      .addHeading(title);

    for (const field of fields) {
      if (field.type === 'text') {
        builder.addInput(field.label, { id: field.label.toLowerCase().replace(/\s+/g, '_') });
      } else if (field.type === 'checkbox') {
        builder.addCheckbox(field.label, { id: field.label.toLowerCase().replace(/\s+/g, '_') });
      }
    }

    builder.addButton('Submit', { id: 'submit', onClick: 'submitForm' });

    return builder;
  }
}

/**
 * MCP App Registry.
 * 
 * Central registry for all available MCP Apps.
 * Makes apps discoverable by LLMs.
 */
export class MCPAppRegistry {
  private apps: Map<string, MCPApp> = new Map();

  /**
   * Register an app
   */
  register(app: MCPApp): void {
    this.apps.set(app.id, app);
  }

  /**
   * Unregister an app
   */
  unregister(appId: string): void {
    this.apps.delete(appId);
  }

  /**
   * Get app by ID
   */
  getApp(appId: string): MCPApp | undefined {
    return this.apps.get(appId);
  }

  /**
   * Get all apps
   */
  getAllApps(): MCPApp[] {
    return Array.from(this.apps.values());
  }

  /**
   * Get apps by category
   */
  getAppsByCategory(category: string): MCPApp[] {
    return this.getAllApps().filter(
      app => app.metadata?.category === category
    );
  }

  /**
   * Get apps compatible with LLM
   */
  getAppsForLLM(llm: string): MCPApp[] {
    return this.getAllApps().filter(
      app => app.metadata?.llmCompatibility?.includes(llm)
    );
  }

  /**
   * Search apps
   */
  search(query: string): MCPApp[] {
    const lowerQuery = query.toLowerCase();
    return this.getAllApps().filter(app =>
      app.name.toLowerCase().includes(lowerQuery) ||
      app.description.toLowerCase().includes(lowerQuery) ||
      app.metadata?.tags?.some(tag => tag.toLowerCase().includes(lowerQuery))
    );
  }

  /**
   * Export all apps as tool metadata
   */
  exportAsTools(): any[] {
    return this.getAllApps().map(app => {
      const builder = new MCPAppBuilder(app.id, app.name);
      builder['app'] = app;
      return builder.exportAsToolMetadata();
    });
  }

  /**
   * Clear registry
   */
  clear(): void {
    this.apps.clear();
  }

  /**
   * Get statistics
   */
  getStatistics(): {
    totalApps: number;
    byCategory: Record<string, number>;
    byLLM: Record<string, number>;
  } {
    const byCategory: Record<string, number> = {};
    const byLLM: Record<string, number> = {};

    for (const app of this.getAllApps()) {
      // Count by category
      const category = app.metadata?.category || 'uncategorized';
      byCategory[category] = (byCategory[category] || 0) + 1;

      // Count by LLM compatibility
      const llms = app.metadata?.llmCompatibility || [];
      for (const llm of llms) {
        byLLM[llm] = (byLLM[llm] || 0) + 1;
      }
    }

    return {
      totalApps: this.apps.size,
      byCategory,
      byLLM,
    };
  }
}
