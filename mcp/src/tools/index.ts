/** Every tool the server offers. To add a feature, write `tools/<feature>.ts`
 * exporting a list of tools and add it here. */

import { accountTools } from "./account.ts";
import { customerTools } from "./customers.ts";
import { dashboardTools } from "./dashboard.ts";
import type { ToolDef } from "./define.ts";
import { eolTools } from "./eol.ts";
import { estimateTools } from "./estimates.ts";
import { packageTools } from "./packages.ts";
import { projectTools } from "./projects.ts";
import { sprintTools } from "./sprints.ts";
import { taskTools } from "./tasks.ts";
import { vulnerabilityTools } from "./vulnerabilities.ts";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export const allTools: readonly ToolDef<any>[] = [
  ...accountTools,
  ...dashboardTools,
  ...vulnerabilityTools,
  ...packageTools,
  ...eolTools,
  ...projectTools,
  ...customerTools,
  ...estimateTools,
  ...taskTools,
  ...sprintTools,
];
