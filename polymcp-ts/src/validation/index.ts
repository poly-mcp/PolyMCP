/**
 * Validation Module
 * 
 * Provides validation utilities for tools, parameters, and configurations.
 */

import { z } from 'zod';
import {
  ValidationResult,
  ValidationErrorDetail,
} from '../types';
import { ValidationError } from '../errors';
import { VALIDATION_DEFAULTS } from '../constants';

/**
 * Validate data against a Zod schema
 */
export async function validate<T>(
  schema: z.ZodSchema<T>,
  data: unknown
): Promise<ValidationResult> {
  try {
    await schema.parseAsync(data);
    return {
      valid: true,
      errors: [],
    };
  } catch (error) {
    if (error instanceof z.ZodError) {
      const errors: ValidationErrorDetail[] = error.errors.map(err => ({
        path: err.path.join('.'),
        message: err.message,
        code: err.code,
      }));
      
      return {
        valid: false,
        errors,
      };
    }
    
    return {
      valid: false,
      errors: [{
        path: '',
        message: String(error),
        code: 'unknown_error',
      }],
    };
  }
}

/**
 * Validate and throw if invalid
 */
export async function validateOrThrow<T>(
  schema: z.ZodSchema<T>,
  data: unknown,
  errorMessage?: string
): Promise<T> {
  try {
    return await schema.parseAsync(data);
  } catch (error) {
    if (error instanceof z.ZodError) {
      const errors = error.errors.map(err =>
        `${err.path.join('.')}: ${err.message}`
      ).join(', ');
      
      throw new ValidationError(
        errorMessage || `Validation failed: ${errors}`,
        error.errors
      );
    }
    
    throw new ValidationError(
      errorMessage || `Validation failed: ${String(error)}`
    );
  }
}

/**
 * Common validation schemas
 */
export const schemas = {
  /**
   * Non-empty string
   */
  nonEmptyString: z.string().min(1, 'String cannot be empty'),
  
  /**
   * Email address
   */
  email: z.string().email('Invalid email address'),
  
  /**
   * URL
   */
  url: z.string().url('Invalid URL'),
  
  /**
   * Port number
   */
  port: z.number().int().min(1).max(65535, 'Invalid port number'),
  
  /**
   * Positive integer
   */
  positiveInt: z.number().int().positive('Must be a positive integer'),
  
  /**
   * Non-negative integer
   */
  nonNegativeInt: z.number().int().nonnegative('Must be non-negative'),
  
  /**
   * Percentage (0-100)
   */
  percentage: z.number().min(0).max(100, 'Must be between 0 and 100'),
  
  /**
   * Timestamp
   */
  timestamp: z.union([z.number(), z.date()]).transform(val =>
    val instanceof Date ? val : new Date(val)
  ),
  
  /**
   * ISO date string
   */
  isoDate: z.string().datetime(),
  
  /**
   * JSON object
   */
  jsonObject: z.record(z.any()),
  
  /**
   * Limited string (max length)
   */
  limitedString: (maxLength: number = VALIDATION_DEFAULTS.MAX_STRING_LENGTH) =>
    z.string().max(maxLength, `String must not exceed ${maxLength} characters`),
  
  /**
   * Limited array (max length)
   */
  limitedArray: <T>(
    itemSchema: z.ZodSchema<T>,
    maxLength: number = VALIDATION_DEFAULTS.MAX_ARRAY_LENGTH
  ) =>
    z.array(itemSchema).max(maxLength, `Array must not exceed ${maxLength} items`),
  
  /**
   * Optional with default
   */
  optionalWithDefault: <T>(schema: z.ZodSchema<T>, defaultValue: T) =>
    schema.optional().transform(val => val ?? defaultValue),
};

/**
 * Validate tool parameters
 */
export async function validateToolParameters(
  schema: z.ZodSchema<any>,
  parameters: unknown
): Promise<{ valid: boolean; data?: any; errors?: string[] }> {
  try {
    const data = await schema.parseAsync(parameters);
    return { valid: true, data };
  } catch (error) {
    if (error instanceof z.ZodError) {
      const errors = error.errors.map(err =>
        `${err.path.join('.')}: ${err.message}`
      );
      return { valid: false, errors };
    }
    return { valid: false, errors: [String(error)] };
  }
}

/**
 * Sanitize input to prevent common security issues
 */
export function sanitizeInput(input: unknown): unknown {
  if (typeof input === 'string') {
    // Remove null bytes
    return input.replace(/\0/g, '');
  }
  
  if (Array.isArray(input)) {
    return input.map(sanitizeInput);
  }
  
  if (typeof input === 'object' && input !== null) {
    const sanitized: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(input)) {
      // Skip __proto__ and other dangerous keys
      if (key === '__proto__' || key === 'constructor' || key === 'prototype') {
        continue;
      }
      sanitized[key] = sanitizeInput(value);
    }
    return sanitized;
  }
  
  return input;
}

/**
 * Validate object depth to prevent stack overflow
 */
export function validateObjectDepth(
  obj: unknown,
  maxDepth: number = VALIDATION_DEFAULTS.MAX_OBJECT_DEPTH
): boolean {
  function checkDepth(value: unknown, depth: number): boolean {
    if (depth > maxDepth) {
      return false;
    }
    
    if (typeof value === 'object' && value !== null) {
      if (Array.isArray(value)) {
        return value.every(item => checkDepth(item, depth + 1));
      } else {
        return Object.values(value).every(val => checkDepth(val, depth + 1));
      }
    }
    
    return true;
  }
  
  return checkDepth(obj, 0);
}

/**
 * Create a validator function from a schema
 */
export function createValidator<T>(
  schema: z.ZodSchema<T>
): (data: unknown) => Promise<T> {
  return async (data: unknown) => {
    return await validateOrThrow(schema, data);
  };
}

/**
 * Batch validate multiple values
 */
export async function validateBatch<T>(
  schema: z.ZodSchema<T>,
  items: unknown[]
): Promise<Array<{ valid: boolean; data?: T; errors?: ValidationErrorDetail[] }>> {
  return await Promise.all(
    items.map(async item => {
      const result = await validate(schema, item);
      if (result.valid) {
        return { valid: true, data: item as T };
      }
      return { valid: false, errors: result.errors };
    })
  );
}

/**
 * Type guard for checking if value is a valid Zod schema
 */
export function isZodSchema(value: unknown): value is z.ZodSchema {
  return value instanceof z.ZodType;
}
