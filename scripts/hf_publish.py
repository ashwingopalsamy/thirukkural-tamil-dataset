"""Upload dist/hf to a PRIVATE Hugging Face dataset repo, tag it, and verify the upload byte for byte.

  python -m tkcore.release --check          build dist/hf from this commit; fails if the committed card is stale
  python scripts/hf_publish.py              dry run: check the folder, the login and the target; upload nothing
  python scripts/hf_publish.py --upload     create the private repo if missing, upload, tag v<version>, verify

Uses the Hugging Face login already on this machine (`hf auth login`); it never reads, prints or accepts a token.
Refuses to upload when the target repo is public, when the tag already exists, when dist/hf holds anything but the
release files listed in MANIFEST.json (so no modern translation or commentary can go up), or while any file still
holds the placeholder site address.
Needs huggingface_hub, which is not in requirements.txt.
"""
import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tkcore.release import CONFIGS, DIST, META, VERSION  # noqa: E402

TOP = {"README.md", "croissant.json", "CITATION.cff", "LICENSE", "LICENSES.md", "CHANGELOG.md", "MANIFEST.json"}
PLACEHOLDER = "thirukkural.example"  # the development address; a file that still carries it was built before base_url was set
EXPECTED = TOP | {f"data/{name}.parquet" for name in CONFIGS}
TAG = f"v{VERSION}"


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def check_folder(folder: Path = DIST) -> dict:
    """The folder holds exactly the release files, each matching MANIFEST.json, for this version."""
    on_disk = {str(p.relative_to(folder)) for p in folder.rglob("*") if p.is_file()}
    if on_disk != EXPECTED:
        raise SystemExit(f"unexpected files: {sorted(on_disk - EXPECTED)}; missing: {sorted(EXPECTED - on_disk)}")
    m = json.loads((folder / "MANIFEST.json").read_text(encoding="utf-8"))
    if m["version"] != VERSION or m["dataset"] != META["hf_repo"]:
        raise SystemExit(f"MANIFEST.json is for {m['dataset']} {m['version']}, release.json says {META['hf_repo']} {VERSION}")
    if set(m["files"]) != EXPECTED - {"MANIFEST.json"}:
        raise SystemExit("MANIFEST.json does not list exactly the release files")
    for rel, meta in m["files"].items():
        if _sha(folder / rel) != meta["sha256"]:
            raise SystemExit(f"{rel} does not match MANIFEST.json; rebuild with python -m tkcore.release")
    return m


def placeholder_files(folder: Path = DIST) -> list[str]:
    """Files that still carry the placeholder site address (permalinks in quote_keys and agent_card)."""
    import pyarrow.parquet as pq
    hits = []
    for rel in sorted(EXPECTED):
        p = folder / rel
        text = (json.dumps(pq.read_table(p).to_pylist(), ensure_ascii=False) if p.suffix == ".parquet"
                else p.read_text(encoding="utf-8", errors="replace"))
        if PLACEHOLDER in text:
            hits.append(rel)
    return hits


def _not_found_error():
    try:
        from huggingface_hub.errors import RepositoryNotFoundError
    except ImportError:  # older huggingface_hub
        from huggingface_hub.utils import RepositoryNotFoundError
    return RepositoryNotFoundError


def target_state(api, repo: str) -> dict:
    try:
        info = api.repo_info(repo, repo_type="dataset")
    except _not_found_error():
        return {"exists": False, "private": None, "tags": []}
    tags = [t.name for t in api.list_repo_refs(repo, repo_type="dataset").tags]
    return {"exists": True, "private": info.private, "tags": tags}


def verify(api, repo: str, folder: Path, m: dict) -> None:
    """Download every file at the tag and compare it with the local build."""
    if not api.repo_info(repo, repo_type="dataset").private:
        raise SystemExit(f"{repo} is public")
    from huggingface_hub import hf_hub_download
    with tempfile.TemporaryDirectory() as d:
        for rel in sorted(EXPECTED):
            got = Path(hf_hub_download(repo, rel, repo_type="dataset", revision=TAG, local_dir=d))
            if _sha(got) != _sha(folder / rel):
                raise SystemExit(f"{rel} on the Hub at {TAG} differs from dist/hf")
            print(f"  ok  {rel}")
    print(f"verified {len(EXPECTED)} files at {repo}@{TAG}; kurals root {m['kurals_root_sha256']}")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--upload", action="store_true", help="upload; without it, a dry run")
    args = ap.parse_args(argv)
    m = check_folder()
    repo = META["hf_repo"]
    print(f"dist/hf: {len(EXPECTED)} files, version {VERSION}, kurals root {m['kurals_root_sha256']}")
    for rel in sorted(EXPECTED - {"MANIFEST.json"}):
        print(f"  {m['files'][rel]['bytes']:>9,}  {m['files'][rel]['sha256'][:16]}  {rel}")

    from huggingface_hub import HfApi
    api = HfApi()
    me = api.whoami()
    owner = repo.split("/")[0]
    if owner != me["name"] and owner not in {o["name"] for o in me.get("orgs", [])}:
        raise SystemExit(f"logged in as {me['name']}, who cannot write to {owner}")
    state = target_state(api, repo)
    print(f"target {repo}: {'exists' if state['exists'] else 'will be created'}"
          f"{', private' if state['private'] else ', PUBLIC' if state['exists'] else ', private'}; tags {state['tags']}")
    if state["exists"] and not state["private"]:
        raise SystemExit("refusing: the target repo is public")
    if TAG in state["tags"]:
        raise SystemExit(f"refusing: {TAG} already exists on {repo}; bump release/release.json")
    stale = placeholder_files()
    if stale:
        raise SystemExit(f"refusing: {stale} still link to {PLACEHOLDER}; set PERMALINK_BASE in tkcore/signature.py, "
                         "rebuild data/signature (python -m tkcore.signature) and the release")
    if not args.upload:
        print("dry run: nothing uploaded. Run with --upload to publish privately.")
        return

    if not state["exists"]:
        api.create_repo(repo, repo_type="dataset", private=True)
        if not api.repo_info(repo, repo_type="dataset").private:
            raise SystemExit(f"{repo} was created public; make it private on the Hub before uploading")
    commit = api.upload_folder(repo_id=repo, repo_type="dataset", folder_path=str(DIST),
                               commit_message=f"Release {TAG}", delete_patterns=["*.md", "*.json", "*.cff", "LICENSE", "data/*"])
    api.create_tag(repo, tag=TAG, revision=commit.oid, repo_type="dataset",
                   tag_message=f"{TAG}; kurals root {m['kurals_root_sha256']}")
    print(f"uploaded {commit.oid[:12]} and tagged {TAG}")
    verify(api, repo, DIST, m)


if __name__ == "__main__":
    main()
