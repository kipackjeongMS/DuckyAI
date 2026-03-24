import { exec } from "node:child_process";

/** Run `az account show` to check login, run `az login` if needed. */
export function ensureAzLogin(): Promise<void> {
  return new Promise((resolve, reject) => {
    // Use exec (shell: true) so Windows can resolve az.cmd from PATH
    exec("az account show --query name -o tsv", (err) => {
      if (!err) {
        resolve();
        return;
      }
      // Not logged in — launch interactive az login
      exec("az login", (loginErr) => {
        if (loginErr) {
          reject(new Error(`az login failed: ${loginErr.message}`));
        } else {
          resolve();
        }
      });
    });
  });
}
