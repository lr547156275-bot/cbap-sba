#!/bin/bash
# D6.1: search for the Figure-2 fixed-cap pilot materials.  Report only.
OUT=/work/v20/recovered_figure2
mkdir -p "$OUT"
R="$OUT/search_report.md"
{
echo "# 图2固定上限对照材料检索报告"
echo
echo "目标：10 Gb/s、64×1 MiB 先导对照；CCT≈58.373/83.949 ms；峰值队列 1279608/62880 B。"
echo "检索时间：$(date -u +%FT%TZ)"
echo
echo "## 已检索位置"
echo
echo '### 1. /work 文件系统'
for p in /work/d2_caponly_out /work/*evidence* /work/g1_matrix \
         /work/g2_validation /work/g3_stress_frontier \
         /work/DISK_RECLAIM_MANIFEST.txt; do
  if ls -d $p >/dev/null 2>&1; then echo "- FOUND: $p"; else echo "- absent: $p"; fi
done
echo "- relverify.py: $(ls /work/relverify.py 2>/dev/null || echo absent)"
echo
echo '### 2. git 分支与提交信息'
cd /work/simulation
echo '```'
git branch -a 2>/dev/null | sed 's/^/branch: /'
echo '```'
echo "提交信息关键词检索（caponly / cap-only / d2_ / g1_matrix / evidence）："
echo '```'
git log --all --oneline --grep="caponly" --grep="cap-only" --grep="d2_" \
        --grep="g1_matrix" --grep="evidence-2026" 2>/dev/null | head -20
echo '```'
echo "历史文件名检索："
echo '```'
git log --all --name-only --format="__%h %s" 2>/dev/null \
  | grep -iE "caponly|cap_only|d2_|g1_matrix|g3_stress|DISK_RECLAIM" \
  | sort -u | head -30
echo '```'
echo
echo '### 3. /work 全盘文件名检索'
echo '```'
find /work -maxdepth 4 \( -iname "*capon*" -o -iname "*cap_only*" \
     -o -iname "*d2_*" -o -iname "*g1_matrix*" -o -iname "*RECLAIM*" \) \
     -not -path "*/build/*" 2>/dev/null | head -20
echo '```'
echo
echo '### 4. 旧配置内容检索（10G + 1 MiB + 上限类键）'
echo '```'
grep -rlE "1048576" /work/v2_400g/configs /work/simulation/experiment 2>/dev/null | head
grep -rliE "cap|LIMIT_NEW|AGG_RATE" /work/simulation/experiment/rwmcr_problem1 2>/dev/null | head
echo '```'
} > "$R"
FOUND=$(grep -c "^- FOUND" "$R")
echo "search report written to $R  (filesystem hits: $FOUND)"
echo "NOTE: 结论与缺失清单见报告正文；未找到时不得从图中吞吐反推上限值。"
