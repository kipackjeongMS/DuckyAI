import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import * as fs from "fs/promises";
import * as path from "path";

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

// Initialize MCP Server
const server = new McpServer({
  name: "duckyai-vault",
  version: "1.0.0",
});

// Helper: Format date as "Friday, February 6, 2026"
function formatDateHeading(dateStr: string): string {
  const date = new Date(dateStr + "T12:00:00"); // Noon to avoid timezone issues
  return date.toLocaleDateString("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
    year: "numeric",
  });
}

// Helper: Get today's date in YYYY-MM-DD format
function getTodayDate(): string {
  return new Date().toISOString().split("T")[0];
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

// Helper: Extract carry-forward items from a daily note
// Pulls uncompleted tasks from Focus Today, Other Tasks, and Carry forward sections
async function extractCarryForward(filePath: string): Promise<string[]> {
  try {
    const content = await fs.readFile(filePath, "utf-8");
    const uncompleted: string[] = [];

    // Extract from Focus Today section (includes Primary and Other Tasks subsections)
    const focusMatch = content.match(/## Focus Today\n([\s\S]*?)(?=\n## Carried from yesterday|\n## Meetings)/);
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
    const today = getTodayDate();
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
    const targetDate = date || getTodayDate();
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
    const dayHeading = formatDateHeading(targetDate);
    const carrySection =
      carryForward.length > 0 ? carryForward.join("\n") : "- (none)";

    // Template matches Templates/Daily Note.md structure
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
${carrySection}

## Meetings
- 

## Tasks Completed
- [x] 

## Notes


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
    const today = getTodayDate();
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
    const today = getTodayDate();
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
    const today = getTodayDate();
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
    const today = getTodayDate();

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
    const today = getTodayDate();

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
    const meetingDate = date || getTodayDate();
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
    const meetingDate = date || getTodayDate();
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

    const mondayStr = monday.toISOString().split("T")[0];
    const fridayStr = friday.toISOString().split("T")[0];

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

// =============================================================================
// Start the server
// =============================================================================
async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error("DuckyAI Vault MCP Server running on stdio");
}

main().catch(console.error);
