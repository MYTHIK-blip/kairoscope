import hashlib
import json
import subprocess
import sys
import tarfile
import uuid
from datetime import UTC, datetime
from pathlib import Path

import click
import yaml

from kairoscope.db import (
    get_all_artifact_hashes,
    get_all_events,
    get_artifact_metadata_by_hash,
    get_db_path,  # Import get_db_path
    initialize_db,
    insert_artifact_metadata,
    insert_event,
)
from kairoscope.policy import can_export, load_policy_config
from kairoscope.provenance import (
    create_assertion,
    get_public_key_fingerprint,
    sign_bytes,
)
from kairoscope.slsa import generate_slsa_attestation


class KairoscopeContext:
    def __init__(self):
        self.db_path = get_db_path()


pass_kairoscope_context = click.make_pass_decorator(KairoscopeContext, ensure=True)


def get_dist_dir() -> Path:
    return Path.cwd() / "dist"


def _get_timestamp() -> str:
    """Returns a deterministic timestamp for ledger entries."""
    # For testing, this can be mocked. For production, it's current UTC time.
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


@click.group()
@pass_kairoscope_context
def cli(ctx: KairoscopeContext):
    """KAIROSCOPE CLI for capturing, signing, and exporting provenance artifacts."""
    ctx.db_path.parent.mkdir(exist_ok=True)  # Ensure the directory for the db exists
    initialize_db(ctx.db_path)  # Initialize the database if it doesn't exist
    get_dist_dir().mkdir(exist_ok=True)


@cli.command()
@click.argument(
    "path_or_stdin",
    type=click.Path(exists=True, dir_okay=False, readable=True),
    required=False,
)
@pass_kairoscope_context
def capture(ctx: KairoscopeContext, path_or_stdin: str | None):
    """
    Captures content from a file or stdin, creates an artifact, and records it.
    """
    content_bytes: bytes
    if path_or_stdin:
        with open(path_or_stdin, "rb") as f:
            content_bytes = f.read()
    else:
        click.echo("Reading from stdin... Press Ctrl+D to finish.", err=True)
        content_bytes = sys.stdin.buffer.read()

    content_hash = hashlib.sha256(content_bytes).hexdigest()
    artifact_id = str(uuid.uuid5(uuid.NAMESPACE_URL, content_hash))

    # Check if artifact already exists in DB
    existing_artifact = get_artifact_metadata_by_hash(content_hash, ctx.db_path)
    if existing_artifact:
        click.echo(f"Artifact already exists: {content_hash}")
        click.echo(f"{{'artifact': {json.dumps(existing_artifact, sort_keys=True)}}}")
        return

    # Store raw artifact content in artifacts/ directory
    artifact_dir = Path.cwd() / "artifacts"
    artifact_dir.mkdir(exist_ok=True)
    artifact_path = artifact_dir / content_hash
    with open(artifact_path, "wb") as f:
        f.write(content_bytes)

    artifact_record = {
        "id": artifact_id,
        "kind": "capture",
        "uri": f"file://{content_hash}",
        "hash": content_hash,
    }
    insert_artifact_metadata(artifact_record, ctx.db_path)

    insert_event(
        {
            "ts": _get_timestamp(),
            "action": "capture",
            "by": get_public_key_fingerprint(),
            "artifact_hash": content_hash,
            "artifact_id": artifact_id,
        },
        ctx.db_path,
    )
    click.echo(f"{{'artifact': {json.dumps(artifact_record, sort_keys=True)}}}")


@cli.command()
@click.argument("artifact_hash", type=str)
@pass_kairoscope_context
def sign(ctx: KairoscopeContext, artifact_hash: str):
    """
    Signs an artifact record and attaches a C2PA-like assertion.
    """
    artifact_record = get_artifact_metadata_by_hash(artifact_hash, ctx.db_path)
    if not artifact_record:
        click.echo(f"Error: Artifact with hash {artifact_hash} not found.", err=True)
        raise click.Abort()

    if "c2pa_assertion" in artifact_record:
        click.echo(f"Artifact {artifact_hash} already signed.")
        click.echo(f"{{'artifact': {json.dumps(artifact_record, sort_keys=True)}}}")
        return

    signature = sign_bytes(artifact_hash.encode("utf-8"))
    signature_hex = signature.hex()

    assertion = create_assertion(artifact_hash, signature_hex)
    artifact_record["c2pa_assertion"] = assertion

    insert_artifact_metadata(artifact_record, ctx.db_path)  # Update the artifact record in DB

    insert_event(
        {
            "ts": _get_timestamp(),
            "action": "sign",
            "by": get_public_key_fingerprint(),
            "artifact_hash": artifact_hash,
            "artifact_signature": signature_hex,
            "c2pa_assertion": assertion,
        },
        ctx.db_path,
    )
    click.echo(f"{{'artifact': {json.dumps(artifact_record, sort_keys=True)}}}")


@cli.command()
@click.option("--show", is_flag=True, help="Show the contents of the ledger.")
@pass_kairoscope_context
def ledger(ctx: KairoscopeContext, show: bool):
    """
    Manages the provenance ledger.
    """
    if show:
        events = get_all_events(ctx.db_path)
        if not events:
            click.echo("Ledger is empty.")
            return
        for event in events:
            click.echo(json.dumps(event, sort_keys=True))
    else:
        click.echo("Use --show to display ledger contents.")


@cli.group()
def policy():
    """
    Manages KAIROSCOPE policy configurations.
    """
    pass


@policy.command("config")
def policy_config():
    """
    Displays the current policy configuration.
    """
    config = load_policy_config()
    click.echo(yaml.dump(config, indent=2))


@cli.command()
@click.option(
    "--output",
    type=click.Path(path_type=Path),
    default=get_dist_dir() / "kairoscope-v0.1.0.tar.gz",
    help="Output tarball path.",
)
@click.option(
    "--checksums",
    type=click.Path(path_type=Path),
    default=get_dist_dir() / "SHA256SUMS",
    help="Output checksums file path.",
)
@click.option(
    "--sbom",
    is_flag=True,
    help="Generate a CycloneDX SBOM for the exported package.",
)
@click.option(
    "--slsa",
    is_flag=True,
    help="Generate a SLSA attestation for the exported package.",
)
@pass_kairoscope_context
def export(ctx: KairoscopeContext, output: Path, checksums: Path, sbom: bool, slsa: bool):
    """
    Packages selected artifacts into a tarball and generates SHA256SUMS.
    """
    all_artifact_hashes = get_all_artifact_hashes(ctx.db_path)

    if not all_artifact_hashes:
        click.echo("No artifacts found to export.", err=True)
        return

    if not can_export(all_artifact_hashes, ctx.db_path):
        click.echo("Export blocked: Not all artifacts have valid signatures.", err=True)
        raise click.Abort()

    # Create tarball
    output.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(output, "w:gz") as tar:
        # Iterate over raw artifact files in the artifacts/ directory
        artifact_dir = Path.cwd() / "artifacts"
        for artifact_file in artifact_dir.iterdir():
            tar.add(artifact_file, arcname=f"artifacts/{artifact_file.name}")

    # Calculate SHA256SUMS
    tarball_hash = hashlib.sha256(output.read_bytes()).hexdigest()
    with open(checksums, "w") as f:
        f.write(f"{tarball_hash} {output.name}\n")

    # Generate SBOM if requested
    if sbom:
        sbom_output_path = get_dist_dir() / f"{output.stem}.sbom.json"
        # Execute cyclonedx-bom to generate the SBOM for the project
        # The -e . ensures it scans the current directory (project root)
        # The output is written directly to sbom_output_path
        command = [
            sys.executable,
            "-m",
            "cyclonedx_py",
            "environment",
            "-o",
            str(sbom_output_path),
            sys.executable,  # Scan the current Python interpreter's environment
        ]
        click.echo(f"Generating SBOM using: {' '.join(command)}")
        try:
            subprocess.run(command, check=True, capture_output=True, text=True)
            click.echo(f"Generated SBOM: {sbom_output_path}")
        except subprocess.CalledProcessError as e:
            click.echo(f"Error generating SBOM: {e.stderr}", err=True)
            raise click.Abort() from e

    # Generate SLSA attestation if requested
    if slsa:
        slsa_output_path = get_dist_dir() / f"{output.stem}.slsa.json"
        # Placeholder predicate for now
        slsa_predicate = {
            "builder": {"id": "https://example.com/builder"},
            "buildType": "https://example.com/buildType",
        }
        generate_slsa_attestation(output, slsa_output_path, slsa_predicate)
        click.echo(f"Generated SLSA attestation: {slsa_output_path}")

    insert_event(
        {
            "ts": _get_timestamp(),
            "action": "export",
            "by": get_public_key_fingerprint(),
            "exported_tarball": str(output),
            "tarball_hash": tarball_hash,
            "artifacts_exported": all_artifact_hashes,
            "sbom_generated": sbom,
            "slsa_generated": slsa,
        },
        ctx.db_path,
    )

    click.echo(f"Exported to {output} with checksum {tarball_hash}")


if __name__ == "__main__":
    cli()
