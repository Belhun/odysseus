# Odysseus docs

This is the documentation hub for the Belhun fork of Odysseus.

Feature work no longer lives on long-lived branches. Use the feature map below, then the matching research and plan folders.

## Start here

| I want to… | Go to |
|------------|--------|
| See every fork feature and where its docs live | [`features/INDEX.md`](features/INDEX.md) |
| Install / run / secure Odysseus | [`setup.md`](setup.md) |
| Work on finance / banking | [`features/finance.md`](features/finance.md) |
| Work on local email sync | [`features/email.md`](features/email.md) |
| Work on SysForge Business | [`features/sysforge.md`](features/sysforge.md) |
| Work on performance tracking | [`features/performance.md`](features/performance.md) |

## Layout

```text
docs/
  README.md                 ← you are here
  features/                 ← feature map + how to extend each area
  research/
    finance/                ← was top-level "Banking Research/"
    sysforge/               ← was top-level "Sysforge research/"
    performance/            ← was top-level "Performance tracking/"
  plans/
    finance/
    email/
    sysforge/
    followups/
  migration-audit/          ← SysForge desktop → plugin audit archive
  setup.md, backup-restore.md, …
```

## Core product docs

| Doc | Topic |
|-----|--------|
| [`setup.md`](setup.md) | Install, config, security |
| [`performance-tracking.md`](performance-tracking.md) | How to run and validate perf tracking |
| [`backup-restore.md`](backup-restore.md) | Backup / restore |
| [`CONFIRMATION_GATES.md`](CONFIRMATION_GATES.md) | Confirmation gate design |
| [`attachments.md`](attachments.md) | Attachments |
| [`email-outlook.md`](email-outlook.md) | Outlook / email notes |
| [`security-ci.md`](security-ci.md) | Security CI |
| [`agent-migration.md`](agent-migration.md) | Agent migration notes |

## Path renames (2026-07)

Old top-level folders keep a short README stub that points here:

| Old path | New path |
|----------|----------|
| `Banking Research/` | `docs/research/finance/` |
| `Sysforge research/` | `docs/research/sysforge/` |
| `Performance tracking/` | `docs/research/performance/` |
| Flat `docs/plans/*.md` | `docs/plans/{finance,email,sysforge,followups}/` |
