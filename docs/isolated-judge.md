# Isolated programming judge

The main Windows runtime uses bounded SQL and declarative/data practice. Programming execution is a separate optional service, implemented in `services/judge/`. It is never replaced by native execution if the sandbox is missing.

Two original programming practices (merge intervals and rolling event count) are supported in Python and JavaScript. A successful practice does not change a professional category. The trusted checker compares outputs outside the sandbox; expected answers are never mounted into it. Only trusted task IDs and deployment-configured images are allowed.

## Separate Linux VM

Provision a dedicated, disposable Linux VM with Docker and the [gVisor runsc runtime](https://gvisor.dev/docs/user_guide/quick_start/docker/). Sandbox flags include `--runtime=runsc`, `--pull=never`, `--network=none`, `--read-only`, `--cap-drop=ALL`, `--security-opt=no-new-privileges:true`, non-root user, 256 MB RAM/no additional swap, one CPU, 32 PIDs, 16 MB noexec tmpfs, 64 KB bounded output and a 20-second watchdog. [Docker resource constraints](https://docs.docker.com/engine/containers/resource_constraints/) require host support and must be verified on the target VM.

Docker administration has substantial host privileges even when the application service is non-root. This VM must not host the API database, identity secrets, user uploads or other workloads. No Docker socket is mounted into submitted containers. Network access to gateway port 8091 must be limited to the API host; use a private network or an authenticated TLS reverse proxy across hosts.

1. Install the project API dependencies into `/opt/vector/.venv`, copy `services/judge/` and `services/common/`.
2. Provision trusted official Python/Node images manually; record resolved `image@sha256:...` values. A tag such as `latest` is rejected. The service never pulls images on a submission.
3. Set `/etc/vector-judge.env` using the template in `deploy/judge/`, with an independent random shared secret of at least 32 characters and a writable job directory owned by `vector-judge`.
4. Install `deploy/judge/vector-judge.service` under the VM's service manager. Verify `GET /ready` reports runsc availability; verify real resource enforcement and adversarial cleanup before enabling user submissions.
5. Configure the API's `JUDGE_URL` and matching `JUDGE_SHARED_SECRET`. API availability requires the gateway to explicitly report `isolation=gvisor_runsc`.

The gateway authenticates timestamp + exact body with HMAC-SHA256. A bounded request reader rejects oversized chunked bodies; a locked in-flight receipt prevents duplicate execution/conflicting ID reuse. It returns aggregate test outcomes, not hidden inputs or expected results. API stores only the source hash, scoped result and audit record. Replay receipts are in memory for five minutes; persistent API records and deployment transport remain separate boundaries.

## What was actually verified

Windows fail-closed behavior; required command flags; mandatory image digest; public oracle separation; request signature/body/validation handling; exact replay and concurrent in-flight deduplication. These tests never execute submitted source.

Linux container execution, seccomp/gVisor enforcement, escape resistance and real kill/orphan cleanup are **not tested on the current Windows machine**, which has neither Docker nor enabled WSL. Do not describe configuration or mocked boundary tests as proof of sandbox security. The local UI correctly disables this execution route while retaining safe practice.
