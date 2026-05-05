/**
 * Targeted YAML utilities for duckyai.yml agent configuration.
 *
 * These work with the known structure of duckyai.yml without a full YAML parser.
 * The file uses a flat list of node objects under `orchestrator.nodes:`.
 * Each node has a `name` field containing the abbreviation in parens, e.g. "Teams Chat Summary (TCS)".
 */

/** Available AI model options for agent execution */
export const AVAILABLE_MODELS = [
  { id: "claude-sonnet-4.6", label: "Claude Sonnet 4.6" },
  { id: "claude-haiku-4.6", label: "Claude Haiku 4.6 (Fast)" },
  { id: "claude-opus-4.6", label: "Claude Opus 4.6" },
  { id: "claude-opus-4.7", label: "Claude Opus 4.7 (Premium)" },
  { id: "gpt-5.5", label: "GPT-5.5" },
  { id: "gpt-5.4", label: "GPT-5.4" },
  { id: "gpt-5.4-mini", label: "GPT-5.4 Mini (Fast)" },
] as const;

export type ModelId = (typeof AVAILABLE_MODELS)[number]["id"] | string;

/**
 * Extract the current model for a given agent abbreviation from duckyai.yml content.
 * Returns null if no model is explicitly set (agent uses default).
 */
export function getAgentModel(yamlContent: string, abbreviation: string): string | null {
  const nodeBlock = findNodeBlock(yamlContent, abbreviation);
  if (!nodeBlock) return null;

  const lines = nodeBlock.split("\n");
  let inAgentParams = false;
  let agentParamsIndent = -1;

  for (const line of lines) {
    const apMatch = line.match(/^(\s+)agent_params:\s*$/);
    if (apMatch) {
      inAgentParams = true;
      agentParamsIndent = apMatch[1].length;
      continue;
    }
    if (inAgentParams) {
      const leadingMatch = line.match(/^(\s+)/);
      const indent = leadingMatch ? leadingMatch[1].length : 0;
      if (indent <= agentParamsIndent && line.trim() !== "") {
        break;
      }
      const modelMatch = line.match(/^\s+model:\s*(.+)/);
      if (modelMatch) {
        return modelMatch[1].trim();
      }
    }
  }
  return null;
}

/**
 * Update the model for a given agent in duckyai.yml content.
 * Returns the modified YAML string.
 *
 * If model is null/empty, removes the model key from agent_params.
 */
export function setAgentModel(yamlContent: string, abbreviation: string, model: string | null): string {
  const lines = yamlContent.split("\n");
  const nodeRange = findNodeRange(lines, abbreviation);
  if (!nodeRange) return yamlContent;

  const { start, end } = nodeRange;
  const nodeLines = lines.slice(start, end);

  let agentParamsIdx = -1;
  let modelLineIdx = -1;
  let agentParamsIndent = -1;

  for (let i = 0; i < nodeLines.length; i++) {
    const line = nodeLines[i];
    const apMatch = line.match(/^(\s+)agent_params:\s*$/);
    if (apMatch) {
      agentParamsIdx = i;
      agentParamsIndent = apMatch[1].length;
      continue;
    }
    if (agentParamsIdx >= 0 && i > agentParamsIdx) {
      const leadingMatch = line.match(/^(\s+)/);
      const indent = leadingMatch ? leadingMatch[1].length : 0;
      if (indent <= agentParamsIndent && line.trim() !== "") {
        break;
      }
      if (/^\s+model:/.test(line)) {
        modelLineIdx = i;
      }
    }
  }

  const childIndent = " ".repeat((agentParamsIndent >= 0 ? agentParamsIndent : 2) + 2);

  if (model) {
    if (modelLineIdx >= 0) {
      nodeLines[modelLineIdx] = `${childIndent}model: ${model}`;
    } else if (agentParamsIdx >= 0) {
      nodeLines.splice(agentParamsIdx + 1, 0, `${childIndent}model: ${model}`);
    } else {
      // No agent_params — add before node ends
      const baseIndent = "  ";
      nodeLines.push(`${baseIndent}agent_params:`);
      nodeLines.push(`${baseIndent}  model: ${model}`);
    }
  } else {
    if (modelLineIdx >= 0) {
      nodeLines.splice(modelLineIdx, 1);
      // Check if agent_params is now empty
      const hasOtherChildren = nodeLines.some((line, idx) => {
        if (idx <= agentParamsIdx) return false;
        const m = line.match(/^(\s+)/);
        const indent = m ? m[1].length : 0;
        if (indent <= agentParamsIndent && line.trim() !== "") return false;
        return indent > agentParamsIndent && line.trim() !== "";
      });
      if (!hasOtherChildren && agentParamsIdx >= 0) {
        nodeLines.splice(agentParamsIdx, 1);
      }
    }
  }

  const result = [...lines.slice(0, start), ...nodeLines, ...lines.slice(end)];
  return result.join("\n");
}

function findNodeBlock(yamlContent: string, abbreviation: string): string | null {
  const lines = yamlContent.split("\n");
  const range = findNodeRange(lines, abbreviation);
  if (!range) return null;
  return lines.slice(range.start, range.end).join("\n");
}

/**
 * Find line range [start, end) for a node with matching abbreviation.
 * Nodes start with `- type: agent` and contain `(ABBR)` in their name field.
 */
function findNodeRange(lines: string[], abbreviation: string): { start: number; end: number } | null {
  const namePattern = new RegExp(`\\(${abbreviation}\\)`);
  let nodeStart = -1;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    // Detect node boundaries
    if (/^\s*-\s+type:\s*agent/.test(line)) {
      // If we had a previous node that matched, we would have returned already.
      // Start tracking this new node.
      nodeStart = i;
    }

    // Check if current line has our abbreviation in name
    if (nodeStart >= 0 && namePattern.test(line) && /name:/.test(line)) {
      const end = findNodeEnd(lines, nodeStart);
      return { start: nodeStart, end };
    }
  }

  return null;
}

function findNodeEnd(lines: string[], nodeStart: number): number {
  for (let i = nodeStart + 1; i < lines.length; i++) {
    if (/^\s*-\s+type:/.test(lines[i])) {
      return i;
    }
  }
  return lines.length;
}

/**
 * Extract the default model from `defaults.agent_params.model` in duckyai.yml.
 */
export function getDefaultModel(yamlContent: string): string | null {
  const lines = yamlContent.split("\n");
  let inDefaults = false;
  let inAgentParams = false;
  let defaultsIndent = -1;
  let agentParamsIndent = -1;

  for (const line of lines) {
    // Detect `defaults:` top-level key
    const dMatch = line.match(/^(defaults):\s*$/);
    if (dMatch) {
      inDefaults = true;
      defaultsIndent = 0;
      inAgentParams = false;
      continue;
    }
    if (inDefaults) {
      // Non-indented line that isn't empty = new top-level key → stop
      if (line.trim() !== "" && !line.startsWith(" ") && !line.startsWith("\t")) {
        break;
      }
      const apMatch = line.match(/^(\s+)agent_params:\s*$/);
      if (apMatch) {
        inAgentParams = true;
        agentParamsIndent = apMatch[1].length;
        continue;
      }
      if (inAgentParams) {
        const leadingMatch = line.match(/^(\s+)/);
        const indent = leadingMatch ? leadingMatch[1].length : 0;
        if (indent <= agentParamsIndent && line.trim() !== "") break;
        const modelMatch = line.match(/^\s+model:\s*(.+)/);
        if (modelMatch) return modelMatch[1].trim();
      }
    }
  }
  return null;
}

/**
 * Set the default model in `defaults.agent_params.model`.
 * If model is null/empty, removes the model line.
 */
export function setDefaultModel(yamlContent: string, model: string | null): string {
  const lines = yamlContent.split("\n");
  let defaultsLineIdx = -1;
  let agentParamsLineIdx = -1;
  let modelLineIdx = -1;
  let agentParamsIndent = -1;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (/^defaults:\s*$/.test(line)) {
      defaultsLineIdx = i;
      continue;
    }
    if (defaultsLineIdx >= 0 && i > defaultsLineIdx) {
      // End of defaults block
      if (line.trim() !== "" && !line.startsWith(" ") && !line.startsWith("\t")) break;

      const apMatch = line.match(/^(\s+)agent_params:\s*$/);
      if (apMatch) {
        agentParamsLineIdx = i;
        agentParamsIndent = apMatch[1].length;
        continue;
      }
      if (agentParamsLineIdx >= 0 && i > agentParamsLineIdx) {
        const leadingMatch = line.match(/^(\s+)/);
        const indent = leadingMatch ? leadingMatch[1].length : 0;
        if (indent <= agentParamsIndent && line.trim() !== "") break;
        if (/^\s+model:/.test(line)) {
          modelLineIdx = i;
          break;
        }
      }
    }
  }

  if (model) {
    const childIndent = " ".repeat((agentParamsIndent >= 0 ? agentParamsIndent : 2) + 2);
    if (modelLineIdx >= 0) {
      lines[modelLineIdx] = `${childIndent}model: ${model}`;
    } else if (agentParamsLineIdx >= 0) {
      lines.splice(agentParamsLineIdx + 1, 0, `${childIndent}model: ${model}`);
    } else if (defaultsLineIdx >= 0) {
      lines.splice(defaultsLineIdx + 1, 0, `  agent_params:`, `    model: ${model}`);
    } else {
      // No defaults section at all — append before nodes:
      const nodesIdx = lines.findIndex((l) => /^nodes:\s*$/.test(l));
      const insertAt = nodesIdx >= 0 ? nodesIdx : lines.length;
      lines.splice(insertAt, 0, `defaults:`, `  agent_params:`, `    model: ${model}`, ``);
    }
  } else {
    if (modelLineIdx >= 0) {
      lines.splice(modelLineIdx, 1);
    }
  }

  return lines.join("\n");
}

/** Path to duckyai.yml relative to vault root */
export const DUCKYAI_YML_PATH = ".duckyai/duckyai.yml";
