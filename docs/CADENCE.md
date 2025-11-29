# ⬡ KAIROSCOPE Cadence: Workflow & Ethos

This document outlines the development cadence, contribution guidelines, and core principles for the KAIROSCOPE project. It is a guide for all contributors and operators to ensure the project's integrity, coherence, and long-term health.

---

## 1. Guiding Principles (The Covenant)

Our work is guided by the principles laid out in our `ADDENDUM.md`. All contributions and maintenance activities must align with this covenant. The key pillars are:

-   **Provenance-Mandatory by Design:** Verifiable proof of origin and transformation is not an optional feature; it is the core of the system.
-   **Anti-Enclosure & Open Ecosystem:** We build for interoperability and data portability, using open standards to prevent vendor lock-in.
-   **Continuity & Exportability:** The system is designed for long-term data integrity and resilience, with offline-first capabilities and easy data migration.
-   **Ethical AI & Data Sovereignty:** We are committed to verifiable AI provenance, user control over data, and mitigating algorithmic bias.

---

## 2. Git & Release Workflow

We follow a structured workflow to ensure that every change is deliberate, traceable, and aligns with our quality standards.

### Commit Message Convention (Gemstones)

To provide a clear and immediate understanding of the nature of each change, all commit messages **must** be prefixed with a "gemstone" emoticon and a conventional commit type.

-   `✨ feat:` A new feature is introduced.
-   `🐛 fix:` A bug is fixed.
-   `📚 docs:` Documentation-only changes.
-   `💎 style:` Code style changes that do not affect the meaning of the code (e.g., formatting, white-space).
-   `🔨 refactor:` A code change that neither fixes a bug nor adds a feature.
-   `🧪 test:` Adding missing tests or correcting existing tests.
-   `⚙️ chore:` Changes to the build process, auxiliary tools, dependencies, or other project maintenance.

### Release Tagging Convention (Medallions)

Major releases are tagged in alignment with the project's "Medallion" roadmap. These tags mark significant, stable milestones.

-   `🥉 v0.1.x-bronze`
-   `🥈 v0.2.x-silver`
-   `🥇 v0.3.x-gold`
-   `🏆 v0.4.x-platinum`

---

## 3. End-to-End Workflow: Command Reference

This section provides a consolidated list of commands for the entire development and release lifecycle.

### A. Everyday Development Cycle

Follow these steps when making any change.

1.  **Activate Environment:**
    ```bash
    source .venv/bin/activate
    ```

2.  **Make Code/Doc Changes:**
    *   Edit the relevant files in `src/`, `tests/`, `docs/`, etc.

3.  **Run Local Quality & Test Gates:**
    *   This is a crucial step to ensure your changes are valid before committing.
    ```bash
    # Run all checks in sequence
    ruff check . && black --check . && mypy --ignore-missing-imports src/kairoscope && pytest -q
    ```

4.  **Run Pre-Commit Hooks (Optional but Recommended):**
    *   This can auto-fix some issues and ensures alignment with project standards.
    ```bash
    pre-commit run --all-files
    ```

5.  **Stage and Commit:**
    *   Use the gemstone convention for your commit message.
    ```bash
    git add .
    git commit -m "✨ feat: describe the new feature"
    ```

6.  **Push to Remote:**
    ```bash
    git push origin main
    ```

### B. Release & Tagging Cycle

Follow these steps when creating a new project release. This should only be done when `main` is stable and ready.

1.  **Create Annotated Tag:**
    *   Use the Medallion convention.
    ```bash
    # Example for a Silver release
    git tag -a v0.2.0-silver -m "Silver v0.2 Release: Advanced policy engine and SLSA/SBOM integration."
    ```

2.  **Push Tag to Remote:**
    *   Commits should be pushed before the tag.
    ```bash
    git push --tags
    ```

3.  **Generate Release Tarball:**
    *   This creates the source code archive for reproducibility and air-gapped deployment.
    ```bash
    # Example for the v0.2.0-silver release
    git archive --format=tar.gz --prefix=kairoscope-0.2.0/ -o kairoscope-v0.2.0-silver.tar.gz v0.2.0-silver
    ```
    *   This tarball should then be uploaded or stored as a release artifact.

---

## 4. Community & Contribution

We welcome contributions that align with our project's vision and quality standards.

### Contribution Workflow

1.  **Discuss:** Before starting significant work, open an issue to discuss your proposed changes.
2.  **Develop:** Adhere to the project's coding standards and the commit message conventions outlined above.
3.  **Test & Lint:** Ensure your changes pass all local quality gates as shown in the command reference.
4.  **Commit:** Create a pull request with a clear description of your changes. Your commit history should be clean and follow the gemstone convention.

### Licensing, Legitimacy & Ethics

-   **Licensing:** By contributing code, you agree to license it under the **AGPL-3.0**. By contributing documentation, you agree to license it under **CC BY-SA 4.0**. This ensures the project and its derivatives remain open and accessible.
-   **Legitimacy:** The legitimacy of KAIROSCOPE is derived from its transparency, cryptographic verifiability, and adherence to open standards. We build trust by making our processes and our code open to scrutiny.
-   **Ethics:** This tool is designed to enhance truth and accountability. It should not be used to create or propagate deceptive or malicious content. While the license does not restrict use, the community and its operators are guided by the ethical principles of data sovereignty and provenance, as detailed in the `ADDENDUM.md`. We reserve the right to refuse contributions that conflict with these principles.
