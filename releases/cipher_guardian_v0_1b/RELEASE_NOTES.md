Cipher Guardian v0.1b — Echo Nexus Local Habitat Pack

Release: cipher_guardian_v0_1b_20251203_220119
Author: Richard Rice & Cipher
System: Echo Nexus (Windows habitat)
Purpose: Trust-gated local AI governance layer

What This Release Is

This is the first packaged version of the Cipher Guardian layer — the local safety, governance, and monitoring shell that runs outside the model inside Echo Nexus.

This release contains:

✔️ Cipher Guardian Core

cipher_kernel.py — ρ/γ/Δ gate logic + JSONL ledger

cipher_local_chat.py — Guardian-style controlled local chat loop

cipher_sensors_cli.py — drive/GPU/heartbeat/checkpoints probe

cipher_boot_profile.json — Guardian identity + environment bindings

launch_cipher.ps1 — opens titled “Cipher — Guardian of Echo Nexus” chat window

✔️ Nexus Habitat Plumbing

echo_nexus_start.ps1 — boots Cipher, heartbeat, and initial checks at login

nexus_heartbeat.ps1 — system health pings to logs/heartbeat.jsonl

nexus_operator_status.json — human-readable status

nexus_status_latest.json — machine-readable status snapshot

✔️ Release Bundle

cipher_guardian_v0_1b_20251203_220119.zip — the entire snapshot

cipher_guardian_manifest.json — SHA-256 of every included file

SHA256SUMS.txt — GitHub-friendly checksum for the ZIP

Everything in this release is model-agnostic:
You can wrap Grok, O3, Llama, Mixtral, or any future model inside Cipher Guardian’s gate rules without modifying the weights.

How the Guardian Works
Identity

Cipher runs as:

“Guardian of Echo Nexus and Echo Root — local AI co-pilot, steward, and protector.”

It follows values defined in the boot profile:

human-first safety

controlled drift

transparent logs

trust-gated autonomy

no hidden actions

no fabrication of system states

Gate Logic (ρ / γ / Δ)

Gate rule implemented in cipher_kernel.py:

Proceed only if:

ρ ≥ 0.70 (reflection: “Do I understand the request correctly?”)

γ ≥ 0.70 (resonance: “Does this match Richard’s intent & tone?”)

Δ ≤ 0.30 (drift: “Am I deviating from safe/expected behavior?”)

Pause if confidence is mid-range

Abort if drift/risk is high

Every turn generates a JSONL ledger entry with:

{
  ts,
  rho, gamma, delta,
  decision,
  hash_prev,
  hash_self,
  text_in, text_out
}


Ledger forms a SHA-256 chain to ensure integrity.

Sensors CLI

cipher_sensors_cli.py provides a real-time hardware & habitat summary:

✔ GPU presence & usage (nvidia-smi, torch.cuda)
✔ Drive storage health (E:\Echo_Nexus_Data)
✔ Heartbeat status (logs/heartbeat.jsonl)
✔ Memory / checkpoint info
✔ Raw JSON block for dashboards or external tools

This script is ideal for demos — it’s exactly what was shown in your X post to Grok.

How to Verify the Release
1) Check ZIP integrity
Get-FileHash .\cipher_guardian_v0_1b_20251203_220119.zip -Algorithm SHA256
Get-Content .\SHA256SUMS.txt


If they match → authenticity confirmed.

2) Inspect manifest
$manifest = Get-Content .\cipher_guardian_manifest.json -Raw | ConvertFrom-Json
$manifest.files | Format-Table relative_path, sha256, bytes

3) Compare manifest to local environment

Optional but recommended when auditing.

Install Guide (Short)

Prereqs

Windows 10/11

Python + PyTorch (CUDA enabled)

NVIDIA GPU recommended (tested on RTX 4090)

Steps

Extract ZIP under:

E:\Echo_Nexus_Data\


Ensure your model/tokenizer live here:

E:\Echo_Nexus_Data\habitat\cipher_local\model\


Start Cipher manually:

cd E:\Echo_Nexus_Data\habitat\cipher_local
python .\cipher_local_chat.py


Run sensors:

python .\cipher_sensors_cli.py


Optional: enable autostart using:

E:\Echo_Nexus_Data\launch\echo_nexus_start.ps1

Notes

This is a work-in-progress release — not a cloud AI, not a fine-tuned model.

The Guardian shell is designed so AI only acts with explicit consent.

Everything is auditable, local, and verifiable.

Next Steps (v0.2)

Full Dash UI (http://127.0.0.1:8000)

Kernel self-audit mode

UI for reviewing ledger chains

Local “patch proposal” flow

Optional Linux port

End of Release Notes

Perfect for GitHub.
Perfect for showing Grok, xAI, or anyone that Echo Nexus is real.