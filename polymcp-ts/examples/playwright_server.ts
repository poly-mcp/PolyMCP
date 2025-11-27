/**
 * Playwright Server Example
 * 
 * Advanced MCP server that exposes browser automation tools using Playwright.
 * Demonstrates complex tool creation with real-world browser automation.
 * 
 * Install additional dependency:
 * npm install playwright
 * npx playwright install chromium
 */

import { tool, exposeToolsHttp } from '../src';
import { z } from 'zod';
import { chromium, Browser, Page } from 'playwright';

// ============================================================================
// Playwright Manager
// ============================================================================

class PlaywrightManager {
  private browser: Browser | null = null;
  private pages: Map<string, Page> = new Map();
  
  async ensureBrowser(): Promise<Browser> {
    if (!this.browser) {
      this.browser = await chromium.launch({
        headless: true,
        args: ['--no-sandbox', '--disable-setuid-sandbox'],
      });
    }
    return this.browser;
  }
  
  async newPage(sessionId: string): Promise<Page> {
    const browser = await this.ensureBrowser();
    const page = await browser.newPage();
    this.pages.set(sessionId, page);
    return page;
  }
  
  getPage(sessionId: string): Page | undefined {
    return this.pages.get(sessionId);
  }
  
  async closePage(sessionId: string): Promise<void> {
    const page = this.pages.get(sessionId);
    if (page) {
      await page.close();
      this.pages.delete(sessionId);
    }
  }
  
  async cleanup(): Promise<void> {
    for (const page of this.pages.values()) {
      await page.close();
    }
    this.pages.clear();
    
    if (this.browser) {
      await this.browser.close();
      this.browser = null;
    }
  }
}

const manager = new PlaywrightManager();

// ============================================================================
// Browser Navigation Tools
// ============================================================================

const navigateTool = tool({
  name: 'browser_navigate',
  description: 'Navigate to a URL in the browser',
  inputSchema: z.object({
    url: z.string().url().describe('URL to navigate to'),
    sessionId: z.string().default('default').describe('Browser session ID'),
    waitUntil: z.enum(['load', 'domcontentloaded', 'networkidle']).default('load'),
  }),
  function: async ({ url, sessionId, waitUntil }) => {
    const sid = sessionId ?? 'default';
    let page = manager.getPage(sid);
    if (!page) {
      page = await manager.newPage(sid);
    }
    
    await page.goto(url, { waitUntil });
    const title = await page.title();
    
    return {
      success: true,
      url: page.url(),
      title,
      sessionId: sid,
    };
  },
});

const screenshotTool = tool({
  name: 'browser_screenshot',
  description: 'Take a screenshot of the current page',
  inputSchema: z.object({
    sessionId: z.string().default('default'),
    fullPage: z.boolean().default(false).describe('Capture full page or just viewport'),
    selector: z.string().optional().describe('CSS selector to screenshot specific element'),
  }),
  function: async ({ sessionId, fullPage, selector }) => {
    const sid = sessionId ?? 'default';
    const page = manager.getPage(sid);
    if (!page) {
      return { success: false, error: 'No active browser session' };
    }
    
    const options: any = { fullPage, type: 'png' };
    let screenshot: Buffer;
    
    if (selector) {
      const element = await page.locator(selector).first();
      screenshot = await element.screenshot(options);
    } else {
      screenshot = await page.screenshot(options);
    }
    
    return {
      success: true,
      screenshot: screenshot.toString('base64'),
      format: 'png',
      encoding: 'base64',
    };
  },
});

// ============================================================================
// Page Interaction Tools
// ============================================================================

const clickTool = tool({
  name: 'browser_click',
  description: 'Click on an element',
  inputSchema: z.object({
    selector: z.string().describe('CSS selector of element to click'),
    sessionId: z.string().default('default'),
    button: z.enum(['left', 'right', 'middle']).default('left'),
    clickCount: z.number().default(1).describe('Number of clicks (for double-click use 2)'),
  }),
  function: async ({ selector, sessionId, button, clickCount }) => {
    const sid = sessionId ?? 'default';
    const page = manager.getPage(sid);
    if (!page) {
      return { success: false, error: 'No active browser session' };
    }
    
    await page.click(selector, { button, clickCount });
    
    return {
      success: true,
      selector,
      action: 'clicked',
    };
  },
});

const fillTool = tool({
  name: 'browser_fill',
  description: 'Fill a form field with text',
  inputSchema: z.object({
    selector: z.string().describe('CSS selector of input field'),
    value: z.string().describe('Text to fill'),
    sessionId: z.string().default('default'),
  }),
  function: async ({ selector, value, sessionId }) => {
    const sid = sessionId ?? 'default';
    const page = manager.getPage(sid);
    if (!page) {
      return { success: false, error: 'No active browser session' };
    }
    
    await page.fill(selector, value);
    
    return {
      success: true,
      selector,
      value,
      action: 'filled',
    };
  },
});

const pressKeyTool = tool({
  name: 'browser_press_key',
  description: 'Press a keyboard key',
  inputSchema: z.object({
    key: z.string().describe('Key to press (e.g., "Enter", "Escape", "ArrowDown")'),
    sessionId: z.string().default('default'),
    selector: z.string().optional().describe('Focus this element first'),
  }),
  function: async ({ key, sessionId, selector }) => {
    const sid = sessionId ?? 'default';
    const page = manager.getPage(sid);
    if (!page) {
      return { success: false, error: 'No active browser session' };
    }
    
    if (selector) {
      await page.focus(selector);
    }
    
    await page.keyboard.press(key);
    
    return {
      success: true,
      key,
      action: 'pressed',
    };
  },
});

// ============================================================================
// Data Extraction Tools
// ============================================================================

const extractTextTool = tool({
  name: 'browser_extract_text',
  description: 'Extract text content from elements',
  inputSchema: z.object({
    selector: z.string().describe('CSS selector of elements'),
    sessionId: z.string().default('default'),
    multiple: z.boolean().default(false).describe('Extract from all matching elements'),
  }),
  function: async ({ selector, sessionId, multiple }) => {
    const sid = sessionId ?? 'default';
    const page = manager.getPage(sid);
    if (!page) {
      return { success: false, error: 'No active browser session' };
    }
    
    if (multiple) {
      const texts = await page.locator(selector).allTextContents();
      return {
        success: true,
        selector,
        texts,
        count: texts.length,
      };
    } else {
      const text = await page.locator(selector).first().textContent();
      return {
        success: true,
        selector,
        text,
      };
    }
  },
});

const extractAttributeTool = tool({
  name: 'browser_extract_attribute',
  description: 'Extract attribute value from an element',
  inputSchema: z.object({
    selector: z.string().describe('CSS selector'),
    attribute: z.string().describe('Attribute name (e.g., "href", "src", "class")'),
    sessionId: z.string().default('default'),
  }),
  function: async ({ selector, attribute, sessionId }) => {
    const sid = sessionId ?? 'default';
    const page = manager.getPage(sid);
    if (!page) {
      return { success: false, error: 'No active browser session' };
    }
    
    const value = await page.locator(selector).first().getAttribute(attribute);
    
    return {
      success: true,
      selector,
      attribute,
      value,
    };
  },
});

const evaluateJSTool = tool({
  name: 'browser_evaluate_js',
  description: 'Execute JavaScript code in the browser context',
  inputSchema: z.object({
    code: z.string().describe('JavaScript code to execute'),
    sessionId: z.string().default('default'),
  }),
  function: async ({ code, sessionId }) => {
    const sid = sessionId ?? 'default';
    const page = manager.getPage(sid);
    if (!page) {
      return { success: false, error: 'No active browser session' };
    }
    
    try {
      const result = await page.evaluate(code);
      return {
        success: true,
        result,
      };
    } catch (error: any) {
      return {
        success: false,
        error: error.message,
      };
    }
  },
});

// ============================================================================
// Wait Tools
// ============================================================================

const waitForSelectorTool = tool({
  name: 'browser_wait_for_selector',
  description: 'Wait for an element to appear',
  inputSchema: z.object({
    selector: z.string().describe('CSS selector to wait for'),
    sessionId: z.string().default('default'),
    timeout: z.number().default(30000).describe('Timeout in milliseconds'),
    state: z.enum(['attached', 'detached', 'visible', 'hidden']).default('visible'),
  }),
  function: async ({ selector, sessionId, timeout, state }) => {
    const sid = sessionId ?? 'default';
    const page = manager.getPage(sid);
    if (!page) {
      return { success: false, error: 'No active browser session' };
    }
    
    try {
      await page.waitForSelector(selector, { timeout, state });
      return {
        success: true,
        selector,
        state,
      };
    } catch (error: any) {
      return {
        success: false,
        error: `Timeout waiting for selector: ${selector}`,
      };
    }
  },
});

const waitForNavigationTool = tool({
  name: 'browser_wait_for_navigation',
  description: 'Wait for page navigation to complete',
  inputSchema: z.object({
    sessionId: z.string().default('default'),
    timeout: z.number().default(30000),
    waitUntil: z.enum(['load', 'domcontentloaded', 'networkidle']).default('load'),
  }),
  function: async ({ sessionId, timeout, waitUntil }) => {
    const sid = sessionId ?? 'default';
    const page = manager.getPage(sid);
    if (!page) {
      return { success: false, error: 'No active browser session' };
    }
    
    await page.waitForLoadState(waitUntil, { timeout });
    
    return {
      success: true,
      url: page.url(),
      title: await page.title(),
    };
  },
});

// ============================================================================
// Session Management Tools
// ============================================================================

const closeSessionTool = tool({
  name: 'browser_close_session',
  description: 'Close a browser session',
  inputSchema: z.object({
    sessionId: z.string().default('default'),
  }),
  function: async ({ sessionId }) => {
    const sid = sessionId ?? 'default';
    await manager.closePage(sid);
    return {
      success: true,
      sessionId: sid,
      action: 'closed',
    };
  },
});

// ============================================================================
// Start Server
// ============================================================================

async function main() {
  const tools = [
    // Navigation
    navigateTool,
    screenshotTool,
    
    // Interaction
    clickTool,
    fillTool,
    pressKeyTool,
    
    // Extraction
    extractTextTool,
    extractAttributeTool,
    evaluateJSTool,
    
    // Wait
    waitForSelectorTool,
    waitForNavigationTool,
    
    // Session
    closeSessionTool,
  ];
  
  console.log('🎭 Starting Playwright MCP Server...\n');
  
  const app = exposeToolsHttp(tools, {
    title: 'Playwright Automation Server',
    description: 'Browser automation tools powered by Playwright',
    verbose: true,
  });
  
  const PORT = 3100;
  const HOST = '0.0.0.0';
  
  app.listen(PORT, HOST, () => {
    console.log('\n✅ Playwright Server started!');
    console.log(`📡 Listening on http://localhost:${PORT}`);
    console.log('\n🔧 Available tools:');
    tools.forEach(tool => {
      console.log(`  - ${tool.name}: ${tool.description}`);
    });
    
    console.log('\n📝 Example workflow:');
    console.log('1. Navigate to page:');
    console.log(`   curl -X POST http://localhost:${PORT}/mcp/invoke \\`);
    console.log(`     -H "Content-Type: application/json" \\`);
    console.log(`     -d '{"tool": "browser_navigate", "parameters": {"url": "https://example.com"}}'`);
    
    console.log('\n2. Extract text:');
    console.log(`   curl -X POST http://localhost:${PORT}/mcp/invoke \\`);
    console.log(`     -H "Content-Type: application/json" \\`);
    console.log(`     -d '{"tool": "browser_extract_text", "parameters": {"selector": "h1"}}'`);
    
    console.log('\n3. Take screenshot:');
    console.log(`   curl -X POST http://localhost:${PORT}/mcp/invoke \\`);
    console.log(`     -H "Content-Type: application/json" \\`);
    console.log(`     -d '{"tool": "browser_screenshot", "parameters": {"fullPage": true}}'`);
    
    console.log('\n\n⌨️  Press Ctrl+C to stop the server\n');
  });
  
  // Cleanup on exit
  process.on('SIGINT', async () => {
    console.log('\n\n🧹 Cleaning up...');
    await manager.cleanup();
    console.log('✅ Cleanup complete');
    process.exit(0);
  });
}

main().catch(console.error);
