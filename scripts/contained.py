"""Explicit container entry point for contained kube-burner execution or verified publication."""

import argparse
import os
from pathlib import Path

from scripts import contained_inputs as inputs
from scripts import contained_observation as observation
from scripts import contained_publish as publisher
from scripts import contained_run as runner


def main(argv: list[str] | None = None) -> int:
    """Keep operational errors credential-free; never retry execution or perform implicit cleanup."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("run", "publish"))
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--request-sha256", required=True)
    parser.add_argument("--output", type=Path, default=Path("/results"))
    args = parser.parse_args(argv)
    stage = "request and packaged-input validation"
    try:
        request = inputs.load(args.request, args.request_sha256)
        if args.action == "run":
            stage = "owned-target qualification and supervised measurement"
            print("Verifying target ownership, warm image and initial observations...", flush=True)
            runner.run(
                request,
                args.output,
                observation.Kubernetes(),
                os.environ["PERFENG_EXECUTOR_POD_UID"],
            )
            print("Complete capture retained; Kubernetes resources remain control-plane owned.")
        else:
            stage = "frozen capture verification"
            publisher.prepare(request, args.output)
            stage = "conditional object publication and read-back verification"
            result = publisher.publish(publisher.client(), request, args.output)
            print(inputs.encode(result).decode(), end="")
        return 0
    except KeyboardInterrupt:
        print("Contained execution interrupted; partial evidence retained, no automatic cleanup.")
        return 130
    except Exception:
        print(
            f"Contained operation failed during {stage}; inspect retained evidence. External output withheld; no cleanup or replacement was attempted.",
            flush=True,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
