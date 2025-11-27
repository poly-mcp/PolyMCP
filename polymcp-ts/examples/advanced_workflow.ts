/**
 * Advanced Workflow Example - E-commerce Price Monitor
 * 
 * Real-world scenario: Automated price monitoring and notification system.
 * 
 * This example demonstrates a complete workflow that:
 * 1. Monitors e-commerce websites for product prices
 * 2. Compares prices across different retailers
 * 3. Stores data and generates reports
 * 4. Sends notifications when prices drop
 * 
 * Prerequisites:
 * - Playwright server running (npm run example:playwright-server)
 * - Ollama running locally
 * 
 * This showcases enterprise-grade automation with PolyMCP.
 */

import { UnifiedPolyAgent } from '../src/agent/unified_agent';
import { OllamaProvider, OpenAIProvider } from '../src/agent/llm_providers';
import { tool, exposeToolsHttp } from '../src';
import { z } from 'zod';
import * as fs from 'fs';
import * as path from 'path';
import * as http from 'http';

// ============================================================================
// Data Storage Tools
// ============================================================================

interface PriceData {
  productName: string;
  retailer: string;
  price: number;
  currency: string;
  timestamp: string;
  url: string;
}

const priceDatabase: PriceData[] = [];

// Tools server instance
let toolsServer: http.Server | null = null;

async function startToolsServer(): Promise<void> {
  return new Promise((resolve, reject) => {
    const tools = [
      savePriceTool,
      getPriceHistoryTool,
      comparePricesTool,
      sendNotificationTool,
      generateReportTool,
    ];
    
    const app = exposeToolsHttp(tools, {
      title: 'Price Monitoring Tools',
      description: 'Tools for e-commerce price monitoring',
      verbose: false,
    });
    
    toolsServer = app.listen(3201, () => {
      if (process.env.VERBOSE) {
        console.log('✅ Price monitoring tools server started on http://localhost:3201');
      }
      resolve();
    });
    
    toolsServer.on('error', reject);
  });
}

async function stopToolsServer(): Promise<void> {
  return new Promise((resolve) => {
    if (toolsServer) {
      toolsServer.close(() => {
        if (process.env.VERBOSE) {
          console.log('✅ Tools server stopped');
        }
        resolve();
      });
    } else {
      resolve();
    }
  });
}


const savePriceTool = tool({
  name: 'save_price_data',
  description: 'Save price information to the database',
  inputSchema: z.object({
    productName: z.string(),
    retailer: z.string(),
    price: z.number(),
    currency: z.string().default('USD'),
    url: z.string().url(),
  }),
  function: async ({ productName, retailer, price, currency, url }) => {
    const entry: PriceData = {
      productName,
      retailer,
      price,
      currency,
      timestamp: new Date().toISOString(),
      url,
    };
    
    priceDatabase.push(entry);
    
    // Also save to file
    const dataDir = path.join(__dirname, 'data');
    if (!fs.existsSync(dataDir)) {
      fs.mkdirSync(dataDir, { recursive: true });
    }
    
    const filePath = path.join(dataDir, 'price_history.json');
    fs.writeFileSync(filePath, JSON.stringify(priceDatabase, null, 2));
    
    console.log(`💾 Saved price: ${productName} at ${retailer} for ${currency}${price}`);
    
    return {
      success: true,
      id: priceDatabase.length - 1,
      entry,
    };
  },
});

const getPriceHistoryTool = tool({
  name: 'get_price_history',
  description: 'Get price history for a product',
  inputSchema: z.object({
    productName: z.string(),
    retailer: z.string().optional(),
  }),
  function: async ({ productName, retailer }) => {
    let filtered = priceDatabase.filter(
      entry => entry.productName.toLowerCase().includes(productName.toLowerCase())
    );
    
    if (retailer) {
      filtered = filtered.filter(
        entry => entry.retailer.toLowerCase().includes(retailer.toLowerCase())
      );
    }
    
    return {
      product: productName,
      retailer: retailer || 'all',
      entries: filtered,
      count: filtered.length,
    };
  },
});

const comparePricesTool = tool({
  name: 'compare_prices',
  description: 'Compare prices across different retailers for the same product',
  inputSchema: z.object({
    productName: z.string(),
  }),
  function: async ({ productName }) => {
    const filtered = priceDatabase.filter(
      entry => entry.productName.toLowerCase().includes(productName.toLowerCase())
    );
    
    if (filtered.length === 0) {
      return {
        product: productName,
        message: 'No price data found',
        retailers: [],
      };
    }
    
    // Group by retailer and get latest price
    const byRetailer = new Map<string, PriceData>();
    for (const entry of filtered) {
      const existing = byRetailer.get(entry.retailer);
      if (!existing || new Date(entry.timestamp) > new Date(existing.timestamp)) {
        byRetailer.set(entry.retailer, entry);
      }
    }
    
    const retailers = Array.from(byRetailer.values());
    const prices = retailers.map(r => r.price);
    const lowest = Math.min(...prices);
    const highest = Math.max(...prices);
    const lowestRetailer = retailers.find(r => r.price === lowest);
    
    return {
      product: productName,
      retailers: retailers.map(r => ({
        name: r.retailer,
        price: r.price,
        currency: r.currency,
        timestamp: r.timestamp,
        isLowest: r.price === lowest,
      })),
      lowest: {
        price: lowest,
        retailer: lowestRetailer?.retailer,
      },
      highest,
      savings: highest - lowest,
    };
  },
});

// ============================================================================
// Notification Tools
// ============================================================================

const sendNotificationTool = tool({
  name: 'send_notification',
  description: 'Send a notification (email/SMS simulation)',
  inputSchema: z.object({
    type: z.enum(['email', 'sms', 'slack']),
    recipient: z.string(),
    subject: z.string(),
    message: z.string(),
    priority: z.enum(['low', 'normal', 'high']).default('normal'),
  }),
  function: async ({ type, recipient, subject, message, priority }) => {
    console.log(`\n📬 Notification (${type.toUpperCase()}):`);
    console.log(`   To: ${recipient}`);
    console.log(`   Subject: ${subject}`);
    console.log(`   Priority: ${priority}`);
    console.log(`   Message: ${message}\n`);
    
    return {
      success: true,
      type,
      recipient,
      messageId: `notif_${Date.now()}`,
      timestamp: new Date().toISOString(),
    };
  },
});

// ============================================================================
// Report Generation Tools
// ============================================================================

const generateReportTool = tool({
  name: 'generate_report',
  description: 'Generate a price comparison report',
  inputSchema: z.object({
    format: z.enum(['text', 'json', 'html']).default('text'),
    productName: z.string().optional(),
  }),
  function: async ({ format, productName }) => {
    const data = productName
      ? priceDatabase.filter(e => e.productName.toLowerCase().includes(productName.toLowerCase()))
      : priceDatabase;
    
    if (format === 'json') {
      return {
        format: 'json',
        report: JSON.stringify(data, null, 2),
      };
    }
    
    if (format === 'html') {
      const html = `
<!DOCTYPE html>
<html>
<head><title>Price Report</title></head>
<body>
  <h1>Price Monitoring Report</h1>
  <table border="1">
    <tr><th>Product</th><th>Retailer</th><th>Price</th><th>Date</th></tr>
    ${data.map(e => `
      <tr>
        <td>${e.productName}</td>
        <td>${e.retailer}</td>
        <td>${e.currency}${e.price}</td>
        <td>${new Date(e.timestamp).toLocaleString()}</td>
      </tr>
    `).join('')}
  </table>
</body>
</html>`;
      
      const reportPath = path.join(__dirname, 'data', 'report.html');
      fs.writeFileSync(reportPath, html);
      
      return {
        format: 'html',
        report: html,
        saved: reportPath,
      };
    }
    
    // Text format
    let report = '=== PRICE MONITORING REPORT ===\n\n';
    report += `Total entries: ${data.length}\n`;
    report += `Generated: ${new Date().toLocaleString()}\n\n`;
    
    for (const entry of data) {
      report += `Product: ${entry.productName}\n`;
      report += `Retailer: ${entry.retailer}\n`;
      report += `Price: ${entry.currency}${entry.price}\n`;
      report += `Date: ${new Date(entry.timestamp).toLocaleString()}\n`;
      report += `URL: ${entry.url}\n`;
      report += '---\n\n';
    }
    
    return {
      format: 'text',
      report,
    };
  },
});

// ============================================================================
// Workflow Orchestration
// ============================================================================

async function monitorProductPrice() {
  console.log('🛒 E-commerce Price Monitor Example\n');
  console.log('═'.repeat(70));
  console.log('Scenario: Monitor prices for a product across retailers');
  console.log('═'.repeat(70) + '\n');
  
  const agent = new UnifiedPolyAgent({
    llmProvider: new OllamaProvider({
      model: 'llama2',
      baseUrl: 'http://localhost:11434',
    }),
    mcpServers: [
      'http://localhost:3100', // Playwright server for web scraping
      'http://localhost:3201', // Our custom price monitoring tools
    ],
    verbose: true,
  });
  
  await agent.start();  // Discover tools from servers
  
  try {
    console.log('📊 Task: Monitor laptop prices on example.com\n');
    
    const result = await agent.runAsync(`
      I need you to help me monitor laptop prices:
      
      1. Navigate to https://example.com (pretend this is an e-commerce site)
      2. Extract the page title as if it were a product name
      3. Simulate that you found the price is $899
      4. Save this price data for "Dell XPS 13" at "Amazon" for $899
      5. Save another price for the same product at "BestBuy" for $949
      6. Compare the prices between the two retailers
      7. Generate a text report
      8. If there's a price difference of more than $30, send a notification
      
      Give me a summary of what you found and what actions were taken.
    `, 15);
    
    console.log('\n✅ Price monitoring completed!');
    console.log('📊 Result:', result);
    
  } catch (error: any) {
    console.error('❌ Error:', error.message);
  }
}

// ============================================================================
// Advanced Workflow: Multi-Product Monitoring
// ============================================================================

async function multiProductMonitoring() {
  console.log('\n\n' + '═'.repeat(70));
  console.log('🎯 Multi-Product Monitoring Workflow');
  console.log('═'.repeat(70) + '\n');
  
  const agent = new UnifiedPolyAgent({
    llmProvider: new OllamaProvider({
      model: 'llama2',
      baseUrl: 'http://localhost:11434',
    }),
    mcpServers: [
      'http://localhost:3100', // Playwright server
      'http://localhost:3201', // Price monitoring tools
    ],
    verbose: true,
  });
  
  await agent.start();  // Discover tools from servers
  
  try {
    console.log('📊 Task: Monitor multiple products and find best deals\n');
    
    const result = await agent.runAsync(`
      Monitor prices for multiple products:
      
      1. Save these laptop prices:
         - MacBook Air M2 at Apple Store: $1199
         - MacBook Air M2 at BestBuy: $1099
         - Dell XPS 13 at Amazon: $899
         - Dell XPS 13 at BestBuy: $949
         - ThinkPad X1 at Lenovo: $1299
         - ThinkPad X1 at Amazon: $1249
      
      2. Compare prices for each product
      3. Find which retailer has the lowest average prices
      4. Generate an HTML report
      5. Send a notification with the top 3 deals
      
      Provide a summary of the best deals found.
    `, 15);
    
    console.log('\n✅ Multi-product monitoring completed!');
    console.log('📊 Summary:', result);
    
  } catch (error: any) {
    console.error('❌ Error:', error.message);
  }
}

// ============================================================================
// Advanced Workflow: Price Drop Alert System
// ============================================================================

async function priceDropAlertSystem() {
  console.log('\n\n' + '═'.repeat(70));
  console.log('🔔 Price Drop Alert System');
  console.log('═'.repeat(70) + '\n');
  
  const agent = new UnifiedPolyAgent({
    llmProvider: new OllamaProvider({
      model: 'llama2',
      baseUrl: 'http://localhost:11434',
    }),
    mcpServers: [
      'http://localhost:3100',
      'http://localhost:3201', // Price monitoring tools
    ],
    verbose: true,
  });
  
  await agent.start();  // Discover tools from servers
  
  try {
    console.log('📊 Task: Check for price drops and send alerts\n');
    
    // Simulate some historical data
    await savePriceTool.function({
      productName: 'iPhone 15 Pro',
      retailer: 'Apple',
      price: 999,
      currency: 'USD',
      url: 'https://apple.com/iphone-15-pro',
    });
    
    await savePriceTool.function({
      productName: 'iPhone 15 Pro',
      retailer: 'Apple',
      price: 899, // Price dropped!
      currency: 'USD',
      url: 'https://apple.com/iphone-15-pro',
    });
    
    const result = await agent.runAsync(`
      Check the price history for iPhone 15 Pro:
      
      1. Get the price history for "iPhone 15 Pro"
      2. Check if the price has dropped
      3. Calculate the percentage savings
      4. If price dropped by more than 5%, send a HIGH priority notification
      5. Generate a report showing the price trend
      
      Tell me if there were any significant price drops.
    `, 15);
    
    console.log('\n✅ Price drop analysis completed!');
    console.log('📊 Result:', result);
    
  } catch (error: any) {
    console.error('❌ Error:', error.message);
  }
}

// ============================================================================
// Real Browser Scraping Example (if websites are available)
// ============================================================================

async function realBrowserScraping() {
  console.log('\n\n' + '═'.repeat(70));
  console.log('🌐 Real Browser Scraping Example');
  console.log('═'.repeat(70) + '\n');
  
  console.log('⚠️  This example would scrape real e-commerce sites.');
  console.log('    For demo purposes, we use example.com\n');
  
  const agent = new UnifiedPolyAgent({
    llmProvider: new OllamaProvider({
      model: 'llama2',
      baseUrl: 'http://localhost:11434',
    }),
    mcpServers: [
      'http://localhost:3100', // Playwright server
      'http://localhost:3201', // Price monitoring tools
    ],
    verbose: true,
  });
  
  await agent.start();  // Discover tools from servers
  
  try {
    const result = await agent.runAsync(`
      Perform a real web scraping workflow:
      
      1. Navigate to https://example.com
      2. Extract the page title
      3. Extract all links on the page
      4. Count how many links there are
      5. Take a screenshot
      6. Generate a report with your findings
      
      This simulates what you'd do on a real e-commerce site.
    `, 15);
    
    console.log('\n✅ Browser scraping completed!');
    console.log('📊 Result:', result);
    
  } catch (error: any) {
    console.error('❌ Error:', error.message);
  }
}

// ============================================================================
// Main Entry Point
// ============================================================================

async function main() {
  console.log('🚀 Advanced Workflow Examples - E-commerce Price Monitor\n');
  console.log('═'.repeat(70));
  console.log('This demonstrates enterprise-grade automation with PolyMCP:');
  console.log('- Web scraping with Playwright');
  console.log('- Data storage and retrieval');
  console.log('- Price comparison logic');
  console.log('- Automated notifications');
  console.log('- Report generation');
  console.log('═'.repeat(70) + '\n');
  
  // Start tools server once at the beginning
  await startToolsServer();
  await new Promise(resolve => setTimeout(resolve, 500));
  
  const args = process.argv.slice(2);
  
  if (args.includes('--help') || args.includes('-h')) {
    console.log('Usage: npm run example:advanced-workflow [options]\n');
    console.log('Options:');
    console.log('  --monitor          Single product monitoring');
    console.log('  --multi            Multi-product monitoring');
    console.log('  --alerts           Price drop alert system');
    console.log('  --scraping         Real browser scraping');
    console.log('  --all              Run all workflows (default)\n');
    await stopToolsServer();
    return;
  }
  
  try {
    if (args.includes('--monitor')) {
      await monitorProductPrice();
    } else if (args.includes('--multi')) {
      await multiProductMonitoring();
    } else if (args.includes('--alerts')) {
      await priceDropAlertSystem();
    } else if (args.includes('--scraping')) {
      await realBrowserScraping();
    } else {
      // Run all by default
      await monitorProductPrice();
      await multiProductMonitoring();
      await priceDropAlertSystem();
      await realBrowserScraping();
    }
    
    console.log('\n\n✅ All workflows completed!\n');
    console.log('📁 Check the ./examples/data/ directory for generated reports\n');
  } finally {
    // Always stop the tools server
    await stopToolsServer();
  }
}

main().catch(async (error) => {
  console.error(error);
  await stopToolsServer();
  process.exit(1);
});
