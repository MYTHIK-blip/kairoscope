# Kairoscope System Overview

**Date:** 2025-11-11

## 1. Core Purpose

Based on our analysis and testing, Kairoscope is a command-line tool that functions as a **digital notary for files**. Its primary purpose is to create a permanent, verifiable, and cryptographically secure "chain of custody" for any digital artifact.

It does not automatically "fetch" or "ingest" data into an inbox. Instead, the user directs it to a specific file that already exists. The system then creates a verifiable record of that file's existence and state at a particular moment in time, without altering the original file itself.

## 2. Core Workflow

The system's functionality is exposed through a series of simple commands, which we have successfully tested:

1.  **`capture <file_path>`**:
    *   The user provides a path to a file.
    *   Kairoscope calculates a unique fingerprint of the file (a SHA256 hash).
    *   It creates a timestamped "capture" event and records it in the ledger. The original file remains untouched.

2.  **`sign <hash>`**:
    *   The user takes the hash generated during the capture step.
    *   This command uses the system's cryptographic key (a private key stored locally) to sign the record of the file.
    *   This creates a non-repudiable link between the signer and the file's specific version at that time. This is the core "attestation" step.

3.  **`ledger --show`**:
    *   This command displays the full, immutable log of all events (captures, signs, exports) that the system has recorded. The ledger appears to be stored in both a local SQLite database (`kairoscope.db`) and a human-readable JSONL file (`events.jsonl`).

4.  **`export`**:
    *   This command packages artifacts and their attestations into a secure distributable format (`.tar.gz`).
    *   Crucially, it can also generate and include software supply chain metadata like SBOM (Software Bill of Materials) and SLSA attestations, which enhances its utility in software security contexts.

## 3. Key Components

The system is composed of several distinct parts:

*   **Command-Line Interface (`cli.py`):** The main entry point for users.
*   **Provenance Engine (`provenance.py`):** The core of the system, responsible for generating cryptographic keys, hashing files, and handling the signing/verification logic.
*   **Ledger:** A database (`kairoscope.db`) and log file (`events.jsonl`) that serves as the immutable record of events.
*   **Policy Engine (`policy.py`):** A governance layer that enforces rules. For example, the default policy might require an artifact to be signed before it can be exported.

## 4. Current Status (As of v0.2 Silver)

*   The system is **functional and not just conceptual**.
*   We have successfully run its internal test suite (`pytest`), which passed after minor formatting fixes.
*   We have demonstrated the primary capture -> sign -> ledger workflow with a test file.
*   The current version is designated "Silver (v0.2)", indicating it has moved beyond a basic prototype and includes a more advanced policy engine and supply-chain security features (SBOM/SLSA).

## 5. Path to Real-World Use

While functional, the system's own roadmap indicates several key steps are needed for it to be considered "industry standard":

*   **Hardware-Backed Keys:** Moving cryptographic keys from files to secure hardware (like a TPM or Secure Enclave) to prevent key theft.
*   **Edge Deployment:** Adapting the tool to run on mobile phones, IoT devices, and wearables, so data can be certified at its point of origin.
*   **Advanced Trust & Privacy:** Implementing multi-party signatures and privacy-preserving proofs (like ZKPs) for more complex, regulated use cases.

## 6. Further Analysis & Clarifications

**Timestamp:** 2025-11-11

This section details additional findings based on a deeper analysis of the system's architecture and philosophy.

### Data Input Model: Reactive, Not Proactive
Kairoscope does not feature an ETL (Extract, Transform, Load) process or any built-in connectors for hardware or databases. It operates on a **reactive model**. Data is sourced by providing a direct file path to the `capture` command. The responsibility of creating or placing the file on the local filesystem lies with the user or an external process.

### AI Integration: A Future Goal
The system **does not currently have any integrated AI models**. The references to AI in the documentation describe a future capability. The intended purpose is to use AI for tasks like summarization, anomaly detection, or data interpretation, with the crucial feature that the AI's actions would themselves be captured and signed by Kairoscope to ensure an auditable trail.

### License (AGPL-3.0) & Misuse
The AGPL-3.0 license is designed to ensure the software and its modifications remain open-source, particularly for network-based services. It does not, and cannot, prevent the software from being used for malicious purposes. This is standard for all open-source licenses. The project's `ADDENDUM.md` serves as a social contract outlining ethical intent, but the license itself governs the code's distribution, not its use case.

### Directory Structure: `tests/` vs. `artifacts/`
- The **`/tests`** directory contains the automated test scripts (`pytest`) that verify the correctness of the application's code.
- The **`/artifacts`** directory is the storage location for the content of files that have been processed by the `kairoscope capture` command.

## 7. Project Housekeeping

**Timestamp:** 2025-11-11

To maintain a clean project structure, the following actions were taken:
- The temporary file created for our demonstration, `test_document.txt`, was moved into the `/tests` directory.
- A stray file named `test_artifact.txt` was investigated. It was found to be unreferenced by any part of the project and was removed.
