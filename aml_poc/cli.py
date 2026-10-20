import argparse
import json
import os
import signal
import subprocess
import sys
import time

from .config import DATA, ROOT, RUNTIME


def prepare():
    from .data import Dataset
    from .evaluate import evaluate
    from .generate import generate
    from .store import Store

    manifest = generate(DATA)
    dataset = Dataset(DATA)
    metrics = {"history": evaluate(dataset), "combined": evaluate(dataset, include_stream=True)}
    RUNTIME.mkdir(parents=True, exist_ok=True)
    (RUNTIME / "evaluation.json").write_text(json.dumps(metrics, indent=2) + "\n")
    store = Store(RUNTIME)
    store.set_metadata("evaluation", metrics)
    store.close()
    print(
        json.dumps(
            {
                "stream": manifest,
                "history": {
                    k: metrics["history"][k] for k in ["alerts", "detected_groups", "scenario_pattern_groups"]
                },
                "combined": {
                    k: metrics["combined"][k]
                    for k in ["alerts", "detected_groups", "scenario_pattern_groups"]
                },
            },
            indent=2,
        )
    )


def serve(api_port=8001, ui_port=8501):
    import requests

    if not (DATA / "stream_transactions.csv").exists() or not (RUNTIME / "evaluation.json").exists():
        prepare()
    processes = []
    try:
        api = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "aml_poc.api:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(api_port),
            ],
            cwd=ROOT,
        )
        processes.append(api)
        address = f"http://127.0.0.1:{api_port}"
        ready = False
        for _ in range(100):
            if api.poll() is not None:
                raise RuntimeError("API exited during startup. Check the error above.")
            try:
                ready = requests.get(address + "/health", timeout=1).ok
                if ready:
                    break
            except requests.RequestException:
                pass
            time.sleep(0.2)
        if not ready:
            raise RuntimeError("API did not become ready")
        environment = {**os.environ, "AML_API_URL": address, "STREAMLIT_BROWSER_GATHER_USAGE_STATS": "false"}
        ui = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                str(ROOT / "aml_poc" / "ui.py"),
                "--server.address",
                "127.0.0.1",
                "--server.port",
                str(ui_port),
                "--server.headless",
                "true",
                "--browser.gatherUsageStats",
                "false",
            ],
            cwd=ROOT,
            env=environment,
        )
        processes.append(ui)
        print(
            f"\nConsole: http://127.0.0.1:{ui_port}\nAPI docs: {address}/docs\nCtrl+C stops both services.\n",
            flush=True,
        )
        while all(p.poll() is None for p in processes):
            time.sleep(0.5)
        if any(p.returncode not in (None, 0) for p in processes):
            raise RuntimeError("A service exited unexpectedly")
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.send_signal(signal.SIGINT)
        for process in processes:
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.terminate()


def main():
    parser = argparse.ArgumentParser(description="Streaming AML investigation POC")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("prepare", help="Generate 1,000 stream events and evaluate detectors")
    sub.add_parser("backtest", help="Evaluate history and stream against held-out labels")
    launch = sub.add_parser("serve", help="Run the API and Streamlit console")
    launch.add_argument("--api-port", type=int, default=8001)
    launch.add_argument("--ui-port", type=int, default=8501)
    replay = sub.add_parser("replay", help="Start the server's Python replay worker")
    replay.add_argument("--rate", type=float, default=50)
    replay.add_argument("--api", default="http://127.0.0.1:8001")
    replay.add_argument("--no-investigate", action="store_true")
    args = parser.parse_args()
    if args.command in {"prepare", "backtest"}:
        prepare()
    elif args.command == "replay":
        import requests

        response = requests.post(
            args.api + "/replay/start",
            json={"events_per_second": args.rate, "auto_investigate": not args.no_investigate},
            timeout=30,
        )
        response.raise_for_status()
        print(json.dumps(response.json(), indent=2))
    else:
        try:
            serve(getattr(args, "api_port", 8001), getattr(args, "ui_port", 8501))
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
