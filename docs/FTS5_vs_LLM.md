# FTS5 Ledger vs. LLM-based Data Retrieval in Kairoscope

**Date:** 2025-12-03

This document addresses a core architectural question in Kairoscope: Why use a structured, searchable database (like an FTS5-enabled SQLite ledger) for provenance data instead of using a Large Language Model (LLM) to crawl and interpret a simple log file?

## The Core Difference: Verification vs. Interpretation

The answer lies in the fundamental difference between what a database and an LLM are designed to do, especially within a system where trust and verifiability are paramount.

*   **A Database (with FTS5) is a Verifier:** Its primary job is to store and retrieve structured data with perfect fidelity. When you query the Kairoscope ledger for a signed event, it returns that exact, byte-for-byte record. Its strength is the **deterministic retrieval of verifiable facts**. You can then independently check the cryptographic signatures within that record to confirm its authenticity. The database doesn't interpret or guess; it retrieves.

*   **An LLM is an Interpreter:** An LLM's power lies in its ability to understand natural language, summarize unstructured text, and identify complex patterns. However, it is an *interpreter*, not a witness. It doesn't "verify" truth; it generates a plausible response based on the data it's given. If you were to ask an LLM to find an event in a simple log file, it would find text that *looks* like that event. It cannot, however, guarantee the cryptographic integrity of that log entry. It could be fooled by a tampered record, misinterpret an ambiguous entry, or even "hallucinate" details that aren't there.

## Where AI Fits in the Kairoscope Architecture

AI is not the gatekeeper of the data; it is a powerful **consumer** of the **verified data** that the core system provides. The Kairoscope ethos is "provenance-first," which means establishing a cryptographically secure "ground truth" *before* any AI-driven interpretation occurs.

The correct workflow is as follows:

1.  **Capture & Verify (No AI):** The core Kairoscope pipeline captures an artifact, signs it, and records the event in the SQLite ledger. This process is deterministic, verifiable, and does not involve any AI. This is your "ground truth."
2.  **Retrieve with Certainty (FTS5):** When you need to find a specific event, artifact, or piece of data, you use the FTS5-enabled ledger. This provides a fast, efficient, and direct way to retrieve the exact, verified records you need.
3.  **Interpret & Analyze (AI):** *After* you have retrieved the trustworthy data from the ledger, you can then pass it to an LLM for higher-level tasks, such as:
    *   "Here are the last 20 verified events from the ledger. Please provide a summary of the activity."
    *   "I've retrieved the signed provenance records for these three artifacts. Can you explain the relationship between them?"
    *   "This artifact is a signed transcript of a meeting. Please extract the key decisions and action items."

## Why Not Just Use an LLM on a Raw Log File?

Using an LLM to directly crawl a simple log file would violate several of Kairoscope's core principles:

*   **Trust & Verifiability:** An LLM cannot guarantee the integrity of the data it's reading. The FTS5 ledger, containing signed and hashed records, provides this guarantee.
*   **Speed & Efficiency:** For direct lookups and simple queries, a local, indexed FTS5 search is orders of magnitude faster and more resource-efficient than making an API call to a large language model.
*   **Cost:** Relying on an LLM for every data retrieval task would be prohibitively expensive.
*   **"Collapse-Aware Design":** Kairoscope is designed to be resilient and offline-first. Relying on a cloud-based LLM for a core function like data retrieval would create a critical dependency that goes against this ethos. A local SQLite database is far more robust and self-contained.

## Conclusion

In summary, you don't build an FTS5 ledger *instead* of using an LLM. You build an FTS5 ledger to have a **fast, efficient, and trustworthy source of truth**. You then use an LLM to perform complex analysis and interpretation **on that trusted data**.

This separation of concerns is fundamental to the Kairoscope architecture, ensuring that the system is both powerful and secure.
