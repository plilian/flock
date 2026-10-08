import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const packageRoot = dirname(fileURLToPath(import.meta.url));
const skillPath = resolve(packageRoot, 'skills/flock/SKILL.md');
const helperPath = resolve(packageRoot, 'skills/flock/scripts/flock.py');
const skillFile = readFileSync(skillPath, 'utf8');
const skillContent = skillFile.replace(/^---\s*[\s\S]*?\n---\s*/, '').trim();

export const name = 'flock-deepseek-harness';
export const inject = ['skills'];

export function apply(ctx) {
  ctx.skills.register({
    name: 'flock',
    description: 'Audit source evidence and compare controlled synthetic social scenarios.',
    content: `${skillContent}\n\n## Installed helper path\n\nThe Flock Python helper for this installation is at \`${helperPath}\`. Run it from the user's selected workspace with \`--workspace .\`.`,
    path: skillPath,
  });
}

