"""Audit exact lockfiles against OSV/npm; no source or credentials leave the host."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import urllib.request
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--report', default='docs/audits/dependencies.json')
    args = parser.parse_args()
    lock = ROOT / 'deploy/requirements.lock'
    packages = [line.split('==', 1) for line in lock.read_text('utf-8').splitlines()
                if line and not line.startswith('#')]
    request = urllib.request.Request('https://api.osv.dev/v1/querybatch',
        data=json.dumps({'queries': [{'package': {'name': name, 'ecosystem': 'PyPI'},
                                     'version': version} for name, version in packages]}).encode(),
        headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=60) as response:
        results = json.load(response)['results']
    if len(results) != len(packages):
        raise RuntimeError('Incomplete OSV response')
    findings = [{'package': name, 'version': version,
                 'advisories': sorted(v['id'] for v in result.get('vulns', []))}
                for (name, version), result in zip(packages, results) if result.get('vulns')]
    npm = subprocess.run(['npm.cmd' if __import__('os').name == 'nt' else 'npm', 'audit', '--json'],
                         cwd=ROOT / 'apps/web', capture_output=True, text=True, encoding='utf-8')
    npm_report = json.loads(npm.stdout)
    if npm_report.get('error') or 'metadata' not in npm_report:
        raise RuntimeError('npm audit unavailable')
    report = {'checked_at': datetime.now(timezone.utc).isoformat(),
              'sources': ['https://api.osv.dev/v1/querybatch', 'npm audit registry advisories'],
              'python_packages_checked': len(packages), 'python_findings': findings,
              'npm': npm_report, 'lock_sha256': {
                  'python': hashlib.sha256(lock.read_bytes()).hexdigest(),
                  'npm': hashlib.sha256((ROOT / 'apps/web/package-lock.json').read_bytes()).hexdigest()},
              'limitations': ['Published advisory databases only; absence of findings is not proof of security.',
                              'Container/OS/JRE/Keycloak vulnerability scans are not included.'],
              'status': 'passed' if not findings and npm_report['metadata']['vulnerabilities']['total'] == 0 else 'review_required'}
    path = ROOT / args.report
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', 'utf-8', newline='\n')
    print(json.dumps({'status': report['status'], 'python_packages': len(packages),
                      'python_findings': findings, 'npm_vulnerabilities': npm_report['metadata']['vulnerabilities']}, ensure_ascii=False))
    raise SystemExit(0 if report['status'] == 'passed' else 1)


if __name__ == '__main__':
    main()
