/**
 * LLM Provider Implementations
 * Production-ready providers for OpenAI, Anthropic, Ollama, and more.
 */

import OpenAI from 'openai';
import Anthropic from '@anthropic-ai/sdk';
import axios from 'axios';
import { LLMProvider, LLMConfig } from '../types';

/**
 * OpenAI GPT Provider
 */
export class OpenAIProvider implements LLMProvider {
  private client: any; // Using any to avoid TypeScript errors with openai SDK
  private model: string;
  private temperature: number;
  private maxTokens: number;

  constructor(config: LLMConfig = {}) {
    const apiKey = config.apiKey || process.env.OPENAI_API_KEY;
    if (!apiKey) {
      throw new Error('OpenAI API key not provided. Set OPENAI_API_KEY environment variable or pass apiKey in config');
    }

    this.client = new OpenAI({ apiKey });
    this.model = config.model || 'gpt-4';
    this.temperature = config.temperature ?? 0.7;
    this.maxTokens = config.maxTokens || 2000;
  }

  async generate(prompt: string, options: Record<string, any> = {}): Promise<string> {
    try {
      const response = await this.client.chat.completions.create({
        model: this.model,
        messages: [{ role: 'user', content: prompt }],
        temperature: options.temperature ?? this.temperature,
        max_tokens: options.maxTokens ?? this.maxTokens,
      });

      return response.choices[0]?.message?.content || '';
    } catch (error: any) {
      throw new Error(`OpenAI API call failed: ${error.message}`);
    }
  }
}

/**
 * Anthropic Claude Provider
 */
export class AnthropicProvider implements LLMProvider {
  private client: any; // Using any to avoid TypeScript errors with @anthropic-ai/sdk
  private model: string;
  private temperature: number;
  private maxTokens: number;

  constructor(config: LLMConfig = {}) {
    const apiKey = config.apiKey || process.env.ANTHROPIC_API_KEY;
    if (!apiKey) {
      throw new Error('Anthropic API key not provided. Set ANTHROPIC_API_KEY environment variable or pass apiKey in config');
    }

    this.client = new Anthropic({ apiKey });
    this.model = config.model || 'claude-3-5-sonnet-20241022';
    this.temperature = config.temperature ?? 0.7;
    this.maxTokens = config.maxTokens || 2000;
  }

  async generate(prompt: string, options: Record<string, any> = {}): Promise<string> {
    try {
      const response = await this.client.messages.create({
        model: this.model,
        messages: [{ role: 'user', content: prompt }],
        temperature: options.temperature ?? this.temperature,
        max_tokens: options.maxTokens ?? this.maxTokens,
      });

      const textContent = response.content.find((block: any) => block.type === 'text');
      return textContent && 'text' in textContent ? textContent.text : '';
    } catch (error: any) {
      throw new Error(`Anthropic API call failed: ${error.message}`);
    }
  }
}

/**
 * Ollama Provider for local models
 */
export class OllamaProvider implements LLMProvider {
  private baseUrl: string;
  private model: string;
  private temperature: number;

  constructor(config: LLMConfig = {}) {
    this.baseUrl = config.baseUrl || 'http://localhost:11434';
    this.model = config.model || 'llama2';
    this.temperature = config.temperature ?? 0.7;
  }

  async generate(prompt: string, options: Record<string, any> = {}): Promise<string> {
    try {
      const url = `${this.baseUrl}/api/generate`;
      
      const response = await axios.post(url, {
        model: this.model,
        prompt,
        stream: false,
        options: {
          temperature: options.temperature ?? this.temperature,
        },
      }, {
        timeout: 60000,
      });

      return response.data.response || '';
    } catch (error: any) {
      throw new Error(`Ollama API call failed: ${error.message}`);
    }
  }
}

/**
 * Kimi (Moonshot AI) Provider
 */
export class KimiProvider implements LLMProvider {
  private apiKey: string;
  private baseUrl: string;
  private model: string;
  private temperature: number;
  private maxTokens: number;

  constructor(config: LLMConfig = {}) {
    this.apiKey = config.apiKey || process.env.KIMI_API_KEY || '';
    if (!this.apiKey) {
      throw new Error('Kimi API key not provided. Set KIMI_API_KEY environment variable or pass apiKey in config');
    }

    this.baseUrl = 'https://api.moonshot.cn/v1';
    this.model = config.model || 'moonshot-v1-8k';
    this.temperature = config.temperature ?? 0.7;
    this.maxTokens = config.maxTokens || 2000;
  }

  async generate(prompt: string, options: Record<string, any> = {}): Promise<string> {
    try {
      const url = `${this.baseUrl}/chat/completions`;
      
      const response = await axios.post(url, {
        model: this.model,
        messages: [{ role: 'user', content: prompt }],
        temperature: options.temperature ?? this.temperature,
        max_tokens: options.maxTokens ?? this.maxTokens,
      }, {
        headers: {
          'Authorization': `Bearer ${this.apiKey}`,
          'Content-Type': 'application/json',
        },
        timeout: 30000,
      });

      return response.data.choices[0]?.message?.content || '';
    } catch (error: any) {
      throw new Error(`Kimi API call failed: ${error.message}`);
    }
  }
}

/**
 * DeepSeek Provider
 */
export class DeepSeekProvider implements LLMProvider {
  private apiKey: string;
  private baseUrl: string;
  private model: string;
  private temperature: number;
  private maxTokens: number;

  constructor(config: LLMConfig = {}) {
    this.apiKey = config.apiKey || process.env.DEEPSEEK_API_KEY || '';
    if (!this.apiKey) {
      throw new Error('DeepSeek API key not provided. Set DEEPSEEK_API_KEY environment variable or pass apiKey in config');
    }

    this.baseUrl = 'https://api.deepseek.com/v1';
    this.model = config.model || 'deepseek-chat';
    this.temperature = config.temperature ?? 0.7;
    this.maxTokens = config.maxTokens || 2000;
  }

  async generate(prompt: string, options: Record<string, any> = {}): Promise<string> {
    try {
      const url = `${this.baseUrl}/chat/completions`;
      
      const response = await axios.post(url, {
        model: this.model,
        messages: [{ role: 'user', content: prompt }],
        temperature: options.temperature ?? this.temperature,
        max_tokens: options.maxTokens ?? this.maxTokens,
      }, {
        headers: {
          'Authorization': `Bearer ${this.apiKey}`,
          'Content-Type': 'application/json',
        },
        timeout: 30000,
      });

      return response.data.choices[0]?.message?.content || '';
    } catch (error: any) {
      throw new Error(`DeepSeek API call failed: ${error.message}`);
    }
  }
}
