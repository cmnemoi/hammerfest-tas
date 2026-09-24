#!/usr/bin/env bash
set -euo pipefail

RUFFLE="ruffle"
LIBTAS="libTAS"

# TAS=1 to launch Ruffle under libTAS instead of directly
TAS="${TAS:-0}"

# MIRROR=record: Ruffle goes through a local mirror that saves every eternalfest.net response
# MIRROR=replay: reuse the recorded run and responses, no network (identical launches for TAS)
MIRROR="${MIRROR:-}"
MIRROR_DIR="${MIRROR_DIR:-$(dirname "$(realpath "$0")")/mirror}"
MIRROR_PORT="${MIRROR_PORT:-8765}"
# System Python explicitly: the mise shim has no global version
PYTHON="${PYTHON:-/usr/bin/python3}"

BASE_URL="https://eternalfest.net"
GAME_ID="0dc0d559-de83-4e0c-982d-fc56100dfdd5"
VERSION="2.5.1"

# DEBUG=1 to print full JSON payloads exchanged with the API
DEBUG="${DEBUG:-0}"
# Ruffle log level (e.g. RUST_LOG=debug ./run.sh)
export RUST_LOG="${RUST_LOG:-warn,ruffle=info,avm_trace=info}"

# --- Logging helpers ----------------------------------------------------------

if [[ -t 2 ]]; then
  C_RESET=$'\e[0m'; C_DIM=$'\e[2m'; C_BLUE=$'\e[34m'; C_GREEN=$'\e[32m'
  C_YELLOW=$'\e[33m'; C_RED=$'\e[31m'; C_BOLD=$'\e[1m'
else
  C_RESET=""; C_DIM=""; C_BLUE=""; C_GREEN=""; C_YELLOW=""; C_RED=""; C_BOLD=""
fi

_log() { printf '%s%s%s %s%-5s%s %s\n' "$C_DIM" "$(date +%H:%M:%S.%3N)" "$C_RESET" "$1" "$2" "$C_RESET" "$3" >&2; }
log_step()  { printf '\n%s==> %s%s\n' "$C_BOLD" "$*" "$C_RESET" >&2; }
log_info()  { _log "$C_BLUE" INFO "$*"; }
log_ok()    { _log "$C_GREEN" OK "$*"; }
log_warn()  { _log "$C_YELLOW" WARN "$*"; }
log_error() { _log "$C_RED" ERROR "$*"; }
log_debug() { [[ "$DEBUG" == 1 ]] && _log "$C_DIM" DEBUG "$*" || true; }
log_json()  { [[ "$DEBUG" == 1 ]] && { log_debug "$1:"; jq . <<< "$2" | sed 's/^/    /' >&2; } || true; }

trap 'log_error "Failed at line $LINENO (command: $BASH_COMMAND, exit code: $?)"' ERR

# API call that logs the HTTP status and duration.
# Usage: api_call <METHOD> <PATH> [extra curl args...]
# Writes the response body to stdout.
api_call() {
  local method="$1" path="$2"; shift 2
  local body_file; body_file="$(mktemp)"
  local meta

  log_info "$method $path"
  if ! meta="$(
    curl -sS -X "$method" \
      --cookie "$EF_COOKIE" \
      --output "$body_file" \
      --write-out '%{http_code} %{time_total}' \
      "$@" \
      "$BASE_URL$path"
  )"; then
    log_error "Network error on $method $path"
    rm -f "$body_file"
    return 1
  fi

  local status="${meta%% *}" duration="${meta##* }"
  if [[ "$status" -ge 400 ]]; then
    log_error "$method $path -> HTTP $status (${duration}s)"
    log_error "Response: $(cat "$body_file")"
    rm -f "$body_file"
    return 1
  fi

  log_ok "$method $path -> HTTP $status (${duration}s)"
  cat "$body_file"
  rm -f "$body_file"
}

# --- Script -------------------------------------------------------------------

log_step "0. Checks"

# Must be set before running the script:
# export EF_COOKIE='ef_sid=...; locale=fr-FR'
# (not needed in replay mode: nothing reaches Eternalfest)
if [[ "$MIRROR" == replay ]]; then
  EF_COOKIE=""
elif [[ -z "${EF_COOKIE:-}" ]]; then
  log_error "Missing EF_COOKIE (export EF_COOKIE='ef_sid=...; locale=fr-FR')"
  exit 1
else
  log_ok "EF_COOKIE set (${#EF_COOKIE} chars)"
fi

if [[ -n "$MIRROR" && "$MIRROR" != record && "$MIRROR" != replay ]]; then
  log_error "Unknown MIRROR=$MIRROR (expected record or replay)"
  exit 1
fi

DEPS=(curl jq "$RUFFLE")
[[ "$TAS" == 1 ]] && DEPS+=("$LIBTAS")
[[ -n "$MIRROR" ]] && DEPS+=("$PYTHON")
for cmd in "${DEPS[@]}"; do
  if ! command -v "$cmd" > /dev/null; then
    log_error "Command not found: $cmd"
    exit 1
  fi
done
log_ok "Dependencies found: curl, jq, $("$RUFFLE" --version)"
log_info "Game: $GAME_ID (version $VERSION)"

# Creates a new run on Eternalfest and sets RUN_JSON
create_run() {
  log_step "1. Fetching logged-in user"
  AUTH_JSON="$(api_call GET /api/v1/auth/self)"
  log_json "auth/self" "$AUTH_JSON"

  USER_ID="$(jq -r '.user.id // empty' <<< "$AUTH_JSON")"
  if [[ -z "$USER_ID" ]]; then
    log_error "No user in response (expired cookie?): $AUTH_JSON"
    exit 1
  fi
  USER_NAME="$(jq -r '.user.display_name // .user.displayName // "?"' <<< "$AUTH_JSON")"
  log_ok "User: $USER_NAME ($USER_ID)"

  log_step "2. Building run creation request"
  CREATE_RUN_JSON="$(
    jq -nc \
      --arg game_id "$GAME_ID" \
      --arg version "$VERSION" \
      --arg user_id "$USER_ID" \
      '{
        game: {
          id: $game_id
        },
        channel: "main",
        version: $version,
        user: {
          type: "User",
          id: $user_id
        },
        game_mode: "deluxe",
        game_options: [
          "nightmare",
          "noeffect"
        ],
        settings: {
          detail: true,
          shake: true,
          sound: true,
          music: false,
          volume: 100,
          locale: "fr-FR"
        }
      }'
  )"
  log_info "Mode: $(jq -r '.game_mode' <<< "$CREATE_RUN_JSON"), options: $(jq -r '.game_options | join(", ")' <<< "$CREATE_RUN_JSON")"
  log_json "Request" "$CREATE_RUN_JSON"

  log_step "3. Creating new run"
  RUN_JSON="$(
    api_call POST /api/v1/runs \
      --header 'Content-Type: application/json' \
      --header "Origin: $BASE_URL" \
      --header "Referer: $BASE_URL/games/$GAME_ID?channel=main" \
      --data "$CREATE_RUN_JSON"
  )"
  log_json "Run" "$RUN_JSON"

  RUN_ID="$(jq -r '.id // empty' <<< "$RUN_JSON")"
  if [[ -z "$RUN_ID" ]]; then
    log_error "No id in run creation response: $RUN_JSON"
    exit 1
  fi
  log_ok "Run created: $RUN_ID ($BASE_URL/runs/$RUN_ID)"
}

if [[ "$MIRROR" == replay ]]; then
  log_step "1-3. Reusing recorded run"
  if [[ ! -f "$MIRROR_DIR/run.json" ]]; then
    log_error "No recorded run in $MIRROR_DIR: launch once with MIRROR=record first"
    exit 1
  fi
  RUN_JSON="$(cat "$MIRROR_DIR/run.json")"
  RUN_ID="$(jq -r '.id' <<< "$RUN_JSON")"
  log_ok "Run: $RUN_ID (recorded $(jq -r '.created_at' <<< "$RUN_JSON"))"
else
  create_run
  if [[ "$MIRROR" == record ]]; then
    # Start from an empty mirror: the new run's responses replace the old ones
    rm -rf "$MIRROR_DIR"
    mkdir -p "$MIRROR_DIR"
    printf '%s\n' "$RUN_JSON" > "$MIRROR_DIR/run.json"
    log_ok "Run saved to $MIRROR_DIR/run.json"
  fi
fi

log_step "4. Building loader options"
# Eternalfest passes this projection of the run separately
OPTIONS_JSON="$(
  jq -c '{
    mode: .game_mode,
    options: .game_options,
    settings: (.settings + {volume: 100}),
    locale: .settings.locale
  }' <<< "$RUN_JSON"
)"
log_info "Options: $OPTIONS_JSON"

# The loader calls the API on the server it was loaded from: serving it from the mirror
# sends every game request through the mirror
GAME_URL="$BASE_URL"
if [[ -n "$MIRROR" ]]; then
  log_step "5. Starting mirror ($MIRROR)"
  GAME_URL="http://127.0.0.1:$MIRROR_PORT"
  "$PYTHON" "$(dirname "$(realpath "$0")")/mirror.py" "$MIRROR" "$MIRROR_DIR" "$MIRROR_PORT" &
  MIRROR_PID=$!
  # Stop the mirror with the script, including on Ctrl+C / kill (EXIT alone skips signals)
  trap 'kill "$MIRROR_PID" 2> /dev/null' EXIT
  trap 'exit 130' INT TERM
  for _ in {1..50}; do
    # Probe the port only: a real request would be recorded (or a 404 in replay)
    (: > "/dev/tcp/127.0.0.1/$MIRROR_PORT") 2> /dev/null && break
    sleep 0.1
  done
  log_ok "Mirror listening on $GAME_URL ($MIRROR_DIR)"
fi

log_step "6. Launching Ruffle"
log_info "SWF: $GAME_URL/assets/loader.swf"
log_info "RUST_LOG=$RUST_LOG"

# Arguments to launch the exact Eternalfest loader
RUFFLE_ARGS=(
  --base "$GAME_URL/"
  --spoof-url "$GAME_URL/assets/loader.swf"
  --referer "$GAME_URL/runs/$RUN_ID"
  --dummy-external-interface
  -P "object_id=swf1234"
  -P "run=$RUN_JSON"
  -P "game=$GAME_ID"
  -P "options=$OPTIONS_JSON"
)
[[ -n "$EF_COOKIE" ]] && RUFFLE_ARGS+=(--cookie "$EF_COOKIE")

set +e
if [[ "$TAS" == 1 ]]; then
  # - blocking loads: network latency no longer shifts frames, so movies stay in sync
  # - gl backend: lets libTAS force software rendering (needed for savestates)
  # - no GUI: the menu bar would eat inputs and change the window size
  # The window stays at 800x600 under X11: Ruffle asks to shrink it to the SWF size (or
  # --width/--height) once loaded, but the window manager restores 800x600 when mapping it.
  RUFFLE_ARGS+=(--load-behavior blocking --graphics gl --no-gui)
  # libTAS preloads itself into the real binary: pass Ruffle's absolute path, never a wrapper.
  # libTAS is X11-only: hide Wayland so Ruffle falls back to XWayland.
  # libTAS joins the game args into one string run through `sh -c` (dash): single-quote
  # each one, otherwise the `;` in the cookie and the spaces in the JSON split the command.
  RUFFLE_ARGS+=("$GAME_URL/assets/loader.swf")
  QUOTED_ARGS=()
  for arg in "${RUFFLE_ARGS[@]}"; do QUOTED_ARGS+=("'${arg//\'/\'\\\'\'}'"); done
  # libTAS fakes the clock, starting at 1970 by default: HTTPS certificates are then
  # "not yet valid" and Ruffle reports it as a domain resolution failure. Start at today.
  # In replay (no HTTPS), start at the recorded run's creation instead, so the clock the game
  # sees never changes from one day to the next.
  if [[ "$MIRROR" == replay ]]; then
    TAS_START_TIME="$(date -d "$(jq -r '.created_at' <<< "$RUN_JSON")" +%s)"
  else
    TAS_START_TIME="$(date -d 'today 00:00' +%s)"
  fi
  log_info "Launcher: $LIBTAS (system time: $(date -d "@$TAS_START_TIME" -Iseconds))"
  env -u WAYLAND_DISPLAY "$LIBTAS" --system-time-sec "$TAS_START_TIME" \
    "$(command -v "$RUFFLE")" "${QUOTED_ARGS[@]}"
else
  "$RUFFLE" "${RUFFLE_ARGS[@]}" "$GAME_URL/assets/loader.swf"
fi
RUFFLE_EXIT=$?
set -e

if [[ "$RUFFLE_EXIT" -eq 0 ]]; then
  log_ok "Ruffle exited normally"
else
  log_warn "Ruffle exited with code $RUFFLE_EXIT"
fi
exit "$RUFFLE_EXIT"
