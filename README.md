# prosperity4-cal

Local workspace for IMC Prosperity strategy development, run analysis, and log visualization.

## Main files

- [main.py](/mnt/c/Users/-/Downloads/34362/Kaan_v0-1.py): current baseline strategy
- [convert_imc_visualizer_log.py](/mnt/c/Users/-/Downloads/34362/convert_imc_visualizer_log.py): converts IMC JSON-style exports into a file the Prosperity 3 visualizer can open
- [imc-prosperity-3-visualizer-master](/mnt/c/Users/-/Downloads/34362/imc-prosperity-3-visualizer-master): local checkout of the public Prosperity 3 visualizer

## Typical workflow

1. Run a backtest or submission on IMC.
2. Download the result files, usually a `.json` and `.log`.
3. Inspect performance locally with the custom visualizer or convert the log for the public visualizer.

## Convert IMC logs for the Prosperity 3 visualizer

Some IMC downloads are JSON-style exports and do not load directly in the public visualizer. Convert them first:

```bash
python3 convert_imc_visualizer_log.py 42163.log
```

This creates:

```text
42163_visualizer.log
```

Load that converted file in the visualizer's `Load from file` page.

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
