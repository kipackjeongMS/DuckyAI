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

    const today = getTodayDate();
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
    const today = getTodayDate();

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
    const targetDate = date || getTodayDate();
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
    const heading = formatDateHeading(targetDate);
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

// SKILL: startOrchestrator
// =============================================================================
server.tool(
  "startOrchestrator",
  "Start the DuckyAI orchestrator daemon (file watcher + cron scheduler for automated agents)",
  {},
  async () => {
    const { exec } = await import("child_process");
    const orchestratorYaml = path.join(VAULT_ROOT, "orchestrator.yaml");

    try {
      await fs.access(orchestratorYaml);
    } catch {
      return { content: [{ type: "text", text: "orchestrator.yaml not found. Run 'duckyai init' first." }] };
    }

    // Check if already running
    const pidFile = path.join(VAULT_ROOT, ".orchestrator.pid");
    try {
      const pid = (await fs.readFile(pidFile, "utf-8")).trim();
      try {
        process.kill(parseInt(pid), 0);
        return { content: [{ type: "text", text: `Orchestrator already running (PID ${pid}).` }] };
      } catch {
        // PID not running, clean up stale pid file
      }
    } catch {
      // No pid file
    }

    return new Promise((resolve) => {
      const child = exec(
        `cd "${VAULT_ROOT}" && python -m duckyai_cli.main.cli -o &`,
        { cwd: VAULT_ROOT },
        (error) => {
          if (error) {
            resolve({ content: [{ type: "text", text: `Failed to start orchestrator: ${error.message}` }] });
          }
        }
      );
      if (child.pid) {
        fs.writeFile(pidFile, String(child.pid), "utf-8").catch(() => {});
      }
      setTimeout(() => {
        resolve({ content: [{ type: "text", text: `✅ Orchestrator daemon started. File watcher and cron scheduler are active.` }] });
      }, 2000);
    });
  }
);

// SKILL: stopOrchestrator
// =============================================================================
server.tool(
  "stopOrchestrator",
  "Stop the running DuckyAI orchestrator daemon",
  {},
  async () => {
    const pidFile = path.join(VAULT_ROOT, ".orchestrator.pid");
    try {
      const pid = (await fs.readFile(pidFile, "utf-8")).trim();
      try {
        process.kill(parseInt(pid), "SIGTERM");
        await fs.unlink(pidFile).catch(() => {});
        return { content: [{ type: "text", text: `✅ Orchestrator stopped (PID ${pid}).` }] };
      } catch {
        await fs.unlink(pidFile).catch(() => {});
        return { content: [{ type: "text", text: "Orchestrator was not running (stale PID file cleaned up)." }] };
      }
    } catch {
      return { content: [{ type: "text", text: "No orchestrator is currently running." }] };
    }
  }
);

// SKILL: orchestratorStatus
// =============================================================================
server.tool(
  "orchestratorStatus",
  "Show the current status of the DuckyAI orchestrator (running/stopped, loaded agents, schedules)",
  {},
  async () => {
    const orchestratorYaml = path.join(VAULT_ROOT, "orchestrator.yaml");
    let configContent: string;
    try {
      configContent = await fs.readFile(orchestratorYaml, "utf-8");
    } catch {
      return { content: [{ type: "text", text: "orchestrator.yaml not found." }] };
    }

    // Check if running
    const pidFile = path.join(VAULT_ROOT, ".orchestrator.pid");
    let running = false;
    let pid = "";
    try {
      pid = (await fs.readFile(pidFile, "utf-8")).trim();
      process.kill(parseInt(pid), 0);
      running = true;
    } catch {
      running = false;
    }

    // Parse agents from yaml (simple regex extraction)
    const agentNames = [...configContent.matchAll(/name:\s*(.+)/g)].map(m => m[1].trim());
    const cronJobs = [...configContent.matchAll(/cron:\s*(.+)/g)].map(m => m[1].trim());

    const status = [
      `**Orchestrator**: ${running ? `🟢 Running (PID ${pid})` : "🔴 Stopped"}`,
      `**Vault**: ${VAULT_ROOT}`,
      `**Agents**: ${agentNames.length}`,
      ...agentNames.map(a => `  - ${a}`),
      `**Scheduled jobs**: ${cronJobs.length}`,
      ...cronJobs.map(c => `  - ${c}`),
    ].join("\n");

    return { content: [{ type: "text", text: status }] };
  }
);

// SKILL: triggerAgent
// =============================================================================
server.tool(
  "triggerAgent",
  "Manually trigger a DuckyAI orchestrator agent by abbreviation (e.g., EIC, GDR, TIU, EDM)",
  {
    agent: z.string().describe("Agent abbreviation (e.g., EIC, GDR, TIU, EDM)"),
    file: z.string().optional().describe("Optional input file path relative to vault root"),
  },
  async ({ agent, file }) => {
    const { execSync } = await import("child_process");
    let cmd = `python -m duckyai_cli.main.cli trigger ${agent}`;
    if (file) {
      cmd += ` --file "${file}"`;
    }

    try {
      const output = execSync(cmd, {
        cwd: VAULT_ROOT,
        timeout: 10000,
        encoding: "utf-8",
      });
      return { content: [{ type: "text", text: `✅ Triggered agent: ${agent}\n${output}` }] };
    } catch (error: any) {
      return { content: [{ type: "text", text: `Failed to trigger ${agent}: ${error.message}` }] };
    }
  }
);

// SKILL: listAgents
// =============================================================================
server.tool(
  "listAgents",
  "List all available DuckyAI orchestrator agents with their triggers, input/output paths, and schedules",
  {},
  async () => {
    const orchestratorYaml = path.join(VAULT_ROOT, "orchestrator.yaml");
    let configContent: string;
    try {
      configContent = await fs.readFile(orchestratorYaml, "utf-8");
    } catch {
      return { content: [{ type: "text", text: "orchestrator.yaml not found." }] };
    }

    // Parse nodes section
    const lines = configContent.split("\n");
    const agents: string[] = [];
    let currentAgent = "";

    for (const line of lines) {
      const nameMatch = line.match(/^\s+name:\s*(.+)/);
      const inputMatch = line.match(/^\s+input_path:\s*(.+)/);
      const outputMatch = line.match(/^\s+output_path:\s*(.+)/);
      const cronMatch = line.match(/^\s+cron:\s*(.+)/);
      const enabledMatch = line.match(/^\s+enabled:\s*(.+)/);

      if (nameMatch) {
        if (currentAgent) agents.push(currentAgent);
        currentAgent = `**${nameMatch[1].trim()}**`;
      }
      if (inputMatch && currentAgent) currentAgent += ` | Input: \`${inputMatch[1].trim()}\``;
      if (outputMatch && currentAgent) currentAgent += ` | Output: \`${outputMatch[1].trim()}\``;
      if (cronMatch && currentAgent) currentAgent += ` | Cron: \`${cronMatch[1].trim()}\``;
      if (enabledMatch && currentAgent) currentAgent += ` | Enabled: ${enabledMatch[1].trim()}`;
    }
    if (currentAgent) agents.push(currentAgent);

    return {
      content: [
        { type: "text", text: `Available agents:\n${agents.map(a => `- ${a}`).join("\n")}` },
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
