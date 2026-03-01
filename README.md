# Terraform Plan Visualizer

Fast, shell-based Terraform plan visualizer. Parses `terraform plan` text output into a beautiful, self-contained HTML report.

![Screenshot](https://img.shields.io/badge/output-single%20HTML%20file-7B42BC?style=flat-square)
![Dependencies](https://img.shields.io/badge/dependencies-bash%20%2B%20awk%20%2B%20python3-blue?style=flat-square)
![License](https://img.shields.io/badge/license-MIT-green?style=flat-square)

## Features

- **Single self-contained HTML file** - no server, no dependencies, open in any browser
- **Fast shell extraction** - single-pass `awk` parsing, no line-by-line loops
- **Summary dashboard** - color-coded cards for create/update/destroy/replace/import/move/read
- **Multi-select filters** - toggle action types independently
- **Search** - filter resources by address, type, name, or module
- **Module sidebar** - browse resources grouped by Terraform module
- **Collapsible diff view** - syntax-highlighted attribute changes per resource
- **Raw diff tab** - full HCL diff block with color highlighting
- **Dark/Light theme** - persists via localStorage
- **Forces replacement badges** - highlights attributes causing resource replacement
- **Responsive** - works on desktop and mobile
- **Zero external dependencies** - all CSS/JS inline

## Quick Start

```bash
# Capture plan output to a file
terraform plan -no-color 2>&1 | tee plan.log

# Generate the report
./build-report.sh plan.log

# Or specify output path
./build-report.sh plan.log my-report.html
```

On macOS, the report auto-opens in your default browser.

## Requirements

- `bash`
- `awk` (BSD or GNU)
- `python3` (for JSON injection into template)
- `rg` ([ripgrep](https://github.com/BurntSushi/ripgrep)) - for fast text extraction

## How It Works

```
plan.log ──> extract.sh ──> JSON ──> build-report.sh ──> report.html
              (awk/rg)              (python3 inject)
```

1. **`extract.sh`** - Parses the plan text output in a single `awk` pass. Extracts resource actions, attribute changes, moves, imports, warnings, and summary counts. Outputs structured JSON.

2. **`template.html`** - Self-contained HTML dashboard with a `__PLAN_DATA__` placeholder. All CSS and JavaScript are inline.

3. **`build-report.sh`** - Orchestrator that runs the extractor, validates JSON, injects it into the template, and produces the final HTML file.

## What It Extracts

| Data | Source Pattern |
|------|---------------|
| Creates | `# resource.addr will be created` |
| Updates | `# resource.addr will be updated in-place` |
| Destroys | `# resource.addr will be destroyed` |
| Replaces | `# resource.addr must be replaced` + `-/+` blocks |
| Moves | `# old.addr has moved to new.addr` |
| Imports | `# (imported from "azure-resource-id")` |
| Reads | `# data.addr will be read during apply` |
| Attribute changes | `~ attr = "old" -> "new"` |
| Forces replacement | `# forces replacement` annotations |
| Warnings | `Warning:` blocks after the plan summary |

## Color Scheme

| Action | Color | Hex |
|--------|-------|-----|
| Create | Green | `#107c10` |
| Update | Blue | `#0078d4` |
| Destroy | Red | `#a4262c` |
| Replace | Orange | `#d83b01` |
| Import | Purple | `#5c2d91` |
| Move | Gray | `#737373` |
| Read | Teal | `#038387` |

## ANSI Color Handling

The extractor automatically strips ANSI escape codes. You can capture plan output with or without `-no-color`:

```bash
# Both work
terraform plan -no-color 2>&1 | tee plan.log
terraform plan 2>&1 | tee plan.log
```

## License

MIT
