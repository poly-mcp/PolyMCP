/**
 * MCP Skill Loader - PRODUCTION IMPLEMENTATION
 * Loads and caches generated MCP skills for use in agents.
 * 
 * Features:
 * - Efficient file loading with caching
 * - Category filtering
 * - Token counting and limits
 * - Automatic refresh
 * - Context window management
 */

import * as fs from 'fs-extra';
import * as path from 'path';

/**
 * Loaded skill content
 */
export interface LoadedSkill {
  category: string;
  content: string;
  tokens: number;
  tools: string[];
  lastModified: Date;
}

/**
 * Skill metadata
 */
interface SkillMetadata {
  generated_at: string;
  version: string;
  stats: {
    total_tools: number;
    total_servers: number;
    total_categories: number;
    categories: Record<string, number>;
    generation_time_seconds: number;
    errors: string[];
  };
  token_estimates: Record<string, number>;
}

/**
 * Loader options
 */
export interface SkillLoaderOptions {
  skillsDir?: string;
  maxTokens?: number;
  cacheTimeout?: number; // milliseconds
  autoRefresh?: boolean;
  verbose?: boolean;
}

/**
 * Production-grade skill loader with caching and optimization.
 * 
 * Efficiently loads generated MCP skills, manages caching,
 * respects token limits, and provides automatic refresh.
 * 
 * Example:
 * ```typescript
 * const loader = new MCPSkillLoader({
 *   skillsDir: './mcp_skills',
 *   maxTokens: 50000,
 *   autoRefresh: true
 * });
 * 
 * // Load specific categories
 * const skills = await loader.loadSkills(['filesystem', 'api']);
 * 
 * // Get all available categories
 * const categories = await loader.getAvailableCategories();
 * 
 * // Load within token budget
 * const optimized = await loader.loadOptimized(['filesystem', 'api', 'web']);
 * ```
 */
export class MCPSkillLoader {
  private skillsDir: string;
  private maxTokens: number;
  private cacheTimeout: number;
  private autoRefresh: boolean;
  private verbose: boolean;
  
  // Cache
  private cache: Map<string, LoadedSkill> = new Map();
  private metadata: SkillMetadata | null = null;
  private lastCacheRefresh: number = 0;

  constructor(options: SkillLoaderOptions = {}) {
    this.skillsDir = options.skillsDir || './mcp_skills';
    this.maxTokens = options.maxTokens || 100000;
    this.cacheTimeout = options.cacheTimeout || 300000; // 5 minutes default
    this.autoRefresh = options.autoRefresh !== false;
    this.verbose = options.verbose || false;
  }

  /**
   * Get available skill categories
   */
  async getAvailableCategories(): Promise<string[]> {
    await this.ensureInitialized();
    
    if (!this.metadata) {
      return [];
    }

    return Object.keys(this.metadata.stats.categories);
  }

  /**
   * Load specific skills by category
   */
  async loadSkills(categories: string[]): Promise<LoadedSkill[]> {
    await this.ensureInitialized();
    
    const skills: LoadedSkill[] = [];
    let totalTokens = 0;

    for (const category of categories) {
      const skill = await this.loadSkill(category);
      
      if (skill) {
        // Check token limit
        if (totalTokens + skill.tokens <= this.maxTokens) {
          skills.push(skill);
          totalTokens += skill.tokens;
        } else {
          if (this.verbose) {
            console.log(`⚠️  Skipping ${category}: would exceed token limit`);
          }
          break;
        }
      }
    }

    if (this.verbose) {
      console.log(`✅ Loaded ${skills.length} skills (${totalTokens} tokens)`);
    }

    return skills;
  }

  /**
   * Load skills optimized for token budget
   * Prioritizes by tool count and relevance
   */
  async loadOptimized(
    preferredCategories?: string[]
  ): Promise<LoadedSkill[]> {
    await this.ensureInitialized();
    
    const available = await this.getAvailableCategories();
    
    // Sort categories by preference and tool count
    const sorted = available.sort((a, b) => {
      // Preferred categories first
      const aPreferred = preferredCategories?.includes(a) ? 1 : 0;
      const bPreferred = preferredCategories?.includes(b) ? 1 : 0;
      
      if (aPreferred !== bPreferred) {
        return bPreferred - aPreferred;
      }
      
      // Then by tool count
      const aCount = this.metadata?.stats.categories[a] || 0;
      const bCount = this.metadata?.stats.categories[b] || 0;
      
      return bCount - aCount;
    });

    // Load skills until token limit
    const skills: LoadedSkill[] = [];
    let totalTokens = 0;

    for (const category of sorted) {
      const skill = await this.loadSkill(category);
      
      if (skill) {
        if (totalTokens + skill.tokens <= this.maxTokens) {
          skills.push(skill);
          totalTokens += skill.tokens;
        } else {
          break;
        }
      }
    }

    if (this.verbose) {
      console.log(`✅ Optimized load: ${skills.length} skills (${totalTokens} tokens)`);
    }

    return skills;
  }

  /**
   * Load all skills (respecting token limit)
   */
  async loadAll(): Promise<LoadedSkill[]> {
    const categories = await this.getAvailableCategories();
    return this.loadSkills(categories);
  }

  /**
   * Load a single skill by category
   */
  async loadSkill(category: string): Promise<LoadedSkill | null> {
    // Check cache
    if (this.shouldRefreshCache()) {
      await this.refreshCache();
    }

    const cached = this.cache.get(category);
    if (cached) {
      return cached;
    }

    // Load from file
    const skillPath = path.join(this.skillsDir, `${category}.md`);
    
    if (!(await fs.pathExists(skillPath))) {
      if (this.verbose) {
        console.log(`⚠️  Skill not found: ${category}`);
      }
      return null;
    }

    try {
      const content = await fs.readFile(skillPath, 'utf-8');
      const stats = await fs.stat(skillPath);
      const tools = this.extractToolNames(content);
      
      const skill: LoadedSkill = {
        category,
        content,
        tokens: this.estimateTokens(content),
        tools,
        lastModified: stats.mtime,
      };

      // Cache it
      this.cache.set(category, skill);

      return skill;

    } catch (error: any) {
      if (this.verbose) {
        console.error(`❌ Error loading ${category}: ${error.message}`);
      }
      return null;
    }
  }

  /**
   * Get skill metadata (total tools, categories, etc.)
   */
  async getMetadata(): Promise<SkillMetadata | null> {
    await this.ensureInitialized();
    return this.metadata;
  }

  /**
   * Get total token count for all skills
   */
  async getTotalTokens(categories?: string[]): Promise<number> {
    await this.ensureInitialized();
    
    if (!this.metadata) {
      return 0;
    }

    if (categories) {
      let total = 0;
      for (const category of categories) {
        total += this.metadata.token_estimates[category] || 0;
      }
      return total;
    }

    return this.metadata.token_estimates.total || 0;
  }

  /**
   * Format skills for agent context
   */
  formatForContext(skills: LoadedSkill[]): string {
    let context = '# Available MCP Skills\n\n';
    
    context += `Loaded ${skills.length} skill categories with the following tools:\n\n`;

    for (const skill of skills) {
      context += `## ${skill.category.charAt(0).toUpperCase() + skill.category.slice(1)}\n\n`;
      context += `**Tools**: ${skill.tools.join(', ')}\n\n`;
      context += skill.content + '\n\n';
      context += '---\n\n';
    }

    return context;
  }

  /**
   * Clear cache
   */
  clearCache(): void {
    this.cache.clear();
    this.metadata = null;
    this.lastCacheRefresh = 0;
    
    if (this.verbose) {
      console.log('🗑️  Cache cleared');
    }
  }

  /**
   * Refresh cache manually
   */
  async refreshCache(): Promise<void> {
    this.cache.clear();
    this.lastCacheRefresh = Date.now();
    
    // Reload metadata
    await this.loadMetadata();
    
    if (this.verbose) {
      console.log('🔄 Cache refreshed');
    }
  }

  /**
   * Ensure loader is initialized
   */
  private async ensureInitialized(): Promise<void> {
    if (!this.metadata) {
      await this.loadMetadata();
    }

    if (this.autoRefresh && this.shouldRefreshCache()) {
      await this.refreshCache();
    }
  }

  /**
   * Load metadata file
   */
  private async loadMetadata(): Promise<void> {
    const metadataPath = path.join(this.skillsDir, '_metadata.json');
    
    if (!(await fs.pathExists(metadataPath))) {
      if (this.verbose) {
        console.log('⚠️  No metadata file found. Generate skills first.');
      }
      return;
    }

    try {
      this.metadata = await fs.readJson(metadataPath);
      
      if (this.verbose) {
        console.log(`📊 Loaded metadata: ${this.metadata?.stats.total_tools} tools in ${this.metadata?.stats.total_categories} categories`);
      }
    } catch (error: any) {
      if (this.verbose) {
        console.error(`❌ Error loading metadata: ${error.message}`);
      }
    }
  }

  /**
   * Check if cache should be refreshed
   */
  private shouldRefreshCache(): boolean {
    if (!this.autoRefresh) {
      return false;
    }

    const elapsed = Date.now() - this.lastCacheRefresh;
    return elapsed > this.cacheTimeout;
  }

  /**
   * Estimate tokens for content
   */
  private estimateTokens(content: string): number {
    // Rough estimation: ~4 characters per token
    return Math.floor(content.length / 4);
  }

  /**
   * Extract tool names from skill content
   */
  private extractToolNames(content: string): string[] {
    const tools: string[] = [];
    const regex = /^### (.+)$/gm;
    let match;

    while ((match = regex.exec(content)) !== null) {
      tools.push(match[1].trim());
    }

    return tools;
  }

  /**
   * Get skill statistics
   */
  async getStats(): Promise<{
    totalSkills: number;
    totalTools: number;
    totalTokens: number;
    cacheSize: number;
    cacheAge: number;
  }> {
    await this.ensureInitialized();

    return {
      totalSkills: this.metadata?.stats.total_categories || 0,
      totalTools: this.metadata?.stats.total_tools || 0,
      totalTokens: this.metadata?.token_estimates.total || 0,
      cacheSize: this.cache.size,
      cacheAge: Date.now() - this.lastCacheRefresh,
    };
  }
}

/**
 * Helper function to load skills with default options
 */
export async function loadSkills(
  categories: string[],
  options?: SkillLoaderOptions
): Promise<LoadedSkill[]> {
  const loader = new MCPSkillLoader(options);
  return loader.loadSkills(categories);
}

/**
 * Helper function to load all available skills
 */
export async function loadAllSkills(
  options?: SkillLoaderOptions
): Promise<LoadedSkill[]> {
  const loader = new MCPSkillLoader(options);
  return loader.loadAll();
}
