# Public release review

The public repository was assembled in a separate directory with fresh Git history. Only the generator, adapters, default parameters, research notes, geometry recipe, tests and preview images are included. The custom MicroStation MCP and its implementation remain private.

The candidate release was checked with a local pattern scan and manual review for credential formats, secret assignments, email addresses, absolute workstation paths, local account names, private network addresses, session identifiers, configuration files and unexpected binaries. Python imports and file-writing behavior were reviewed for external dependencies and host assumptions. No credentials, private personal information or machine-specific paths were identified in the release candidate. Public source authors and attribution links are intentionally retained.

Preview PNGs were inspected visually. EXIF and text metadata were stripped, including render metadata, while retaining the original compressed pixel stream. Native DGN/Blender files, bytecode caches, generated logs, temporary scripts and raw MCP receipts are excluded from the repository. A public GitHub noreply identity is used for the release commit.

The public scripts do not contact a network service, install packages, load the private MCP, or read credentials. Paths are resolved relative to the scripts, supplied by the caller, or obtained from the active CAD file. MicroStation's native Python API and Blender's embedded API are intentional application requirements. The standard-library geometry code can be tested separately.

This was a targeted release hygiene review using local checks, not a third-party security audit or a guarantee against every possible secret pattern. Generated outputs on another machine can contain that application's own metadata and should be reviewed before being shared.

The researched interior/electrical update received the same working-tree and committed-blob review, plus a scan of every blob and commit reachable from the public repository's local Git refs. No findings remained. Seven new native-model preview PNGs were stripped of ancillary metadata without changing their compressed image data. The source register links public documents and records fingerprints; third-party PDFs, drawings and embedded contact details are not redistributed. The private MCP, host outputs and local automation helpers remain excluded.
