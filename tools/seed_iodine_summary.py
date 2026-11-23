"""What the basis-coordinate penalty did to the iodine deviation, per run.

Section 3.3 compares the spread of the iodine deviation across training seeds with the
change the penalty itself produced. Both quantities were written into the manuscript by
hand, and the second one did not survive being checked: the printed interval could not be
reproduced from any frozen file, and the shipped D2-minus-D1 difference is several times
smaller than what the sentence claimed. The runbook's rule is that a number in the prose
is read out of a result file, not typed; this script is that file for these numbers.

Nothing is retrained. It reads three frozen evaluations that already exist -
`denoised_eval.json` (D1), `denoised_eval_d2.json` (the archived D2 weights) and
`seed_replication_d2.json` (the three seeds) - and reports, for the quarter-count
conditions:

* the absolute iodine deviation of D1, of the archived D2 weights, and of each seed;
* the change in absolute deviation each D2 run produced against D1, signed, so that a
  negative number is an improvement and the count of improvements is not a matter of
  interpretation;
* the spread across seeds within one condition, which is the quantity the manuscript
  compares that change against.

    python tools/seed_iodine_summary.py
"""
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / 'results'
OUT = RESULTS / 'seed_iodine_summary.json'
QUARTER = 0.25


def conditions(name):
    return {(c['size_cm'], c['dose_fraction']): c
            for c in json.loads((RESULTS / name).read_text())['conditions']}


def mean_dev(entry):
    """Mean iodine deviation in mgI/mL. The evaluations store g/cm3."""
    return 1000.0 * entry['quantitation']['denoised_dev']['mean']


def main():
    d1 = conditions('denoised_eval.json')
    d2 = conditions('denoised_eval_d2.json')
    seeds = json.loads((RESULTS / 'seed_replication_d2.json').read_text())
    seed_ids = seeds['seeds']
    by_key = {(c['size_cm'], c['dose_fraction']): c for c in seeds['conditions']}

    rows = []
    for key in sorted(k for k in by_key if k[1] == QUARTER):
        base = abs(mean_dev(d1[key]))
        shipped = abs(mean_dev(d2[key]))
        values = [abs(v) for v in by_key[key]['iodine_deviation_mgi_ml']['values']]
        rows.append({
            'size_cm': key[0],
            'dose_fraction': key[1],
            'd1_abs_deviation_mgi_ml': base,
            'shipped_d2_abs_deviation_mgi_ml': shipped,
            'shipped_change_vs_d1_mgi_ml': shipped - base,
            'seed_abs_deviation_mgi_ml': dict(zip(map(str, seed_ids), values)),
            'seed_change_vs_d1_mgi_ml': [v - base for v in values],
            'seed_spread_mgi_ml': max(values) - min(values),
        })

    changes = [c for r in rows for c in r['seed_change_vs_d1_mgi_ml']]
    improved = [c for c in changes if c < 0]
    worsened = [c for c in changes if c >= 0]
    spreads = [r['seed_spread_mgi_ml'] for r in rows]
    shipped_changes = [abs(r['shipped_change_vs_d1_mgi_ml']) for r in rows]

    record = {
        'written': '2026-11-24',
        'what': ('The change in absolute iodine deviation that the basis-coordinate '
                 'penalty produced against the D1 arm, at quarter count, for the '
                 'archived D2 weights and for each of the three seed replicates. '
                 'Derived from frozen evaluations; nothing was retrained.'),
        'sources': ['results/denoised_eval.json', 'results/denoised_eval_d2.json',
                    'results/seed_replication_d2.json'],
        'conditions': rows,
        'verdict': {
            'n_runs': len(changes),
            'n_improved': len(improved),
            'n_worsened': len(worsened),
            'largest_improvement_mgi_ml': -min(changes),
            'largest_worsening_mgi_ml': max(changes),
            'seed_spread_within_condition_mgi_ml': [min(spreads), max(spreads)],
            'shipped_change_vs_d1_abs_mgi_ml': [min(shipped_changes), max(shipped_changes)],
        },
    }
    OUT.write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')

    v = record['verdict']
    print('quarter count, %d runs over %d conditions and %d seeds'
          % (v['n_runs'], len(rows), len(seed_ids)))
    for r in rows:
        print('  %g cm  D1 %.3f  archived D2 %.3f (%+.3f)  seeds %s  spread %.3f'
              % (r['size_cm'], r['d1_abs_deviation_mgi_ml'],
                 r['shipped_d2_abs_deviation_mgi_ml'], r['shipped_change_vs_d1_mgi_ml'],
                 ' '.join('%.3f' % x for x in r['seed_abs_deviation_mgi_ml'].values()),
                 r['seed_spread_mgi_ml']))
    print('  improved in %d of %d runs; change from %.2f mgI/mL better to %.2f worse'
          % (v['n_improved'], v['n_runs'], v['largest_improvement_mgi_ml'],
             v['largest_worsening_mgi_ml']))
    print('  seed spread within a condition %.2f-%.2f mgI/mL'
          % tuple(v['seed_spread_within_condition_mgi_ml']))
    print('  archived weights changed the deviation by %.3f-%.3f mgI/mL'
          % tuple(v['shipped_change_vs_d1_abs_mgi_ml']))
    print('wrote %s' % OUT)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
