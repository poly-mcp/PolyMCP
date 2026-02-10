/**
 * Validation System
 * 
 * Goal achievement detection and validation:
 * - Validation modes (OFF, CONSERVATIVE, AGGRESSIVE)
 * - LLM-based goal validation
 * - Confidence scoring
 * - Early stopping when goals met
 * - Progress tracking
 */

/**
 * Validation mode enum
 */
export enum ValidationMode {
  /** No validation - always continue */
  OFF = 'OFF',
  
  /** Conservative validation - require high confidence before stopping */
  CONSERVATIVE = 'CONSERVATIVE',
  
  /** Aggressive validation - stop early if goal seems met */
  AGGRESSIVE = 'AGGRESSIVE',
}

/**
 * Validation result
 */
export interface ValidationResult {
  /** Whether goal is achieved */
  goalAchieved: boolean;
  
  /** Confidence score (0-100) */
  confidence: number;
  
  /** Explanation of validation */
  explanation: string;
  
  /** Remaining work (if goal not achieved) */
  remainingWork?: string[];
  
  /** Validation timestamp */
  timestamp: number;
}

/**
 * Goal Validator.
 * 
 * Validates whether a goal has been achieved.
 * Enables early stopping and intelligent completion detection.
 * 
 * Features:
 * - Three validation modes
 * - LLM-based validation
 * - Confidence scoring
 * - Progress tracking
 * - Multi-criteria validation
 * - Explanation generation
 * 
 * Example:
 * ```typescript
 * const validator = new GoalValidator(llmProvider);
 * 
 * // Validate goal achievement
 * const result = await validator.validateGoalAchieved(
 *   'Generate sales report for Q4',
 *   [
 *     { step: 'Fetched sales data', result: {...} },
 *     { step: 'Analyzed trends', result: {...} },
 *     { step: 'Created report', result: {...} }
 *   ],
 *   ValidationMode.CONSERVATIVE
 * );
 * 
 * if (result.goalAchieved && result.confidence >= 80) {
 *   console.log('Goal achieved!');
 *   console.log(result.explanation);
 * } else {
 *   console.log('Still work to do:', result.remainingWork);
 * }
 * ```
 */
export class GoalValidator {
  private llmProvider: any; // LLMProvider interface

  constructor(llmProvider: any) {
    this.llmProvider = llmProvider;
  }

  /**
   * Validate if goal has been achieved
   */
  async validateGoalAchieved(
    originalGoal: string,
    executedSteps: Array<{ step: string; result?: any }>,
    mode: ValidationMode = ValidationMode.CONSERVATIVE
  ): Promise<ValidationResult> {
    if (mode === ValidationMode.OFF) {
      // No validation - always return not achieved
      return {
        goalAchieved: false,
        confidence: 0,
        explanation: 'Validation disabled (OFF mode)',
        timestamp: Date.now(),
      };
    }

    // Build context of what's been done
    const stepsContext = executedSteps
      .map((s, i) => `${i + 1}. ${s.step}${s.result ? `\n   Result: ${JSON.stringify(s.result)}` : ''}`)
      .join('\n');

    // Validate using LLM
    const validation = await this.validateWithLLM(
      originalGoal,
      stepsContext,
      mode
    );

    return {
      ...validation,
      timestamp: Date.now(),
    };
  }

  /**
   * Validate using LLM
   */
  private async validateWithLLM(
    goal: string,
    stepsContext: string,
    mode: ValidationMode
  ): Promise<Omit<ValidationResult, 'timestamp'>> {
    const confidenceThreshold = mode === ValidationMode.CONSERVATIVE ? 90 : 70;

    const prompt = `You are a goal achievement validator. Determine if the following goal has been achieved based on the steps executed.

Original Goal: ${goal}

Steps Executed:
${stepsContext}

Analysis Requirements:
${mode === ValidationMode.CONSERVATIVE
  ? `- Be CONSERVATIVE: Only confirm goal achievement if you are highly confident (>=${confidenceThreshold}%)`
  : `- Be AGGRESSIVE: Confirm goal achievement if it appears mostly complete (>=${confidenceThreshold}%)`
}

Respond with ONLY valid JSON in this exact format:
{
  "goalAchieved": true or false,
  "confidence": <number 0-100>,
  "explanation": "<brief explanation of your assessment>",
  "remainingWork": ["<task 1>", "<task 2>"] or null if goal achieved
}

Respond ONLY with JSON, no additional text.`;

    try {
      let response = await this.llmProvider.generate(prompt);
      response = response.trim();

      // Extract JSON from markdown if present
      if (response.includes('```json')) {
        response = response.split('```json')[1].split('```')[0].trim();
      } else if (response.includes('```')) {
        response = response.split('```')[1].split('```')[0].trim();
      }

      const parsed = JSON.parse(response);

      return {
        goalAchieved: parsed.goalAchieved === true,
        confidence: Math.min(100, Math.max(0, parsed.confidence || 0)),
        explanation: parsed.explanation || 'No explanation provided',
        remainingWork: parsed.remainingWork || undefined,
      };
    } catch (error: any) {
      // Fallback on error
      return {
        goalAchieved: false,
        confidence: 0,
        explanation: `Validation failed: ${error.message}`,
        remainingWork: ['Unable to validate - retry validation'],
      };
    }
  }

  /**
   * Check if should stop based on validation result and mode
   */
  shouldStop(result: ValidationResult, mode: ValidationMode): boolean {
    if (mode === ValidationMode.OFF) {
      return false;
    }

    const confidenceThreshold = mode === ValidationMode.CONSERVATIVE ? 90 : 70;

    return result.goalAchieved && result.confidence >= confidenceThreshold;
  }

  /**
   * Validate partial progress
   */
  async validateProgress(
    originalGoal: string,
    executedSteps: Array<{ step: string; result?: any }>,
    totalStepsPlanned: number
  ): Promise<{
    progressPercentage: number;
    onTrack: boolean;
    assessment: string;
  }> {
    const stepsContext = executedSteps
      .map((s, i) => `${i + 1}. ${s.step}`)
      .join('\n');

    const prompt = `Assess progress toward a goal.

Goal: ${originalGoal}

Steps Completed (${executedSteps.length} of ${totalStepsPlanned} planned):
${stepsContext}

Provide assessment in JSON:
{
  "progressPercentage": <number 0-100>,
  "onTrack": true or false,
  "assessment": "<brief assessment>"
}

Respond ONLY with JSON.`;

    try {
      let response = await this.llmProvider.generate(prompt);
      response = response.trim();

      if (response.includes('```json')) {
        response = response.split('```json')[1].split('```')[0].trim();
      } else if (response.includes('```')) {
        response = response.split('```')[1].split('```')[0].trim();
      }

      const parsed = JSON.parse(response);

      return {
        progressPercentage: Math.min(100, Math.max(0, parsed.progressPercentage || 0)),
        onTrack: parsed.onTrack === true,
        assessment: parsed.assessment || 'Progress assessment unavailable',
      };
    } catch (error: any) {
      // Fallback
      const simpleProgress = (executedSteps.length / totalStepsPlanned) * 100;
      return {
        progressPercentage: simpleProgress,
        onTrack: true,
        assessment: `${executedSteps.length}/${totalStepsPlanned} steps completed`,
      };
    }
  }

  /**
   * Validate with multiple criteria
   */
  async validateMultiCriteria(
    criteria: Array<{ name: string; description: string; weight: number }>,
    executedSteps: Array<{ step: string; result?: any }>
  ): Promise<{
    overallScore: number;
    criteriaResults: Array<{ name: string; met: boolean; score: number }>;
    allCriteriaMet: boolean;
  }> {
    const stepsContext = executedSteps
      .map((s, i) => `${i + 1}. ${s.step}`)
      .join('\n');

    const criteriaContext = criteria
      .map(c => `- ${c.name} (weight: ${c.weight}): ${c.description}`)
      .join('\n');

    const prompt = `Evaluate if criteria are met based on executed steps.

Steps Executed:
${stepsContext}

Criteria to Evaluate:
${criteriaContext}

For each criterion, determine if it's met and score it 0-100.

Respond with JSON:
{
  "criteriaResults": [
    { "name": "<criterion name>", "met": true/false, "score": <0-100> },
    ...
  ]
}

Respond ONLY with JSON.`;

    try {
      let response = await this.llmProvider.generate(prompt);
      response = response.trim();

      if (response.includes('```json')) {
        response = response.split('```json')[1].split('```')[0].trim();
      } else if (response.includes('```')) {
        response = response.split('```')[1].split('```')[0].trim();
      }

      const parsed = JSON.parse(response);
      const results = parsed.criteriaResults || [];

      // Calculate weighted overall score
      let totalScore = 0;
      let totalWeight = 0;

      for (let i = 0; i < criteria.length && i < results.length; i++) {
        const criterion = criteria[i];
        const result = results[i];

        totalScore += result.score * criterion.weight;
        totalWeight += criterion.weight;
      }

      const overallScore = totalWeight > 0 ? totalScore / totalWeight : 0;
      const allCriteriaMet = results.every((r: any) => r.met === true);

      return {
        overallScore,
        criteriaResults: results,
        allCriteriaMet,
      };
    } catch (error: any) {
      // Fallback - assume not met
      return {
        overallScore: 0,
        criteriaResults: criteria.map(c => ({
          name: c.name,
          met: false,
          score: 0,
        })),
        allCriteriaMet: false,
      };
    }
  }

  /**
   * Simple validation without LLM (pattern matching)
   */
  validateSimple(
    goal: string,
    executedSteps: Array<{ step: string; result?: any }>,
    successPatterns: string[]
  ): ValidationResult {
    const stepsText = executedSteps
      .map(s => `${s.step} ${JSON.stringify(s.result || {})}`)
      .join(' ')
      .toLowerCase();

    const goalLower = goal.toLowerCase();

    // Check if success patterns are present
    let matchedPatterns = 0;
    for (const pattern of successPatterns) {
      if (stepsText.includes(pattern.toLowerCase()) || 
          goalLower.includes(pattern.toLowerCase())) {
        matchedPatterns++;
      }
    }

    const confidence = successPatterns.length > 0
      ? (matchedPatterns / successPatterns.length) * 100
      : 0;

    const goalAchieved = confidence >= 70;

    return {
      goalAchieved,
      confidence,
      explanation: goalAchieved
        ? `Goal appears achieved (${matchedPatterns}/${successPatterns.length} success patterns matched)`
        : `Goal not yet achieved (${matchedPatterns}/${successPatterns.length} success patterns matched)`,
      remainingWork: goalAchieved ? undefined : ['Continue working toward goal'],
      timestamp: Date.now(),
    };
  }
}

/**
 * Validation Factory for common configurations
 */
export class ValidationFactory {
  /**
   * Create conservative validator (high confidence required)
   */
  static createConservative(llmProvider: any): GoalValidator {
    return new GoalValidator(llmProvider);
  }

  /**
   * Create aggressive validator (lower confidence threshold)
   */
  static createAggressive(llmProvider: any): GoalValidator {
    return new GoalValidator(llmProvider);
  }

  /**
   * Create validator with custom LLM
   */
  static createCustom(llmProvider: any): GoalValidator {
    return new GoalValidator(llmProvider);
  }
}
