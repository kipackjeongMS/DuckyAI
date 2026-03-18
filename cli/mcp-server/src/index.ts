import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import * as fs from "fs/promises";
import * as path from "path";
import * as os from "os";

// Configuration — resolve vault root from the script's location (mcp-server/dist/)
const VAULT_ROOT = process.env.DUCKYAI_VAULT_ROOT || path.resolve(path.dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Z]:)/, '$1')), '..', '..');
const DAILY_DIR = path.join(VAULT_ROOT, "04-Periodic/Daily");
const WEEKLY_DIR = path.join(VAULT_ROOT, "04-Periodic/Weekly");
const CONTACTS_DIR = path.join(VAULT_ROOT, "02-People/Contacts");
const TASKS_DIR = path.join(VAULT_ROOT, "01-Work/Tasks");
const MEETINGS_DIR = path.join(VAULT_ROOT, "02-People/Meetings");
const ONE_ON_ONES_DIR = path.join(VAULT_ROOT, "02-People/1-on-1s");
const ARCHIVE_DIR = path.join(VAULT_ROOT, "05-Archive");
const TEMPLATES_DIR = path.join(VAULT_ROOT, "Templates");

// Common timezone abbreviation → IANA name mapping
const TIMEZONE_MAP: Record<string, string> = {
  "PST": "America/Los_Angeles",
  "PDT": "America/Los_Angeles",
  "MST": "America/Denver",
  "MDT": "America/Denver",
  "CST": "America/Chicago",
  "CDT": "America/Chicago",
  "EST": "America/New_York",
  "EDT": "America/New_York",
  "UTC": "UTC",
  "GMT": "UTC",
  "KST": "Asia/Seoul",
  "JST": "Asia/Tokyo",
  "IST": "Asia/Kolkata",
  "CET": "Europe/Berlin",
  "CEST": "Europe/Berlin",
  "GMT+0": "UTC",
  "Pacific Standard Time": "America/Los_Angeles",
  "Mountain Standard Time": "America/Denver",
  "Central Standard Time": "America/Chicago",
  "Eastern Standard Time": "America/New_York",
};

// Resolve a timezone string (abbreviation or IANA) to a valid IANA timezone name
function resolveTimezone(tz: string): string {
  if (TIMEZONE_MAP[tz]) return TIMEZONE_MAP[tz];
  // Validate as IANA name by attempting to use it
  try {
    Intl.DateTimeFormat(undefined, { timeZone: tz });
    return tz;
  } catch {
    return "UTC";
  }
}

// Cached vault config values read from duckyai.yml
let _cachedVaultId: string | null = null;
let _cachedTimezone: string | null = null;

// Diagnostic file logger for MCP tool calls
const MCP_LOG_PATH = path.join(os.homedir(), ".duckyai", "mcp-server.log");
async function mcpLog(message: string): Promise<void> {
  const timestamp = new Date().toISOString();
  const line = `[${timestamp}] ${message}\n`;
  try {
    await fs.appendFile(MCP_LOG_PATH, line, "utf-8");
  } catch {
    // If we can't write the log, write to stderr as fallback
    console.error(line.trim());
  }
}

async function readVaultConfig(): Promise<{ vaultId: string; timezone: string }> {
  if (_cachedVaultId !== null && _cachedTimezone !== null) {
    return { vaultId: _cachedVaultId, timezone: _cachedTimezone };
  }
  let vaultId = "default";
  let timezone = "UTC";
  try {
    const configPath = path.join(VAULT_ROOT, "duckyai.yml");
    const configContent = await fs.readFile(configPath, "utf-8");
    const idMatch = configContent.match(/^id:\s*(.+)$/m);
    if (idMatch) vaultId = idMatch[1].trim();
    const tzMatch = configContent.match(/^\s*timezone:\s*"?([^"\n]+)"?$/m);
    if (tzMatch) timezone = resolveTimezone(tzMatch[1].trim());
  } catch { /* fallback to defaults */ }
  _cachedVaultId = vaultId;
  _cachedTimezone = timezone;
  return { vaultId, timezone };
}

// Get the user-configured IANA timezone
async function getUserTimezone(): Promise<string> {
  const { timezone } = await readVaultConfig();
  return timezone;
}

// Helper: Resolve vault-local runtime state directory (<vault_root>/.duckyai/state/)
// Falls back to legacy ~/.duckyai/vaults/{vault_id}/state/ and migrates data forward.
async function getGlobalStateDir(): Promise<string> {
  const { vaultId } = await readVaultConfig();
  const newStateDir = path.join(VAULT_ROOT, ".duckyai", "state");
  const oldStateDir = path.join(os.homedir(), ".duckyai", "vaults", vaultId, "state");

  // Migrate from old location if needed
  try {
    const migrationMarker = path.join(VAULT_ROOT, ".duckyai", ".migrated");
    await fs.access(migrationMarker);
    // Already migrated
  } catch {
    // Check if old state dir exists and new doesn't
    try {
      await fs.access(oldStateDir);
      try {
        await fs.access(newStateDir);
      } catch {
        // Old exists, new doesn't — migrate
        await fs.mkdir(newStateDir, { recursive: true });
        const files = await fs.readdir(oldStateDir);
        for (const file of files) {
          await fs.copyFile(path.join(oldStateDir, file), path.join(newStateDir, file));
        }
        await fs.writeFile(
          path.join(VAULT_ROOT, ".duckyai", ".migrated"),
          `Migrated from ${oldStateDir}`,
          "utf-8"
        );
      }
    } catch {
      // Old doesn't exist — nothing to migrate
    }
  }

  await fs.mkdir(newStateDir, { recursive: true });
  return newStateDir;
}

// Initialize MCP Server
const server = new McpServer({
  name: "duckyai-vault",
  version: "1.0.0",
});

// Helper: Format a Date to YYYY-MM-DD in the user's timezone
function toLocalDateString(date: Date, timezone: string): string {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: timezone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(date);
  const year = parts.find((p) => p.type === "year")!.value;
  const month = parts.find((p) => p.type === "month")!.value;
  const day = parts.find((p) => p.type === "day")!.value;
  return `${year}-${month}-${day}`;
}

// Helper: Format date as "Friday, February 6, 2026"
async function formatDateHeading(dateStr: string): Promise<string> {
  const tz = await getUserTimezone();
  const date = new Date(dateStr + "T12:00:00"); // Noon to avoid timezone issues
  return date.toLocaleDateString("en-US", {
    timeZone: tz,
    weekday: "long",
    month: "long",
    day: "numeric",
    year: "numeric",
  });
}

// Helper: Get today's date in YYYY-MM-DD format (timezone-aware)
async function getTodayDate(): Promise<string> {
  const tz = await getUserTimezone();
  return toLocalDateString(new Date(), tz);
}

// Helper: Find the most recent daily note before a given date
async function findPreviousDailyNote(beforeDate: string): Promise<string | null> {
  try {
    const files = await fs.readdir(DAILY_DIR);
    const sorted = files
      .filter((f) => f.endsWith(".md") && f < `${beforeDate}.md`)
      .sort()
      .reverse();
    return sorted.length > 0 ? sorted[0] : null;
  } catch {
    return null;
  }
}

// Helper: Ensure a daily note exists for a given date, creating it if needed
async function ensureDailyNote(targetDate: string): Promise<void> {
  const dailyPath = path.join(DAILY_DIR, `${targetDate}.md`);
  try {
    await fs.access(dailyPath);
  } catch {
    // Daily note doesn't exist — create a minimal one
    await fs.mkdir(DAILY_DIR, { recursive: true });
    const dayHeading = await formatDateHeading(targetDate);
    const template = `---
created: ${targetDate}
type: daily
date: ${targetDate}
tags:
  - daily
---

# ${dayHeading}

## Focus Today
- [ ] 

## Carried from yesterday
- (none)

## Tasks
- [ ] 

## Tasks Completed
- [ ] 

## Notes


## Teams Meeting Highlights


## Teams Chat Highlights


## End of Day
### What went well?
- 

### What could improve?
- 

### Carry forward to tomorrow
- [ ] 
`;
    await fs.writeFile(dailyPath, template, "utf-8");
  }
}

// Helper: Extract carry-forward items from a daily note
// Pulls uncompleted tasks from Focus Today, Other Tasks, and Carry forward sections
async function extractCarryForward(filePath: string): Promise<string[]> {
  try {
    const content = await fs.readFile(filePath, "utf-8");
    const uncompleted: string[] = [];

    // Extract from Focus Today section
    const focusMatch = content.match(/## Focus Today\n([\s\S]*?)(?=\n## Carried from yesterday|\n## Tasks)/);
    if (focusMatch) {
      const lines = focusMatch[1].split("\n");
      for (const line of lines) {
        // Match uncompleted tasks, skip headers and empty lines
        if (line.match(/^- \[ \]/)) {
          uncompleted.push(line);
        }
      }
    }

    // Extract from Carry forward to tomorrow section
    const carryMatch = content.match(/### Carry forward to tomorrow\n([\s\S]*?)(?=\n##|$)/);
    if (carryMatch) {
      const lines = carryMatch[1].trim().split("\n");
      for (const line of lines) {
        if (line.match(/^- \[ \]/) && !uncompleted.includes(line)) {
          uncompleted.push(line);
        }
      }
    }

    return uncompleted;
  } catch {
    // File doesn't exist or can't be read
  }
  return [];
}

// Helper: Normalize line endings to LF
function normalizeLineEndings(content: string): string {
  return content.replace(/\r\n/g, "\n");
}

// Helper: Read and process a template file
async function readTemplate(templateName: string): Promise<string> {
  const templatePath = path.join(TEMPLATES_DIR, `${templateName}.md`);
  const content = await fs.readFile(templatePath, "utf-8");
  return normalizeLineEndings(content);
}

// Helper: Process template variables
// Supports: {{date:FORMAT}}, {{date:FORMAT|modifier}}, {{title}}, {{week}}
function processTemplate(
  template: string,
  variables: {
    date?: string;
    title?: string;
    week?: string;
    weekStart?: string;
    weekEnd?: string;
    person?: string;
  }
): string {
  const dateObj = variables.date 
    ? new Date(variables.date + "T12:00:00") 
    : new Date();
  
  let result = template;
  
  // Replace {{title}}
  if (variables.title) {
    result = result.replace(/\{\{title\}\}/g, variables.title);
  }
  
  // Replace {{date:FORMAT}} patterns
  result = result.replace(/\{\{date:([^}|]+)(?:\|([^}]+))?\}\}/g, (match, format, modifier) => {
    let targetDate = dateObj;
    
    // Handle modifiers like |monday, |friday
    if (modifier === "monday") {
      const day = dateObj.getDay();
      const diff = dateObj.getDate() - day + (day === 0 ? -6 : 1);
      targetDate = new Date(dateObj);
      targetDate.setDate(diff);
    } else if (modifier === "friday") {
      const day = dateObj.getDay();
      const diff = dateObj.getDate() - day + (day === 0 ? -2 : 5);
      targetDate = new Date(dateObj);
      targetDate.setDate(diff);
    }
    
    return formatDate(targetDate, format);
  });
  
  // Replace person in frontmatter for 1:1s
  if (variables.person) {
    result = result.replace(/^(person:\s*)$/m, `$1"[[${variables.person}]]"`);
  }
  
  return result;
}

// Helper: Format date according to template format string
function formatDate(date: Date, format: string): string {
  const year = date.getFullYear();
  const month = date.getMonth() + 1;
  const day = date.getDate();
  const dayOfWeek = date.getDay();
  
  // Get ISO week number
  const tempDate = new Date(date.getTime());
  tempDate.setHours(0, 0, 0, 0);
  tempDate.setDate(tempDate.getDate() + 3 - ((tempDate.getDay() + 6) % 7));
  const week1 = new Date(tempDate.getFullYear(), 0, 4);
  const weekNum = 1 + Math.round(((tempDate.getTime() - week1.getTime()) / 86400000 - 3 + ((week1.getDay() + 6) % 7)) / 7);
  
  const weekdays = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
  const months = ["January", "February", "March", "April", "May", "June", 
                  "July", "August", "September", "October", "November", "December"];
  
  let result = format;
  
  // Order matters - longer patterns first
  result = result.replace(/YYYY/g, year.toString());
  result = result.replace(/\[W\]ww/g, `W${weekNum.toString().padStart(2, "0")}`);
  result = result.replace(/ww/g, weekNum.toString().padStart(2, "0"));
  result = result.replace(/MM/g, month.toString().padStart(2, "0"));
  result = result.replace(/DD/g, day.toString().padStart(2, "0"));
  result = result.replace(/MMMM/g, months[month - 1]);
  result = result.replace(/dddd/g, weekdays[dayOfWeek]);
  result = result.replace(/D/g, day.toString());
  
  return result;
}

// Helper: Ensure contact file exists (general purpose)
async function ensureContactExists(
  personName: string,
  context: string
): Promise<boolean> {
  const contactPath = path.join(CONTACTS_DIR, `${personName}.md`);
  try {
    await fs.access(contactPath);
    return false; // Already exists
  } catch {
    const today = await getTodayDate();
    // Template matches Templates/Person.md structure
    const template = `---
created: ${today}
type: person
role: 
team: 
email: 
tags:
  - person
---

# ${personName}

## Role
- **Title:** 
- **Team:** 
- **Reports to:** 

## Contact
- **Email:** 
- **Teams:** 

## Working Style
- 

## Topics / Expertise
- 

## 1:1 History
\`\`\`dataview
LIST
FROM "02-People/1-on-1s"
WHERE contains(person, this.file.name)
SORT date DESC
LIMIT 5
\`\`\`

## Meeting History
\`\`\`dataview
LIST
FROM "02-People/Meetings"
WHERE contains(attendees, this.file.name)
SORT date DESC
LIMIT 5
\`\`\`

## Notes
- ${context}
`;
    await fs.writeFile(contactPath, template, "utf-8");
    return true; // Created new
  }
}

// =============================================================================
// SKILL: prepareDailyNote
// =============================================================================
server.tool(
  "prepareDailyNote",
  "Create today's daily note with carry-forward items from yesterday",
  {
    date: z
      .string()
      .optional()
      .describe("Date in YYYY-MM-DD format, defaults to today"),
  },
  async ({ date }) => {
    const targetDate = date || await getTodayDate();
    const targetPath = path.join(DAILY_DIR, `${targetDate}.md`);

    // Check if already exists
    try {
      await fs.access(targetPath);
      return {
        content: [
          {
            type: "text",
            text: `Daily note for ${targetDate} already exists.`,
          },
        ],
      };
    } catch {
      // Doesn't exist, continue
    }

    // Find yesterday's note and extract carry-forward
    const previousNote = await findPreviousDailyNote(targetDate);
    let carryForward: string[] = [];
    if (previousNote) {
      carryForward = await extractCarryForward(path.join(DAILY_DIR, previousNote));
    }

    // Generate the daily note
    const dayHeading = await formatDateHeading(targetDate);
    const carrySection =
      carryForward.length > 0 ? carryForward.join("\n") : "- (none)";

    // Template matches .playbook/templates/Daily Note Template.md structure
    const template = `---
created: "${targetDate}"
type: daily
date: "${targetDate}"
tags:
  - daily
---

# ${dayHeading}

## Focus Today
- [ ]

## Carried from yesterday
${carrySection}

## Tasks
- [ ]

## Tasks Completed
- [ ]

## Notes


## Teams Meeting Highlights


## Teams Chat Highlights


## End of Day
### What went well?
-

### What could improve?
-

### Carry forward to tomorrow
- [ ]
`;

    await fs.writeFile(targetPath, template, "utf-8");

    return {
      content: [
        {
          type: "text",
          text: `Created ${targetDate}.md with ${carryForward.length} carried items from ${previousNote || "nowhere"}`,
        },
      ],
    };
  }
);

// =============================================================================
// SKILL: logPRReview
// =============================================================================
server.tool(
  "logPRReview",
  "Log a PR review or comment to today's daily note",
  {
    person: z.string().describe("Name of the PR author (e.g., 'Shi Chen')"),
    prNumber: z.string().describe("PR number (e.g., '14653251')"),
    prUrl: z.string().describe("Full PR URL"),
    description: z.string().describe("Brief description of what the PR does"),
    action: z
      .enum(["reviewed", "commented"])
      .describe("Whether you reviewed or commented on the PR"),
  },
  async ({ person, prNumber, prUrl, description, action }) => {
    const today = await getTodayDate();
    const dailyPath = path.join(DAILY_DIR, `${today}.md`);

    // Ensure daily note exists
    try {
      await fs.access(dailyPath);
    } catch {
      return {
        content: [
          {
            type: "text",
            text: `Daily note for ${today} doesn't exist. Run prepareDailyNote first.`,
          },
        ],
      };
    }

    let content = normalizeLineEndings(await fs.readFile(dailyPath, "utf-8"));

    // Build the log entry
    const actionText = action === "reviewed" ? "Reviewed" : "Commented on"
    const logEntry = `- [x] ${actionText} [[${person}]]'s PR - [PR ${prNumber}](${prUrl}) - ${description}`;

    // Insert after existing completed tasks
    const tasksMatch = content.match(/(## Tasks Completed\n)([\s\S]*?)(\n## )/);
    if (tasksMatch) {
      const existingTasks = tasksMatch[2].trim();
      const newTasks = existingTasks === "- [x]" 
        ? logEntry 
        : `${existingTasks}\n${logEntry}`;
      content = content.replace(
        tasksMatch[0],
        `${tasksMatch[1]}${newTasks}\n\n${tasksMatch[3]}`
      );
    }

    await fs.writeFile(dailyPath, content, "utf-8");

    // Ensure contact exists
    const createdContact = await ensureContactExists(
      person,
      `First referenced in [PR ${prNumber}](${prUrl}) - ${description}`
    );

    const contactMsg = createdContact
      ? ` (created contact for ${person})`
      : "";

    return {
      content: [
        {
          type: "text",
          text: `Logged ${action} on ${person}'s PR ${prNumber}${contactMsg}`,
        },
      ],
    };
  }
);

// =============================================================================
// SKILL: logAction
// =============================================================================
server.tool(
  "logAction",
  "Log a completed action to today's daily note",
  {
    action: z.string().describe("Description of what was completed"),
    addToCarryForward: z
      .string()
      .optional()
      .describe("Optional follow-up item to add to carry forward"),
  },
  async ({ action, addToCarryForward }) => {
    const today = await getTodayDate();
    const dailyPath = path.join(DAILY_DIR, `${today}.md`);

    try {
      await fs.access(dailyPath);
    } catch {
      return {
        content: [
          {
            type: "text",
            text: `Daily note for ${today} doesn't exist. Run prepareDailyNote first.`,
          },
        ],
      };
    }

    let content = normalizeLineEndings(await fs.readFile(dailyPath, "utf-8"));

    // Add to Tasks Completed
    const logEntry = `- [x] ${action}`;
    const tasksMatch = content.match(/(## Tasks Completed\n)([\s\S]*?)(\n## )/);
    if (tasksMatch) {
      const existingTasks = tasksMatch[2].trim();
      const newTasks = existingTasks === "- [x]"
        ? logEntry
        : `${existingTasks}\n${logEntry}`;
      content = content.replace(
        tasksMatch[0],
        `${tasksMatch[1]}${newTasks}\n\n${tasksMatch[3]}`
      );
    }

    // Optionally add to carry forward
    if (addToCarryForward) {
      const carryEntry = `- [ ] ${addToCarryForward}`;
      content = content.replace(
        /(### Carry forward to tomorrow\n)([\s\S]*?)$/,
        (match, header, existing) => {
          const trimmed = existing.trim();
          const newItems = trimmed === "- [ ]"
            ? carryEntry
            : `${trimmed}\n${carryEntry}`;
          return `${header}${newItems}\n`;
        }
      );
    }

    await fs.writeFile(dailyPath, content, "utf-8");

    const carryMsg = addToCarryForward
      ? ` + added follow-up to carry forward`
      : "";

    return {
      content: [
        {
          type: "text",
          text: `Logged: ${action}${carryMsg}`,
        },
      ],
    };
  }
);

// =============================================================================
// SKILL: createTask
// =============================================================================
server.tool(
  "createTask",
  "Create a new task in 01-Work/Tasks/",
  {
    title: z.string().describe("Task title (will be used as filename)"),
    description: z.string().optional().describe("Task description"),
    priority: z.enum(["P0", "P1", "P2", "P3"]).default("P2").describe("Priority level"),
    project: z.string().optional().describe("Related project name (without [[]])"),
    due: z.string().optional().describe("Due date in YYYY-MM-DD format"),
  },
  async ({ title, description, priority, project, due }) => {
    await mcpLog(`createTask called — title=${title}, priority=${priority}`);
    const today = await getTodayDate();
    const taskPath = path.join(TASKS_DIR, `${title}.md`);

    // Check if already exists
    try {
      await fs.access(taskPath);
      return {
        content: [{ type: "text", text: `Task "${title}" already exists.` }],
      };
    } catch {
      // Doesn't exist, continue
    }

    // Read and process template
    let template = await readTemplate("Task");
    template = processTemplate(template, { date: today, title });

    // Update frontmatter values
    template = template.replace(/^(priority:\s*)P2$/m, `$1${priority}`);
    if (project) {
      template = template.replace(/^(project:\s*)$/m, `$1"[[${project}]]"`);
    }
    if (due) {
      template = template.replace(/^(due:\s*)$/m, `$1${due}`);
    }

    // Add description if provided
    if (description) {
      template = template.replace(
        /^(## Description\n)$/m,
        `$1${description}\n`
      );
    }

    await fs.writeFile(taskPath, template, "utf-8");

    return {
      content: [
        { type: "text", text: `Created task: ${title} (${priority})` },
      ],
    };
  }
);

// =============================================================================
// SKILL: archiveTask
// =============================================================================
server.tool(
  "archiveTask",
  "Move a completed/cancelled task to 05-Archive/",
  {
    title: z.string().describe("Task title (filename without .md)"),
    status: z.enum(["done", "cancelled"]).default("done").describe("Final status"),
  },
  async ({ title, status }) => {
    const sourcePath = path.join(TASKS_DIR, `${title}.md`);
    const destPath = path.join(ARCHIVE_DIR, `${title}.md`);
    const today = await getTodayDate();

    // Check source exists
    try {
      await fs.access(sourcePath);
    } catch {
      return {
        content: [{ type: "text", text: `Task "${title}" not found in Tasks folder.` }],
      };
    }

    // Read and update the file
    let content = normalizeLineEndings(await fs.readFile(sourcePath, "utf-8"));
    
    // Update status
    content = content.replace(/^(status:\s*)\S+$/m, `$1${status}`);
    
    // Update modified date
    content = content.replace(/^(modified:\s*)\S+$/m, `$1${today}`);

    // Write to archive
    await fs.writeFile(destPath, content, "utf-8");
    
    // Delete from Tasks
    await fs.unlink(sourcePath);

    return {
      content: [
        { type: "text", text: `Archived "${title}" as ${status}` },
      ],
    };
  }
);

// =============================================================================
// SKILL: updateTaskStatus
// =============================================================================
server.tool(
  "updateTaskStatus",
  "Update the status of a task",
  {
    title: z.string().describe("Task title (filename without .md)"),
    status: z.enum(["todo", "in-progress", "blocked", "done", "cancelled"]).describe("New status"),
  },
  async ({ title, status }) => {
    const taskPath = path.join(TASKS_DIR, `${title}.md`);
    const today = await getTodayDate();

    try {
      await fs.access(taskPath);
    } catch {
      return {
        content: [{ type: "text", text: `Task "${title}" not found.` }],
      };
    }

    let content = normalizeLineEndings(await fs.readFile(taskPath, "utf-8"));
    
    // Update status
    content = content.replace(/^(status:\s*)\S+$/m, `$1${status}`);
    
    // Update modified date
    content = content.replace(/^(modified:\s*)\S+$/m, `$1${today}`);

    await fs.writeFile(taskPath, content, "utf-8");

    return {
      content: [
        { type: "text", text: `Updated "${title}" status to ${status}` },
      ],
    };
  }
);

// =============================================================================
// SKILL: createMeeting
// =============================================================================
server.tool(
  "createMeeting",
  "Create a new meeting note in 02-People/Meetings/",
  {
    title: z.string().describe("Meeting topic/title"),
    date: z.string().optional().describe("Meeting date in YYYY-MM-DD (defaults to today)"),
    time: z.string().optional().describe("Meeting time in HH:MM format"),
    attendees: z.array(z.string()).optional().describe("List of attendee names"),
    project: z.string().optional().describe("Related project name"),
  },
  async ({ title, date, time, attendees, project }) => {
    const meetingDate = date || await getTodayDate();
    const filename = `${meetingDate} ${title}.md`;
    const meetingPath = path.join(MEETINGS_DIR, filename);

    // Check if already exists
    try {
      await fs.access(meetingPath);
      return {
        content: [{ type: "text", text: `Meeting note "${filename}" already exists.` }],
      };
    } catch {
      // Doesn't exist, continue
    }

    // Read and process template
    let template = await readTemplate("Meeting");
    template = processTemplate(template, { date: meetingDate, title });

    // Update time if provided
    if (time) {
      template = template.replace(/^(time:\s*)$/m, `$1${time}`);
    }

    // Update attendees
    if (attendees && attendees.length > 0) {
      const attendeeLinks = attendees.map(a => `"[[${a}]]"`);
      template = template.replace(/^(attendees:\s*)\[\]$/m, `$1[${attendeeLinks.join(", ")}]`);
      
      // Also fill in the Attendees section
      const attendeeList = attendees.map(a => `- [[${a}]]`).join("\n");
      template = template.replace(/^(## Attendees\n)- $/m, `$1${attendeeList}`);
    }

    // Update project if provided
    if (project) {
      template = template.replace(/^(project:\s*)$/m, `$1"[[${project}]]"`);
    }

    await fs.writeFile(meetingPath, template, "utf-8");

    // Ensure contacts exist for all attendees
    const createdContacts: string[] = [];
    if (attendees) {
      for (const attendee of attendees) {
        const created = await ensureContactExists(attendee, `First met in meeting: ${title}`);
        if (created) createdContacts.push(attendee);
      }
    }

    const contactMsg = createdContacts.length > 0 
      ? ` (created contacts: ${createdContacts.join(", ")})` 
      : "";

    return {
      content: [
        { type: "text", text: `Created meeting: ${filename}${contactMsg}` },
      ],
    };
  }
);

// =============================================================================
// SKILL: create1on1
// =============================================================================
server.tool(
  "create1on1",
  "Create a new 1:1 meeting note in 02-People/1-on-1s/",
  {
    person: z.string().describe("Person's name for the 1:1"),
    date: z.string().optional().describe("Meeting date in YYYY-MM-DD (defaults to today)"),
  },
  async ({ person, date }) => {
    const meetingDate = date || await getTodayDate();
    const filename = `${meetingDate} ${person}.md`;
    const filePath = path.join(ONE_ON_ONES_DIR, filename);

    // Check if already exists
    try {
      await fs.access(filePath);
      return {
        content: [{ type: "text", text: `1:1 note "${filename}" already exists.` }],
      };
    } catch {
      // Doesn't exist, continue
    }

    // Read and process template
    let template = await readTemplate("1-on-1");
    template = processTemplate(template, { date: meetingDate, person });

    // Update person in frontmatter
    template = template.replace(/^(person:\s*)$/m, `$1"[[${person}]]"`);

    // Update the title
    template = template.replace(
      /^# 1:1 - .*$/m,
      `# 1:1 with [[${person}]] - ${meetingDate}`
    );

    await fs.writeFile(filePath, template, "utf-8");

    // Ensure contact exists
    const createdContact = await ensureContactExists(person, `1:1 partner`);
    const contactMsg = createdContact ? ` (created contact for ${person})` : "";

    return {
      content: [
        { type: "text", text: `Created 1:1: ${filename}${contactMsg}` },
      ],
    };
  }
);

// =============================================================================
// SKILL: prepareWeeklyReview
// =============================================================================
server.tool(
  "prepareWeeklyReview",
  "Create a weekly review note with aggregated data from daily notes",
  {
    week: z.string().optional().describe("Week in YYYY-Www format (e.g., 2026-W06), defaults to current week"),
  },
  async ({ week }) => {
    const today = new Date();
    
    // Calculate current week if not provided
    let targetWeek = week;
    if (!targetWeek) {
      const tempDate = new Date(today.getTime());
      tempDate.setHours(0, 0, 0, 0);
      tempDate.setDate(tempDate.getDate() + 3 - ((tempDate.getDay() + 6) % 7));
      const week1 = new Date(tempDate.getFullYear(), 0, 4);
      const weekNum = 1 + Math.round(((tempDate.getTime() - week1.getTime()) / 86400000 - 3 + ((week1.getDay() + 6) % 7)) / 7);
      targetWeek = `${today.getFullYear()}-W${weekNum.toString().padStart(2, "0")}`;
    }

    const filename = `${targetWeek}.md`;
    const filePath = path.join(WEEKLY_DIR, filename);

    // Check if already exists
    try {
      await fs.access(filePath);
      return {
        content: [{ type: "text", text: `Weekly review ${filename} already exists.` }],
      };
    } catch {
      // Doesn't exist, continue
    }

    // Calculate Monday and Friday of the week
    const [yearStr, weekStr] = targetWeek.split("-W");
    const year = parseInt(yearStr);
    const weekNum = parseInt(weekStr);
    
    // Get January 4th of the year (always in week 1)
    const jan4 = new Date(year, 0, 4);
    const dayOfWeek = jan4.getDay() || 7; // Convert Sunday (0) to 7
    
    // Calculate Monday of week 1
    const week1Monday = new Date(jan4);
    week1Monday.setDate(jan4.getDate() - dayOfWeek + 1);
    
    // Calculate Monday of target week
    const monday = new Date(week1Monday);
    monday.setDate(week1Monday.getDate() + (weekNum - 1) * 7);
    
    const friday = new Date(monday);
    friday.setDate(monday.getDate() + 4);

    const tz = await getUserTimezone();
    const mondayStr = toLocalDateString(monday, tz);
    const fridayStr = toLocalDateString(friday, tz);

    // Aggregate completed tasks from daily notes
    const completedTasks: string[] = [];
    const dailyFiles = await fs.readdir(DAILY_DIR);
    
    for (const file of dailyFiles) {
      if (!file.endsWith(".md")) continue;
      const fileDate = file.replace(".md", "");
      if (fileDate >= mondayStr && fileDate <= fridayStr) {
        const content = normalizeLineEndings(
          await fs.readFile(path.join(DAILY_DIR, file), "utf-8")
        );
        
        // Extract completed tasks
        const tasksMatch = content.match(/## Tasks Completed\n([\s\S]*?)(?=\n## )/);
        if (tasksMatch) {
          const tasks = tasksMatch[1].trim().split("\n").filter(line => 
            line.startsWith("- [x]") && line !== "- [x]"
          );
          completedTasks.push(...tasks);
        }
      }
    }

    // Read and process template
    let template = await readTemplate("Weekly Review");
    template = processTemplate(template, { date: mondayStr });

    // Update frontmatter
    template = template.replace(/^(week:\s*).*$/m, `$1${targetWeek}`);
    template = template.replace(/^(start:\s*).*$/m, `$1${mondayStr}`);
    template = template.replace(/^(end:\s*).*$/m, `$1${fridayStr}`);

    // Add aggregated completed tasks
    if (completedTasks.length > 0) {
      const tasksSection = completedTasks.join("\n");
      template = template.replace(
        /^(## Key Accomplishments\n)- $/m,
        `$1${tasksSection}`
      );
    }

    await fs.writeFile(filePath, template, "utf-8");

    return {
      content: [
        { 
          type: "text", 
          text: `Created ${filename} (${mondayStr} to ${fridayStr}) with ${completedTasks.length} completed tasks aggregated` 
        },
      ],
    };
  }
);

// SKILL: triageInbox
// =============================================================================
server.tool(
  "triageInbox",
  "Scan 00-Inbox/ and categorize items into appropriate vault folders (Tasks, Knowledge, Meetings, etc.)",
  {
    dryRun: z.boolean()
      .default(true)
      .describe("If true, only report what would be moved without making changes"),
  },
  async ({ dryRun }) => {
    const INBOX_DIR = path.join(VAULT_ROOT, "00-Inbox");

    let files: string[];
    try {
      files = (await fs.readdir(INBOX_DIR)).filter(f => f.endsWith(".md"));
    } catch {
      return { content: [{ type: "text", text: "00-Inbox/ directory not found or empty." }] };
    }

    if (files.length === 0) {
      return { content: [{ type: "text", text: "Inbox is empty — nothing to triage." }] };
    }

    const results: string[] = [];
    for (const file of files) {
      const filePath = path.join(INBOX_DIR, file);
      const content = normalizeLineEndings(await fs.readFile(filePath, "utf-8"));

      // Determine destination based on frontmatter type or content heuristics
      let destination = "";
      let category = "unknown";

      const typeMatch = content.match(/^type:\s*(.+)$/m);
      const type = typeMatch ? typeMatch[1].trim() : "";

      if (type === "task" || /\b(todo|task|fix|implement|bug)\b/i.test(content.split("\n").slice(0, 5).join(" "))) {
        destination = TASKS_DIR;
        category = "task";
      } else if (type === "meeting" || /\b(meeting|standup|sync|retro)\b/i.test(content.split("\n").slice(0, 5).join(" "))) {
        destination = MEETINGS_DIR;
        category = "meeting";
      } else if (type === "documentation" || type === "reference") {
        destination = path.join(VAULT_ROOT, "03-Knowledge/Documentation");
        category = "documentation";
      } else {
        destination = path.join(VAULT_ROOT, "03-Knowledge/Topics");
        category = "knowledge";
      }

      if (!dryRun) {
        await fs.mkdir(destination, { recursive: true });
        await fs.rename(filePath, path.join(destination, file));
        results.push(`✅ Moved "${file}" → ${category} (${path.relative(VAULT_ROOT, destination)}/)`);
      } else {
        results.push(`📋 "${file}" → ${category} (${path.relative(VAULT_ROOT, destination)}/)`);
      }
    }

    const header = dryRun ? "Triage preview (dry run):" : "Triage complete:";
    return {
      content: [{ type: "text", text: `${header}\n${results.join("\n")}` }],
    };
  }
);

// SKILL: enrichNote
// =============================================================================
server.tool(
  "enrichNote",
  "Enrich a note by adding frontmatter, wiki links, summary section, and structure improvements",
  {
    filePath: z.string().describe("Path to the note file relative to vault root"),
  },
  async ({ filePath }) => {
    const fullPath = path.join(VAULT_ROOT, filePath);
    let content: string;
    try {
      content = normalizeLineEndings(await fs.readFile(fullPath, "utf-8"));
    } catch {
      return { content: [{ type: "text", text: `File not found: ${filePath}` }] };
    }

    const today = await getTodayDate();
    const changes: string[] = [];

    // Add frontmatter if missing
    if (!content.startsWith("---")) {
      const title = path.basename(filePath, ".md");
      const frontmatter = `---\ncreated: ${today}\nmodified: ${today}\ntype: documentation\ncategory: reference\ntags:\n  - enriched\n---\n\n`;
      content = frontmatter + content;
      changes.push("Added frontmatter");
    } else {
      // Update modified date
      content = content.replace(/^(modified:\s*).+$/m, `$1${today}`);
      // Add enriched tag if not present
      if (!content.includes("enriched")) {
        content = content.replace(/^(tags:\s*\n)/m, `$1  - enriched\n`);
      }
      changes.push("Updated modified date and tags");
    }

    // Add Summary section if missing
    if (!/^## Summary/m.test(content)) {
      const endOfFrontmatter = content.indexOf("---", 4);
      if (endOfFrontmatter !== -1) {
        const insertPos = content.indexOf("\n", endOfFrontmatter) + 1;
        content = content.slice(0, insertPos) + "\n## Summary\n\n*Summary to be written.*\n\n" + content.slice(insertPos);
        changes.push("Added Summary section placeholder");
      }
    }

    // Scan for potential wiki links (capitalized multi-word phrases that might be note names)
    const existingLinks = content.match(/\[\[.+?\]\]/g) || [];
    changes.push(`Found ${existingLinks.length} existing wiki links`);

    await fs.writeFile(fullPath, content, "utf-8");

    return {
      content: [
        {
          type: "text",
          text: `Enriched "${filePath}":\n${changes.map(c => `- ${c}`).join("\n")}`,
        },
      ],
    };
  }
);

// SKILL: updateTopicIndex
// =============================================================================
server.tool(
  "updateTopicIndex",
  "Update or create a topic index file in 03-Knowledge/Topics/ by scanning for related notes across the vault",
  {
    topic: z.string().describe("Topic name to create or update index for"),
  },
  async ({ topic }) => {
    const TOPICS_DIR = path.join(VAULT_ROOT, "03-Knowledge/Topics");
    const topicFile = path.join(TOPICS_DIR, `${topic}.md`);
    const today = await getTodayDate();

    await fs.mkdir(TOPICS_DIR, { recursive: true });

    // Scan vault for files mentioning this topic
    const dirsToScan = [
      "01-Work/Tasks",
      "01-Work/Investigations",
      "01-Work/Projects",
      "02-People/Meetings",
      "03-Knowledge/Documentation",
      "04-Periodic/Daily",
    ];

    const relatedNotes: { file: string; context: string }[] = [];
    const topicLower = topic.toLowerCase();

    for (const dir of dirsToScan) {
      const fullDir = path.join(VAULT_ROOT, dir);
      let files: string[];
      try {
        files = (await fs.readdir(fullDir)).filter(f => f.endsWith(".md"));
      } catch {
        continue;
      }

      for (const file of files) {
        try {
          const fileContent = await fs.readFile(path.join(fullDir, file), "utf-8");
          if (fileContent.toLowerCase().includes(topicLower)) {
            // Extract a snippet of context
            const lines = fileContent.split("\n");
            const matchLine = lines.find(l => l.toLowerCase().includes(topicLower));
            const context = matchLine ? matchLine.trim().slice(0, 100) : "";
            relatedNotes.push({ file: `${dir}/${file.replace(".md", "")}`, context });
          }
        } catch {
          continue;
        }
      }
    }

    // Build topic index content
    let existingContent = "";
    try {
      existingContent = normalizeLineEndings(await fs.readFile(topicFile, "utf-8"));
    } catch {
      // New file
    }

    const refsSection = relatedNotes.length > 0
      ? relatedNotes.map(n => `- [[${n.file}]]${n.context ? ` — ${n.context}` : ""}`).join("\n")
      : "*No related notes found yet.*";

    let newContent: string;
    if (existingContent) {
      // Update existing: replace or append Related Notes section
      if (/^## Related Notes/m.test(existingContent)) {
        newContent = existingContent.replace(
          /^## Related Notes[\s\S]*?(?=\n## |\n---|\Z)/m,
          `## Related Notes\n\n${refsSection}\n`
        );
      } else {
        newContent = existingContent.trimEnd() + `\n\n## Related Notes\n\n${refsSection}\n`;
      }
      newContent = newContent.replace(/^(modified:\s*).+$/m, `$1${today}`);
    } else {
      newContent = `---\ncreated: ${today}\nmodified: ${today}\ntype: documentation\ncategory: reference\ntags:\n  - topic\n  - ${topicLower.replace(/\s+/g, "-")}\n---\n\n## ${topic}\n\n*Topic overview to be written.*\n\n## Related Notes\n\n${refsSection}\n`;
    }

    await fs.writeFile(topicFile, newContent, "utf-8");

    return {
      content: [
        {
          type: "text",
          text: `Updated topic index: ${topic} — found ${relatedNotes.length} related notes across the vault`,
        },
      ],
    };
  }
);

// SKILL: generateRoundup
// =============================================================================
server.tool(
  "generateRoundup",
  "Generate a rich daily roundup by aggregating completed tasks, meetings, and key notes from today's daily note and vault activity",
  {
    date: z.string()
      .optional()
      .describe("Date to generate roundup for (YYYY-MM-DD). Defaults to today."),
  },
  async ({ date }) => {
    const targetDate = date || await getTodayDate();
    const dailyPath = path.join(DAILY_DIR, `${targetDate}.md`);

    let dailyContent: string;
    try {
      dailyContent = normalizeLineEndings(await fs.readFile(dailyPath, "utf-8"));
    } catch {
      return {
        content: [{ type: "text", text: `No daily note found for ${targetDate}. Create one first with prepareDailyNote.` }],
      };
    }

    // Extract sections from daily note
    const completedTasks: string[] = [];
    const meetings: string[] = [];
    const notes: string[] = [];
    const carryForward: string[] = [];

    const lines = dailyContent.split("\n");
    let currentSection = "";

    for (const line of lines) {
      if (/^##\s/.test(line)) {
        const heading = line.replace(/^#+\s*/, "").toLowerCase();
        if (heading.includes("completed") || heading.includes("done")) currentSection = "completed";
        else if (heading.includes("meeting")) currentSection = "meetings";
        else if (heading.includes("note") || heading.includes("log")) currentSection = "notes";
        else if (heading.includes("carry") || heading.includes("tomorrow")) currentSection = "carry";
        else currentSection = "";
        continue;
      }

      if (line.trim().startsWith("-") && currentSection) {
        const item = line.trim();
        if (currentSection === "completed") completedTasks.push(item);
        else if (currentSection === "meetings") meetings.push(item);
        else if (currentSection === "notes") notes.push(item);
        else if (currentSection === "carry") carryForward.push(item);
      }
    }

    // Scan for tasks modified today
    let tasksModifiedToday: string[] = [];
    try {
      const taskFiles = (await fs.readdir(TASKS_DIR)).filter(f => f.endsWith(".md"));
      for (const tf of taskFiles) {
        try {
          const tc = await fs.readFile(path.join(TASKS_DIR, tf), "utf-8");
          if (tc.includes(`modified: ${targetDate}`)) {
            const statusMatch = tc.match(/^status:\s*(.+)$/m);
            tasksModifiedToday.push(`- [[${tf.replace(".md", "")}]] (${statusMatch?.[1]?.trim() || "unknown"})`);
          }
        } catch { continue; }
      }
    } catch { /* Tasks dir may not exist */ }

    // Scan for meetings created today
    let meetingsToday: string[] = [];
    try {
      const meetingFiles = (await fs.readdir(MEETINGS_DIR)).filter(f => f.startsWith(targetDate));
      meetingsToday = meetingFiles.map(f => `- [[${f.replace(".md", "")}]]`);
    } catch { /* Meetings dir may not exist */ }

    // Build roundup
    const heading = await formatDateHeading(targetDate);
    const sections = [
      `# Daily Roundup — ${heading}`,
      "",
      "## Accomplishments",
      completedTasks.length > 0 ? completedTasks.join("\n") : "*None logged yet.*",
      "",
      "## Meetings",
      meetingsToday.length > 0 ? meetingsToday.join("\n") : meetings.length > 0 ? meetings.join("\n") : "*No meetings.*",
      "",
      "## Tasks Updated",
      tasksModifiedToday.length > 0 ? tasksModifiedToday.join("\n") : "*No task files modified.*",
      "",
      "## Notes & Context",
      notes.length > 0 ? notes.join("\n") : "*No notes logged.*",
      "",
      "## Carry Forward",
      carryForward.length > 0 ? carryForward.join("\n") : "*Nothing to carry forward.*",
    ];

    const roundupContent = sections.join("\n") + "\n";

    // Append roundup to daily note (or create separate section)
    const separator = "\n---\n\n";
    if (dailyContent.includes("# Daily Roundup")) {
      // Replace existing roundup
      const updated = dailyContent.replace(/# Daily Roundup[\s\S]*$/, roundupContent);
      await fs.writeFile(dailyPath, updated, "utf-8");
    } else {
      await fs.writeFile(dailyPath, dailyContent.trimEnd() + separator + roundupContent, "utf-8");
    }

    const stats = [
      `${completedTasks.length} completed tasks`,
      `${meetingsToday.length || meetings.length} meetings`,
      `${tasksModifiedToday.length} tasks updated`,
      `${carryForward.length} items to carry forward`,
    ].join(", ");

    return {
      content: [
        { type: "text", text: `Generated roundup for ${targetDate}: ${stats}` },
      ],
    };
  }
);

// =============================================================================
// SKILL: getTeamsChatSyncState
// =============================================================================
server.tool(
  "getTeamsChatSyncState",
  "Get the last Teams chat sync timestamp (watermark). Returns ISO timestamp of last successful sync.",
  {},
  async () => {
    const stateDir = await getGlobalStateDir();
    const stateFile = path.join(stateDir, "tcs-last-sync.json");

    try {
      const raw = await fs.readFile(stateFile, "utf-8");
      const state = JSON.parse(raw);
      return {
        content: [{
          type: "text",
          text: JSON.stringify({
            lastSynced: state.lastSynced || null,
            processedThreads: state.processedThreads || [],
            syncCount: state.syncCount || 0,
          }),
        }],
      };
    } catch {
      return {
        content: [{
          type: "text",
          text: JSON.stringify({
            lastSynced: null,
            processedThreads: [],
            syncCount: 0,
          }),
        }],
      };
    }
  }
);

// =============================================================================
// SKILL: updateTeamsChatSyncState
// =============================================================================
server.tool(
  "updateTeamsChatSyncState",
  "Update the Teams chat sync watermark after a successful sync",
  {
    lastSynced: z.string().describe("ISO timestamp of this sync (e.g., 2026-03-09T20:00:00Z)"),
    processedThreadIds: z.array(z.string()).optional().describe("Thread/conversation IDs processed in this sync"),
  },
  async ({ lastSynced, processedThreadIds }) => {
    await mcpLog(`updateTeamsChatSyncState called — lastSynced=${lastSynced}, threads=${processedThreadIds?.length ?? 0}`);
    const stateDir = await getGlobalStateDir();
    const stateFile = path.join(stateDir, "tcs-last-sync.json");

    // Read existing state to merge
    let existing: any = { processedThreads: [], syncCount: 0 };
    try {
      const raw = await fs.readFile(stateFile, "utf-8");
      existing = JSON.parse(raw);
    } catch { /* first run */ }

    // Merge: keep last 500 thread IDs to prevent unbounded growth
    const allThreads = [
      ...(processedThreadIds || []),
      ...(existing.processedThreads || []),
    ];
    const uniqueThreads = [...new Set(allThreads)].slice(0, 500);

    const newState = {
      lastSynced,
      previousSynced: existing.lastSynced || null,
      processedThreads: uniqueThreads,
      syncCount: (existing.syncCount || 0) + 1,
      updatedAt: new Date().toISOString(),
    };

    await fs.writeFile(stateFile, JSON.stringify(newState, null, 2), "utf-8");

    return {
      content: [{
        type: "text",
        text: `✅ Sync state updated. Last synced: ${lastSynced} (sync #${newState.syncCount})`,
      }],
    };
  }
);

// =============================================================================
// SKILL: appendTeamsChatHighlights
// =============================================================================
server.tool(
  "appendTeamsChatHighlights",
  "Append a Teams Chat Highlights section to today's daily note. Idempotent: updates existing section if present.",
  {
    date: z.string().optional().describe("Date in YYYY-MM-DD format (defaults to today)"),
    highlights: z.string().describe("Markdown content for the Teams Chat Highlights section"),
    people: z.array(z.string()).optional().describe("Names of people mentioned in chats (will ensure contacts exist and update their notes)"),
    personNotes: z.array(z.object({
      name: z.string(),
      note: z.string(),
    })).optional().describe("Per-person notes to append to their contact files"),
  },
  async ({ date, highlights, people, personNotes }) => {
    await mcpLog(`appendTeamsChatHighlights called — date=${date}, highlights=${highlights?.length ?? 0} chars, people=${people?.length ?? 0}, personNotes=${personNotes?.length ?? 0}`);
    const targetDate = date || await getTodayDate();
    const dailyPath = path.join(DAILY_DIR, `${targetDate}.md`);
    await mcpLog(`  resolved targetDate=${targetDate}, dailyPath=${dailyPath}`);

    // Ensure daily note exists (auto-create if missing)
    await ensureDailyNote(targetDate);

    let content = normalizeLineEndings(await fs.readFile(dailyPath, "utf-8"));

    // Split incoming highlights into H3 blocks (### [[Person Name]])
    // Each block = one participant's chats. Dedup by checking if the H3 heading already exists.
    function deduplicateHighlights(existing: string, incoming: string): string {
      // Split incoming into blocks at H3 boundaries
      const incomingBlocks = incoming.split(/(?=^### )/m).filter(b => b.trim());
      const newBlocks: string[] = [];
      for (const block of incomingBlocks) {
        // Extract the H3 line for matching
        const h3Match = block.match(/^### .+/);
        if (h3Match) {
          // Check H4 sub-headings within this block — only add those not already present
          const h3Line = h3Match[0];
          const h4Sections = block.split(/(?=^#### )/m);
          const h3Header = h4Sections.shift() || ""; // The H3 line + any content before first H4
          const newH4s: string[] = [];
          for (const h4 of h4Sections) {
            const h4Title = h4.match(/^#### .+/)?.[0] || "";
            // Strip markdown link for comparison: "#### [Topic](url)" → "Topic"
            const h4Plain = h4Title.replace(/^####\s*\[([^\]]+)\].*/, "$1").replace(/^####\s*/, "").trim();
            if (h4Plain && !existing.includes(h4Plain)) {
              newH4s.push(h4.trimEnd());
            }
          }
          if (newH4s.length > 0) {
            // Check if H3 participant already exists
            if (existing.includes(h3Line.trim())) {
              // Participant exists — just add the new H4 sections
              newBlocks.push(newH4s.join("\n\n"));
            } else {
              // New participant — add full block with only new H4s
              newBlocks.push(h3Header.trimEnd() + "\n" + newH4s.join("\n\n"));
            }
          } else if (!h3Match && block.trim()) {
            // No H4s, just raw content — check if it exists
            if (!existing.includes(block.trim())) {
              newBlocks.push(block.trimEnd());
            }
          }
        } else if (block.trim() && !existing.includes(block.trim())) {
          newBlocks.push(block.trimEnd());
        }
      }
      return newBlocks.join("\n\n");
    }

    // Idempotent: merge into existing section or insert new
    if (/^## Teams Chat Highlights/m.test(content)) {
      // Extract existing section content
      const sectionMatch = content.match(/## Teams Chat Highlights\n([\s\S]*?)(?=\n## )/) ||
                           content.match(/## Teams Chat Highlights\n([\s\S]*)$/);
      if (sectionMatch && sectionMatch.index !== undefined) {
        const existingContent = sectionMatch[1].trimEnd();
        const newContent = deduplicateHighlights(existingContent, highlights);
        if (newContent) {
          const mergedSection = `## Teams Chat Highlights\n\n${existingContent}\n\n${newContent}`;
          content = content.slice(0, sectionMatch.index) +
            mergedSection + "\n\n" +
            content.slice(sectionMatch.index + sectionMatch[0].length);
        }
        // If newContent is empty, everything was duplicate — no change needed
      }
    } else {
      // Insert before "## End of Day" or append at the end
      const newSection = `## Teams Chat Highlights\n\n${highlights}`;
      const endOfDayMatch = content.match(/\n## End of Day/);
      if (endOfDayMatch && endOfDayMatch.index !== undefined) {
        content =
          content.slice(0, endOfDayMatch.index) +
          "\n\n" + newSection + "\n" +
          content.slice(endOfDayMatch.index);
      } else {
        content = content.trimEnd() + "\n\n" + newSection + "\n";
      }
    }

    await fs.writeFile(dailyPath, content, "utf-8");

    // Ensure contacts exist and update person notes
    const createdContacts: string[] = [];
    const updatedContacts: string[] = [];

    const allPeople = [
      ...(people || []),
      ...(personNotes || []).map(pn => pn.name),
    ];
    const uniquePeople = [...new Set(allPeople)];

    for (const person of uniquePeople) {
      const created = await ensureContactExists(person, `Referenced in Teams chat on ${targetDate}`);
      if (created) createdContacts.push(person);
    }

    // Append per-person notes
    if (personNotes) {
      for (const { name, note } of personNotes) {
        const contactPath = path.join(CONTACTS_DIR, `${name}.md`);
        try {
          let contactContent = normalizeLineEndings(await fs.readFile(contactPath, "utf-8"));

          // Append under ## Notes section
          const noteEntry = `- [${targetDate}] ${note}`;
          if (/^## Notes/m.test(contactContent)) {
            contactContent = contactContent.replace(
              /^(## Notes\n)([\s\S]*?)$/m,
              (match, header, existing) => {
                const trimmed = existing.trimEnd();
                // Avoid duplicate entries for the same date + note
                if (trimmed.includes(noteEntry)) return match;
                const items = trimmed === "-" ? noteEntry : `${trimmed}\n${noteEntry}`;
                return `${header}${items}\n`;
              }
            );
          } else {
            contactContent += `\n## Notes\n${noteEntry}\n`;
          }

          await fs.writeFile(contactPath, contactContent, "utf-8");
          updatedContacts.push(name);
        } catch {
          // Contact file might not exist yet — already created above
        }
      }
    }

    const stats = [
      `Updated daily note ${targetDate}`,
      createdContacts.length > 0 ? `created contacts: ${createdContacts.join(", ")}` : null,
      updatedContacts.length > 0 ? `updated notes for: ${updatedContacts.join(", ")}` : null,
    ].filter(Boolean).join("; ");

    return {
      content: [{ type: "text", text: `✅ ${stats}` }],
    };
  }
);

// =============================================================================
// SKILL: getTeamsMeetingSyncState
// =============================================================================
server.tool(
  "getTeamsMeetingSyncState",
  "Get the last Teams meeting sync timestamp (watermark). Returns ISO timestamp of last successful sync.",
  {},
  async () => {
    const stateDir = await getGlobalStateDir();
    const stateFile = path.join(stateDir, "tms-last-sync.json");

    try {
      const raw = await fs.readFile(stateFile, "utf-8");
      const state = JSON.parse(raw);
      return {
        content: [{
          type: "text",
          text: JSON.stringify({
            lastSynced: state.lastSynced || null,
            processedMeetings: state.processedMeetings || [],
            syncCount: state.syncCount || 0,
          }),
        }],
      };
    } catch {
      return {
        content: [{
          type: "text",
          text: JSON.stringify({
            lastSynced: null,
            processedMeetings: [],
            syncCount: 0,
          }),
        }],
      };
    }
  }
);

// =============================================================================
// SKILL: updateTeamsMeetingSyncState
// =============================================================================
server.tool(
  "updateTeamsMeetingSyncState",
  "Update the Teams meeting sync watermark after a successful sync",
  {
    lastSynced: z.string().describe("ISO timestamp of this sync (e.g., 2026-03-09T20:00:00Z)"),
    processedMeetingIds: z.array(z.string()).optional().describe("Meeting/event IDs processed in this sync"),
  },
  async ({ lastSynced, processedMeetingIds }) => {
    const stateDir = await getGlobalStateDir();
    const stateFile = path.join(stateDir, "tms-last-sync.json");

    let existing: any = { processedMeetings: [], syncCount: 0 };
    try {
      const raw = await fs.readFile(stateFile, "utf-8");
      existing = JSON.parse(raw);
    } catch { /* first run */ }

    const allMeetings = [
      ...(processedMeetingIds || []),
      ...(existing.processedMeetings || []),
    ];
    const uniqueMeetings = [...new Set(allMeetings)].slice(0, 500);

    const newState = {
      lastSynced,
      previousSynced: existing.lastSynced || null,
      processedMeetings: uniqueMeetings,
      syncCount: (existing.syncCount || 0) + 1,
      updatedAt: new Date().toISOString(),
    };

    await fs.writeFile(stateFile, JSON.stringify(newState, null, 2), "utf-8");

    return {
      content: [{
        type: "text",
        text: `✅ Meeting sync state updated. Last synced: ${lastSynced} (sync #${newState.syncCount})`,
      }],
    };
  }
);

// =============================================================================
// SKILL: appendTeamsMeetingHighlights
// =============================================================================
server.tool(
  "appendTeamsMeetingHighlights",
  "Append a Teams Meeting Highlights section to today's daily note. Idempotent: updates existing section if present.",
  {
    date: z.string().optional().describe("Date in YYYY-MM-DD format (defaults to today)"),
    highlights: z.string().describe("Markdown content for the Teams Meeting Highlights section"),
    people: z.array(z.string()).optional().describe("Names of people mentioned in meetings (will ensure contacts exist and update their notes)"),
    personNotes: z.array(z.object({
      name: z.string(),
      note: z.string(),
    })).optional().describe("Per-person notes to append to their contact files"),
  },
  async ({ date, highlights, people, personNotes }) => {
    const targetDate = date || await getTodayDate();
    const dailyPath = path.join(DAILY_DIR, `${targetDate}.md`);

    // Ensure daily note exists (auto-create if missing)
    await ensureDailyNote(targetDate);

    let content = normalizeLineEndings(await fs.readFile(dailyPath, "utf-8"));

    const sectionContent = `## Teams Meeting Highlights\n\n${highlights}`;

    // Dedup: split incoming into H3 blocks, only append those not already present
    function deduplicateMeetingHighlights(existing: string, incoming: string): string {
      const incomingBlocks = incoming.split(/(?=^### )/m).filter(b => b.trim());
      const newBlocks: string[] = [];
      for (const block of incomingBlocks) {
        const h3Match = block.match(/^### .+/);
        if (h3Match) {
          // Strip markdown link for comparison: "### [Meeting](url)" → "Meeting"
          const h3Plain = h3Match[0].replace(/^###\s*\[([^\]]+)\].*/, "$1").replace(/^###\s*/, "").trim();
          if (h3Plain && !existing.includes(h3Plain)) {
            newBlocks.push(block.trimEnd());
          }
        } else if (block.trim() && !existing.includes(block.trim())) {
          newBlocks.push(block.trimEnd());
        }
      }
      return newBlocks.join("\n\n");
    }

    if (/^## Teams Meeting Highlights/m.test(content)) {
      const sectionMatch = content.match(/## Teams Meeting Highlights\n([\s\S]*?)(?=\n## )/) ||
                           content.match(/## Teams Meeting Highlights\n([\s\S]*)$/);
      if (sectionMatch && sectionMatch.index !== undefined) {
        const existingContent = sectionMatch[1].trimEnd();
        const newContent = deduplicateMeetingHighlights(existingContent, highlights);
        if (newContent) {
          const mergedSection = `## Teams Meeting Highlights\n\n${existingContent}\n\n${newContent}`;
          content = content.slice(0, sectionMatch.index) +
            mergedSection + "\n\n" +
            content.slice(sectionMatch.index + sectionMatch[0].length);
        }
      }
    } else {
      // Insert before Teams Chat Highlights or End of Day, or append at end
      const insertBefore = content.match(/\n## Teams Chat Highlights|\n## End of Day/);
      if (insertBefore && insertBefore.index !== undefined) {
        content =
          content.slice(0, insertBefore.index) +
          "\n\n" + sectionContent + "\n" +
          content.slice(insertBefore.index);
      } else {
        content = content.trimEnd() + "\n\n" + sectionContent + "\n";
      }
    }

    await fs.writeFile(dailyPath, content, "utf-8");

    const createdContacts: string[] = [];
    const updatedContacts: string[] = [];

    const allPeople = [
      ...(people || []),
      ...(personNotes || []).map(pn => pn.name),
    ];
    const uniquePeople = [...new Set(allPeople)];

    for (const person of uniquePeople) {
      const created = await ensureContactExists(person, `Attended meeting on ${targetDate}`);
      if (created) createdContacts.push(person);
    }

    if (personNotes) {
      for (const { name, note } of personNotes) {
        const contactPath = path.join(CONTACTS_DIR, `${name}.md`);
        try {
          let contactContent = normalizeLineEndings(await fs.readFile(contactPath, "utf-8"));

          const noteEntry = `- [${targetDate}] ${note}`;
          if (/^## Notes/m.test(contactContent)) {
            contactContent = contactContent.replace(
              /^(## Notes\n)([\s\S]*?)$/m,
              (match, header, existing) => {
                const trimmed = existing.trimEnd();
                if (trimmed.includes(noteEntry)) return match;
                const items = trimmed === "-" ? noteEntry : `${trimmed}\n${noteEntry}`;
                return `${header}${items}\n`;
              }
            );
          } else {
            contactContent += `\n## Notes\n${noteEntry}\n`;
          }

          await fs.writeFile(contactPath, contactContent, "utf-8");
          updatedContacts.push(name);
        } catch {
          // Contact file might not exist yet
        }
      }
    }

    const stats = [
      `Updated daily note ${targetDate} with meeting highlights`,
      createdContacts.length > 0 ? `created contacts: ${createdContacts.join(", ")}` : null,
      updatedContacts.length > 0 ? `updated notes for: ${updatedContacts.join(", ")}` : null,
    ].filter(Boolean).join("; ");

    return {
      content: [{ type: "text", text: `✅ ${stats}` }],
    };
  }
);

// =============================================================================
// Start the server
// =============================================================================
async function main() {
  await mcpLog(`Server starting — VAULT_ROOT=${VAULT_ROOT}`);
  const transport = new StdioServerTransport();
  await server.connect(transport);
  await mcpLog("Server connected on stdio");
  console.error("DuckyAI Vault MCP Server running on stdio");
}

main().catch(console.error);
