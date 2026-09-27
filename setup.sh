#!/usr/bin/env bash
# setup.sh — install Media Pipeline and register it with Hermes Agent.
#
#   ./setup.sh                 check deps, install Python packages, create
#                              ig_config.json, create the Hermes profile,
#                              install the skill, register the cron jobs
#   ./setup.sh --no-hermes     skip everything Hermes-related
#   ./setup.sh --all-paused    register every job paused (dry install)
#
# Safe to re-run: existing config, skill files, and jobs are left alone
# (the skill is refreshed). Publishing (reel-4-auto-publish) is always
# registered PAUSED — resume it once you've reviewed a few reels:
#   hermes -p media-pipeline cron resume <job-id>
set -euo pipefail

PROFILE="${MEDIA_PIPELINE_PROFILE:-media-pipeline}"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HERMES_ROOT="${HERMES_ROOT:-$HOME/.hermes}"
PROFILE_DIR="$HERMES_ROOT/profiles/$PROFILE"
WITH_HERMES=1
ALL_PAUSED=0
for arg in "$@"; do
  case "$arg" in
    --no-hermes) WITH_HERMES=0 ;;
    --all-paused) ALL_PAUSED=1 ;;
    -h|--help) sed -n '2,13p' "$0"; exit 0 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

say()  { printf '\033[1m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[33mwarning:\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[31merror:\033[0m %s\n' "$*" >&2; exit 1; }

# 1. Dependencies -----------------------------------------------------------
say "Checking dependencies"
command -v python3 >/dev/null || die "python3 not found"
command -v ffmpeg  >/dev/null || die "ffmpeg not found (macOS: brew install ffmpeg)"
command -v tesseract >/dev/null || warn "tesseract not found — the QC gate's watermark check will be skipped (macOS: brew install tesseract)"
python3 -m pip install --quiet -r "$REPO/requirements.txt"

# 2. Local config -----------------------------------------------------------
if [ ! -f "$REPO/ig_config.json" ]; then
  cp "$REPO/ig_config.example.json" "$REPO/ig_config.json"
  say "Created ig_config.json — fill in your Instagram credentials"
fi

[ "$WITH_HERMES" = 1 ] || { say "Done (Hermes skipped)"; exit 0; }

# 3. Hermes profile + skill -------------------------------------------------
command -v hermes >/dev/null || die "hermes not found — install Hermes Agent: https://github.com/NousResearch/hermes-agent (or re-run with --no-hermes)"

if [ ! -d "$PROFILE_DIR" ]; then
  say "Creating Hermes profile '$PROFILE' (model settings cloned from your active profile)"
  hermes profile create "$PROFILE" --clone --no-alias \
    --description "Runs the Media Pipeline: news to published Instagram Reels."
fi

# The skill and prompts refer to the repo as ~/media-pipeline; point them at
# wherever this checkout actually lives.
REPO_REF="$REPO"
case "$REPO" in "$HOME"/*) REPO_REF="~/${REPO#"$HOME"/}" ;; esac

say "Installing skill into $PROFILE_DIR/skills/media-pipeline/"
SKILL_DIR="$PROFILE_DIR/skills/media-pipeline/media-pipeline"
mkdir -p "$SKILL_DIR"
sed "s#~/media-pipeline#$REPO_REF#g" "$REPO/hermes/skills/media-pipeline/SKILL.md" > "$SKILL_DIR/SKILL.md"

# The token-refresh job runs a script from the profile's scripts/ dir;
# a small wrapper keeps the real script (and its config lookup) in the repo.
mkdir -p "$PROFILE_DIR/scripts"
cat > "$PROFILE_DIR/scripts/media_pipeline_refresh_token.sh" <<EOF
#!/usr/bin/env bash
exec python3 "$REPO/scripts/refresh_token.py"
EOF
chmod +x "$PROFILE_DIR/scripts/media_pipeline_refresh_token.sh"

# 4. Cron jobs ----------------------------------------------------------------
say "Registering cron jobs"
REPO_REF="$REPO_REF" ALL_PAUSED="$ALL_PAUSED" PROFILE="$PROFILE" \
JOBS_FILE="$REPO/hermes/cron/jobs.example.json" EXISTING="$PROFILE_DIR/cron/jobs.json" \
python3 - <<'PY'
import json, os, subprocess
profile, repo_ref = os.environ["PROFILE"], os.environ["REPO_REF"]
all_paused = os.environ["ALL_PAUSED"] == "1"
existing = set()
if os.path.exists(os.environ["EXISTING"]):
    existing = {j.get("name") for j in json.load(open(os.environ["EXISTING"])).get("jobs", [])}
for job in json.load(open(os.environ["JOBS_FILE"]))["jobs"]:
    name = job["name"]
    if name in existing:
        print(f"  = {name} (already registered)")
        continue
    cmd = ["hermes", "-p", profile, "cron", "create", job["schedule"]["expr"]]
    if job.get("no_agent"):
        cmd += ["--no-agent", "--script", "media_pipeline_refresh_token.sh"]
    else:
        # the prompt is positional and must directly follow the schedule
        cmd.append(job["prompt"].replace("~/media-pipeline", repo_ref))
        for skill in job.get("skills") or []:
            cmd += ["--skill", skill]
    cmd += ["--name", name]
    paused = all_paused or name == "reel-4-auto-publish"
    if paused:
        cmd += ["--paused", "--paused-reason", "review reels before enabling auto-publish"
                if name == "reel-4-auto-publish" else "installed with --all-paused"]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)
    print(f"  + {name} ({job['schedule']['expr']}){' [paused]' if paused else ''}")
PY

say "Done. Next steps:"
cat <<EOF
  1. Fill in $REPO/ig_config.json (and brand.json for your account's name/handle/avatar).
  2. Make sure the schedule actually fires — keep the Hermes desktop app open, or run
     a gateway:  hermes -p $PROFILE gateway install --start-now --start-on-login
  3. Watch the first reels land in queue/:  python3 $REPO/scripts/dashboard.py
  4. When you're happy, enable publishing:  hermes -p $PROFILE cron list   (then cron resume <id>)
EOF
