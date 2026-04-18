#!/usr/bin/env bash
# ==============================================================================
# setup-env.sh — Generate .env files for each profile from shared base + overrides
# ==============================================================================
# Usage: ./scripts/setup-env.sh [--dry-run] [--profile <name>]
#
# This script concatenates shared/env.base + profiles/<name>/.env.overrides
# into profiles/<name>/.env for each active profile.
#
# The generated .env files are gitignored. Only .env.base and .env.overrides
# are tracked in git.
# ==============================================================================

set -euo pipefail

HERMES_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SHARED_ENV="$HERMES_ROOT/shared/env.base"
PROFILES_DIR="$HERMES_ROOT/profiles"

DRY_RUN=false
TARGET_PROFILE=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run) DRY_RUN=true; shift ;;
        --profile) TARGET_PROFILE="$2"; shift 2 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

if [[ ! -f "$SHARED_ENV" ]]; then
    echo "ERROR: shared/env.base not found at $SHARED_ENV"
    exit 1
fi

generate_env() {
    local profile_name="$1"
    local profile_dir="$PROFILES_DIR/$profile_name"
    local overrides="$profile_dir/.env.overrides"
    local output="$profile_dir/.env"

    if [[ ! -d "$profile_dir" ]]; then
        echo "SKIP: profile '$profile_name' directory not found"
        return
    fi

    if [[ "$DRY_RUN" == true ]]; then
        echo "DRY RUN: Would generate $output"
        echo "  Source: $SHARED_ENV + $overrides"
        return
    fi

    # Concatenate base + overrides
    cat "$SHARED_ENV" > "$output"
    echo "" >> "$output"
    echo "# =============================================================================" >> "$output"
    echo "# Profile-specific overrides for $profile_name" >> "$output"
    echo "# =============================================================================" >> "$output"
    echo "" >> "$output"

    if [[ -f "$overrides" ]]; then
        cat "$overrides" >> "$output"
    else
        echo "# (No overrides for this profile)" >> "$output"
    fi

    echo "OK: $output generated ($(wc -l < "$output") lines)"
}

if [[ -n "$TARGET_PROFILE" ]]; then
    generate_env "$TARGET_PROFILE"
else
    echo "Generating .env files for all profiles..."
    for profile_dir in "$PROFILES_DIR"/*/; do
        profile_name="$(basename "$profile_dir")"
        generate_env "$profile_name"
    done
fi

echo ""
echo "Done. Run 'hermes -p <profile>' to verify."