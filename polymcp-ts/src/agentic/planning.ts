/**
 * Planning System
 * 
 * Multi-step task planning for complex operations:
 * - Planning modes (OFF, SOFT, STRICT)
 * - Step-by-step plan generation
 * - Plan validation
 * - Re-planning on failures
 * - Plan execution tracking
 */

/**
 * Planning mode enum
 */
export enum PlanningMode {
  /** No planning - direct execution */
  OFF = 'OFF',
  
  /** Soft planning - create plan but allow deviations */
  SOFT = 'SOFT',
  
  /** Strict planning - must follow plan exactly */
  STRICT = 'STRICT',
}

/**
 * Single step in a plan
 */
export interface PlanStep {
  /** Step number (1-indexed) */
  stepNumber: number;
  
  /** Description of what to do */
  description: string;
  
  /** Tool to use (if applicable) */
  toolName?: string;
  
  /** Expected inputs/parameters */
  inputs?: Record<string, any>;
  
  /** Expected outputs */
  expectedOutputs?: string[];
  
  /** Dependencies (step numbers that must complete first) */
  dependencies?: number[];
  
  /** Whether this step is completed */
  completed: boolean;
  
  /** Result of execution (if completed) */
  result?: any;
  
  /** Error if step failed */
  error?: string;
}

/**
 * Complete plan
 */
export interface Plan {
  /** Unique plan ID */
  id: string;
  
  /** Original user goal/request */
  goal: string;
  
  /** List of steps */
  steps: PlanStep[];
  
  /** Planning mode used */
  mode: PlanningMode;
  
  /** When plan was created */
  createdAt: number;
  
  /** Current step being executed (1-indexed, 0 = not started) */
  currentStep: number;
  
  /** Whether plan is complete */
  completed: boolean;
  
  /** Whether plan was successful */
  success?: boolean;
  
  /** Overall result */
  result?: any;
}

/**
 * Planner.
 * 
 * Generates and manages multi-step execution plans.
 * Enables complex task decomposition and systematic execution.
 * 
 * Features:
 * - Three planning modes (OFF, SOFT, STRICT)
 * - LLM-based plan generation
 * - Step dependency tracking
 * - Plan validation
 * - Re-planning on failures
 * - Execution tracking
 * - Plan export/import
 * 
 * Example:
 * ```typescript
 * const planner = new Planner(llmProvider);
 * 
 * // Generate plan
 * const plan = await planner.createPlan(
 *   'Analyze sales data and generate report',
 *   availableTools,
 *   PlanningMode.SOFT
 * );
 * 
 * // Execute plan
 * for (const step of plan.steps) {
 *   console.log(`Step ${step.stepNumber}: ${step.description}`);
 *   
 *   try {
 *     const result = await executeStep(step);
 *     planner.markStepCompleted(plan, step.stepNumber, result);
 *   } catch (error) {
 *     planner.markStepFailed(plan, step.stepNumber, error.message);
 *     
 *     // Re-plan if needed
 *     if (plan.mode === PlanningMode.SOFT) {
 *       const newPlan = await planner.replan(plan, availableTools);
 *       // Continue with new plan
 *     }
 *   }
 * }
 * ```
 */
export class Planner {
  private llmProvider: any; // LLMProvider interface

  constructor(llmProvider: any) {
    this.llmProvider = llmProvider;
  }

  /**
   * Create a plan for a goal
   */
  async createPlan(
    goal: string,
    availableTools: any[],
    mode: PlanningMode = PlanningMode.SOFT
  ): Promise<Plan> {
    if (mode === PlanningMode.OFF) {
      // No planning mode - return empty plan
      return {
        id: this.generatePlanId(),
        goal,
        steps: [],
        mode,
        createdAt: Date.now(),
        currentStep: 0,
        completed: false,
      };
    }

    // Generate plan using LLM
    const planText = await this.generatePlanWithLLM(goal, availableTools, mode);
    
    // Parse plan into steps
    const steps = this.parsePlan(planText);

    return {
      id: this.generatePlanId(),
      goal,
      steps,
      mode,
      createdAt: Date.now(),
      currentStep: 0,
      completed: false,
    };
  }

  /**
   * Generate plan using LLM
   */
  private async generatePlanWithLLM(
    goal: string,
    availableTools: any[],
    mode: PlanningMode
  ): Promise<string> {
    const toolsDescription = availableTools
      .map(tool => `- ${tool.name}: ${tool.description}`)
      .join('\n');

    const modeGuidance = mode === PlanningMode.STRICT
      ? 'Create a DETAILED, STRICT plan. Every step must be clearly defined and must use specific tools.'
      : 'Create a FLEXIBLE plan. Steps can be adjusted during execution if needed.';

    const prompt = `You are a task planning assistant. Break down the following goal into clear, executable steps.

Goal: ${goal}

Available tools:
${toolsDescription}

${modeGuidance}

Create a step-by-step plan. For each step, specify:
1. Step number
2. Description of what to do
3. Tool to use (if applicable)
4. Dependencies (which steps must complete first)

Format your response as a numbered list of steps. Use this exact format:

STEP 1: [description]
TOOL: [tool_name or "none"]
DEPENDENCIES: [comma-separated step numbers or "none"]

STEP 2: [description]
TOOL: [tool_name or "none"]
DEPENDENCIES: [comma-separated step numbers or "none"]

... and so on.

Provide ONLY the numbered steps, no additional explanation.`;

    const response = await this.llmProvider.generate(prompt);
    return response.trim();
  }

  /**
   * Parse plan text into steps
   */
  parsePlan(planText: string): PlanStep[] {
    const steps: PlanStep[] = [];
    const stepRegex = /STEP (\d+):\s*(.+?)(?:\nTOOL:\s*(.+?))?(?:\nDEPENDENCIES:\s*(.+?))?(?=\n\nSTEP|\n*$)/gs;

    let match;
    while ((match = stepRegex.exec(planText)) !== null) {
      const stepNumber = parseInt(match[1]);
      const description = match[2].trim();
      const toolName = match[3]?.trim().toLowerCase() !== 'none' ? match[3]?.trim() : undefined;
      const depsStr = match[4]?.trim();

      const dependencies: number[] = [];
      if (depsStr && depsStr.toLowerCase() !== 'none') {
        const depParts = depsStr.split(',').map(s => s.trim());
        for (const dep of depParts) {
          const depNum = parseInt(dep);
          if (!isNaN(depNum)) {
            dependencies.push(depNum);
          }
        }
      }

      steps.push({
        stepNumber,
        description,
        toolName,
        dependencies: dependencies.length > 0 ? dependencies : undefined,
        completed: false,
      });
    }

    // Sort by step number
    steps.sort((a, b) => a.stepNumber - b.stepNumber);

    return steps;
  }

  /**
   * Validate plan
   */
  validatePlan(plan: Plan): { valid: boolean; errors: string[] } {
    const errors: string[] = [];

    if (plan.steps.length === 0) {
      errors.push('Plan has no steps');
    }

    // Check step numbers are sequential
    for (let i = 0; i < plan.steps.length; i++) {
      if (plan.steps[i].stepNumber !== i + 1) {
        errors.push(`Step numbers not sequential at index ${i}`);
      }
    }

    // Check dependencies are valid
    for (const step of plan.steps) {
      if (step.dependencies) {
        for (const dep of step.dependencies) {
          if (dep >= step.stepNumber) {
            errors.push(`Step ${step.stepNumber} depends on future step ${dep}`);
          }
          if (!plan.steps.find(s => s.stepNumber === dep)) {
            errors.push(`Step ${step.stepNumber} depends on non-existent step ${dep}`);
          }
        }
      }
    }

    return {
      valid: errors.length === 0,
      errors,
    };
  }

  /**
   * Get next step to execute
   */
  getNextStep(plan: Plan): PlanStep | null {
    // Find first incomplete step whose dependencies are met
    for (const step of plan.steps) {
      if (step.completed) continue;

      // Check dependencies
      if (step.dependencies) {
        const allDepsMet = step.dependencies.every(dep => {
          const depStep = plan.steps.find(s => s.stepNumber === dep);
          return depStep?.completed === true;
        });

        if (!allDepsMet) continue;
      }

      return step;
    }

    return null;
  }

  /**
   * Mark step as completed
   */
  markStepCompleted(plan: Plan, stepNumber: number, result?: any): void {
    const step = plan.steps.find(s => s.stepNumber === stepNumber);
    if (!step) return;

    step.completed = true;
    step.result = result;
    plan.currentStep = stepNumber;

    // Check if all steps completed
    if (plan.steps.every(s => s.completed)) {
      plan.completed = true;
      plan.success = plan.steps.every(s => !s.error);
    }
  }

  /**
   * Mark step as failed
   */
  markStepFailed(plan: Plan, stepNumber: number, error: string): void {
    const step = plan.steps.find(s => s.stepNumber === stepNumber);
    if (!step) return;

    step.completed = true;
    step.error = error;
    plan.currentStep = stepNumber;

    // In strict mode, failure means plan fails
    if (plan.mode === PlanningMode.STRICT) {
      plan.completed = true;
      plan.success = false;
    }
  }

  /**
   * Re-plan from current state
   */
  async replan(
    originalPlan: Plan,
    availableTools: any[]
  ): Promise<Plan> {
    // Get completed steps
    const completedSteps = originalPlan.steps.filter(s => s.completed && !s.error);
    const failedStep = originalPlan.steps.find(s => s.error);

    // Create updated goal incorporating what's been done
    const completedDesc = completedSteps
      .map(s => `✓ Step ${s.stepNumber}: ${s.description}`)
      .join('\n');

    const failedDesc = failedStep
      ? `✗ Step ${failedStep.stepNumber} failed: ${failedStep.description} (${failedStep.error})`
      : '';

    const updatedGoal = `Original goal: ${originalPlan.goal}

Completed steps:
${completedDesc}

${failedDesc ? `Failed step:\n${failedDesc}\n\n` : ''}
Continue from this point to achieve the original goal.`;

    // Create new plan
    return await this.createPlan(updatedGoal, availableTools, originalPlan.mode);
  }

  /**
   * Get plan progress (0-100)
   */
  getProgress(plan: Plan): number {
    if (plan.steps.length === 0) return 0;

    const completed = plan.steps.filter(s => s.completed).length;
    return (completed / plan.steps.length) * 100;
  }

  /**
   * Get plan summary
   */
  getSummary(plan: Plan): {
    id: string;
    goal: string;
    totalSteps: number;
    completedSteps: number;
    failedSteps: number;
    progress: number;
    currentStepNumber: number;
    completed: boolean;
    success?: boolean;
  } {
    const completedSteps = plan.steps.filter(s => s.completed && !s.error).length;
    const failedSteps = plan.steps.filter(s => s.error).length;

    return {
      id: plan.id,
      goal: plan.goal,
      totalSteps: plan.steps.length,
      completedSteps,
      failedSteps,
      progress: this.getProgress(plan),
      currentStepNumber: plan.currentStep,
      completed: plan.completed,
      success: plan.success,
    };
  }

  /**
   * Generate unique plan ID
   */
  private generatePlanId(): string {
    return `plan-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
  }

  /**
   * Export plan to JSON
   */
  exportPlan(plan: Plan): string {
    return JSON.stringify(plan, null, 2);
  }

  /**
   * Import plan from JSON
   */
  importPlan(json: string): Plan {
    return JSON.parse(json) as Plan;
  }
}
