"""IoO publication evidence gate. Offline; never calls an AI or submits a paper."""
import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROLES = ('Claude Code', 'Codex', 'ChatGPT')
CHECKS = ('discussion_limitations', 'contribution_supported', 'clinical_scope',
          'ending_reviewed', 'abstract_consistent', 'artifacts_verified')
CANONICAL_POLICY = Path(__file__).with_name('IoO_Publication_Policy.md')

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def resolve(root, name):
    p = Path(name)
    if p.is_absolute() or '..' in p.parts:
        raise ValueError('Only project-relative paths are allowed')
    p = (root / p).resolve()
    if not p.is_relative_to(root.resolve()) or not p.is_file():
        raise ValueError('Missing file or path outside project: ' + name)
    return p

def stamp(value):
    d = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if d.tzinfo is None or d > datetime.now(timezone.utc):
        raise ValueError('Timestamp needs timezone and must not be in future')
    return d

def text(value):
    return isinstance(value, str) and bool(value.strip()) and not re.search(
        r'TODO|TBD|PLACEHOLDER|未記入|<[^>]+>', value, re.I)

def snapshot(config, root):
    if sha(resolve(root, config['policy'])) != sha(CANONICAL_POLICY):
        raise ValueError('Policy differs from canonical policy distributed with IoO gate')
    names = [config['manuscript'], config['policy'], *config['artifacts']]
    if not config['artifacts'] or len(set(names)) != len(names):
        raise ValueError('Declare distinct manuscript, policy and final artifacts')
    hashes = {name: sha(resolve(root, name)) for name in names}
    # Bind configuration too: changing section selection or evidence paths revokes approval.
    payload = {'config': config, 'files': hashes}
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True,
                            ensure_ascii=False).encode()).hexdigest()
    return digest, hashes

def conclusion(source):
    matches = list(re.finditer(r'^#{1,6}\s+(?:\d+[.\s]+)?(?:Conclusions?|結論)\s*$',
                              source, re.I | re.M))
    if len(matches) != 1:
        raise ValueError('Exactly one Markdown Conclusion heading required; normalize source first')
    start = matches[0].end()
    rest = source[start:]
    level = len(matches[0].group().lstrip().split()[0])
    end = re.search(r'^#{1,' + str(level) + r'}\s+', rest, re.M)
    body = rest[:end.start()] if end else rest
    # Subsections belong to the Conclusion; headings are not ending prose.
    body = re.sub(r'^#{1,6}\s+.*$', '', body, flags=re.M)
    paragraphs = [p.strip() for p in re.split(r'\n\s*\n', body) if p.strip()]
    if not paragraphs:
        raise ValueError('Empty Conclusion')
    return paragraphs[-1]

def warnings(ending):
    return ['ENDING_REQUIRES_REVIEW'] if re.search(
        r'not\s+(?:yet\s+)?(?:been\s+)?(?:evaluat|validat|test|assess)|neither|never\s+performed|'
        r'no\s+clinical|remain\w*\s+un(?:test|validat)|未検証|未実施|評価していない|評価されていない|検証されていない',
        ending, re.I) else []

def check(config, root):
    digest, _ = snapshot(config, root)
    ending = conclusion(resolve(root, config['manuscript']).read_text(encoding='utf-8-sig'))
    alerts = warnings(ending)
    errors, review_hashes, times = [], {}, []
    if set(config['reviews']) != set(ROLES):
        raise ValueError('All three AI review paths required')
    if len(set(config['reviews'].values())) != 3:
        raise ValueError('Independent review files required')
    for role in ROLES:
        p = resolve(root, config['reviews'][role])
        r = load(p)
        review_hashes[role] = sha(p)
        times.append(stamp(r['reviewed_at']))
        if (r.get('role') != role or r.get('snapshot') != digest
                or r.get('decision') != 'pass' or r.get('independent') is not True
                or r.get('unresolved') != [] or not text(r.get('session'))
                or r.get('policy_sha256') != sha(resolve(root, config['policy']))
                or r.get('ending_quote') != ending):
            errors.append(role + ': missing, stale or unsuccessful review')
        for key in CHECKS:
            item = r.get('checks', {}).get(key, {})
            if item.get('pass') is not True or not text(item.get('evidence')):
                errors.append(role + ': missing check ' + key)
        if not text(r.get('ending_rationale')):
            errors.append(role + ': warning requires reasoned disposition')
    human = load(resolve(root, config['human']))
    approval_time = stamp(human['approved_at'])
    if (human.get('approved') is not True or human.get('snapshot') != digest
            or human.get('review_sha256') != review_hashes
            or not text(human.get('name')) or not text(human.get('approval_evidence'))
            or approval_time < max(times)):
        errors.append('Human approval missing, stale or predates reviews')
    if not text(human.get('ending_rationale')):
        errors.append('Human must resolve ending warning')
    return {'status': 'BLOCKED' if errors else 'PASS', 'snapshot': digest,
            'warnings': alerts, 'errors': errors}

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('config', type=Path)
    p.add_argument('--snapshot', action='store_true')
    args = p.parse_args()
    try:
        config = load(args.config)
        root = (args.config.parent / config['project_root']).resolve()
        if args.snapshot:
            digest, hashes = snapshot(config, root)
            result = {'status': 'SNAPSHOT_ONLY', 'snapshot': digest, 'files': hashes}
        else:
            result = check(config, root)
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        result = {'status': 'BLOCKED', 'errors': [str(exc)]}
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0 if result['status'] in ('PASS', 'SNAPSHOT_ONLY') else 1

if __name__ == '__main__':
    raise SystemExit(main())
