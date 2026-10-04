#!/usr/bin/env bash
# boards/check.sh -- does every board directory say what it claims to say?
#
# Checks, in order:
#   1. bash -n on every script and every board.env
#   2. every board directory has README.md, board.env, uboot.config, kernel.config
#   3. every board.env carries the required keys with values that make sense, and
#      STATUS=verified is backed by a VERIFIED_BY and a KERNEL_DTB (the honesty rule)
#   4. every uboot.config has a DRAM clock, a DRAM type, a device tree and a board name,
#      and CONFIG_DRAM_CLK equals the DRAM clock of the board's installer profile; a board with
#      VARIANTS instead has a variants/<name>/variant.env for each name and no other, and every
#      variant passes 3 on its own values (board.env, then variant.env) and names a DRAM_CLK
#      equal to its profile variant's, not below the base's, under an IMAGE_NAME of its own
#   5. board.env and mainline/config/versions.env have not drifted apart
#   6. the ddr3/lpddr3 aliases in build/build.sh resolve to board directories
#   7. every board base release/build-all.sh builds from <UBOOT_BOARD>_defconfig has its
#      release and installer roles in the MATRIX of build/uboot-prove-fragments.sh
#   8. no file in these places names the fan stall parameter of hy310-board-mgr (any case,
#      - or _): board directories, kernel and U-Boot defconfigs/fragments/environment files,
#      rootfs overlay and scripts, userspace/, installer/, release/, mainline/build/*.sh; no
#      added line of a patch names it outside the driver's own source, and none sets
#      fg-warn-speed or fg-warn-cnt to 0
#
# Reads the installer profiles with python3 (stdlib only). Override their location with
# H713_PROFILES=<dir> if the checkout is not the repository. H713_EXTRA_PATCHES="<files>"
# adds patch files to section 8 (a package's patches before they are integrated).
#
# Usage: bash boards/check.sh          exit 0 = green, 1 = something is wrong

set -uo pipefail

BOARDS=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
ROOT=$(cd "$BOARDS/.." && pwd)
PROFILES=${H713_PROFILES:-$ROOT/installer/h713/profiles}
VERSIONS="$ROOT/mainline/config/versions.env"
BUILD_SH="$ROOT/mainline/build/build.sh"
PROVE_SH="$ROOT/mainline/build/uboot-prove-fragments.sh"
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

# value of KEY for one variant: board.env, then the variant's variant.env over it
variant_value() {
  ( set +u; . "$1" >/dev/null 2>&1; . "$2" >/dev/null 2>&1; eval "printf '%s' \"\${$3-}\"" )
}

# "<clk> <type>" of an installer profile (of one of its variants), read from the module itself
profile_dram() {
  python3 - "$@" <<'PY' 2>/dev/null
import importlib.util
import sys

spec = importlib.util.spec_from_file_location("board_profile", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
dram = (module.PROFILE["variants"][sys.argv[2]] if len(sys.argv) > 2 else module.PROFILE)["dram"]
print("%s %s" % (dram.get("clk"), dram.get("type")))
PY
}

# "<board_dt> <uboot_board> <variants>" of an installer profile ("-" for None/none), read from the module
profile_board() {
  python3 - "$1" <<'PY' 2>/dev/null
import importlib.util
import sys

spec = importlib.util.spec_from_file_location("board_profile", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
print("%s %s %s" % (module.PROFILE.get("board_dt") or "-", module.PROFILE.get("uboot_board") or "-",
                   " ".join(module.PROFILE.get("variants") or ()) or "-"))
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
  variants=$(value_of "$env_file" VARIANTS)
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
    if [ -n "$variants" ]; then
      ok "DRAM clock $clk MHz is the base; each variant names its own (below)"
    elif [ -z "$p_clk" ]; then
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
    read -r p_dt p_ub p_var <<<"$(profile_board "$PROFILES/$profile.py")"
    if [ "${p_dt:--}" != "${kernel_dtb:--}" ]; then
      fail "PROFILE=$profile board_dt=$p_dt but board.env KERNEL_DTB='$kernel_dtb' (drift)"
    else
      ok "profile $profile board_dt == KERNEL_DTB (${kernel_dtb:-empty})"
    fi
    if [ "${p_ub:--}" != "-" ] && [ "$p_ub" != "$uboot_board" ]; then
      fail "PROFILE=$profile uboot_board=$p_ub but board.env UBOOT_BOARD='$uboot_board' (drift)"
    fi
    if [ "$(printf '%s\n' ${p_var:--} | sort)" != "$(printf '%s\n' ${variants:--} | sort)" ]; then
      fail "PROFILE=$profile has the variants '${p_var:--}', board.env VARIANTS='$variants' (drift)"
    fi
  fi

  # a board whose units left the factory with different firmware: each variant on its own values
  if [ -n "$variants" ]; then
    for d in $(cd "$dir" && ls -d variants/*/ 2>/dev/null | sed 's#^variants/##; s#/$##'); do
      case " $variants " in *" $d "*) ;; *) fail "variants/$d is not named in VARIANTS" ;; esac
    done
    images=" "
    for v in $variants; do
      venv="$dir/variants/$v/variant.env"
      if [ ! -f "$venv" ] || ! bash -n "$venv" 2>/dev/null; then
        fail "variant $v: no sourceable variants/$v/variant.env"
        continue
      fi
      v_name=$(variant_value "$env_file" "$venv" VARIANT)
      v_status=$(variant_value "$env_file" "$venv" STATUS)
      v_by=$(variant_value "$env_file" "$venv" VERIFIED_BY)
      v_image=$(variant_value "$env_file" "$venv" IMAGE_NAME)
      v_clk=$(variant_value "$env_file" "$venv" DRAM_CLK)
      [ "$v_name" = "$v" ] || fail "variant $v: VARIANT='$v_name' is not the directory name"
      case " $STATUS_VALUES " in
        *" $v_status "*) ;;
        *) fail "variant $v: STATUS='$v_status' is not one of: $STATUS_VALUES" ;;
      esac
      if [ "$v_status" = verified ]; then
        [ -n "$v_by" ] || fail "variant $v: STATUS=verified without VERIFIED_BY"
      else
        [ -z "$v_by" ] || fail "variant $v: STATUS=$v_status but VERIFIED_BY names '$v_by'"
      fi
      case "$images" in *" $v_image "*) fail "variant $v: IMAGE_NAME '$v_image' is not its own" ;; esac
      images="$images$v_image "
      read -r p_clk p_type <<<"$(profile_dram "$PROFILES/$profile.py" "$v")"
      if ! [[ "$v_clk" =~ ^[0-9]+$ ]]; then
        fail "variant $v: DRAM_CLK='$v_clk' is not a clock in MHz"
      elif [ "$v_clk" != "$p_clk" ] || [ "$dram_type" != "$p_type" ]; then
        fail "variant $v: DRAM_CLK=$v_clk type $dram_type, profile $profile/$v says ${p_clk:-?} type ${p_type:-?}"
      elif [ -n "$clk" ] && [ "$v_clk" -lt "$clk" ]; then
        fail "variant $v: DRAM_CLK=$v_clk is below the base's $clk: a build without a variant would run faster"
      else
        ok "variant $v: STATUS=$v_status, DRAM $v_clk MHz == profile $profile/$v dram.clk, image $v_image"
      fi
    done
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

printf '\n== 7. uboot-prove-fragments.sh MATRIX ==\n'
# only the value of MATRIX="..." (it spans lines), not comments or other code of the script
matrix=$(awk '/^MATRIX="/ { on = 1; sub(/^MATRIX="/, "") }
              on { if (index($0, "\"")) { sub(/".*/, ""); print; exit } print }' "$PROVE_SH" 2>/dev/null)
assignments=$(grep -c '^MATRIX=' "$PROVE_SH" 2>/dev/null)
if [ -f "$PROVE_SH" ] && [ "${assignments:-0}" -gt 1 ]; then
  # only the first value is read above; a second one would be what the script really uses
  fail "build/uboot-prove-fragments.sh: MATRIX= is assigned $assignments times, expected once"
elif [ -f "$PROVE_SH" ] && [ -z "$matrix" ]; then
  fail "build/uboot-prove-fragments.sh: no MATRIX=\"...\" value found"
elif [ -f "$PROVE_SH" ]; then
  for id in $boards; do
    env_file="$BOARDS/$id/board.env"
    [ -f "$env_file" ] || continue
    ub=$(value_of "$env_file" UBOOT_BOARD)
    # An image needs a DTB; cstenger's boards name a defconfig of their own and are not proven here.
    [ -n "$(value_of "$env_file" KERNEL_DTB)" ] && [ -z "$(value_of "$env_file" UBOOT_DEFCONFIG)" ] || continue
    for role in release installer; do
      if printf '%s\n' $matrix | grep -qxF "$ub:$role"; then
        ok "$ub:$role in the proof matrix"
      else
        fail "$ub:$role is not in the MATRIX of build/uboot-prove-fragments.sh ($id)"
      fi
    done
  done
else
  note "no $PROVE_SH"
fi

printf '\n== 8. no file names the fan stall parameter ==\n'
# hy310-board-mgr powers the projector off when the fan stalls (module parameter, default on).
# No file in the places below may name that parameter. The kernel treats - and _ in parameter
# names alike (kernel/params.c, parameq); the match also ignores case. The pattern is written
# so that this file does not match itself.
stall='fan[-_]stall[-_]shutdown'
UB="$ROOT/mainline/external/u-boot"
places="$BOARDS/*/ $ROOT/mainline/patches/kernel/board $ROOT/rootfs/overlay $ROOT/rootfs/*.sh
        $ROOT/userspace $ROOT/installer $ROOT/release $ROOT/mainline/build/*.sh"
if [ -d "$UB/configs" ]; then
  places="$places $UB/configs/*_defconfig $UB/configs/fragments $UB/board/sunxi/*.env"
else
  note "no U-Boot fork at ${UB#$ROOT/}: its defconfigs are covered through uboot-h713/ only"
fi
before=$fails
# text files only (a built hy310_board_mgr.ko names its own parameter); installer/out and
# installer/tmp are build output (.gitignore) and are not read
# shellcheck disable=SC2086
named=$(find $places \( -path "$ROOT/installer/out" -o -path "$ROOT/installer/tmp" \
          -o -name __pycache__ \) -prune -o -type f -print0 2>/dev/null |
        xargs -0 -r grep -IilE -- "$stall" 2>/dev/null)
for f in $named; do
  fail "${f#$ROOT/} names the fan stall parameter"
done
# added lines of every patch a build applies (zurueckgenommen/ holds withdrawn ones): inside
# the driver's own source only a default of false/0 counts; nowhere fg-warn-speed/-cnt = <0>
patches="$(ls "$ROOT"/mainline/patches/*/*.patch "$ROOT"/uboot-h713/*.patch 2>/dev/null |
           grep -v '/mainline/patches/zurueckgenommen/') ${H713_EXTRA_PATCHES:-}"
n=0
for p in $patches; do
  [ -f "$p" ] || { fail "no patch file $p"; continue; }
  n=$((n + 1))
  hits=$(awk -v pat="$stall" -v drv="drivers/misc/hy310-board-mgr.c" '
    /^\+\+\+ / { file = $2; sub(/^b\//, "", file); next }
    /^\+/ {
      low = tolower($0)
      if (low ~ pat && (file != drv || low ~ (pat "[[:space:]]*=[[:space:]]*(false|0)[[:space:]]*;")))
        printf "names the fan stall parameter: %d: %s\n", FNR, $0
      else if (low ~ /fg-warn-(speed|cnt)[[:space:]]*=[[:space:]]*<[[:space:]]*(0|0x0+)[[:space:]]*>/)
        printf "sets a fan warn threshold to 0: %d: %s\n", FNR, $0
    }' "$p")
  while IFS= read -r line; do
    [ -n "$line" ] && fail "added line ${line%%: *}: ${p#$ROOT/}:${line#*: }"
  done <<<"$hits"
done
[ "$fails" -eq "$before" ] && \
  ok "fan stall parameter: named in no scanned file and no added line of $n patch(es); no fg-warn-* = <0>"

printf '\n== summary ==\n'
printf '  boards: %s\n' "$(printf '%s\n' "$boards" | tr '\n' ' ')"
printf '  notes:  %d\n' "$notes"
if [ "$fails" -eq 0 ]; then
  printf '  result: green (0 failures)\n'
  exit 0
fi
printf '  result: %d failure(s)\n' "$fails"
exit 1
