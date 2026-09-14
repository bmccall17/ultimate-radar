import json, numpy as np, collections, sys
SC = (r'C:\Users\BRETTA~1\AppData\Local\Temp\claude'
      r'\E--dev-playertrackerultimate-ultimate-radar'
      r'\d561224d-591f-4a27-aae9-c0002e65675b\scratchpad')
for d in sys.argv[1:]:
    for tag, path in (('BEFORE', f'{SC}\\cal.{d}.pre.json'),
                      ('AFTER', f'work/{d}/calibration.json')):
        try:
            cal = json.load(open(path))
        except FileNotFoundError:
            print(f'{d} {tag}: missing'); continue
        fr = cal['frames']
        conf = np.array([r.get('confidence') or 0 for r in fr])
        res = np.array([r.get('residual_yd') if r.get('residual_yd') is not None
                        else np.nan for r in fr])
        pd = np.array([r.get('pose_disagreement_yd', np.nan) for r in fr], float)
        vt = cal.get('venue_transform', {})
        print('%s %-6s conf>=0.5 %3d/%-4d (%3.0f%%)  median residual %.4f  '
              'y_offset %s measured=%s' % (
                  d, tag, (conf >= 0.5).sum(), len(fr), 100 * (conf >= 0.5).mean(),
                  float(np.nanmedian(res)), vt.get('y_offset'), vt.get('measured')))
        if np.isfinite(pd).any():
            ok = conf >= 0.5
            pan = np.array([(r.get('camera') or {}).get('pan_deg', np.nan)
                            for r in fr], float)
            rate = np.abs(np.gradient(pan))
            m = np.isfinite(pd) & np.isfinite(rate) & ok
            c = float(np.corrcoef(rate[m], pd[m])[0, 1]) if m.sum() > 3 else float('nan')
            print('        pose_disagreement median %.3f yd (accepted %.3f); '
                  'corr with |pan rate| %.3f' % (
                      float(np.nanmedian(pd)), float(np.nanmedian(pd[ok])), c))
        n = collections.Counter((r.get('note') or 'ok')[:38]
                                for r in fr if (r.get('confidence') or 0) < 0.5)
        print('        still rejected:', dict(n))
