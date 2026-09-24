#!/usr/bin/env bash
set -euo pipefail

RUFFLE="ruffle"
LIBTAS="libTAS"

# TAS=1 to launch Ruffle under libTAS instead of directly
TAS="${TAS:-0}"

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
if [[ -z "${EF_COOKIE:-}" ]]; then
  log_error "Missing EF_COOKIE (export EF_COOKIE='ef_sid=...; locale=fr-FR')"
  exit 1
fi
log_ok "EF_COOKIE set (${#EF_COOKIE} chars)"

DEPS=(curl jq "$RUFFLE")
[[ "$TAS" == 1 ]] && DEPS+=("$LIBTAS")
for cmd in "${DEPS[@]}"; do
  if ! command -v "$cmd" > /dev/null; then
    log_error "Command not found: $cmd"
    exit 1
  fi
done
log_ok "Dependencies found: curl, jq, $("$RUFFLE" --version)"
log_info "Game: $GAME_ID (version $VERSION)"

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

log_step "5. Launching Ruffle"
log_info "SWF: $BASE_URL/assets/loader.swf"
log_info "RUST_LOG=$RUST_LOG"

# Arguments to launch the exact Eternalfest loader
RUFFLE_ARGS=(
  --base "$BASE_URL/"
  --spoof-url "$BASE_URL/assets/loader.swf"
  --referer "$BASE_URL/runs/$RUN_ID"
  --cookie "$EF_COOKIE"
  --dummy-external-interface
  -P "object_id=swf1234"
  -P "run=$RUN_JSON"
  -P "game=$GAME_ID"
  -P "options=$OPTIONS_JSON"
)

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
  RUFFLE_ARGS+=("$BASE_URL/assets/loader.swf")
  QUOTED_ARGS=()
  for arg in "${RUFFLE_ARGS[@]}"; do QUOTED_ARGS+=("'${arg//\'/\'\\\'\'}'"); done
  # libTAS fakes the clock, starting at 1970 by default: HTTPS certificates are then
  # "not yet valid" and Ruffle reports it as a domain resolution failure. Start at today.
  TAS_START_TIME="$(date -d 'today 00:00' +%s)"
  log_info "Launcher: $LIBTAS (system time: $(date -d "@$TAS_START_TIME" -Iseconds))"
  env -u WAYLAND_DISPLAY "$LIBTAS" --system-time-sec "$TAS_START_TIME" \
    "$(command -v "$RUFFLE")" "${QUOTED_ARGS[@]}"
else
  "$RUFFLE" "${RUFFLE_ARGS[@]}" "$BASE_URL/assets/loader.swf"
fi
RUFFLE_EXIT=$?
set -e

if [[ "$RUFFLE_EXIT" -eq 0 ]]; then
  log_ok "Ruffle exited normally"
else
  log_warn "Ruffle exited with code $RUFFLE_EXIT"
fi
exit "$RUFFLE_EXIT"
