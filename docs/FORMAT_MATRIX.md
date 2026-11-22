# Format and Feature Matrix

## Document control

| Field | Value |
| --- | --- |
| Matrix version | 1 |
| Status | Manual certification passed; scheduled release gate pending |
| Date | 2026-11-22 |
| Machine-readable source | `tests/fixtures/golden/format-matrix.json` |
| Certification scorecard | `docs/certification-scorecard.json` |
| Certification plan | `docs/production-readiness-plan.md` |

## Certification targets

| LMS | Release | Runtime target |
| --- | --- | --- |
| Moodle | 5.3 LTS (pin 5.3.1 in the harness) | PHP 8.4 and MariaDB 11.4 |
| Open edX | Verawood (Verawood.2) | Tutor 22.0.4 |

The import checks below pass against the pinned environments in two consecutive
manual `all` runs at commit `8e993d3`: Moodle verified 17 of 23 features with 6
lost/expected gaps; Open edX verified 22 of 34 features with 12 lost/expected
gaps. The aggregate scorecard is 39 verified features, 33 transformed plus 6
native, and 18 lost/expected gaps. Two consecutive scheduled nightly runs are
still required before this becomes a release gate.

## Status definitions

| Status | Meaning |
| --- | --- |
| native | The target format represents the source feature directly. |
| transformed | The source feature is converted into a different but functional target representation. |
| placeholder | Visible content is preserved, but the feature needs manual review or replacement. |
| unsupported | The feature is preserved only in the canonical model or report and is not emitted to the target export. |
| control | The feature is a validation, security, or roundtrip check rather than a target content classification. |

Every feature identifier in `tests/golden/features.py` must appear exactly once.
Fixture and snapshot evidence is anchored to a case in
`tests/fixtures/golden/manifest.json`. A status is a claim about the current
exporter, not proof that a live LMS import succeeds.

## Open edX to Moodle

| Feature | Description | Status | Import check | Evidence | Notes |
| --- | --- | --- | --- | --- | --- |
| `openedx.assets.nested` | Nested Open edX static asset paths preserved during parsing and remapped for Moodle files. | transformed | moodle:restore | `openedx/core` | Moodle uses content-addressed file storage, so nested paths are not retained. |
| `openedx.discussion` | Open edX discussion mapped to a Moodle forum. | transformed | moodle:restore | `openedx/core` | - |
| `openedx.hierarchy` | Open edX chapter, sequential, and vertical hierarchy collapsed into Moodle sections and activities. | transformed | moodle:restore | `openedx/core` | - |
| `openedx.html` | Open edX HTML component mapped to a Moodle page or label. | transformed | moodle:restore | `openedx/core` | - |
| `openedx.lti` | Open edX LTI component mapped to a Moodle URL fallback. | placeholder | moodle:restore | `openedx/core` | LTI launch URL and configuration are not preserved; manual replacement is required. |
| `openedx.openassessment` | Open edX open assessment mapped to a Moodle workshop stub. | placeholder | moodle:restore | `openedx/core` | The generated workshop is a stub and requires manual review. |
| `openedx.problem.code_placeholder` | Code-response problem rendered as a Moodle placeholder question. | placeholder | moodle:restore | `openedx/core` | Reported as UNSUPPORTED_QUESTION_TYPE. |
| `openedx.problem.custom_placeholder` | Custom-response problem rendered as a Moodle placeholder question. | placeholder | moodle:restore | `openedx/core` | Reported as UNSUPPORTED_QUESTION_TYPE. |
| `openedx.problem.formula_placeholder` | Formula-response problem rendered as a Moodle placeholder question. | placeholder | moodle:restore | `openedx/core` | Reported as UNSUPPORTED_QUESTION_TYPE. |
| `openedx.problem.legacy_numericalinput` | Legacy Open edX numerical input mapped to a Moodle numerical question. | transformed | moodle:restore | `openedx/core` | - |
| `openedx.problem.legacy_textinput` | Legacy Open edX text input mapped to a Moodle short-answer question. | transformed | moodle:restore | `openedx/core` | - |
| `openedx.problem.multichoice` | Open edX multiple-choice problem mapped to a Moodle multichoice question. | transformed | moodle:restore | `openedx/core` | - |
| `openedx.problem.multiselect` | Open edX multi-select problem mapped to a Moodle multichoice question. | transformed | moodle:restore | `openedx/core` | - |
| `openedx.problem.numerical` | Open edX numerical problem mapped to a Moodle numerical question. | transformed | moodle:restore | `openedx/core` | - |
| `openedx.problem.shortanswer` | Open edX short-answer problem mapped to a Moodle short-answer question. | transformed | moodle:restore | `openedx/core` | - |
| `openedx.problem.truefalse` | Open edX true/false problem mapped to a Moodle truefalse question. | transformed | moodle:restore | `openedx/core` | - |
| `openedx.raw_fragments` | Raw Open edX XML fragments preserved in canonical IR only. | unsupported | - | `openedx/core` | Raw fragments are not emitted to the target export. |
| `openedx.scorm` | Open edX SCORM component mapped to a Moodle SCORM activity. | transformed | moodle:restore | `openedx/core` | - |
| `openedx.unknown_component` | Unknown Open edX component rendered as a Moodle label placeholder. | placeholder | moodle:restore | `openedx/core` | Reported as UNSUPPORTED_NODES. |
| `openedx.video.asset` | Open edX self-hosted video mapped to a Moodle file resource. | transformed | moodle:restore | `openedx/core` | - |
| `openedx.video.youtube` | Open edX YouTube video mapped to a Moodle URL activity. | transformed | moodle:restore | `openedx/core` | - |

## Moodle to Open edX

| Feature | Description | Status | Import check | Evidence | Notes |
| --- | --- | --- | --- | --- | --- |
| `moodle.assign` | Moodle assignment activity, title and intro preserved as an HTML fallback. | placeholder | openedx:import | `moodle/core` | HTML fallback requires manual review. |
| `moodle.book` | Moodle book chapters rendered into a single HTML activity. | transformed | openedx:import | `moodle/core` | Book chapter structure is flattened. |
| `moodle.choice` | Moodle choice activity represented as a manual-review HTML activity. | placeholder | openedx:import | `moodle/core` | Choice options are not emitted; the title and intro are preserved. |
| `moodle.forum` | Moodle forum mapped to an Open edX discussion component. | transformed | openedx:import | `moodle/core` | - |
| `moodle.glossary` | Moodle glossary represented as an HTML overview. | placeholder | openedx:import | `moodle/core` | Glossary entries are not preserved. |
| `moodle.hierarchy` | Moodle sections and activities mapped to an Open edX chapter, sequential, and vertical hierarchy. | transformed | openedx:import | `moodle/core` | - |
| `moodle.label.html` | Moodle HTML label mapped to an Open edX HTML component. | transformed | openedx:import | `moodle/core` | - |
| `moodle.label.youtube` | Moodle label containing a YouTube link mapped to an Open edX video component. | transformed | openedx:import | `moodle/core` | - |
| `moodle.lesson` | Moodle lesson represented as a manual-review HTML activity. | placeholder | openedx:import | `moodle/core` | Lesson pages and navigation are not preserved. |
| `moodle.page` | Moodle page body mapped to an Open edX HTML component. | transformed | openedx:import | `moodle/core` | - |
| `moodle.question.description` | Moodle description question rendered as a placeholder problem. | placeholder | openedx:import | `moodle/core` | Reported as ESSAY_QUESTION and requires manual review. |
| `moodle.question.essay` | Moodle essay question rendered as a placeholder problem. | placeholder | openedx:import | `moodle/core` | Reported as ESSAY_QUESTION and requires manual review. |
| `moodle.question.multichoice_multi` | Moodle multi-select question mapped to an Open edX checkbox response. | transformed | openedx:import | `moodle/core` | - |
| `moodle.question.multichoice_single` | Moodle single-select question mapped to an Open edX multiple-choice response. | transformed | openedx:import | `moodle/core` | - |
| `moodle.question.numerical_tolerance` | Moodle numerical question mapped to an Open edX numerical response. | transformed | openedx:import | `moodle/core` | Tolerance is emitted as an OLX responseparam and checked during certification. |
| `moodle.question.shortanswer` | Moodle short-answer question mapped to an Open edX string response. | transformed | openedx:import | `moodle/core` | - |
| `moodle.question.truefalse` | Moodle true/false question mapped to an Open edX multiple-choice response. | transformed | openedx:import | `moodle/core` | - |
| `moodle.question.unknown` | Unknown Moodle question type rendered as a manual-review placeholder. | placeholder | openedx:import | `moodle/core` | Reported as UNSUPPORTED_QUESTION_TYPE. |
| `moodle.question_bank_link` | Question-bank entries linked into Moodle quiz assessments. | transformed | openedx:import | `moodle/core` | - |
| `moodle.quiz` | Moodle quiz mapped to an Open edX problem with its linked questions. | transformed | openedx:import | `moodle/core` | - |
| `moodle.raw_fragments` | Raw Moodle XML fragments preserved in canonical IR only. | unsupported | - | `moodle/core` | Raw fragments are not emitted to the target export. |
| `moodle.resource.file` | Moodle file resource copied and exposed as an HTML download activity. | transformed | openedx:import | `moodle/core` | - |
| `moodle.resource.missing_file` | Moodle resource with a missing file rendered with a manual-review message. | placeholder | openedx:import | `moodle/core` | The absent file is not recoverable. |
| `moodle.resource.video` | Moodle video resource mapped to an Open edX video component. | transformed | openedx:import | `moodle/core` | - |
| `moodle.scorm` | Moodle SCORM package mapped to an Open edX SCORM XBlock. | transformed | openedx:import | `moodle/core` | - |
| `moodle.scorm.missing_package` | Moodle SCORM activity without a package rendered as a manual-review HTML fallback. | placeholder | openedx:import | `moodle/core` | The missing package must be supplied manually. |
| `moodle.unknown_module` | Unknown Moodle module represented as a manual-review HTML activity. | placeholder | openedx:import | `moodle/core` | Reported as UNSUPPORTED_NODES. |
| `moodle.url.external` | Moodle external URL mapped to an Open edX HTML link. | transformed | openedx:import | `moodle/core` | - |
| `moodle.url.youtube` | Moodle YouTube URL mapped to an Open edX video component. | transformed | openedx:import | `moodle/core` | - |
| `moodle.video` | Moodle video file activity mapped to an Open edX video component. | transformed | openedx:import | `moodle/core` | - |
| `moodle.wiki` | Moodle wiki represented as a manual-review HTML activity. | placeholder | openedx:import | `moodle/core` | Wiki pages are not preserved. |
| `moodle.workshop` | Moodle workshop mapped to an Open edX open assessment stub. | placeholder | openedx:import | `moodle/core` | The generated open assessment is a stub and requires manual review. |

## Target capabilities

| Feature | Description | Status | Import check | Evidence | Notes |
| --- | --- | --- | --- | --- | --- |
| `target.moodle.assets` | Moodle backup emits file records and content-addressed asset files. | native | moodle:restore | `openedx/core` | - |
| `target.moodle.modules` | Moodle backup emits sections, module records, and activity XML. | native | moodle:restore | `openedx/core` | Aligned with Moodle 5.3.1 backup metadata. |
| `target.moodle.questions` | Moodle backup emits question categories, questions, and answer records. | native | moodle:restore | `openedx/core` | - |
| `target.openedx.assets` | Open edX export emits static assets and asset policy entries. | native | openedx:import | `moodle/core` | - |
| `target.openedx.components` | Open edX export emits chapter, sequential, vertical, and component XML. | native | openedx:import | `moodle/core` | - |
| `target.openedx.questions` | Open edX export emits problem XML with supported response types. | native | openedx:import | `moodle/core` | - |

## Validation, security, and roundtrip controls

| Feature | Description | Status | Import check | Evidence | Notes |
| --- | --- | --- | --- | --- | --- |
| `moodle.validation.null_section_title` | Empty Moodle section title receives a positional fallback title. | control | - | `moodle/edge-cases` | - |
| `moodle.validation.stale_manifest_title` | Authoritative course title is read from course.xml when the manifest is stale. | control | - | `moodle/edge-cases` | - |
| `openedx.validation.empty_course` | Empty course produces a validation error before migration. | control | - | `openedx/empty` | - |
| `openedx.validation.problem_without_assessment` | Problem without an assessment produces a placeholder warning. | control | - | `openedx/edge-cases` | - |
| `openedx.validation.video_without_source` | Video without a source produces a placeholder warning. | control | - | `openedx/edge-cases` | - |
| `roundtrip.moodle_to_openedx` | Moodle to Open edX export parses back into canonical IR in the golden corpus. | control | roundtrip | `moodle/core` | - |
| `roundtrip.openedx_to_moodle` | Open edX to Moodle export parses back into canonical IR in the golden corpus. | control | roundtrip | `openedx/core` | - |
| `security.archive.bomb` | Compression-ratio and expansion limits reject archive bombs. | control | - | `invalid/zip-bomb` | - |
| `security.archive.device` | Archive device entries are rejected. | control | - | `invalid/tar-device` | - |
| `security.archive.duplicate` | Duplicate archive entries are rejected. | control | - | `invalid/tar-duplicate` | - |
| `security.archive.encrypted_zip` | Encrypted ZIP archives are rejected. | control | - | `invalid/zip-encrypted` | - |
| `security.archive.symlink` | Archive symlink entries are rejected. | control | - | `invalid/tar-symlink` | - |
| `security.path.traversal` | Archive entries escaping the extraction root are rejected. | control | - | `invalid/openedx-path-traversal` | Also covered by invalid/moodle-path-traversal. |
| `security.upload.boundaries` | Upload content-length, size, and boundary limits are enforced. | control | - | `invalid/upload-boundaries` | - |
| `security.xml.depth_limit` | XML nesting depth exceeds the configured limit and is rejected. | control | - | `invalid/xml-depth-limit` | - |
| `security.xml.entity_expansion` | XML entity expansion is rejected by the hardened parser. | control | - | `invalid/xml-entity-expansion` | - |
| `security.xml.malformed` | Malformed XML is rejected. | control | - | `invalid/xml-malformed` | - |
| `security.xml.size_limit` | XML document size exceeds the configured limit and is rejected. | control | - | `invalid/xml-size-limit` | - |

## Known gaps after manual certification

- Manual certification is green for the committed matrix; two consecutive
  scheduled nightly `all` runs are still required for the release gate.
- Any change to a feature status, target adapter, or pinned LMS patch requires
  new runs.
- Some transformed features are certified by presence or count checks rather
  than full content comparison.
- LTI launch data and raw fragments are not emitted to target exports.
- HTML fallbacks for Moodle choice, book, glossary, wiki, assignment, and
  lesson activities do not yet have dedicated report codes.

## Version policy

- Increment `matrix_version` when a feature status, target, or import check
  changes.
- Increment `schema_version` when the matrix structure changes.
- Record a new certification run against the exact Moodle and Open edX patch
  versions in `docs/certification-scorecard.json` when a feature status or
  target adapter changes.
- Do not promote a row to `native` or `transformed` without evidence from both
  the golden corpus and a live pinned LMS import.
