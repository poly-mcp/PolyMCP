/**
 * PolyMCP Version Information
 * 
 * This file contains the version information for the PolyMCP library.
 * The version follows Semantic Versioning (semver.org).
 */

export const VERSION = '2.0.0';

export const VERSION_INFO = {
  major: 2,
  minor: 0,
  patch: 0,
  prerelease: null as string | null,
  build: null as string | null,
} as const;

/**
 * Get the full version string
 */
export function getVersion(): string {
  let version = `${VERSION_INFO.major}.${VERSION_INFO.minor}.${VERSION_INFO.patch}`;
  
  if (VERSION_INFO.prerelease) {
    version += `-${VERSION_INFO.prerelease}`;
  }
  
  if (VERSION_INFO.build) {
    version += `+${VERSION_INFO.build}`;
  }
  
  return version;
}

/**
 * Check if a version is compatible with the current version
 */
export function isCompatible(otherVersion: string): boolean {
  const [otherMajor] = otherVersion.split('.').map(Number);
  return otherMajor === VERSION_INFO.major;
}
