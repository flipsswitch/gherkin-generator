# Public release review

The public repository was assembled in a separate directory with fresh Git history. Only the generator, adapters, default parameters, research notes, geometry recipe, tests and preview images are included. The custom MicroStation MCP and its implementation remain private.

The candidate release was checked with a local pattern scan and manual review for credential formats, secret assignments, email addresses, absolute workstation paths, local account names, private network addresses, session identifiers, configuration files and unexpected binaries. Python imports and file-writing behavior were reviewed for external dependencies and host assumptions. No credentials, private personal information or machine-specific paths were identified in the release candidate. Public source authors and attribution links are intentionally retained.

Preview PNGs were inspected visually. EXIF and text metadata were stripped, including render metadata, while retaining the original compressed pixel stream. Native DGN/Blender files, bytecode caches, generated logs, temporary scripts and raw MCP receipts are excluded from the repository. A public GitHub noreply identity is used for the release commit.

The model generators do not contact a network service, install packages, load the private MCP, or read credentials. Paths are resolved relative to the scripts, supplied by the caller, or obtained from the active CAD file. MicroStation's native Python API and Blender's embedded API are intentional application requirements. The standard-library geometry code can be tested separately. The privacy inspection tool invokes local Git; it does not fetch data or read credentials.

This was a targeted release hygiene review using local checks, not a third-party security audit or a guarantee against every possible secret pattern. Generated outputs on another machine can contain that application's own metadata and should be reviewed before being shared.

The researched interior/electrical update received the same working-tree and committed-blob review, plus a scan of every blob and commit reachable from the public repository's local Git refs. No findings remained. Seven new native-model preview PNGs were stripped of ancillary metadata without changing their compressed image data. The source register links public documents and records fingerprints; third-party PDFs, drawings and embedded contact details are not redistributed. The private MCP, host outputs and local automation helpers remain excluded.

## Follow-up privacy audit, 17 October 2026

The supplied static audit inspected commit `11e4da0` and reported no confirmed private PII exposure. Its three preventive findings also applied to the researched release at `0791a3b`: raw exception text in structured logs, an absolute report path printed by MicroStation, and incomplete exclusion of custom output folders. It also identified the absence of automated privacy checks.

The follow-up reviewed the current source, all three pre-existing commits and their 68 unique blobs, the previous 55-file source ZIP, and all 14 public PNGs. No credentials, private contact information or workstation paths were found in those public materials. Public source attribution, application versions and the public GitHub identity are retained intentionally. No history rewrite or credential rotation was indicated by these findings.

The remediation adds:

- Error events containing only a bounded exception category, a generic diagnostic message and a recognized numeric operating-system error code when available. Neither raw exception text nor arbitrary exception class names are copied to `run-log.json` or the interior adapter's printed event records.
- A generic MicroStation success message with no active DGN name or absolute report directory.
- A `.gitignore` in every newly created output directory, excluding its complete contents. Geometry-only single-file exports and standalone schedules get exact filename rules; existing rules are preserved. Common generated reports, native models, archives and credential-file extensions are also excluded at repository level.
- Automatic removal of PNG text, EXIF and other unapproved ancillary chunks after each render. PNG checksums and end-of-file integrity are checked; compressed image data is preserved. The saved Blender scene now uses a relative default render destination.
- A dependency-free privacy scanner and a CI job with full Git history. The job also creates and scans the exact committed source archive.

## Run the checks

From a full Git checkout with Python 3.10 or newer and Git available on PATH:

```sh
python tools/privacy_scan.py --history
python -m unittest discover -s tests -v
git archive --format=zip --prefix=gherkin-generator/ --output=public-source.zip HEAD
python tools/privacy_scan.py --archive public-source.zip
```

The first command screens tracked files, unignored additions, every reachable historical blob, commit/tag text and historical filenames. It refuses a shallow checkout. The archive command inspects entries without extracting them. Reports give rules and locations without printing matched values; suspicious filenames are redacted. Exit status is zero for no findings, one for findings and two for incomplete inspection. GitHub Actions checks the fetched branch/tag history; local scans cover local refs. Neither claim includes unrelated forks, deleted remote refs, issue attachments or GitHub account settings.

Checks cover common credential formats, quoted secret assignments, bearer tokens, JWTs, credential-bearing URLs, email addresses, recognizable phone numbers, workstation paths, private networks, private tool state, generated/native files, unexpected binary formats, symlinks, PNG metadata and archive metadata. Synthetic tests verify detection, including a secret deleted from a later commit. The scanner is a targeted standard-library control, not a replacement for every capability of a specialist secret scanner. Arbitrary names, postal addresses, obfuscated secrets and sensitive image pixels still require human review.

## Local artifacts and diagnostics

Generated `run-log.json` error events are suitable for review without raw exception payloads. Other fields can still reflect customized parameters; inspect all reports before publishing them. Native application output and Python tracebacks may contain absolute paths and host identifiers. They remain private diagnostics and are not made shareable by the structured-log change. Failures still propagate so command-line exit status and host error handling remain intact.

The existing local DGN was independently inspected as a compound document: its `SummaryInformation` stream contains a workstation account identifier. It is **not cleared for public release unchanged**. That file is not committed or included in the source ZIP. The existing Blender file had no linked libraries or embedded text scripts; its exposed dependency/render paths were inspected through Blender. The GLB JSON had no scanner findings or external buffers. These checks do not fully decode all proprietary or compressed native metadata, so none of these local native files is certified free of identifying metadata.

Use the source ZIP or repository for public distribution. Native files, raw console logs, downloaded research documents and private MCP tooling remain excluded. Ignore rules cannot prevent forced additions or remove already tracked data; the CI scanner provides a second check. Customized parameter files can contain personal annotations and are not automatically scrubbed, because silently changing modeling inputs would compromise reproducibility.

The numerical geometry, original parameters and historical validation evidence are unchanged. Hashes and timings in the existing model-validation summaries describe their original builds; they are not relabeled as measurements of this privacy revision.

## Remediation validation

The 36-test regression suite passed locally, followed by all 13 privacy tests after adding an ignore-negation edge case; the complete suite now contains 37 tests. Blender 5.2.1 LTS rebuilt the original exterior and researched interior, saved and reopened both, and passed 131 exterior checks plus 2,433 interior native checks and 57 layout checks. All 2,431 researched native mesh fingerprints match the earlier saved model. Nine newly rendered PNGs pass metadata inspection. Injected adapter failures confirm that structured errors omit planted paths and tokens while failure propagation remains intact. See [privacy-validation.json](privacy-validation.json) for the measurements and source fingerprints.

MicroStation's three small output/logging changes use the same tested standard-library helpers. This follow-up did not repeat a native MicroStation build; the earlier native validation remains recorded separately. CI runs all regression tests on Windows and Linux with Python 3.10 and 3.12, plus the history/archive privacy job.
