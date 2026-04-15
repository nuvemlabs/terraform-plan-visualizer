# Workflow State: Real-World Scenario Verification (flightchecker)

## Status: ANALYSIS COMPLETE - NEEDS_PLAN_APPROVAL

## Issues Found

### 1. Raw Diff tab is broken - displays as single line
- **Root cause**: In `extract.sh` awk, `diff_block` is built using literal `"\\n"` (backslash+n text) instead of actual newlines
- After `json_escape()` doubles backslashes, the JSON contains `\\n` which JavaScript parses as the literal text `\n`, not a newline character
- `highlightDiff()` in template.html calls `raw.split('\n')` on actual newlines, so it never splits - the entire diff renders as one unbroken line

### 2. Changes tab shows too few attributes for create/destroy
- Create: hardcoded to only extract `name`, `id`, `location`, `resource_group_name`, `description`
- Destroy: hardcoded to only `name`, `id`, `description`, `resource_group_name` (missing `location`)
- All other attributes are silently hidden, making the Changes tab incomplete

### 3. Changes tab value formatting is adequate but could improve
- The old→new display works but long values are cramped in the fixed 200px/1fr grid
- The `→` arrow between old/new values blends into the text

## Plan

### Step 1: Fix diffBlock newline encoding in extract.sh
- Change all `diff_block = diff_block "\\n"` to `diff_block = diff_block "\n"` (real newlines)
- Add `gsub(/\n/, "\\n", s)` to the `json_escape()` function to properly escape newlines for JSON output
- This ensures the JSON contains `\n` (JSON escape), which JavaScript parses as actual newline characters

### Step 2: Extract all attributes for create/destroy in extract.sh
- Remove the `if (a == "name" || a == "id" || ...)` whitelist filter for both create and destroy
- All `+ attr = value` lines will emit changes for create
- All `- attr = value` lines will emit changes for destroy
- This makes the Changes tab show every attribute, matching the Raw Diff

### Step 3: Improve Changes tab display in template.html
- Widen attribute column or make it flexible for long attribute names
- Add clearer visual separation between old and new values (e.g., show on separate lines for `change` action)
- Better color-coding and spacing for the arrow separator
- Improve the grid layout from rigid `200px 1fr` to something more responsive

### Step 4: Improve Raw Diff display in template.html
- Add line numbers to the diff block
- Ensure proper indentation is preserved
- Verify syntax highlighting works correctly with actual newlines

### Step 5: Rebuild demo and verify in browser
- Regenerate report from mixed_actions.log
- Browse with Playwright to verify both tabs render correctly
- Test with replace and heredoc fixtures for edge cases

### Step 6: Run existing tests
- Run test suite to ensure no regressions

## Log
- Browsed the report in browser, confirmed Raw Diff renders as single line
- Confirmed Changes tab shows limited attributes for create/destroy
- Traced root cause to awk `\\n` vs `\n` in extract.sh
- Plan approved, dispatched two parallel agents (extract.sh + template.html)
- Agent 1: Fixed json_escape newline handling + removed attribute whitelists in extract.sh
- Agent 2: Improved change-line layout, stacked old/new display, added diff line numbers in template.html
- All 126 tests pass
- Browser verified: mixed_actions (destroy shows 3 attrs, update shows stacked old/new, raw diff has numbered lines)
- Browser verified: single_replace (REPLACE badges, forces replacement in raw diff, 7 numbered lines)
- Found multi-line change values broken (ip_range_filter showed just "[")
- Fixed: awk now accumulates multi-line arrays/objects via bracket depth tracking
- Fixed: template renders multi-line values as syntax-highlighted code blocks
- Browser verified: cosmos ip_range_filter shows full 5-IP array diff with line numbers

---

## TDD Fix: Import Parsing Bugs (Dual-Tag Approach) - 2026-04-15

### Status: COMPLETE

### Phases
1. **RED** - Create fixtures + failing tests - DONE (17 failures, 131 passes)
2. **GREEN** - Fix extract.sh + template.html - DONE (148/148 pass)
3. **VERIFY** - Run all tests + flightchecker validation - DONE

### Log
- Phase 1: Created 3 fixtures (pure_import, import_mixed, create_multiline) + 27 new tests
- Phase 1: Confirmed 17 failures mapping to BUGs 1,2,3,5,6
- Phase 2: Fixed extract.sh (BUGs 1,2,3,5,6) + template.html (filter, badges, icon)
- Phase 3: All 148 tests pass, flightchecker verified (72 resources, 41 imported, 0 unknowns)

---

## Real-World Verification: flightchecker (2026-04-15)

### Ground Truth (tfplan.json)
- 72 total resource_changes: 13 create, 18 update, 18 read, 23 no-op, 0 destroy/replace
- Plan summary line: "41 to import, 13 to add, 18 to change, 0 to destroy"

### Issues Found in extract.sh + report

#### BUG 1: "Update + Import" resources misclassified as "import" (18 resources)
- **Location**: extract.sh line 266: `if (pending_action == "update") pending_action = "import"`
- Header says `will be updated in-place`, so action = "update"
- Annotation line says `(imported from "...")`, code overwrites action to "import"
- These are update-with-import, primary action is update; import is metadata
- All 18 update resources get wrong action in the report

#### BUG 2: Pure "import" (no-change) resources classified as "unknown" (23 resources)
- **Location**: extract.sh lines 226-251 (action detection)
- No pattern checks for `will be imported` in the header matching
- Falls through to `pending_action = "unknown"`
- Block-start regex on line 278 expects prefix symbol (+/~/</-)
- Pure import blocks have NO prefix, just `    resource "..."` - partially caught by line 287 fallback

#### BUG 3: Summary counts internally inconsistent (adds to 90, not 72)
- Summary: create=13 + update=18 + read=18 + import=41 = 90
- Total field = 72 (from resource count grep)
- update=18 comes from Plan: summary line, import=41 also from Plan: line
- But 18 of those import resources are ALSO counted as update
- Double-counting: 18 resources counted in both update and import

#### BUG 4: 23 "unknown" resources invisible in HTML report
- template.html allActions = ['destroy','replace','update','create','import','move','read']
- No "unknown" entry, no filter pill, activeFilters["unknown"] never set
- getFiltered() excludes all 23 resources - they can never be displayed

#### BUG 5: Multi-line value parsing broken for create (+) lines (13 instances)
- Arrays like `key_permissions = [...]` and objects like `tags = {...}` truncated
- Multi-line accumulator only handles `~` (change) lines
- `+` (add) line handler on lines 416-432 has no multi-line support
- Values captured as just `"["` or `"{"` instead of full content

#### BUG 6: Data source type parsing wrong (18 resources)
- For `data.azurerm_application_insights.stack-appinsights`
- type = "data", name = "azurerm_application_insights" (wrong)
- Should be: type = "azurerm_application_insights", name = "stack-appinsights"
- Parser doesn't handle `data.` prefix in resource part

#### BUG 7: Warning extraction incomplete
- Plan says "(and 3 more similar warnings elsewhere)" = 4 total
- Only 1 warning extracted
