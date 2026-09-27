#!/bin/bash
# V20 batch-1: assemble the deliverable tree, hash, zip (ZIP64), self-verify.
set -u
ROOT=/work/v20
TS=$(date +%Y%m%d)
NAME="CBAP_V20_SUPPLEMENT_BATCH1_${TS}"
B=$ROOT/bundle/$NAME
rm -rf "$ROOT/bundle"
mkdir -p "$B"/{provenance/source_snapshot,inputs,raw,detailed,reused,recovered_figure2,derived,scripts,validation,figures}

echo "== provenance =="
cd /work/simulation
{
  echo "branch: $(git rev-parse --abbrev-ref HEAD)"
  echo "HEAD:   $(git rev-parse HEAD)"
  echo "tracked modifications: $(git status --porcelain | grep -cv '^??')"
  git status --porcelain | grep -v '^??' | head
  echo "binary: $(sha256sum build/scratch/third)"
  echo "binary in REGV4_OK allowlist: $(grep -c "$(sha256sum build/scratch/third | awk '{print $1}')" /work/v2_400g/logs/REGV4_OK)"
  echo "NOTE: SeedManager::SetSeed(sim_seed) at scratch/third.cc:4437; run"
  echo "number is NOT set (ns-3 default run=1) - recorded per task book."
} > "$B/provenance/source_version.txt"
git diff 6060114662e084bc5e500cc373c7f8710fa9be42 HEAD -- simulation/src simulation/scratch/third.cc > "$B/provenance/source_diff.patch" 2>/dev/null || true
{
  echo "The runs in this bundle used the PRE-BUILT binary"
  echo "  /work/simulation/build/scratch/third"
  echo "whose SHA256 is in the v2 campaign allowlist REGV4_OK and which"
  echo "byte-reproduces the old formal seed=2 results (see plan/reuse_audit.csv)."
  echo "Rebuild path (ns-3.17-era tree): CC='gcc' CXX='g++' python2 ./waf configure --build-profile=optimized && python2 ./waf build"
  echo "(exact original build flags not preserved; equivalence is established"
  echo "by the byte-level replay audit, not by rebuild.)"
} > "$B/provenance/build_commands.txt"
{ uname -a; g++ --version 2>/dev/null | head -1; python3 --version; } > "$B/provenance/environment.txt" 2>&1
sha256sum build/scratch/third > "$B/provenance/binary_sha256.txt"
for f in src/point-to-point/model/rdma-hw.cc src/point-to-point/model/rdma-hw.h \
         src/point-to-point/model/cbap-sba.cc src/point-to-point/model/cbap-sba.h \
         src/point-to-point/model/rdma-queue-pair.cc src/point-to-point/model/rdma-queue-pair.h \
         src/point-to-point/model/qbb-net-device.cc src/point-to-point/model/switch-node.cc \
         src/network/utils/switch-mmu.cc src/point-to-point/model/switch-mmu.cc scratch/third.cc; do
  [ -f "$f" ] && cp "$f" "$B/provenance/source_snapshot/" 2>/dev/null
done
grep -h "" /work/v2_400g/logs/REGV4_OK > "$B/provenance/REGV4_OK_allowlist.txt" 2>/dev/null || true

echo "== completion report + manifest (generated BEFORE copying) =="
python3 $ROOT/scripts/finalize_report.py

echo "== plan / derived / validation / docs =="
cp $ROOT/plan/run_plan.csv "$B/"
cp $ROOT/plan/run_manifest.csv "$B/" 2>/dev/null || true
cp $ROOT/plan/reuse_audit.csv "$B/" 2>/dev/null || true
cp $ROOT/plan/file_coverage.csv "$B/validation/" 2>/dev/null || true
cp $ROOT/derived/*.csv "$B/derived/" 2>/dev/null || true
cp $ROOT/validation/* "$B/validation/" 2>/dev/null || true
cp $ROOT/docs/*.md "$B/" 2>/dev/null || true
cp $ROOT/scripts/* "$B/scripts/" 2>/dev/null || true
cp -r $ROOT/detailed/* "$B/detailed/" 2>/dev/null || true
cp -r $ROOT/recovered_figure2/* "$B/recovered_figure2/" 2>/dev/null || true

echo "== inputs (configs + referenced flow/sched/path/link/topo, deduped) =="
cp $ROOT/configs/*.txt "$B/inputs/"
for pre in fm200g_s2 fm400g_s2 fm400g_s3 fm400g_s5 fm10g_s2; do
  for f in /work/v2_400g/configs/${pre}_*.txt /work/v2_400g/configs/topo_*.txt; do
    [ -f "$f" ] && cp -n "$f" "$B/inputs/" 2>/dev/null
  done
done

echo "== raw (new runs; CSVs gzipped losslessly) =="
while IFS=, read -r run_id rest; do
  [ "$run_id" = "run_id" ] && continue
  d=$ROOT/results/$run_id
  [ -d "$d" ] || continue
  o="$B/raw/$run_id"
  mkdir -p "$o"
  cp "$d"/STATUS "$d"/stdout.log "$d"/stderr.log "$o/" 2>/dev/null
  for c in "$d"/*.csv; do [ -f "$c" ] && gzip -c "$c" > "$o/$(basename "$c").gz"; done
  for t in "$d"/*.txt; do [ -f "$t" ] && gzip -c "$t" > "$o/$(basename "$t").gz"; done
done < $ROOT/plan/run_plan.csv

echo "== reused (old formal seed=2 + dcqs + cbap0, verbatim) =="
for tag in fm200g_s2 fm400g_s2 fm400g_s3 fm400g_s5; do
  for alg in cbap hpcc dcqn dctcp timely; do
    d=/work/v2_400g/results/${tag}_${alg}
    o="$B/reused/${tag}_${alg}"
    mkdir -p "$o"
    for c in "$d"/*; do
      [ -f "$c" ] || continue
      case "$c" in *.csv) gzip -c "$c" > "$o/$(basename "$c").gz";;
                   *) cp "$c" "$o/";; esac
    done
  done
done
for tag in fm10g_s2_dcqs fm200g_s2_dcqs fm400g_s2_dcqs fm10g_s2_cbap0 fm200g_s2_cbap0 fm400g_s2_cbap0 fm10g_s2_cbap; do
  d=/work/v2_400g/results/$tag
  [ -d "$d" ] || continue
  o="$B/reused/$tag"; mkdir -p "$o"
  for c in "$d"/*; do
    [ -f "$c" ] || continue
    case "$c" in *.csv) gzip -c "$c" > "$o/$(basename "$c").gz";;
                 *) cp "$c" "$o/";; esac
  done
done

echo "== SHA256SUMS =="
( cd "$B" && find . -type f ! -name SHA256SUMS.txt -print0 | sort -z \
  | xargs -0 sha256sum | sed 's# \./# #' > SHA256SUMS.txt )
wc -l "$B/SHA256SUMS.txt"

echo "== zip (ZIP64 via python) =="
python3 - "$ROOT/bundle" "$NAME" <<'PY'
import os, sys, zipfile
root, name = sys.argv[1], sys.argv[2]
zp = os.path.join("/work", name + ".zip")
with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as z:
    base = os.path.join(root, name)
    for dp, _, fns in os.walk(base):
        for fn in fns:
            p = os.path.join(dp, fn)
            z.write(p, os.path.relpath(p, root))
bad = zipfile.ZipFile(zp).testzip()
print("zip:", zp, "entries:", len(zipfile.ZipFile(zp).namelist()),
      "integrity:", "OK" if bad is None else "CORRUPT " + str(bad))
PY

echo "== extract-and-verify in a scratch copy =="
rm -rf /tmp/v20check && mkdir -p /tmp/v20check
python3 -m zipfile -e "/work/${NAME}.zip" /tmp/v20check
python3 $ROOT/scripts/verify_all.py --ziproot "/tmp/v20check/$NAME" \
  && echo "ZIP SELF-CHECK PASS" || echo "ZIP SELF-CHECK FAIL"
sha256sum "/work/${NAME}.zip"
ls -la "/work/${NAME}.zip"
