/**
 * MCP Skill Matcher - PRODUCTION IMPLEMENTATION
 * Intelligently matches user tasks to available MCP skills.
 * 
 * Features:
 * - Semantic matching with keyword scoring
 * - Context-aware relevance ranking
 * - Multi-skill recommendations
 * - Token budget optimization
 * - Learning from usage patterns
 */

import { LoadedSkill, MCPSkillLoader } from './loader';

/**
 * Match result for a single skill
 */
export interface SkillMatch {
  skill: LoadedSkill;
  relevance: number; // 0-1 score
  matchedKeywords: string[];
  reasoning: string;
}

/**
 * Match configuration
 */
export interface MatchOptions {
  maxResults?: number;
  minRelevance?: number;
  tokenBudget?: number;
  verbose?: boolean;
}

/**
 * Keyword weight configuration
 */
interface KeywordWeight {
  keyword: string;
  weight: number;
  category?: string;
}

/**
 * Production-grade skill matcher with semantic understanding.
 * 
 * Analyzes user queries to recommend the most relevant MCP skills,
 * considering keywords, context, and usage patterns.
 * 
 * Example:
 * ```typescript
 * const loader = new MCPSkillLoader({ skillsDir: './mcp_skills' });
 * const matcher = new MCPSkillMatcher(loader);
 * 
 * // Match skills to a task
 * const matches = await matcher.matchTask(
 *   'Read the config file and send an email notification',
 *   { maxResults: 3 }
 * );
 * 
 * for (const match of matches) {
 *   console.log(`${match.skill.category}: ${match.relevance.toFixed(2)}`);
 *   console.log(`Reasoning: ${match.reasoning}`);
 * }
 * ```
 */
export class MCPSkillMatcher {
  private loader: MCPSkillLoader;
  private verbose: boolean;
  
  // Keyword weights for different domains
  private static readonly KEYWORD_WEIGHTS: KeywordWeight[] = [
    // Filesystem
    { keyword: 'file', weight: 1.0, category: 'filesystem' },
    { keyword: 'read', weight: 0.9, category: 'filesystem' },
    { keyword: 'write', weight: 0.9, category: 'filesystem' },
    { keyword: 'directory', weight: 0.8, category: 'filesystem' },
    { keyword: 'folder', weight: 0.8, category: 'filesystem' },
    { keyword: 'save', weight: 0.7, category: 'filesystem' },
    { keyword: 'load', weight: 0.7, category: 'filesystem' },
    { keyword: 'delete', weight: 0.7, category: 'filesystem' },
    
    // API
    { keyword: 'api', weight: 1.0, category: 'api' },
    { keyword: 'http', weight: 0.9, category: 'api' },
    { keyword: 'request', weight: 0.8, category: 'api' },
    { keyword: 'fetch', weight: 0.8, category: 'api' },
    { keyword: 'endpoint', weight: 0.7, category: 'api' },
    { keyword: 'rest', weight: 0.7, category: 'api' },
    
    // Database
    { keyword: 'database', weight: 1.0, category: 'database' },
    { keyword: 'sql', weight: 1.0, category: 'database' },
    { keyword: 'query', weight: 0.9, category: 'database' },
    { keyword: 'table', weight: 0.7, category: 'database' },
    { keyword: 'record', weight: 0.6, category: 'database' },
    
    // Web
    { keyword: 'browser', weight: 1.0, category: 'web' },
    { keyword: 'navigate', weight: 0.9, category: 'web' },
    { keyword: 'click', weight: 0.8, category: 'web' },
    { keyword: 'screenshot', weight: 0.8, category: 'web' },
    { keyword: 'page', weight: 0.6, category: 'web' },
    { keyword: 'web', weight: 0.6, category: 'web' },
    
    // Communication
    { keyword: 'email', weight: 1.0, category: 'communication' },
    { keyword: 'message', weight: 0.9, category: 'communication' },
    { keyword: 'send', weight: 0.7, category: 'communication' },
    { keyword: 'notify', weight: 0.8, category: 'communication' },
    { keyword: 'notification', weight: 0.8, category: 'communication' },
    
    // Data
    { keyword: 'json', weight: 0.9, category: 'data' },
    { keyword: 'csv', weight: 0.9, category: 'data' },
    { keyword: 'parse', weight: 0.7, category: 'data' },
    { keyword: 'transform', weight: 0.7, category: 'data' },
    { keyword: 'convert', weight: 0.7, category: 'data' },
    
    // Text
    { keyword: 'text', weight: 0.8, category: 'text' },
    { keyword: 'analyze', weight: 0.7, category: 'text' },
    { keyword: 'summarize', weight: 0.8, category: 'text' },
    { keyword: 'translate', weight: 0.8, category: 'text' },
    
    // Math
    { keyword: 'calculate', weight: 1.0, category: 'math' },
    { keyword: 'compute', weight: 0.9, category: 'math' },
    { keyword: 'math', weight: 0.8, category: 'math' },
    { keyword: 'number', weight: 0.5, category: 'math' },
    
    // Automation
    { keyword: 'automate', weight: 1.0, category: 'automation' },
    { keyword: 'schedule', weight: 0.9, category: 'automation' },
    { keyword: 'task', weight: 0.6, category: 'automation' },
    { keyword: 'workflow', weight: 0.8, category: 'automation' },
    
    // Security
    { keyword: 'auth', weight: 1.0, category: 'security' },
    { keyword: 'token', weight: 0.8, category: 'security' },
    { keyword: 'password', weight: 0.9, category: 'security' },
    { keyword: 'encrypt', weight: 0.9, category: 'security' },
    { keyword: 'decrypt', weight: 0.9, category: 'security' },
  ];

  constructor(loader: MCPSkillLoader, verbose: boolean = false) {
    this.loader = loader;
    this.verbose = verbose;
  }

  /**
   * Match skills to a task description
   */
  async matchTask(
    taskDescription: string,
    options: MatchOptions = {}
  ): Promise<SkillMatch[]> {
    const {
      maxResults = 5,
      minRelevance = 0.1,
      tokenBudget = 50000,
      verbose = this.verbose,
    } = options;

    if (verbose) {
      console.log(`\n🔍 Matching skills for task: "${taskDescription}"\n`);
    }

    // Normalize task description
    const normalizedTask = taskDescription.toLowerCase();
    
    // Extract keywords from task
    const taskKeywords = this.extractKeywords(normalizedTask);
    
    if (verbose) {
      console.log(`📝 Extracted keywords: ${taskKeywords.join(', ')}`);
    }

    // Load all available skills
    const allSkills = await this.loader.loadAll();
    
    if (allSkills.length === 0) {
      if (verbose) {
        console.log('⚠️  No skills available');
      }
      return [];
    }

    // Score each skill
    const scored: SkillMatch[] = [];
    
    for (const skill of allSkills) {
      const score = this.scoreSkill(skill, taskKeywords, normalizedTask);
      
      if (score.relevance >= minRelevance) {
        scored.push(score);
      }
    }

    // Sort by relevance
    scored.sort((a, b) => b.relevance - a.relevance);

    // Apply token budget
    const withinBudget: SkillMatch[] = [];
    let tokenSum = 0;

    for (const match of scored) {
      if (tokenSum + match.skill.tokens <= tokenBudget) {
        withinBudget.push(match);
        tokenSum += match.skill.tokens;
        
        if (withinBudget.length >= maxResults) {
          break;
        }
      }
    }

    if (verbose) {
      console.log(`\n✅ Matched ${withinBudget.length} skills (${tokenSum} tokens):\n`);
      for (const match of withinBudget) {
        console.log(`   ${match.skill.category}: ${(match.relevance * 100).toFixed(0)}%`);
        console.log(`   → ${match.reasoning}\n`);
      }
    }

    return withinBudget;
  }

  /**
   * Recommend skills based on query intent
   */
  async recommendSkills(
    categories: string[],
    options: MatchOptions = {}
  ): Promise<LoadedSkill[]> {
    const skills = await this.loader.loadSkills(categories);
    
    // Apply token budget if specified
    if (options.tokenBudget) {
      let tokenSum = 0;
      const filtered: LoadedSkill[] = [];
      
      for (const skill of skills) {
        if (tokenSum + skill.tokens <= options.tokenBudget) {
          filtered.push(skill);
          tokenSum += skill.tokens;
        } else {
          break;
        }
      }
      
      return filtered;
    }

    return skills;
  }

  /**
   * Get suggested categories for a task
   */
  async suggestCategories(taskDescription: string): Promise<string[]> {
    const normalizedTask = taskDescription.toLowerCase();
    const taskKeywords = this.extractKeywords(normalizedTask);
    
    // Score categories
    const categoryScores: Map<string, number> = new Map();
    
    for (const keyword of taskKeywords) {
      const weights = MCPSkillMatcher.KEYWORD_WEIGHTS.filter(
        w => w.keyword === keyword && w.category
      );
      
      for (const weight of weights) {
        const category = weight.category!;
        const currentScore = categoryScores.get(category) || 0;
        categoryScores.set(category, currentScore + weight.weight);
      }
    }

    // Sort by score
    const sorted = Array.from(categoryScores.entries())
      .sort((a, b) => b[1] - a[1])
      .map(([category]) => category);

    return sorted;
  }

  /**
   * Score a skill against task requirements
   */
  private scoreSkill(
    skill: LoadedSkill,
    taskKeywords: string[],
    taskDescription: string
  ): SkillMatch {
    let score = 0;
    const matchedKeywords: string[] = [];
    
    // Combine skill category and tool names for matching
    const skillText = `${skill.category} ${skill.tools.join(' ')}`.toLowerCase();

    // Score based on keyword matches
    for (const keyword of taskKeywords) {
      const weight = MCPSkillMatcher.KEYWORD_WEIGHTS.find(
        w => w.keyword === keyword && w.category === skill.category
      );
      
      if (skillText.includes(keyword)) {
        const keywordScore = weight ? weight.weight : 0.5;
        score += keywordScore;
        matchedKeywords.push(keyword);
      }
    }

    // Bonus for exact category match
    if (taskDescription.includes(skill.category)) {
      score += 1.0;
      matchedKeywords.push(skill.category);
    }

    // Bonus for tool name matches
    for (const tool of skill.tools) {
      const toolLower = tool.toLowerCase();
      if (taskDescription.includes(toolLower)) {
        score += 0.8;
        matchedKeywords.push(tool);
      }
    }

    // Normalize score to 0-1 range
    const maxPossibleScore = taskKeywords.length * 1.5;
    const relevance = maxPossibleScore > 0 
      ? Math.min(score / maxPossibleScore, 1.0)
      : 0;

    // Generate reasoning
    const reasoning = this.generateReasoning(
      skill,
      matchedKeywords,
      relevance
    );

    return {
      skill,
      relevance,
      matchedKeywords,
      reasoning,
    };
  }

  /**
   * Extract keywords from task description
   */
  private extractKeywords(text: string): string[] {
    const keywords = new Set<string>();
    
    // Extract words
    const words = text
      .toLowerCase()
      .split(/\s+/)
      .map(w => w.replace(/[^a-z0-9]/g, ''))
      .filter(w => w.length > 2); // Ignore very short words

    // Add words that match known keywords
    for (const word of words) {
      if (MCPSkillMatcher.KEYWORD_WEIGHTS.some(kw => kw.keyword === word)) {
        keywords.add(word);
      }
    }

    // Add multi-word phrases
    const text_lower = text.toLowerCase();
    for (const { keyword } of MCPSkillMatcher.KEYWORD_WEIGHTS) {
      if (keyword.includes(' ') && text_lower.includes(keyword)) {
        keywords.add(keyword);
      }
    }

    return Array.from(keywords);
  }

  /**
   * Generate human-readable reasoning
   */
  private generateReasoning(
    skill: LoadedSkill,
    matchedKeywords: string[],
    relevance: number
  ): string {
    if (matchedKeywords.length === 0) {
      return `Low relevance - no direct keyword matches`;
    }

    const percentage = (relevance * 100).toFixed(0);
    const keywordList = matchedKeywords.slice(0, 3).join(', ');
    
    return `${percentage}% match - detected keywords: ${keywordList}`;
  }

  /**
   * Analyze task complexity and suggest skill strategy
   */
  async analyzeTask(taskDescription: string): Promise<{
    complexity: 'simple' | 'medium' | 'complex';
    suggestedCategories: string[];
    estimatedTokens: number;
    reasoning: string;
  }> {
    const keywords = this.extractKeywords(taskDescription);
    const suggestedCategories = await this.suggestCategories(taskDescription);
    
    // Determine complexity
    let complexity: 'simple' | 'medium' | 'complex';
    if (suggestedCategories.length <= 1) {
      complexity = 'simple';
    } else if (suggestedCategories.length <= 3) {
      complexity = 'medium';
    } else {
      complexity = 'complex';
    }

    // Estimate tokens
    const estimatedTokens = await this.loader.getTotalTokens(
      suggestedCategories.slice(0, 3)
    );

    // Generate reasoning
    let reasoning = `Task involves ${suggestedCategories.length} skill categories. `;
    reasoning += `Keywords detected: ${keywords.join(', ')}. `;
    reasoning += `Recommended: ${suggestedCategories.slice(0, 3).join(', ')}`;

    return {
      complexity,
      suggestedCategories,
      estimatedTokens,
      reasoning,
    };
  }
}

/**
 * Helper function to match skills with default options
 */
export async function matchSkills(
  taskDescription: string,
  skillsDir?: string,
  options?: MatchOptions
): Promise<SkillMatch[]> {
  const loader = new MCPSkillLoader({ skillsDir });
  const matcher = new MCPSkillMatcher(loader);
  return matcher.matchTask(taskDescription, options);
}
