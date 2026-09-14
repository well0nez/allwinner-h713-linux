#!/usr/bin/env bash
# boards/check.sh -- does every board directory say what it claims to say?
#
# Checks, in order:
#   1. bash -n on every script and every board.env
#   2. every board directory has README.md, board.env, uboot.config, kernel.config
#   3. every board.env carries the required keys with values that make sense, and
#      STATUS=verified is backed by a VERIFIED_BY and a KERNEL_DTB (the honesty rule)
#   4. every uboot.config has a DRAM clock, a DRAM type, a device tree and a board name,
#      and CONFIG_DRAM_CLK equals the DRAM clock of the board's installer profile
#   5. board.env and mainline/config/versions.env have not drifted apart
#   6. the ddr3/lpddr3 aliases in build/build.sh resolve to board directories
#
# Reads the installer profiles with python3 (stdlib only). Override their location with
# H713_PROFILES=<dir> if the checkout is not the repository.
#
# Usage: bash boards/check.sh          exit 0 = green, 1 = something is wrong

set -uo pipefail

BOARDS=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
ROOT=$(cd "$BOARDS/.." && pwd)
PROFILES=${H713_PROFILES:-$ROOT/installer/h713/profiles}
VERSIONS="$ROOT/mainline/config/versions.env"
BUILD_SH="$ROOT/mainline/build/build.sh"
STATUS_VALUES="verified profile-only partial"
REQUIRED_KEYS="BOARD_ID STATUS PROFILE IMAGE_NAME KERNEL_DTB UBOOT_BOARD VERIFIED_BY"

fails=0
notes=0
ok()   { printf '  ok    %s\n' "$*"; }
note() { printf '  note  %s\n' "$*"; notes=$((notes + 1)); }
fail() { printf '  FAIL  %s\n' "$*"; fails=$((fails + 1)); }

# value of KEY in a board.env, empty if unset; the file is sourced in a subshell
value_of() {
  ( set +u; . "$1" >/dev/null 2>&1; eval "printf '%s' \"\${$2-}\"" )
}

# "<clk> <type>" of an installer profile, read from the module itself
profile_dram() {
  python3 - "$1" <<'PY' 2>/dev/null
import importlib.util
import sys

spec = importlib.util.spec_from_file_location("board_profile", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
dram = module.PROFILE["dram"]
print("%s %s" % (dram.get("clk"), dram.get("type")))
PY
}

# "<board_dt> <uboot_board>" of an installer profile ("-" for None), read from the module
profile_board() {
  python3 - "$1" <<'PY' 2>/dev/null
import importlib.util
import sys

spec = importlib.util.spec_from_file_location("board_profile", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
print("%s %s" % (module.PROFILE.get("board_dt") or "-", module.PROFILE.get("uboot_board") or "-"))
PY
}

printf '== 1. script syntax ==\n'
scripts="$BOARDS/check.sh $BUILD_SH $ROOT/mainline/build/uboot-build.sh"
[ -d "$ROOT/release" ] && scripts="$scripts $(ls "$ROOT"/release/*.sh 2>/dev/null)"
for script in $scripts; do
  if [ ! -f "$script" ]; then
    fail "missing script: $script"
  elif bash -n "$script" 2>/dev/null; then
    ok "bash -n ${script#$ROOT/}"
  else
    fail "bash -n ${script#$ROOT/}"
    bash -n "$script"
  fi
done

boards=$(cd "$BOARDS" && ls -d */ 2>/dev/null | sed 's#/$##' | sort)
[ -n "$boards" ] || { printf '  FAIL  no board directories in %s\n' "$BOARDS"; exit 1; }
printf '\n== 2..5. boards: %s ==\n' "$(echo "$boards" | tr '\n' ' ')"

for id in $boards; do
  dir="$BOARDS/$id"
  printf '\n%s\n' "$id"

  missing=""
  for f in README.md board.env uboot.config kernel.config; do
    [ -f "$dir/$f" ] || missing="$missing $f"
  done
  if [ -n "$missing" ]; then
    fail "missing file(s):$missing"
    continue
  fi
  ok "README.md, board.env, uboot.config, kernel.config present"

  env_file="$dir/board.env"
  if ! bash -n "$env_file" 2>/dev/null; then
    fail "board.env is not sourceable"
    continue
  fi

  absent=""
  for key in $REQUIRED_KEYS; do
    grep -Eq "^$key=" "$env_file" || absent="$absent $key"
  done
  if [ -n "$absent" ]; then
    fail "board.env: missing key(s):$absent"
  else
    ok "board.env: all required keys present"
  fi

  board_id=$(value_of "$env_file" BOARD_ID)
  status=$(value_of "$env_file" STATUS)
  profile=$(value_of "$env_file" PROFILE)
  image_name=$(value_of "$env_file" IMAGE_NAME)
  kernel_dtb=$(value_of "$env_file" KERNEL_DTB)
  uboot_board=$(value_of "$env_file" UBOOT_BOARD)
  verified_by=$(value_of "$env_file" VERIFIED_BY)

  [ "$board_id" = "$id" ] || fail "BOARD_ID='$board_id' is not the directory name '$id'"
  case " $STATUS_VALUES " in
    *" $status "*) ok "STATUS=$status" ;;
    *) fail "STATUS='$status' is not one of: $STATUS_VALUES" ;;
  esac
  [ -n "$image_name" ] || fail "IMAGE_NAME is empty"
  [ -n "$uboot_board" ] || fail "UBOOT_BOARD is empty"
  case "$image_name" in
    [a-z0-9]*) ;;
    *) fail "IMAGE_NAME='$image_name' is not a lower-case image base name" ;;
  esac

  # the honesty rule, mechanically
  if [ "$status" = verified ]; then
    if [ -n "$verified_by" ]; then
      ok "verified by: $verified_by"
    else
      fail "STATUS=verified without VERIFIED_BY -- who ran it, on which board, when?"
    fi
    [ -n "$kernel_dtb" ] || fail "STATUS=verified without KERNEL_DTB"
    [ -n "$profile" ] || note "verified but PROFILE is empty: a release image also needs a profile"
  else
    [ -z "$verified_by" ] || fail "STATUS=$status but VERIFIED_BY names '$verified_by'"
    [ -z "$kernel_dtb" ] && ok "no kernel DTB (nothing of ours has run here)"
  fi

  if [ -n "$kernel_dtb" ]; then
    case "$kernel_dtb" in
      sun50i-h713-*) ;;
      *) fail "KERNEL_DTB='$kernel_dtb' is not a sun50i-h713-* DTB name" ;;
    esac
    case "$kernel_dtb" in
      *.dtb) fail "KERNEL_DTB='$kernel_dtb' must not carry the .dtb suffix" ;;
    esac
  fi

  # uboot.config
  fragment="$dir/uboot.config"
  stray=$(grep -vE '^[[:space:]]*(#.*)?$' "$fragment" | grep -vcE '^CONFIG_[A-Z0-9_]+=' || true)
  [ "$stray" -eq 0 ] || fail "uboot.config: $stray line(s) are neither a comment nor CONFIG_*="
  grep -q '^CONFIG_DEFAULT_DEVICE_TREE="' "$fragment" || fail "uboot.config: no CONFIG_DEFAULT_DEVICE_TREE"
  grep -q '^CONFIG_IDENT_STRING="' "$fragment" || fail "uboot.config: no CONFIG_IDENT_STRING (board name)"
  dram_type=""
  grep -q '^CONFIG_SUNXI_DRAM_H713_DDR3_STOCK=y' "$fragment" && dram_type=3
  grep -q '^CONFIG_SUNXI_DRAM_H713_LPDDR3_STOCK=y' "$fragment" && dram_type=7
  [ -n "$dram_type" ] || fail "uboot.config: no DRAM type (CONFIG_SUNXI_DRAM_H713_{DDR3,LPDDR3}_STOCK=y)"
  clk=$(sed -n 's/^CONFIG_DRAM_CLK=\([0-9][0-9]*\)[[:space:]]*$/\1/p' "$fragment" | head -1)
  [ -n "$clk" ] || fail "uboot.config: no CONFIG_DRAM_CLK=<MHz>"

  # the fragment against the installer profile
  if [ -z "$profile" ]; then
    note "no installer profile: DRAM clock ${clk:-?} MHz is unchecked (values come from a defconfig)"
  elif [ ! -f "$PROFILES/$profile.py" ]; then
    fail "PROFILE=$profile: no $PROFILES/$profile.py"
  else
    read -r p_clk p_type <<<"$(profile_dram "$PROFILES/$profile.py")"
    if [ -z "$p_clk" ]; then
      fail "PROFILE=$profile: could not read PROFILE['dram'] with python3"
    elif [ "$clk" != "$p_clk" ]; then
      fail "CONFIG_DRAM_CLK=$clk but profile $profile says dram.clk=$p_clk"
    else
      ok "DRAM clock $clk MHz == profile $profile dram.clk"
    fi
    if [ -n "$dram_type" ] && [ -n "$p_type" ] && [ "$dram_type" != "$p_type" ]; then
      fail "DRAM type $dram_type in uboot.config but profile $profile says dram.type=$p_type"
    fi
    # the profile's board_dt / uboot_board are board.env's KERNEL_DTB / UBOOT_BOARD, or nothing
    read -r p_dt p_ub <<<"$(profile_board "$PROFILES/$profile.py")"
    if [ "${p_dt:--}" != "${kernel_dtb:--}" ]; then
      fail "PROFILE=$profile board_dt=$p_dt but board.env KERNEL_DTB='$kernel_dtb' (drift)"
    else
      ok "profile $profile board_dt == KERNEL_DTB (${kernel_dtb:-empty})"
    fi
    if [ "${p_ub:--}" != "-" ] && [ "$p_ub" != "$uboot_board" ]; then
      fail "PROFILE=$profile uboot_board=$p_ub but board.env UBOOT_BOARD='$uboot_board' (drift)"
    fi
  fi

  # board.env against versions.env
  if [ -f "$VERSIONS" ]; then
    for key in UBOOT_DEFCONFIG KERNEL_DEFCONFIG; do
      v=$(value_of "$env_file" "$key")
      [ -n "$v" ] || continue
      if grep -Eq "=$v([[:space:]]|$)" "$VERSIONS"; then
        ok "$key=$v also in config/versions.env"
      else
        fail "$key=$v is in no line of config/versions.env (drift)"
      fi
    done
  fi
done

printf '\n== 6. build.sh aliases ==\n'
if [ -f "$BUILD_SH" ]; then
  aliases=$(sed -n 's/^[[:space:]]*\(ddr3\|lpddr3\))[[:space:]]*BOARD=\([a-z0-9-]*\).*/\1 \2/p' "$BUILD_SH")
  if [ "$(printf '%s\n' "$aliases" | grep -c .)" -ne 2 ]; then
    fail "build/build.sh: the ddr3/lpddr3 aliases were not found where they were expected"
  else
    printf '%s\n' "$aliases" | while read -r name target; do
      if [ -d "$BOARDS/$target" ]; then
        printf '  ok    alias %s -> %s\n' "$name" "$target"
      else
        printf '  FAIL  alias %s -> %s: no such board directory\n' "$name" "$target"
        exit 1
      fi
    done || fails=$((fails + 1))
  fi
else
  fail "no $BUILD_SH"
fi

printf '\n== summary ==\n'
printf '  boards: %s\n' "$(printf '%s\n' "$boards" | tr '\n' ' ')"
printf '  notes:  %d\n' "$notes"
if [ "$fails" -eq 0 ]; then
  printf '  result: green (0 failures)\n'
  exit 0
fi
printf '  result: %d failure(s)\n' "$fails"
exit 1
