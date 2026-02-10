import * as fs from 'fs';
import * as path from 'path';
import * as os from 'os';

export interface SkillsShEntry {
  name: string;
  description: string;
  content: string;
  filePath: string;
}

const FRONTMATTER_RE = /^---\s*\n([\s\S]*?)\n---\s*\n/;

function parseFrontmatter(text: string): { meta: Record<string, string>; rest: string } {
  const match = text.match(FRONTMATTER_RE);
  if (!match) {
    return { meta: {}, rest: text };
  }
  const meta: Record<string, string> = {};
  for (const line of match[1].split('\n')) {
    const idx = line.indexOf(':');
    if (idx === -1) continue;
    const key = line.slice(0, idx).trim();
    const val = line.slice(idx + 1).trim().replace(/^['"]|['"]$/g, '');
    if (key) meta[key] = val;
  }
  const rest = text.slice(match[0].length);
  return { meta, rest };
}

function defaultSkillsDirs(extraDirs?: string[]): string[] {
  const dirs: string[] = [];
  const envDirs = process.env.POLYMCP_SKILLS_DIRS || process.env.SKILLS_DIRS;
  if (envDirs) {
    for (const part of envDirs.split(path.delimiter)) {
      if (part.trim()) dirs.push(part.trim());
    }
  }
  if (extraDirs) {
    for (const d of extraDirs) {
      if (d) dirs.push(d);
    }
  }

  const cwd = process.cwd();
  dirs.push(path.join(cwd, '.agents', 'skills'));
  dirs.push(path.join(cwd, '.skills'));

  const home = os.homedir();
  dirs.push(path.join(home, '.agents', 'skills'));

  const unique = Array.from(new Set(dirs));
  return unique.filter(d => fs.existsSync(d) && fs.statSync(d).isDirectory());
}

export function loadSkillsSh(extraDirs?: string[], maxChars: number = 12000): SkillsShEntry[] {
  const entries: SkillsShEntry[] = [];
  for (const base of defaultSkillsDirs(extraDirs)) {
    for (const name of fs.readdirSync(base)) {
      const skillDir = path.join(base, name);
      if (!fs.statSync(skillDir).isDirectory()) continue;
      const skillFile = path.join(skillDir, 'SKILL.md');
      if (!fs.existsSync(skillFile)) continue;
      let text = fs.readFileSync(skillFile, 'utf-8');
      if (text.length > maxChars) text = text.slice(0, maxChars);
      const { meta, rest } = parseFrontmatter(text);
      entries.push({
        name: meta.name || name,
        description: meta.description || '',
        content: rest.trim(),
        filePath: skillFile,
      });
    }
  }
  return entries;
}

function tokenize(text: string): string[] {
  return (text || '')
    .toLowerCase()
    .replace(/[^a-z0-9à-ÿ_]+/gi, ' ')
    .split(/\s+/)
    .filter(Boolean);
}

export function buildSkillsShContext(
  query: string,
  skills: SkillsShEntry[],
  maxSkills: number = 4,
  maxTotalChars: number = 5000,
  maxPerSkillChars: number = 1800
): string {
  if (!skills.length) return '';

  const qTokens = new Set(tokenize(query));
  const scored = skills
    .map(s => {
      const text = `${s.name} ${s.description}`.toLowerCase();
      const tokens = tokenize(text);
      let score = 0;
      for (const t of tokens) {
        if (qTokens.has(t)) score += 1;
      }
      return { skill: s, score };
    })
    .sort((a, b) => b.score - a.score)
    .slice(0, maxSkills)
    .filter(x => x.score > 0);

  if (scored.length === 0) return '';

  let total = 0;
  const blocks: string[] = [];
  for (const item of scored) {
    let content = item.skill.content;
    if (content.length > maxPerSkillChars) {
      content = content.slice(0, maxPerSkillChars).trimEnd() + '\n[truncated]';
    }
    const block = `### ${item.skill.name}\nDescription: ${item.skill.description}\n\n${content}`;
    if (total + block.length > maxTotalChars) break;
    blocks.push(block);
    total += block.length;
  }
  if (!blocks.length) return '';
  return `SKILLS CONTEXT (skills.sh):\n\n${blocks.join('\n\n')}`;
}
