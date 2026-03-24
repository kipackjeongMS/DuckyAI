import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { parse as parseYaml } from "yaml";
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
/** Walk up from CWD or env var to find the vault root (contains duckyai.yml). */
export function resolveVaultPath() {
    const fromEnv = process.env.DUCKYAI_VAULT_ROOT;
    if (fromEnv && fs.existsSync(path.join(fromEnv, "duckyai.yml"))) {
        return fromEnv;
    }
    // Walk up from this file's directory to find duckyai.yml
    let dir = path.resolve(__dirname, "../..");
    for (let i = 0; i < 10; i++) {
        if (fs.existsSync(path.join(dir, "duckyai.yml"))) {
            return dir;
        }
        const parent = path.dirname(dir);
        if (parent === dir)
            break;
        dir = parent;
    }
    throw new Error("Could not find duckyai.yml. Set DUCKYAI_VAULT_ROOT.");
}
export function readConfig(vaultPath) {
    const raw = fs.readFileSync(path.join(vaultPath, "duckyai.yml"), "utf-8");
    return parseYaml(raw);
}
