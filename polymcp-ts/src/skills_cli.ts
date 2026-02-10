import spawn from 'cross-spawn';

export interface SkillsCliOptions {
  bin?: string;
  cwd?: string;
  env?: NodeJS.ProcessEnv;
  stdio?: 'inherit' | 'pipe';
}

function resolveSkillsCommand(binOverride?: string): { command: string; args: string[] } {
  const envBin = binOverride || process.env.POLYMCP_SKILLS_BIN || process.env.SKILLS_CLI;
  if (envBin) {
    const parts = envBin.split(' ').filter(Boolean);
    return { command: parts[0], args: parts.slice(1) };
  }

  return { command: 'npx', args: ['-y', 'skills'] };
}

export function runSkillsCli(
  args: string[],
  options: SkillsCliOptions = {}
): Promise<{ code: number | null; signal: NodeJS.Signals | null }> {
  const base = resolveSkillsCommand(options.bin);
  const child = spawn(base.command, [...base.args, ...args], {
    cwd: options.cwd,
    env: { ...process.env, ...(options.env || {}) },
    stdio: options.stdio || 'inherit',
  });

  return new Promise((resolve, reject) => {
    child.on('error', reject);
    child.on('close', (code, signal) => resolve({ code, signal }));
  });
}
