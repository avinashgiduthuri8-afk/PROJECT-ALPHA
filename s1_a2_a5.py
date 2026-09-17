import paramiko

def run_ssh(ssh, cmd, label=""):
    if label: print(f"\n--- {label} ---")
    stdin, stdout, stderr = ssh.exec_command(f"cd /opt/project-alpha && {cmd}")
    out = stdout.read().decode('utf-8', errors='replace').strip()
    err = stderr.read().decode('utf-8', errors='replace').strip()
    if out: print(out)
    if err and 'warning' not in err.lower() and 'committer' not in err.lower(): print("ERR:", err)
    return out

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('148.113.9.103', 20069, 'root', 'SMT6SiQU2nIUMj0V')

# ═══════════════════════════════════════════════════════════
# Phase A2: Document V2Config alias
# ═══════════════════════════════════════════════════════════
run_ssh(ssh, 'grep -n "V2Config" core/config.py | head -5', "A2: Current V2Config references")

run_ssh(ssh, """python3 -c "
import re
with open('core/config.py', 'r') as f:
    content = f.read()
if '# Backward compatibility alias' not in content:
    content = content.replace('V2Config = AppConfig', '# Backward compatibility alias (permanent, used by legacy tests)\\nV2Config = AppConfig')
    with open('core/config.py', 'w') as f:
        f.write(content)
    print('Added backward compat comment')
else:
    print('Comment already exists')
" """, "A2: Add compat comment")

run_ssh(ssh, 'git add core/config.py && git commit -m "Docs: Document V2Config as permanent backward-compat alias" 2>/dev/null && git log --oneline -1', "A2: Commit")

# ═══════════════════════════════════════════════════════════
# Phase A3: Rename test files
# ═══════════════════════════════════════════════════════════
run_ssh(ssh, 'ls tests/test_v2_*.py 2>/dev/null | wc -l', "A3: Count test_v2_ files")

run_ssh(ssh, """cd tests && for f in test_v2_*.py; do [ -f "$f" ] && mv "$f" "${f/test_v2_/test_}"; done && cd .. && echo "done renaming" """, "A3: Rename all test_v2_*.py")

run_ssh(ssh, 'ls tests/test_v2_*.py 2>/dev/null | wc -l || echo "0 remaining"', "A3: Verify no test_v2_ files remain")
run_ssh(ssh, 'ls tests/test_*.py 2>/dev/null | wc -l', "A3: Count renamed test files")

run_ssh(ssh, 'git add tests/ && git commit -m "Refactor: Rename all test files (test_v2_*.py -> test_*.py)" 2>/dev/null && git log --oneline -1', "A3: Commit")

# ═══════════════════════════════════════════════════════════
# Phase A4: Source code comments
# ═══════════════════════════════════════════════════════════
run_ssh(ssh, 'grep -rn "v2/services/" --include="*.py" background/ core/ scanner/ execution/ telegram/ dashboard/ 2>/dev/null | head -10', "A4: Find v2/services references")

run_ssh(ssh, """find background/ core/ scanner/ execution/ telegram/ dashboard/ -name '*.py' -exec sed -i 's|v2/services/|core/|g' {} \\; && echo "done"  """, "A4: Update v2/services -> core in comments")

run_ssh(ssh, 'git add -A && git diff --cached --stat | tail -5', "A4: Check changes")
run_ssh(ssh, 'git commit -m "Docs: Update module path references in comments (v2/services -> core)" 2>/dev/null && git log --oneline -1', "A4: Commit")

# ═══════════════════════════════════════════════════════════
# Phase A5: CSS/JS class renaming
# ═══════════════════════════════════════════════════════════
run_ssh(ssh, 'grep -rn "\\.v2-" dashboard/static/ dashboard/templates/ 2>/dev/null | wc -l', "A5: Count .v2- CSS references")

run_ssh(ssh, """
find dashboard/static/css/ -name '*.css' -exec sed -i 's/\\.v2-panel-/.alpha-panel-/g' {} \\; 2>/dev/null
find dashboard/static/css/ -name '*.css' -exec sed -i 's/\\.v2-two-col-/.alpha-two-col-/g' {} \\; 2>/dev/null
find dashboard/static/css/ -name '*.css' -exec sed -i 's/\\.v2-section-/.alpha-section-/g' {} \\; 2>/dev/null
find dashboard/static/css/ -name '*.css' -exec sed -i 's/\\.v2-/.alpha-/g' {} \\; 2>/dev/null
find dashboard/templates/ -name '*.html' -exec sed -i 's/class="v2-/class="alpha-/g' {} \\; 2>/dev/null
find dashboard/templates/ -name '*.html' -exec sed -i 's/v2-panel-/alpha-panel-/g' {} \\; 2>/dev/null
find dashboard/templates/ -name '*.html' -exec sed -i 's/v2-two-col-/alpha-two-col-/g' {} \\; 2>/dev/null
find dashboard/templates/ -name '*.html' -exec sed -i 's/v2-section-/alpha-section-/g' {} \\; 2>/dev/null
find dashboard/static/js/ -name '*.js' -exec sed -i 's/class V2InstitutionalDashboard/class AlphaDashboard/g' {} \\; 2>/dev/null
find dashboard/static/js/ -name '*.js' -exec sed -i 's/window\\.v2Dashboard/window.alphaDashboard/g' {} \\; 2>/dev/null
find dashboard/static/js/ -name '*.js' -exec sed -i 's/v2_api_key/alpha_api_key/g' {} \\; 2>/dev/null
echo "done"
""", "A5: Rename CSS/JS classes")

run_ssh(ssh, 'grep -rn "\\.v2-" dashboard/ 2>/dev/null | wc -l || echo "0"', "A5: Verify no .v2- references remain")
run_ssh(ssh, 'git add dashboard/ && git commit -m "Refactor: Rename CSS/JS classes from v2-/V2 to alpha-/Alpha" 2>/dev/null && git log --oneline -1', "A5: Commit")

ssh.close()
print("\n=== Parts A2-A5 Complete ===")

