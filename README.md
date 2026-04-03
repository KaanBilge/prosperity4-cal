# prosperity4-cal

Local workspace for IMC Prosperity strategy development, run analysis, and log visualization.

## Main files

- [main.py](/mnt/c/Users/-/Downloads/34362/Kaan_v0-1.py): current baseline strategy
- [convert_imc_visualizer_log.py](/mnt/c/Users/-/Downloads/34362/convert_imc_visualizer_log.py): deprecated
- [imc-prosperity-3-visualizer-master](/mnt/c/Users/-/Downloads/34362/imc-prosperity-3-visualizer-master): local checkout of the public Prosperity 3 visualizer (Works for prosperity 4 logs now)

## Typical workflow

1. Run a backtest or submission on IMC.
2. Download the result files, usually a `.json` and `.log`.
3. Inspect performance locally with public visualizer.

## Run the public visualizer locally

```bash
cd imc-prosperity-3-visualizer-master
pnpm install
pnpm dev
```

If `pnpm` is not installed:

```bash
npm install
npm run dev
```

Then open the local URL shown by Vite, usually `http://localhost:5173`.

## Notes

- The baseline strategy is `main.py`.
- The custom converter is best-effort reconstruction for visualization, not the original raw server log.
- Keep downloaded runs in separate folders when possible, for example `42163/`.
