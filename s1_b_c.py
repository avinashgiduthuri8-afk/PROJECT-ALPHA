import paramiko

def run_ssh(ssh, cmd, label=""):
    if label: print(f"\n--- {label} ---")
    stdin, stdout, stderr = ssh.exec_command(f"cd /opt/project-alpha && {cmd}")
    out = stdout.read().decode('utf-8', errors='replace').strip()
    err = stderr.read().decode('utf-8', errors='replace').strip()
    if out: print(out.encode('ascii', 'replace').decode('ascii'))
    if err and 'warning' not in err.lower() and 'committer' not in err.lower() and 'configured auto' not in err.lower(): print("ERR:", err.encode('ascii', 'replace').decode('ascii'))
    return out

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('148.113.9.103', 20069, 'root', 'SMT6SiQU2nIUMj0V')

# ═══════════════════════════════════════════════════════════
# Phase B1: Config keys cleanup
# ═══════════════════════════════════════════════════════════
run_ssh(ssh, 'grep -n "LEGACY_FIELD_MAP" core/config.py | head -3', "B1: Current LEGACY_FIELD_MAP")

run_ssh(ssh, """python3 -c "
import re
with open('core/config.py', 'r') as f:
    content = f.read()
if '# Backward-compatibility mapping' not in content:
    content = content.replace('LEGACY_FIELD_MAP = {', '# Backward-compatibility mapping: production deployments may still use V2_* env vars\\nLEGACY_FIELD_MAP = {')
    with open('core/config.py', 'w') as f:
        f.write(content)
    print('Added legacy map comment')
else:
    print('Comment already exists')
" """, "B1: Document LEGACY_FIELD_MAP")

# Clean config_override.json
run_ssh(ssh, """python3 -c "
import json, os
path = 'data/config_override.json'
if os.path.exists(path):
    with open(path, 'r') as f:
        config = json.load(f)
    canonical_only = {k: v for k, v in config.items() if not k.startswith('v2_')}
    with open(path, 'w') as f:
        json.dump(canonical_only, f, indent=2)
    print('Cleaned config_override.json (removed v2_* keys)')
    print(json.dumps(canonical_only, indent=2))
else:
    print('config_override.json not found')
" """, "B1: Clean config_override.json")

run_ssh(ssh, 'git add core/config.py data/config_override.json 2>/dev/null; git commit -m "Refactor: Document legacy config mapping, clean config_override.json to canonical keys only" 2>/dev/null && git log --oneline -1', "B1: Commit")

# ═══════════════════════════════════════════════════════════
# Phase B2: Telegram messaging updates
# ═══════════════════════════════════════════════════════════
run_ssh(ssh, 'grep -n "V2 MISSION CONTROL\\|V2 SYSTEM STATUS\\|V2 COMPONENT\\|PROJECT-ALPHA V2" telegram/*.py | head -10', "B2: Find V2 branding in Telegram")

run_ssh(ssh, """
sed -i 's/PROJECT-ALPHA V2/PROJECT-ALPHA/g' telegram/formatters.py telegram/telegram_interface.py 2>/dev/null
sed -i 's/V2 MISSION CONTROL/MISSION CONTROL/g' telegram/formatters.py telegram/telegram_interface.py 2>/dev/null
sed -i 's/V2 SYSTEM/SYSTEM/g' telegram/formatters.py telegram/telegram_interface.py 2>/dev/null
sed -i 's/V2 COMPONENT/COMPONENT/g' telegram/formatters.py telegram/telegram_interface.py 2>/dev/null
echo "done"
""", "B2: Remove V2 branding")

run_ssh(ssh, 'grep -c "PROJECT-ALPHA V2\\|V2 MISSION\\|V2 SYSTEM\\|V2 COMPONENT" telegram/*.py 2>/dev/null || echo "No V2 strings found (good)"', "B2: Verify")

run_ssh(ssh, 'git add telegram/ && git commit -m "Refactor: Remove V2 branding from Telegram operator messages" 2>/dev/null && git log --oneline -1', "B2: Commit")

# ═══════════════════════════════════════════════════════════
# Phase C1: Documentation updates
# ═══════════════════════════════════════════════════════════
run_ssh(ssh, 'grep -n "PROJECT-ALPHA V2\\|v2/services\\|v2/scanner" PROJECT.md STOCK_CLONE_BLUEPRINT.md 2>/dev/null | head -10', "C1: Find V2 references in docs")

run_ssh(ssh, """
sed -i 's/PROJECT-ALPHA V2/PROJECT-ALPHA/g' PROJECT.md STOCK_CLONE_BLUEPRINT.md 2>/dev/null
sed -i 's/Release Version: v2/Release Version: PROJECT-ALPHA/g' PROJECT.md STOCK_CLONE_BLUEPRINT.md 2>/dev/null
sed -i 's|v2/services|core|g' PROJECT.md STOCK_CLONE_BLUEPRINT.md 2>/dev/null
sed -i 's|v2/scanner|scanner|g' PROJECT.md STOCK_CLONE_BLUEPRINT.md 2>/dev/null
echo "done updating docs"
""", "C1: Update docs")

run_ssh(ssh, 'grep -n "v2\\|V2" README.md 2>/dev/null | head -10', "C1: Check README.md")

run_ssh(ssh, """
[ -f TEST_INFRA.md ] && sed -i 's/test_v2_/test_/g' TEST_INFRA.md && echo "updated TEST_INFRA.md" || echo "TEST_INFRA.md not found"
""", "C1: Update TEST_INFRA.md")

run_ssh(ssh, 'git add PROJECT.md STOCK_CLONE_BLUEPRINT.md README.md TEST_INFRA.md 2>/dev/null; git add -A && git commit -m "Docs: Update references from v2 to PROJECT-ALPHA across all project documentation" 2>/dev/null && git log --oneline -1', "C1: Commit")

ssh.close()
print("\n=== Parts B & C Complete ===")
