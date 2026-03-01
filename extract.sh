#!/usr/bin/env bash
# extract.sh - Extract structured JSON from a terraform plan.log
# Usage: ./extract.sh <plan.log>
# Uses rg, sed, awk for bulk extraction. No line-by-line bash loops over the file.
set -euo pipefail

PLAN_FILE="${1:?Usage: extract.sh <plan.log>}"
[[ -f "$PLAN_FILE" ]] || { echo "Error: File not found: $PLAN_FILE" >&2; exit 1; }

FILENAME=$(basename "$PLAN_FILE")
GENERATED=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

# --- Temp files with cleanup trap ---
TMPDIR_WORK=$(mktemp -d /tmp/tf-extract.XXXXXX)
trap 'rm -rf "$TMPDIR_WORK"' EXIT INT TERM

CLEAN_FILE="$TMPDIR_WORK/plan-clean.log"
RESOURCES_FILE="$TMPDIR_WORK/resources.json"
WARNINGS_FILE="$TMPDIR_WORK/warnings.json"

# --- Strip ANSI escape codes ---
sed 's/\x1b\[[0-9;]*m//g' "$PLAN_FILE" > "$CLEAN_FILE"

# --- Find key line numbers ---
ACTIONS_LINE=$(rg -n "^Terraform will perform the following actions:" "$CLEAN_FILE" | head -1 | cut -d: -f1)
if [[ -z "$ACTIONS_LINE" ]]; then
  REFRESH_COUNT=$(rg -c "Refreshing state\.\.\." "$CLEAN_FILE" 2>/dev/null || echo "0")
  cat <<ENDJSON
{
  "metadata": {"generated": "$GENERATED", "source": "$FILENAME", "terraform_version": ""},
  "summary": {"create": 0, "update": 0, "destroy": 0, "replace": 0, "move": 0, "read": 0, "import": 0, "total": 0},
  "resources": [],
  "warnings": [],
  "refreshCount": $REFRESH_COUNT
}
ENDJSON
  exit 0
fi

REFRESH_COUNT=$(head -n "$ACTIONS_LINE" "$CLEAN_FILE" | rg -c "Refreshing state\.\.\." 2>/dev/null || echo "0")

# --- Extract summary line ---
SUMMARY_LINE=$(rg "^Plan:" "$CLEAN_FILE" | head -1)
S_IMPORT=$(echo "$SUMMARY_LINE" | rg -o '[0-9]+ to import' | rg -o '[0-9]+' || echo "0")
S_ADD=$(echo "$SUMMARY_LINE" | rg -o '[0-9]+ to add' | rg -o '[0-9]+' || echo "0")
S_CHANGE=$(echo "$SUMMARY_LINE" | rg -o '[0-9]+ to change' | rg -o '[0-9]+' || echo "0")
S_DESTROY=$(echo "$SUMMARY_LINE" | rg -o '[0-9]+ to destroy' | rg -o '[0-9]+' || echo "0")

PLAN_LINE_COUNT=$(wc -l < "$CLEAN_FILE" | tr -d ' ')
SUMMARY_LINE_NUM=$(rg -n "^Plan:" "$CLEAN_FILE" | head -1 | cut -d: -f1)

# === Single awk pass: extract resources with diffBlock + parsed changes ===
awk -v actions_start="$ACTIONS_LINE" -v summary_line="${SUMMARY_LINE_NUM:-$PLAN_LINE_COUNT}" '
function json_escape(s) {
  gsub(/\\/, "\\\\", s)
  gsub(/"/, "\\\"", s)
  gsub(/\t/, "\\t", s)
  gsub(/\r/, "", s)
  return s
}

function flush_resource() {
  if (pending_address == "") return
  if (!resource_started) return

  # Close diffBlock string
  printf ",\n    \"diffBlock\": \"%s\"", json_escape(diff_block)
  printf "\n  }"
  resource_started = 0
}

function start_resource() {
  if (pending_address == "") return

  # Parse module path from address
  addr = pending_address
  mod = "root"
  res_part = addr
  rkey = ""

  if (addr ~ /^module\./) {
    mod = ""
    rest = addr
    while (match(rest, /^module\.[a-zA-Z_][a-zA-Z0-9_-]*/)) {
      seg = substr(rest, RSTART, RLENGTH)
      if (mod != "") mod = mod "."
      mod = mod seg
      rest = substr(rest, RSTART + RLENGTH)
      if (match(rest, /^\[[^\]]*\]/)) {
        mod = mod substr(rest, RSTART, RLENGTH)
        rest = substr(rest, RSTART + RLENGTH)
      }
      sub(/^\./, "", rest)
    }
    res_part = rest
  }

  # Parse type.name from resource part
  rtype = res_part
  rname = res_part
  if (match(res_part, /^[a-zA-Z_]+\.[a-zA-Z_][a-zA-Z0-9_-]*/)) {
    full = substr(res_part, RSTART, RLENGTH)
    d = index(full, ".")
    rtype = substr(full, 1, d-1)
    rname = substr(full, d+1)
    trail = substr(res_part, RLENGTH+1)
    if (trail ~ /^\[/) {
      rkey = trail
      gsub(/^\["|"\]$/, "", rkey)
      rname = rname trail
    }
  }

  if (resource_count > 0) printf ","
  resource_count++

  printf "\n  {\n"
  printf "    \"address\": \"%s\",\n", json_escape(pending_address)
  printf "    \"module\": \"%s\",\n", json_escape(mod)
  printf "    \"type\": \"%s\",\n", json_escape(rtype)
  printf "    \"name\": \"%s\",\n", json_escape(rname)
  if (rkey != "") {
    printf "    \"key\": \"%s\",\n", json_escape(rkey)
  }
  printf "    \"action\": \"%s\"", json_escape(pending_action)
  if (pending_move_from != "") {
    printf ",\n    \"moveFrom\": \"%s\"", json_escape(pending_move_from)
  }
  if (pending_import_id != "") {
    printf ",\n    \"importId\": \"%s\"", json_escape(pending_import_id)
  }
  printf ",\n    \"forcesReplacement\": %s", (forces_replacement ? "true" : "false")
  printf ",\n    \"changes\": ["
  change_count = 0
  diff_block = ""
  resource_started = 1
}

function emit_change(attr, old, new_val, act, forces) {
  if (change_count > 0) printf ","
  printf "\n      {\"attribute\": \"%s\", \"old\": \"%s\", \"new\": \"%s\", \"action\": \"%s\"", json_escape(attr), json_escape(old), json_escape(new_val), act
  if (forces) {
    printf ", \"forcesReplacement\": true"
  }
  printf "}"
  change_count++
}

BEGIN {
  in_actions = 0
  resource_count = 0
  resource_started = 0
  in_resource = 0
  in_heredoc = 0
  heredoc_marker = ""
  change_count = 0
  pending_header = 0
  pending_address = ""
  pending_action = ""
  pending_move_from = ""
  pending_import_id = ""
  forces_replacement = 0
  diff_block = ""
  printf "["
}

NR == actions_start { in_actions = 1; next }
NR >= summary_line { in_actions = 0 }
!in_actions { next }

# Track heredoc blocks to avoid premature block termination
in_resource && in_heredoc {
  # Append to diff block
  if (diff_block != "") diff_block = diff_block "\\n"
  diff_block = diff_block $0
  # Check for heredoc end marker
  stripped = $0
  gsub(/^[[:space:]]+/, "", stripped)
  if (stripped == heredoc_marker) {
    in_heredoc = 0
  }
  next
}

# Detect heredoc start: <<-EOT or <<-EOF or <<EOT etc
in_resource && /<<-?[A-Z]+/ {
  if (diff_block != "") diff_block = diff_block "\\n"
  diff_block = diff_block $0
  match($0, /<<-?([A-Z]+)/)
  hd = substr($0, RSTART, RLENGTH)
  gsub(/<<-?/, "", hd)
  heredoc_marker = hd
  in_heredoc = 1
  next
}

# Resource header comment line
/^  # [a-zA-Z]/ {
  # Flush previous resource
  if (in_resource) {
    printf "\n    ]"
    flush_resource()
    in_resource = 0
  }

  header = $0
  sub(/^  # /, "", header)

  pending_action = ""
  pending_address = ""
  pending_move_from = ""
  pending_import_id = ""
  forces_replacement = 0

  if (header ~ /has moved to/) {
    pending_action = "move"
    split(header, hparts, " has moved to ")
    pending_move_from = hparts[1]
    pending_address = hparts[2]
  } else if (header ~ /will be created/) {
    pending_action = "create"
    match(header, /^[^ ]+/)
    pending_address = substr(header, RSTART, RLENGTH)
  } else if (header ~ /will be updated in-place/) {
    pending_action = "update"
    match(header, /^[^ ]+/)
    pending_address = substr(header, RSTART, RLENGTH)
  } else if (header ~ /will be destroyed/) {
    pending_action = "destroy"
    match(header, /^[^ ]+/)
    pending_address = substr(header, RSTART, RLENGTH)
  } else if (header ~ /must be replaced/) {
    pending_action = "replace"
    forces_replacement = 1
    match(header, /^[^ ]+/)
    pending_address = substr(header, RSTART, RLENGTH)
  } else if (header ~ /will be read during apply/) {
    pending_action = "read"
    match(header, /^[^ ]+/)
    pending_address = substr(header, RSTART, RLENGTH)
  } else {
    match(header, /^[^ ]+/)
    pending_address = substr(header, RSTART, RLENGTH)
    pending_action = "unknown"
  }

  pending_header = 1
  next
}

# Annotation lines after header
pending_header && /^  # \(/ {
  line = $0
  sub(/^  # /, "", line)
  if (line ~ /imported from/) {
    match(line, /"[^"]+"/)
    if (RSTART > 0) {
      pending_import_id = substr(line, RSTART+1, RLENGTH-2)
    }
    if (pending_action == "update") pending_action = "import"
  }
  if (line ~ /moved from/) {
    match(line, /moved from [^ )]+/)
    if (RSTART > 0) {
      pending_move_from = substr(line, RSTART+11, RLENGTH-11)
    }
  }
  next
}

# Resource block start: matches +/-/~/<=  resource or data
pending_header && /^[[:space:]]+[+~<-].*resource[[:space:]]+"/ {
  start_resource()
  in_resource = 1
  pending_header = 0
  if (diff_block != "") diff_block = diff_block "\\n"
  diff_block = diff_block $0
  next
}
# Move blocks: plain "    resource" with no symbol prefix
pending_header && /^    resource[[:space:]]+"/ {
  start_resource()
  in_resource = 1
  pending_header = 0
  if (diff_block != "") diff_block = diff_block "\\n"
  diff_block = diff_block $0
  next
}
# Read data source blocks: "<= data"
pending_header && /^[[:space:]]+<=/ {
  start_resource()
  in_resource = 1
  pending_header = 0
  if (diff_block != "") diff_block = diff_block "\\n"
  diff_block = diff_block $0
  next
}
# Destroy blocks: "- resource"
pending_header && /^[[:space:]]+-[[:space:]]+resource[[:space:]]+"/ {
  start_resource()
  in_resource = 1
  pending_header = 0
  if (diff_block != "") diff_block = diff_block "\\n"
  diff_block = diff_block $0
  next
}
# Replace blocks: "-/+ resource" (starts at column 0, no leading whitespace)
pending_header && /^-\/\+[[:space:]]+resource[[:space:]]+"/ {
  start_resource()
  in_resource = 1
  pending_header = 0
  if (diff_block != "") diff_block = diff_block "\\n"
  diff_block = diff_block $0
  next
}

# Reset pending on blank lines
/^$/ { pending_header = 0 }

# End of resource block
in_resource && /^    }[[:space:]]*$/ {
  if (diff_block != "") diff_block = diff_block "\\n"
  diff_block = diff_block $0
  printf "\n    ]"
  flush_resource()
  in_resource = 0
  next
}

# Skip if not in resource
!in_resource { next }

# Accumulate diff block
{
  if (diff_block != "") diff_block = diff_block "\\n"
  diff_block = diff_block $0
}

# Change lines: ~ attr = old -> new
/~[[:space:]]+[a-zA-Z_]/ {
  line = $0
  if (match(line, /~[[:space:]]+([a-zA-Z_][a-zA-Z0-9_.-]*)[[:space:]]+=/)) {
    a = substr(line, RSTART, RLENGTH)
    gsub(/^~[[:space:]]+/, "", a)
    gsub(/[[:space:]]+=.*/, "", a)

    v = line
    sub(/.*=[[:space:]]*/, "", v)

    # Check for # forces replacement annotation
    fr = 0
    if (v ~ /# forces replacement/) {
      fr = 1
      forces_replacement = 1
      sub(/[[:space:]]*# forces replacement/, "", v)
    }

    ov = ""
    nv = ""
    if (match(v, / -> /)) {
      ov = substr(v, 1, RSTART-1)
      nv = substr(v, RSTART+4)
    } else {
      nv = v
    }
    gsub(/^[[:space:]"]+|[[:space:]"]+$/, "", ov)
    gsub(/^[[:space:]"]+|[[:space:]"]+$/, "", nv)
    gsub(/^[[:space:]"]+|[[:space:]"]+$/, "", a)

    emit_change(a, ov, nv, "change", fr)
  }
}

# Add lines for create/import: + attr = value
/^[[:space:]]+\+[[:space:]]+[a-zA-Z_]/ && !/resource[[:space:]]+"/ && !/data[[:space:]]+"/ {
  line = $0
  if (match(line, /\+[[:space:]]+([a-zA-Z_][a-zA-Z0-9_.-]*)[[:space:]]+=/)) {
    a = substr(line, RSTART, RLENGTH)
    gsub(/^\+[[:space:]]+/, "", a)
    gsub(/[[:space:]]+=.*/, "", a)

    v = line
    sub(/.*=[[:space:]]*/, "", v)
    gsub(/^[[:space:]"]+|[[:space:]"]+$/, "", v)
    gsub(/^[[:space:]"]+|[[:space:]"]+$/, "", a)

    if (pending_action == "create" || pending_action == "import") {
      if (a == "name" || a == "id" || a == "location" || a == "resource_group_name" || a == "description") {
        emit_change(a, "", v, "add", 0)
      }
    }
  }
}

# Remove lines for destroy: - attr = value -> null
/^[[:space:]]+-[[:space:]]+[a-zA-Z_]/ && !/resource[[:space:]]+"/ {
  line = $0
  if (match(line, /-[[:space:]]+([a-zA-Z_][a-zA-Z0-9_.-]*)[[:space:]]+=/)) {
    a = substr(line, RSTART, RLENGTH)
    gsub(/^-[[:space:]]+/, "", a)
    gsub(/[[:space:]]+=.*/, "", a)

    v = line
    sub(/.*=[[:space:]]*/, "", v)
    gsub(/ -> null$/, "", v)
    gsub(/^[[:space:]"]+|[[:space:]"]+$/, "", v)
    gsub(/^[[:space:]"]+|[[:space:]"]+$/, "", a)

    if (pending_action == "destroy") {
      if (a == "name" || a == "id" || a == "description" || a == "resource_group_name") {
        emit_change(a, v, "", "remove", 0)
      }
    }
  }
}

END {
  if (in_resource && resource_started) {
    printf "\n    ]"
    flush_resource()
  }
  printf "\n]\n"
}
' "$CLEAN_FILE" > "$RESOURCES_FILE"

# === Extract warnings ===
awk -v start="${SUMMARY_LINE_NUM}" '
function json_escape(s) {
  gsub(/\\/, "\\\\", s)
  gsub(/"/, "\\\"", s)
  gsub(/\t/, "\\t", s)
  return s
}
BEGIN { wc = 0 }
NR <= start { next }
/^Warning:/ {
  wc++
  t = $0; sub(/^Warning: /, "", t)
  titles[wc] = t
  bodies[wc] = ""
  in_w = 1
  next
}
/^─/ || /^Saved the plan/ || /^\(and [0-9]+ more/ { in_w = 0; next }
in_w && !/^$/ {
  line = $0; gsub(/^  /, "", line)
  if (bodies[wc] != "") bodies[wc] = bodies[wc] " "
  bodies[wc] = bodies[wc] line
}
END {
  printf "["
  for (i = 1; i <= wc; i++) {
    if (i > 1) printf ","
    printf "\n    {\"title\": \"%s\", \"message\": \"%s\"}", json_escape(titles[i]), json_escape(bodies[i])
  }
  printf "\n  ]"
}
' "$CLEAN_FILE" > "$WARNINGS_FILE"

# === Count action types from extracted resources ===
S_MOVE=$(rg -c '"action": "move"' "$RESOURCES_FILE" 2>/dev/null || echo "0")
S_READ=$(rg -c '"action": "read"' "$RESOURCES_FILE" 2>/dev/null || echo "0")
S_REPLACE=$(rg -c '"action": "replace"' "$RESOURCES_FILE" 2>/dev/null || echo "0")
S_TOTAL=$((S_IMPORT + S_ADD + S_CHANGE + S_DESTROY + S_MOVE + S_READ))

# === Assemble final JSON ===
cat <<ENDJSON
{
  "metadata": {
    "generated": "$GENERATED",
    "source": "$FILENAME",
    "terraform_version": ""
  },
  "summary": {
    "create": $S_ADD,
    "update": $S_CHANGE,
    "destroy": $S_DESTROY,
    "replace": $S_REPLACE,
    "move": $S_MOVE,
    "read": $S_READ,
    "import": $S_IMPORT,
    "total": $S_TOTAL
  },
  "resources": $(cat "$RESOURCES_FILE"),
  "warnings": $(cat "$WARNINGS_FILE"),
  "refreshCount": $REFRESH_COUNT
}
ENDJSON
